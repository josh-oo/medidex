from ..database.repositories.study import StudyRepository
from ..database.repositories.project import ProjectRepository
from .authors import AuthorFeatureService
from .vectorstore import VectorstoreService
from .report import ReportService
from .aspects import TagScoringService, TagCategories

from typing import List, Any
from types import SimpleNamespace

import math

    
class StudySimilaritySearchService:
    def __init__(self, user_id : str, vectorstore : VectorstoreService, study_repo : StudyRepository, project_repo : ProjectRepository, author_feature_service : AuthorFeatureService, report_service : ReportService):
        self.user_id = user_id
        self.vectorstore = vectorstore
        self.study_repo = study_repo
        self.project_repo = project_repo
        self.author_feature_service = author_feature_service
        self.report_service = report_service

        self.debug = False

        if not self.user_id:
            self.user_id = "user"

    async def get_similar_study_by_query(self, query : Any, cutoff: str, limit: int, negative_studies: List[int], trial_ids: List[str], authors:List[str], return_details: bool):

        #Convert TagCategories:

        found_study_ids = {}
        #found_study_titles = {}
        debug_map = {}

        return_details= return_details or self.debug


        if len(trial_ids) > 0:
            response = await self.study_repo.get_study_id_by_trial_ids(trial_ids, cutoff)
            penalty = 0.00
            if response:
                for trial_id in trial_ids:
                    study_ids = response[trial_id]
                    for study_id in study_ids:
                        if study_id in negative_studies:
                            continue
                        found_study_ids[study_id] = 1.00 - penalty
                        debug_map[study_id] = [{"source_id":trial_id}]
                        penalty += 0.01

        remaining = limit - len(found_study_ids.keys())
        if remaining > 0:

            blacklist = list(found_study_ids.keys()) + negative_studies
            exclude_trial_related_studies = len(found_study_ids.keys()) > 0
            reranked_results = await self.vectorstore.search_similar_studies(query, remaining, cutoff, blacklist, exclude_trial_related_studies)

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
            if return_details:
                row.details = list({d['source_id']: d for d in debug_map[row.id]}.values())
            rows.append(row)

        rows.sort(key=lambda study: study.relevance, reverse=True)

        for study in rows:
            if isinstance(study.relevance, float) and math.isnan(study.relevance):
                print(f"CRITICAL: NaN detected for Study ID {study.id}")
                # Optionally look into debug_map for this ID to see the source
                print(f"Debug info for culprit: {debug_map.get(study.id)}")

        return rows

    async def get_similar_studies_by_id(self, report_id : int, cutoff: str, limit: int, offset: int, negative_studies: List[int], negative_reports: List[int], return_details: bool):
        """Returns (page, has_more): `page` is the [offset, offset + limit) slice of the
        relevance-ranked candidate pool, `has_more` says whether a further page exists.
        The candidate pool has no stable id ordering to page by (it's assembled from
        exact trial-id matches, vectorstore hits and project studies, then re-sorted by
        score), so pagination is offset-based rather than keyset-based like ProjectReportPage -
        see src/utils/pagination.py. One extra candidate beyond the page (`pool_target`)
        is fetched/kept so has_more can be determined without a separate count query.
        """

        if not negative_studies:
            negative_studies = []

        report = await self.report_service.get_report(report_id)

        authors = [item.strip() for item in report.authors.split("//")]
        trial_ids = await self.report_service.get_trial_ids(report_id, include_fulltext=True)

        query = self.vectorstore.build_recommandation_based_on_report_id(report.id, negative_reports)

        pool_target = offset + limit + 1
        rows = await self.get_similar_study_by_query(query,cutoff,pool_target,negative_studies, trial_ids, authors, return_details=return_details)

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


class RelatedTagSearchService:

    def __init__(self, vectorstore : VectorstoreService, tag_scoring_service : TagScoringService, study_similarity_service : StudySimilaritySearchService, study_repo : StudyRepository):
        self.vectorstore = vectorstore
        self.tag_scoring_service = tag_scoring_service
        self.study_similarity_service = study_similarity_service
        self.study_repo = study_repo

    async def search_related_tags_by_study_ids(self, study_ids: List[int], aspect : TagCategories, vectors : Any):
        
        related_tags = []
        if aspect == TagCategories.interventions:
            related_tags = await self.study_repo.get_study_interventions(study_ids)
            related_ids = {item["ID"] for items in related_tags.values() for item in items}
            return await self.tag_scoring_service.score_related_tags(related_ids, vectors, TagCategories.interventions)
        elif aspect == TagCategories.conditions:
            related_tags = await self.study_repo.get_study_conditions(study_ids)
            related_ids = {item["ID"] for items in related_tags.values() for item in items}
            return await self.tag_scoring_service.score_related_tags(related_ids, vectors, TagCategories.conditions)
        elif aspect == TagCategories.outcomes:
            related_tags = await self.study_repo.get_study_outcomes(study_ids=study_ids)
            related_ids = {item["ID"] for items in related_tags.values() for item in items}
            return await self.tag_scoring_service.score_related_tags(related_ids, vectors, TagCategories.outcomes)
    
    async def search_related_tags_by_report_id(self, report_id: int, aspect: TagCategories, k : int, cutoff : str):
        
        #similar_studies = await self.study_similarity_service.get_similar_studies_by_id(report_id, TagCategories.default, cutoff, k, None, None, False)
        similar_studies, _has_more = await self.study_similarity_service.get_similar_studies_by_id(report_id, cutoff, k, 0, None, None, False)
        predicted_studies = [row.id for row in similar_studies]

        vectors = await self.vectorstore.get_vectors_by_report_id(report_id)
        
        return await self.search_related_tags_by_study_ids(predicted_studies, aspect, vectors)
