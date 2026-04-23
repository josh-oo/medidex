from .vectorstore import VectorstoreService
from ..database.repositories.aspects import AspectRepository
from typing import List, Any
import enum

class TagCategories(str, enum.Enum):
    default = 'default'
    interventions = 'interventions'
    conditions = 'conditions'
    outcomes = 'outcomes'
    participants = 'participants'

class TagSimilaritySearchService:

    def __init__(self, vectorstore : VectorstoreService):
        self.vectorstore = vectorstore

    async def get_similar_tags_by_id(self, report_id : int, aspect : TagCategories, sources : List[str], k : int):
        
        query = self.vectorstore.build_recommendation_based_on_report_id(report_id)
        data = await self.vectorstore.get_similar_tags(query, sources, aspect, k)

        result = [
            {"id": i, "keyword": n, "relevance": s}
            for i, n, s in zip(data["ID"], data["Keyword"], data["Relevance"])
        ]
        return result  
    
    async def get_similar_tags_by_string(self, text : str, aspect : TagCategories, sources : List[str], k : int):
        data = await self.vectorstore.get_similar_tags_by_string(text, sources,aspect, k)
        result = [
            {"id": i, "keyword": k, "relevance": r}
            for i, k, r in zip(data["ID"], data["Keyword"], data["Relevance"])
        ]
        return result  
    
class TagScoringService:

    def __init__(self, vectorstore : VectorstoreService, aspect_repo : AspectRepository):
        self.vectorstore = vectorstore
        self.aspect_repo =aspect_repo

    async def score_related_tags(self, tag_ids : List[int], query : Any, aspect : TagCategories):
        if len(tag_ids) == 0:
            return []
        
        tag_scores = await self.vectorstore.score_tags(query, tag_ids, aspect)

        all_ids = [item['id'] for item in tag_scores]

        name_mapping = {}
            
        if aspect == TagCategories.interventions:
            result = await self.aspect_repo.get_all_interventions(all_ids)
            name_mapping = {item.InterventionID: item.InterventionDescription for item in result}
        elif aspect == TagCategories.conditions:
            result = await self.aspect_repo.get_all_conditions(all_ids)
            name_mapping = {item.HealthCareConditionID: item.HealthCareConditionDescription for item in result}
        elif aspect == TagCategories.outcomes:
            result = await self.aspect_repo.get_all_outcomes(all_ids)
            name_mapping = {item.OutcomeID: item.OutcomeDescription for item in result}

        for item in tag_scores:
            item['keyword'] = name_mapping[item['id']].strip()
        
        return tag_scores