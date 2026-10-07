from ..database.repositories.study import StudyRepository
from ..utils.dto import Page, Study, StudyPayload, studies_to_dto
from ..utils.pagination import decode_cursor, encode_cursor
from ..utils.query_parser import QueryNode, parse_advanced_query, parse_search_query

from typing import List, Optional, Tuple, Union

class StudyResourceService:
    def __init__(self, study_repo : StudyRepository):
        self.study_repo = study_repo

    async def add_study(self, study : StudyPayload):
        try:
            new_study = await self.study_repo.add_study(study.model_dump())
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
        parsed here, so the router itself never has to) or an already-structured QueryNode
        """
        ast = parse_advanced_query(query) if isinstance(query, str) else query
        result, has_more = await self.study_repo.search_studies_advanced(ast, limit, offset)
        return studies_to_dto(result), has_more

    async def search_studies_page(self, query: str, limit: int, cursor: Optional[str]) -> Page[Study]:
        """One page of a study search from a raw query string: free-text, or - if the
        string is an advanced field==value expression or JSON filter (see
        parse_search_query) - the advanced search.

        Raises InvalidCursorError for a malformed cursor and QuerySyntaxError for a
        malformed advanced query.
        """
        offset = decode_cursor(cursor) if cursor else 0
        ast = parse_search_query(query)
        if ast is None:
            studies, has_more = await self.search_studies(query, limit, offset)
        else:
            studies, has_more = await self.search_studies_advanced(ast, limit, offset)
        next_cursor = encode_cursor(offset + limit) if has_more else None
        return Page[Study](items=studies, nextCursor=next_cursor)
