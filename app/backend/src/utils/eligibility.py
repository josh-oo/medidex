"""The categories of the eligibility criteria of the study databases, the elements of PICO and the relations the study
ontology (config/medidex-study.yaml) puts in them (annotation `criterion`), and the criteria themselves."""

import hashlib
import json
import logging
from typing import Dict, List, Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .studyconfig import STUDY_CONFIG, ColorName, GraphRelationConfig, StudyConfig

logger = logging.getLogger(__name__)

CriterionKind = Literal["include", "exclude"]


# The elements of PICO a review screens by, in their order, and the study, as the ontology names them (annotation
# `criterion`). The comparison is an intervention as well, so its criteria are those of the intervention.
ELEMENTS = {"population": "Population", "intervention": "Intervention", "outcome": "Outcome", "study": "Study"}


class EligibilityCategoryConfig(BaseModel):
    """A category of criteria: an element of PICO (or the study) as a whole (`population`), or a relation of the study
    ontology in it (`has_condition`); an element with one relation is that relation."""

    model_config = ConfigDict(extra="forbid")

    # The labels from the element to what the criterion is about: ["Population"], ["Population", "Conditions"].
    path: List[str]
    description: str
    color: ColorName
    # The relations whose values a criterion of the category is about.
    relations: List[str]


class EligibilityConfig(BaseModel):
    """The categories of the criteria, in their order: every element of PICO, then the study, each as a whole followed by
    its relations in the order of the ontology."""

    model_config = ConfigDict(extra="forbid")

    categories: Dict[str, EligibilityCategoryConfig] = Field(min_length=1)

    @classmethod
    def of(cls, study: StudyConfig) -> "EligibilityConfig":
        relations = study.graph.relations
        for key, relation in relations.items():
            if relation.criterion is not None and relation.criterion not in ELEMENTS:
                raise ValueError(f"relation '{key}': unknown criterion '{relation.criterion}' (one of {', '.join(ELEMENTS)})")
        categories: Dict[str, EligibilityCategoryConfig] = {}
        for element, label in ELEMENTS.items():
            members = [key for key, relation in relations.items() if relation.criterion == element]
            if not members:
                continue
            # The color of an element is that of its first relation, and its relations share it.
            color = relations[members[0]].color
            categories[element] = EligibilityCategoryConfig(
                path=[label],
                description=relations[members[0]].description or label if len(members) == 1
                else f"{label}: {', '.join(cls._name(relations[key]).lower() for key in members)}.",
                color=color,
                relations=members,
            )
            if len(members) == 1:
                continue
            for key in members:
                relation = relations[key]
                categories[key] = EligibilityCategoryConfig(
                    path=[label, cls._name(relation)],
                    description=relation.description or study.graph.entities[relation.target[0]].description or relation.label,
                    color=color,
                    relations=[key],
                )
        return cls(categories=categories)

    @staticmethod
    def _name(relation: GraphRelationConfig) -> str:
        return relation.criterion_label or relation.label


class EligibilityCriterion(BaseModel):
    """A criterion of a study database: a text in a category, to include (it must hold) or to exclude (it must not hold)
    a report. Its id stays when the text is edited."""

    id: str = Field(min_length=1, max_length=40)
    category: str
    kind: CriterionKind = "include"
    text: str = Field(min_length=1)

    @model_validator(mode="after")
    def _check_category(self) -> "EligibilityCriterion":
        self.text = self.text.strip()
        if not self.text:
            raise ValueError("A criterion needs a text")
        if self.category not in ELIGIBILITY_CONFIG.categories:
            raise ValueError(f"Unknown category '{self.category}' (categories: {', '.join(ELIGIBILITY_CONFIG.categories)})")
        return self


class EligibilityCriteria:
    """The criteria of a database as they are stored (a JSON list of EligibilityCriterion)."""

    @staticmethod
    def validate(criteria: Sequence[EligibilityCriterion]) -> List[EligibilityCriterion]:
        """The criteria in the order of the categories (then as given); raises ValueError for none or a repeated id."""
        if not criteria:
            raise ValueError("A database needs at least one eligibility criterion")
        ids = [criterion.id for criterion in criteria]
        if len(set(ids)) != len(ids):
            raise ValueError("Two eligibility criteria share an id")
        order = list(ELIGIBILITY_CONFIG.categories)
        return sorted(criteria, key=lambda criterion: order.index(criterion.category))

    @staticmethod
    def read(stored: Sequence[dict]) -> List[EligibilityCriterion]:
        """The stored criteria of a database; one whose category the ontology no longer has is left out (and logged)."""
        criteria: List[EligibilityCriterion] = []
        for item in stored or []:
            try:
                criteria.append(EligibilityCriterion.model_validate(item))
            except ValueError as exc:
                logger.warning("Eligibility criterion %s left out: %s", item.get("id") if isinstance(item, dict) else item, exc)
        return criteria

    @staticmethod
    def version(criteria: Sequence[dict]) -> str:
        """What the criteria say, as a short hash: a check of a report against other criteria is outdated."""
        canonical = json.dumps([{k: c.get(k) for k in ("id", "category", "kind", "text")} for c in criteria], sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]


ELIGIBILITY_CONFIG = EligibilityConfig.of(STUDY_CONFIG)
