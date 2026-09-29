from ..database.repositories.study import StudyRepository
from ..utils.dto import StudyPayload, studies_to_dto
from ..utils.query_parser import QueryNode, parse_advanced_query

from typing import List, Tuple, Union

class StudyResourceService:
    def __init__(self, study_repo : StudyRepository):
        self.study_repo = study_repo

    async def add_study(self, study : StudyPayload):
        try:
            new_study = await self.study_repo.add_study(
                    short_name=study.shortName,
                    study_status=study.status,
                    countries=study.countries,
                    duration=study.duration,
                    number_of_participants=study.numberParticipants,
                    comparison=study.comparison,
            )
            await self.study_repo.commit()
            return studies_to_dto([new_study])[0]
        except:
            await self.study_repo.rollback()
            raise

    async def get_studies(self, study_ids : List[int]):
        result = await self.study_repo.get_studies(study_ids)
        return studies_to_dto(result)

    async def search_studies(self, query: str, limit: int, offset: int) -> Tuple[List, bool]:
        result, has_more = await self.study_repo.search_studies(query, limit, offset)
        return studies_to_dto(result), has_more

    async def search_studies_advanced(self, query: Union[str, QueryNode], limit: int, offset: int) -> Tuple[List, bool]:
        """Accepts either a raw advanced-search query string (the REST API's own case -
        parsed here, so the router itself never has to) or an already-structured
        QueryNode (the MCP tool's case - it hands over a validated Comparison/AndGroup/
        OrGroup tree directly, so there's nothing left to parse)."""
        ast = parse_advanced_query(query) if isinstance(query, str) else query
        result, has_more = await self.study_repo.search_studies_advanced(ast, limit, offset)
        return studies_to_dto(result), has_more