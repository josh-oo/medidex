"""What a study consists of and how it is presented, read from config/study.yaml."""

from pathlib import Path
from typing import Dict, Iterator, List, Literal, Optional

import yaml
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

ColorName = Literal["blue", "emerald", "rose", "amber", "slate", "sky", "violet", "teal"]

# Separates the tags kept in a column of the study itself (see `inline` of a tag category).
INLINE_SEPARATOR = "//"

# The name of the field of a study that holds its graph (the column of the study is `graph` as well).
GRAPH_FIELD = "graph"


class DurationUnitConfig(BaseModel):
    """A unit of the durations of a study, e.g. 12 weeks."""

    model_config = ConfigDict(extra="forbid")

    name: str  # singular
    seconds: int


class FieldDeriveConfig(BaseModel):
    """How a field of the study is calculated from its graph while the study has no value of its own: for every entity
    of kind `source` (e.g. every arm), follow the relations of `path` (e.g. participated, size) to the values at their
    end, and aggregate them."""

    model_config = ConfigDict(extra="forbid")

    source: str  # the kind of entity to start at (a key of `graph.entities`)
    path: List[str]  # relations (keys of `graph.relations`), each starting where the one before ended; the last ends at values
    # sum: the values of every entity added up (only if every entity has one, as a part would understate the total);
    # max, min: the largest, smallest value among the entities that have one.
    aggregate: Literal["sum", "max", "min"]


class StudyFieldConfig(BaseModel):
    """A primitive value of a study."""

    model_config = ConfigDict(extra="forbid")

    label: str
    type: Literal["integer", "duration", "enum", "text"]
    icon: str
    color: ColorName
    display: Literal["metric", "text", "none"]
    column: str  # the attribute of the study in the database (see src/database/models.py)
    required: bool = False  # an enum field always is
    values: List[str] = []  # allowed values of an enum
    derive: Optional[FieldDeriveConfig] = None  # what the field is while the study has no value of its own

    @model_validator(mode="after")
    def _check_values(self) -> "StudyFieldConfig":
        if self.derive is not None and self.type not in ("integer", "duration"):
            raise ValueError("only integer and duration fields can be derived from the graph")
        if (self.type == "enum") != bool(self.values):
            raise ValueError("`values` is required for (and only for) fields of type enum")
        if len(set(self.values)) != len(self.values):
            raise ValueError("`values` must be unique")
        return self


class ValueConfig(BaseModel):
    """What an entity that is a value holds: a tag of a category (`category`), or a primitive (`type`)."""

    model_config = ConfigDict(extra="forbid")

    category: Optional[str] = None  # a tag of this category (a key of `categories`)
    type: Optional[Literal["integer", "duration", "enum", "text"]] = None
    values: List[str] = []  # allowed values of an enum

    @model_validator(mode="after")
    def _check(self) -> "ValueConfig":
        if (self.category is None) == (self.type is None):
            raise ValueError("a value is either a tag (`category`) or a primitive (`type`)")
        if (self.type == "enum") != bool(self.values):
            raise ValueError("`values` is required for (and only for) values of type enum")
        if len(set(self.values)) != len(self.values):
            raise ValueError("`values` must be unique")
        return self


class GraphEntityConfig(BaseModel):
    """A kind of entity of the graph of a study. An entity has no properties, only relations to other entities: an arm
    to the interventions it receives, to its dosage, to the population that took part in it. What looks like a property
    is a relation to an entity that is a value (`value`: a tag, a number, a duration, ...)."""

    model_config = ConfigDict(extra="forbid")

    label: str
    icon: str
    color: ColorName
    description: Optional[str] = None  # what the entity is, for the API documentation
    # The study itself. There is exactly one such entity, `study`, which needs no JSON of its own: its data are the fields
    # and categories of config/study.yaml. It is there so that relations can start at the study as a whole.
    root: bool = False
    value: Optional[ValueConfig] = None  # the entity is a value of this kind (e.g. a dosage, an intervention)

    @model_validator(mode="after")
    def _check(self) -> "GraphEntityConfig":
        if self.root and self.value is not None:
            raise ValueError("the root entity (the study itself) is no value")
        return self


class GraphRelationConfig(BaseModel):
    """A kind of relation between two entities of the graph of a study, e.g. the comparison of two arms, or the
    participation of a population in an arm. A relation to entities that are values (e.g. the dosage of an arm) is an
    attribute: it describes its source."""

    model_config = ConfigDict(extra="forbid")

    label: str
    icon: str
    color: ColorName
    description: Optional[str] = None  # what the relation says, for the API documentation
    source: List[str]  # the kinds of entity an edge can start at (keys of `graph.entities`), e.g. the study or an arm
    target: List[str]  # the kinds of entity it can end at
    symmetric: bool = False  # whether source and target are interchangeable (A vs B = B vs A)
    many: bool = False  # whether an entity can have several (several interventions); otherwise one at most
    required: bool = False  # what identifies the source: an extracted entity without it (an arm without interventions) is left out
    line: bool = True  # an attribute is part of its source when that is shown as a line ("A + B (10 mg, 5 weeks)")
    separator: str = " · "  # between source and target when the edge is shown as a line ("A vs B")
    card: bool = False  # also shown as a line on the study cards

    @field_validator("source", "target", mode="before")
    @classmethod
    def _kinds(cls, value):
        """One kind is written as a single name."""
        return [value] if isinstance(value, str) else value


class GraphConfig(BaseModel):
    """What a study says beyond its tags and primitive fields, as a graph: entities (the study itself, its arms, the
    populations that took part, ...) connected by relations. A study keeps its graph as JSON (see src/utils/graph.py)."""

    model_config = ConfigDict(extra="forbid")

    # Column of the study with the plain text of studies from before the graph, shown as it is.
    text_column: Optional[str] = None
    entities: Dict[str, GraphEntityConfig] = {}
    relations: Dict[str, GraphRelationConfig] = {}

    @model_validator(mode="after")
    def _check_relations(self) -> "GraphConfig":
        if sum(entity.root for entity in self.entities.values()) > 1:
            raise ValueError("only one entity can be the root (the study itself)")
        for key, relation in self.relations.items():
            for end in (*relation.source, *relation.target):
                if end not in self.entities:
                    raise ValueError(f"relation '{key}': unknown entity '{end}'")
            values = [self.entities[end].value is not None for end in relation.target]
            if any(values) and not all(values):
                raise ValueError(f"relation '{key}': it leads to values or to entities, not to both")
            if any(values) and (relation.symmetric or any(self.entities[end].value is not None for end in relation.source)):
                raise ValueError(f"relation '{key}': an attribute starts at an entity that is no value")
            if relation.symmetric and set(relation.source) != set(relation.target):
                raise ValueError(f"relation '{key}': a symmetric relation connects the same kinds of entity at both ends")
        return self

    @property
    def root(self) -> Optional[str]:
        """The key of the entity that is the study itself, if there is one."""
        return next((key for key, entity in self.entities.items() if entity.root), None)

    @property
    def root_id(self) -> str:
        """The id edges use for the study itself (it is not stored as a node)."""
        return "study"

    def is_value(self, kind: str) -> bool:
        return self.entities[kind].value is not None

    def is_attribute(self, relation: str) -> bool:
        """Whether the relation leads to values (e.g. the dosage of an arm) rather than to other entities."""
        return self.is_value(self.relations[relation].target[0])

    def attributes_of(self, kind: str) -> Dict[str, GraphRelationConfig]:
        """The attribute relations that start at entities of this kind, in the order of the config."""
        return {key: relation for key, relation in self.relations.items() if kind in relation.source and self.is_attribute(key)}

    def tag_categories(self) -> List[str]:
        """The categories whose tags entities hold."""
        return list(dict.fromkeys(entity.value.category for entity in self.entities.values() if entity.value and entity.value.category))


class StudyMetaConfig(BaseModel):
    """Metadata of the database record of a study."""

    model_config = ConfigDict(extra="forbid")

    label: str
    type: Literal["date"]


class TagCategoryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    icon: str
    color: ColorName
    search_field: str
    description: str
    free_text_search: bool = False
    # The tags are kept in the column of the study with this name (separated by `//`) instead of a table of their own.
    inline: bool = False


class TagCategoryRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    categories: Dict[str, TagCategoryConfig]

    @model_validator(mode="after")
    def _check(self) -> "TagCategoryRegistry":
        if not self.categories:
            raise ValueError("study.yaml defines no categories")
        search_fields = [category.search_field for category in self.categories.values()]
        if len(set(search_fields)) != len(search_fields):
            raise ValueError("study.yaml: search_field must be unique per category")
        return self

    @property
    def names(self) -> List[str]:
        return list(self.categories)

    def where(self, **flags) -> List[str]:
        """The categories whose settings equal the given ones, e.g. where(vector_search=True)."""
        return [name for name, config in self.categories.items() if all(getattr(config, key) == value for key, value in flags.items())]

    @property
    def first(self) -> str:
        return self.names[0]

    def __iter__(self) -> Iterator[str]:  # type: ignore[override]
        return iter(self.categories)

    def __getitem__(self, name: str) -> TagCategoryConfig:
        return self.categories[name]


class StudyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fields: Dict[str, StudyFieldConfig]
    # The units of durations, largest first (e.g. year, month, week, day, hour).
    duration_units: List[DurationUnitConfig] = []
    meta: Dict[str, StudyMetaConfig]
    categories: Dict[str, TagCategoryConfig]
    graph: GraphConfig = GraphConfig()

    @model_validator(mode="after")
    def _check_references(self) -> "StudyConfig":
        # The relations between entities (not the attributes, which only describe their entity) can be what a report adds
        # to a study, so they are named like a field of the study.
        relations = [key for key in self.graph.relations if not self.graph.is_attribute(key)]
        names = [*self.fields, *self.meta, *self.categories, *relations, GRAPH_FIELD]
        if len(set(names)) != len(names):
            raise ValueError(f"study.yaml: fields, meta, categories and the relations between entities share their names (and `{GRAPH_FIELD}` is taken) and need unique ones")
        seconds = [unit.seconds for unit in self.duration_units]
        if seconds != sorted(set(seconds), reverse=True) or any(value <= 0 for value in seconds):
            raise ValueError("duration_units must be positive and ordered from the largest to the smallest unit")
        needs_units = any(field.type == "duration" for field in self.fields.values()) or any(
            entity.value and entity.value.type == "duration" for entity in self.graph.entities.values()
        )
        if needs_units and not self.duration_units:
            raise ValueError("study.yaml has durations, but no duration_units")
        graph = self.graph
        for key, field in self.fields.items():
            derive = field.derive
            if derive is None:
                continue
            if derive.source not in graph.entities or any(step not in graph.relations for step in derive.path) or not derive.path:
                raise ValueError(f"field '{key}': unknown entity or relation in `derive`")
            kinds = {derive.source}
            for step in derive.path:
                relation = graph.relations[step]
                if not kinds & set(relation.source):
                    raise ValueError(f"field '{key}': '{step}' does not start where the path is")
                kinds = set(relation.target)
            ends = [graph.entities[kind].value for kind in kinds]
            if any(value is None or value.type != field.type for value in ends):
                raise ValueError(f"field '{key}' is of type {field.type}, but its `derive` path does not end at such values")
            if derive.aggregate == "sum" and field.type != "integer":
                raise ValueError(f"field '{key}': only integers can be summed")
        for entity_key, entity in graph.entities.items():
            category = entity.value.category if entity.value else None
            if category is not None and category not in self.categories:
                raise ValueError(f"entity '{entity_key}': unknown category '{category}'")
            if category is not None and self.categories[category].inline:
                raise ValueError(f"entity '{entity_key}': the tags of '{category}' are kept in the study and cannot be values")
        return self

    @classmethod
    def load(cls, path: Path | None = None) -> "StudyConfig":
        path = path or Path(__file__).resolve().parent.parent / "config" / "study.yaml"
        with open(path, encoding="utf-8") as handle:
            return cls.model_validate(yaml.safe_load(handle))

    @property
    def enums(self) -> Dict[str, List[str]]:
        """The allowed values of the enum fields, by field."""
        return {key: field.values for key, field in self.fields.items() if field.type == "enum"}

    @property
    def inline_categories(self) -> List[str]:
        """The tag categories kept in a column of the study (e.g. countries)."""
        return [key for key, category in self.categories.items() if category.inline]

    @property
    def tags(self) -> TagCategoryRegistry:
        return TagCategoryRegistry(categories=self.categories)


STUDY_CONFIG = StudyConfig.load()
