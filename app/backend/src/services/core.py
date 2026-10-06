from ..database.repositories.study import StudyRepository
from ..database.repositories.project import ProjectRepository
from ..database.repositories.report import ReportRepository
from ..utils.dto import Page, Study, StudyCandidate, candidate_studies_to_dto
from ..utils.pagination import decode_cursor, encode_cursor
from ..utils.tagconfig import TAG_CATEGORIES
from .authorization import get_authorized_project_id
from .authors import AuthorFeatureService
from .vectorstore import VectorstoreService
from .report import ReportService
from .aspects import TagScoringService, TagCategories, UnsupportedAspectError

from typing import List, Any, Optional
from types import SimpleNamespace

import math


class ReportNotReadyError(Exception):
    """The report hasn't finished embedding/PDF processing yet."""


class StudySimilaritySearchService:
    def __init__(self, user_id : str, vectorstore : VectorstoreService, study_repo : StudyRepository, project_repo : ProjectRepository, author_feature_service : AuthorFeatureService, report_service : ReportService):
        self.user_id = user_id
        self.vectorstore = vectorstore
        self.study_repo = study_repo
        self.project_repo = project_repo
        self.author_feature_service = author_feature_service
        self.report_service = report_service

        if not self.user_id:
            self.user_id = "user"

    async def get_similar_study_by_query(self, query : Any, cutoff: str, limit: int, authors:List[str]):

        #Convert TagCategories:

        found_study_ids = {}
        #found_study_titles = {}
        debug_map = {}

        reranked_results = await self.vectorstore.search_similar_studies(query, limit, cutoff)

        for result in reranked_results:
            for hit in result.hits:
                candidates = hit.payload['belongs_to_study']
                for item in candidates:
                    #item = int(item) #TODO remove later
                    if item not in found_study_ids:
                        found_study_ids[item] = hit.score
                    info = dict(hit.payload)
                    info['score'] = hit.score
                    debug_map[item] = debug_map.get(item, []) + [info]

        if len(found_study_ids.keys()) == 0:
            return []
        all_studies = await self.study_repo.get_studies(list(found_study_ids.keys()))

        #Remove this block for evaluation without authors
        #scores_authors = await self.author_feature_service.get_author_scores(report_authors=authors, study_ids=list(found_study_ids.keys()), cutoff=cutoff)
        #for study_id, score in scores_authors.items():
        #    debug_map[study_id].append({'source_id': 'author_reranking', 'score': 0.65 * score})
        #    found_study_ids[study_id] = min(1.00, found_study_ids[study_id] + 0.65 * score)

        rows = []
        for study in all_studies:
            row = SimpleNamespace(**study.model_dump())
            row.relevance = found_study_ids[row.id]
            rows.append(row)

        rows.sort(key=lambda study: study.relevance, reverse=True)

        for study in rows:
            if isinstance(study.relevance, float) and math.isnan(study.relevance):
                print(f"CRITICAL: NaN detected for Study ID {study.id}")
                # Optionally look into debug_map for this ID to see the source
                print(f"Debug info for culprit: {debug_map.get(study.id)}")

        return rows

    async def get_similar_studies_by_id(self, report_id : int, cutoff: str, limit: int, offset: int):
        """Returns (page, has_more): `page` is the [offset, offset + limit) slice of the
        relevance-ranked candidate pool, `has_more` says whether a further page exists.
        Purely semantic (vectorstore hits plus project studies, then re-sorted by score) -
        trial-id matches are surfaced separately, via the explicit study search
        (StudyRepository.search_studies), not mixed into this ranking. The candidate pool
        has no stable id ordering to page by, so pagination is offset-based rather than
        keyset-based like ProjectReportPage - see src/utils/pagination.py. One extra
        candidate beyond the page (`pool_target`) is fetched/kept so has_more can be
        determined without a separate count query.
        """

        report = await self.report_service.get_report(report_id)

        authors = [item.strip() for item in report.authors.split("//")]

        query = self.vectorstore.build_recommandation_based_on_report_id(report.id)

        pool_target = offset + limit + 1
        rows = await self.get_similar_study_by_query(query,cutoff,pool_target, authors)

        # Check if there are any similar items in the same project which are more similar than already retrieved existing studies
        if rows:
            min_score = min(row.relevance for row in rows)
            project_studies = await self.project_repo.get_similar_report_studies(report.id, min_score)

            # Map of existing study IDs to their row, so project matches can update in place
            existing_study_map = {row.id: row for row in rows}

            for study, score in project_studies:
                study_id = study.id

                # If study already exists, update with higher score
                if study_id in existing_study_map:
                    existing_row = existing_study_map[study_id]
                    if score > existing_row.relevance:
                        existing_row.relevance = score
                else:
                    # Add new study
                    new_row = SimpleNamespace(**study.model_dump())
                    new_row.relevance = score
                    rows.append(new_row)
                    existing_study_map[study_id] = new_row

            # Reorder all results by relevance score (descending)
            rows.sort(key=lambda row: row.relevance, reverse=True)

            # Truncate to the pool target (one more than the page) if we have more
            if len(rows) > pool_target:
                rows = rows[:pool_target]

        has_more = len(rows) > offset + limit
        page = rows[offset:offset + limit]
        return page, has_more

    async def get_referenced_studies(self, report_id: int, user_id: Optional[str]) -> List[StudyCandidate]:
        """Studies of reports in the database that this report cites by DOI (see
        ReportService.get_referenced_studies), each with its relevance for the report.
        `user_id` gates access like get_similar_studies_page does; no readiness
        requirement, since this needs neither the embedding nor the PDF.
        """
        await get_authorized_project_id(report_id, self.report_service.report_repo, self.project_repo, user_id)
        studies = await self.report_service.get_referenced_studies(report_id)
        return await self._with_relevance(report_id, studies)

    async def add_relevance(self, report_id: int, studies: List[Study], user_id: Optional[str]) -> List[StudyCandidate]:
        """Access-checked `_with_relevance`, for callers (e.g. the study search) that
        score studies they retrieved by other means against a report."""
        await get_authorized_project_id(report_id, self.report_service.report_repo, self.project_repo, user_id)
        return await self._with_relevance(report_id, studies)

    async def _with_relevance(self, report_id: int, studies: List[Study]) -> List[StudyCandidate]:
        """Scores exactly these studies against the report in the vectorstore (see
        VectorstoreService.score_studies), independent of the top-k cap of the
        similar-studies search. relevance is 0 for studies without an embedded report, or
        for every study if the report itself isn't embedded yet.
        """
        scores = {}
        if studies and report_id in await self.vectorstore.reports_exist([report_id]):
            query = self.vectorstore.build_recommandation_based_on_report_id(report_id)
            scores = await self.vectorstore.score_studies(query, [study.studyId for study in studies])
        return [StudyCandidate(**study.model_dump(), relevance=scores.get(study.studyId, 0.0)) for study in studies]

    async def get_similar_studies_page(
        self,
        report_id: int,
        cutoff: Optional[str],
        limit: int,
        cursor: Optional[str],
        user_id: Optional[str],
    ) -> Page[StudyCandidate]:
        """Full request-level wrapper around get_similar_studies_by_id: access check,
        readiness check, cursor decoding, and DTO assembly, shared by both heads
        (previously inline in fastapi_app/core.py's similarity_search_studies_by_id, gated
        by a separate check_report_access FastAPI dependency). `user_id` is the caller's
        authenticated id for that access check - kept as an explicit argument rather than
        reusing self.user_id, which this service coerces to a "user" placeholder for
        vectorstore query personalization (see __init__) and so can't double as an
        "is this request even authenticated" signal.

        Raises (from get_authorized_project_id, src/services/authorization.py)
        ReportNotFoundError/AuthenticationRequiredError/ReportAccessDeniedError for the
        access check; ReportNotReadyError unless the report has finished embedding/PDF
        processing (skipped when `cutoff` is given - that's a test-only path over
        historical data, where "ready" doesn't apply); and InvalidCursorError (src/utils/pagination.py) for a malformed cursor.
        """
        await get_authorized_project_id(report_id, self.report_service.report_repo, self.project_repo, user_id)

        if not cutoff and not await self.report_service.is_ready(report_id):
            raise ReportNotReadyError(f"Report {report_id} is not ready for processing")

        offset = decode_cursor(cursor) if cursor else 0

        result, has_more = await self.get_similar_studies_by_id(
            report_id,
            cutoff,
            limit,
            offset,
        )
        studies = candidate_studies_to_dto(result)
        next_cursor = encode_cursor(offset + limit) if has_more else None
        return Page[StudyCandidate](items=studies, nextCursor=next_cursor)


class RelatedTagSearchService:

    def __init__(
        self,
        vectorstore : VectorstoreService,
        tag_scoring_service : TagScoringService,
        study_similarity_service : StudySimilaritySearchService,
        study_repo : StudyRepository,
        report_repo : ReportRepository,
        project_repo : ProjectRepository,
    ):
        self.vectorstore = vectorstore
        self.tag_scoring_service = tag_scoring_service
        self.study_similarity_service = study_similarity_service
        self.study_repo = study_repo
        self.report_repo = report_repo
        self.project_repo = project_repo

    async def search_related_tags_by_study_ids(self, study_ids: List[int], aspect : TagCategories, vectors : Any):

        if aspect.value not in TAG_CATEGORIES:
            raise UnsupportedAspectError(f"No related-tag search is defined for aspect '{aspect}'")

        related_tags = await self.study_repo.get_study_tags(aspect.value, study_ids)
        related_ids = {item.id for items in related_tags.values() for item in items}
        return await self.tag_scoring_service.score_related_tags(related_ids, vectors, aspect)

    async def search_related_tags_by_report_id(self, report_id: int, aspect: TagCategories, k : int, cutoff : str, user_id: Optional[str] = None):
        """`user_id` gates access the same way get_similar_studies_page does (see that
        method's docstring) - previously enforced by a separate check_report_access
        FastAPI dependency ahead of this call.
        """
        await get_authorized_project_id(report_id, self.report_repo, self.project_repo, user_id)

        if aspect.value not in TAG_CATEGORIES:
            raise UnsupportedAspectError(f"No related-tag search is defined for aspect '{aspect}'")

        similar_studies, _has_more = await self.study_similarity_service.get_similar_studies_by_id(report_id, cutoff, k, 0)
        predicted_studies = [row.id for row in similar_studies]

        vectors = await self.vectorstore.get_vectors_by_report_id(report_id)
        
        return await self.search_related_tags_by_study_ids(predicted_studies, aspect, vectors)
