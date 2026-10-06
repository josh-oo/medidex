"""What a study consists of and how it is presented, read from config/study.yaml."""

from pathlib import Path
from typing import Dict, Iterator, List, Literal

import yaml
from pydantic import BaseModel, ConfigDict, model_validator

ColorName = Literal["blue", "emerald", "rose", "amber", "slate", "sky", "violet", "teal"]


class StudyFieldConfig(BaseModel):
    """A primitive value of a study."""

    model_config = ConfigDict(extra="forbid")

    label: str
    type: Literal["integer", "duration", "enum", "text"]
    icon: str
    color: ColorName
    display: Literal["metric", "text"]
    values: List[str] = []  # allowed values of an enum

    @model_validator(mode="after")
    def _check_values(self) -> "StudyFieldConfig":
        if (self.type == "enum") != bool(self.values):
            raise ValueError("`values` is required for (and only for) fields of type enum")
        if len(set(self.values)) != len(self.values):
            raise ValueError("`values` must be unique")
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
    def tags(self) -> TagCategoryRegistry:
        return TagCategoryRegistry(categories=self.categories)


STUDY_CONFIG = StudyConfig.load()
