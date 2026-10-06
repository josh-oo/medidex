from .vectorstore import VectorstoreService
from ..database.repositories.aspects import AspectRepository
from typing import List
import enum

from src.utils.dto import TagCandidate
from src.utils.tagconfig import TAG_CATEGORIES


# The categories of config/study.yaml, plus the default embedding.
TagCategories = enum.Enum(
    "TagCategories",
    {name: name for name in ("default", *TAG_CATEGORIES)},
    type=str,
)


class UnsupportedAspectError(Exception):
    """No tag search is defined for this aspect."""


class TagSimilaritySearchService:

    def __init__(self, vectorstore : VectorstoreService):
        self.vectorstore = vectorstore

    async def get_similar_tags_by_id(self, report_id : int, aspect : TagCategories, sources : List[str], k : int) -> List[TagCandidate]:
        if aspect == TagCategories.default:
            raise UnsupportedAspectError("No tags for 'default' embedding.")

        query = self.vectorstore.build_recommandation_based_on_report_id(report_id)
        return await self.vectorstore.get_similar_tags(query, sources, aspect, k)

    async def get_similar_tags_by_string(self, text : str, aspect : TagCategories, sources : List[str], k : int) -> List[TagCandidate]:
        if aspect == TagCategories.default:
            raise UnsupportedAspectError("No tags for 'default' embedding.")

        return await self.vectorstore.get_similar_tags_by_string(text, sources,aspect, k)
    
class TagScoringService:

    def __init__(self, vectorstore : VectorstoreService, aspect_repo : AspectRepository):
        self.vectorstore = vectorstore
        self.aspect_repo =aspect_repo

    async def score_related_tags(self, tag_ids : List[int], embedding : List[float], aspect : TagCategories) -> List[TagCandidate]:
        if len(tag_ids) == 0:
            return []
        
        return await self.vectorstore.score_tags(embedding, tag_ids, aspect)