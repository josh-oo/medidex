"""The categories of the eligibility criteria of the study databases (config/eligibility.yaml), and the criteria themselves."""

import hashlib
import json
import logging
from pathlib import Path
from typing import ClassVar, Dict, List, Literal, Optional, Sequence

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

logger = logging.getLogger(__name__)

CriterionKind = Literal["include", "exclude"]


class EligibilityCategoryConfig(BaseModel):
    """A category of criteria (e.g. population)."""

    model_config = ConfigDict(extra="forbid")

    label: str
    description: str


class EligibilityConfig(BaseModel):
    """config/eligibility.yaml."""

    model_config = ConfigDict(extra="forbid")

    PATH: ClassVar[Path] = Path(__file__).resolve().parent.parent / "config" / "eligibility.yaml"

    categories: Dict[str, EligibilityCategoryConfig] = Field(min_length=1)

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "EligibilityConfig":
        try:
            raw = yaml.safe_load((path or cls.PATH).read_text(encoding="utf-8"))
            return cls.model_validate(raw)
        except Exception as exc:
            raise RuntimeError(f"Invalid {(path or cls.PATH).name}: {exc}") from exc


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
        """The stored criteria of a database; one whose category is no longer configured is left out (and logged)."""
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


ELIGIBILITY_CONFIG = EligibilityConfig.load()
