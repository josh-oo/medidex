"""What a study consists of and how it is presented, read from config/study.yaml."""

from pathlib import Path
from typing import Dict, Iterator, List, Literal, Optional

import yaml
from pydantic import BaseModel, ConfigDict, model_validator

ColorName = Literal["blue", "emerald", "rose", "amber", "slate", "sky", "violet", "teal"]

# Separates the tags kept in a column of the study itself (see `inline` of a tag category).
INLINE_SEPARATOR = "//"


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

    @model_validator(mode="after")
    def _check_values(self) -> "StudyFieldConfig":
        if (self.type == "enum") != bool(self.values):
            raise ValueError("`values` is required for (and only for) fields of type enum")
        if len(set(self.values)) != len(self.values):
            raise ValueError("`values` must be unique")
        return self


class ViewPartConfig(BaseModel):
    """One part of a group of a view: the tags of a category, or the value of a field."""

    model_config = ConfigDict(extra="forbid")

    label: Optional[str] = None
    category: Optional[str] = None  # tags of this category (a key of `categories`)
    field: Optional[str] = None  # the value of this field (a key of `fields`), only in derived views
    # Values of fields that belong to this part of a stored view next to its tags, e.g. the duration of each side.
    fields: List[str] = []

    @model_validator(mode="after")
    def _check_source(self) -> "ViewPartConfig":
        if (self.category is None) == (self.field is None):
            raise ValueError("a part has either a `category` or a `field`")
        if self.field is not None and self.fields:
            raise ValueError("`fields` belong to the tags of a part with a `category`")
        return self


class StudyViewConfig(BaseModel):
    """A way to present parts of a study together, as groups. A stored view keeps its groups in a column of the
    study (JSON, see src/utils/views.py); a derived view builds its single group from the tags and fields the
    study has anyway."""

    model_config = ConfigDict(extra="forbid")

    label: str
    icon: str
    color: ColorName
    display: Literal["text"] = "text"  # a block below the tiles of the study details
    card: bool = False  # also a line on the study cards
    column: Optional[str] = None  # stored view: the attribute of the study holding the JSON groups
    separator: str = " · "  # between the parts of a group when shown as a line ("A vs B")
    symmetric: bool = False  # whether the order of the parts of a group does not matter (A vs B = B vs A)
    parts: Dict[str, ViewPartConfig]

    @model_validator(mode="after")
    def _check_parts(self) -> "StudyViewConfig":
        if not self.parts:
            raise ValueError("a view needs parts")
        stored = self.column is not None
        for key, part in self.parts.items():
            if stored and part.category is None:
                raise ValueError(f"part '{key}': a stored view refers to tags (`category`), not to a field")
            if not stored and part.fields:
                raise ValueError(f"part '{key}': only a stored view keeps `fields` with its tags")
        return self


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
    meta: Dict[str, StudyMetaConfig]
    categories: Dict[str, TagCategoryConfig]
    views: Dict[str, StudyViewConfig] = {}

    @model_validator(mode="after")
    def _check_references(self) -> "StudyConfig":
        names = [*self.fields, *self.meta, *self.categories, *self.views]
        if len(set(names)) != len(names):
            raise ValueError("study.yaml: fields, meta, categories and views share their names and need unique ones")
        for key, view in self.views.items():
            for part_key, part in view.parts.items():
                if part.category is not None and part.category not in self.categories:
                    raise ValueError(f"view '{key}', part '{part_key}': unknown category '{part.category}'")
                for field in [part.field, *part.fields]:
                    if field is not None and field not in self.fields:
                        raise ValueError(f"view '{key}', part '{part_key}': unknown field '{field}'")
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
    def stored_views(self) -> Dict[str, StudyViewConfig]:
        return {key: view for key, view in self.views.items() if view.column is not None}

    @property
    def tags(self) -> TagCategoryRegistry:
        return TagCategoryRegistry(categories=self.categories)


STUDY_CONFIG = StudyConfig.load()
