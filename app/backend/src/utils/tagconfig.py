"""The tag categories of the application (the tag categories of config/medidex-study.yaml)."""

from .studyconfig import STUDY_CONFIG, TagCategoryConfig, TagCategoryRegistry

TAG_CATEGORIES = STUDY_CONFIG.tags

__all__ = ["TAG_CATEGORIES", "TagCategoryConfig", "TagCategoryRegistry"]
