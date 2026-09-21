from typing import Optional

from .aspects import TagSimilaritySearchService, TagCategories
from ..utils.llm.extraction import extract_pico, find_match

import asyncio

class LanguageModelService:
    def __init__(self, tag_similarity_service : TagSimilaritySearchService):
        self.tag_similarity_service = tag_similarity_service

    async def extract_pico(self, title : str, abstract : str, fulltext : Optional[str]):
        async def _select_candidate(term, category):
            candidates = await self.tag_similarity_service.get_similar_tags_by_string(term, category, ["internal"], 10)
            #remove the relevance information preventing llm distraction
            candidates_without_relevance = [{k: v for k, v in item.items() if k != 'relevance'} for item in candidates]
            return await find_match(term, candidates_without_relevance)
        
        result = await extract_pico(title, abstract, fulltext)
        selection_tasks = []
        for intervention in result.interventions:
            selection_tasks.append(_select_candidate(intervention,TagCategories.interventions))
        selection_results = await asyncio.gather(*selection_tasks)
        
        result_dict = result.dict()
        result_dict['intervention_selection'] = selection_results
        return result_dict