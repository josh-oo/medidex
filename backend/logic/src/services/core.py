from ..database.repositories.study import StudyRepository
from ..database.repositories.project import ProjectRepository
from .authors import AuthorFeatureService
from .vectorstore import VectorstoreService
from .report import ReportService
from .aspects import TagScoringService, TagCategories

from typing import List, Any

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

    async def get_similar_study_by_query(self, query : Any, cutoff: str, k: int, negative_studies: List[int], trial_ids: List[str], authors:List[str], return_details: bool):
    
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

        k = k - len(found_study_ids.keys())
        if k > 0:

            blacklist = list(found_study_ids.keys()) + negative_studies
            exclude_trial_related_studies = len(found_study_ids.keys()) > 0
            reranked_results = await self.vectorstore.search_similar_studies(query, k, cutoff, blacklist, exclude_trial_related_studies)

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
            return {'CRGStudyID': [] , 'Relevance' : []}
        all_studies = await self.study_repo.get_studies(list(found_study_ids.keys()))
        #list of dicts to dict of lists:

        #Remove this block for evaluation without authors
        #scores_authors = await self.author_feature_service.get_author_scores(report_authors=authors, study_ids=list(found_study_ids.keys()), cutoff=cutoff)
        #for study_id, score in scores_authors.items():
        #    debug_map[study_id].append({'source_id': 'author_reranking', 'score': 0.65 * score})
        #    found_study_ids[study_id] = min(1.00, found_study_ids[study_id] + 0.65 * score)

        for i in range(0, len(all_studies)):
            item = all_studies[i].dict()
            item['Relevance'] = found_study_ids[item['CRGStudyID']]
            all_studies[i] = item

        result = {}
        for study in all_studies:
            for key, value in study.items(): 
                result.setdefault(key, []).append(value)

        order = ['CRGStudyID', 'Relevance', 'ShortName', 'NumberParticipants', 'Duration', 'Comparison', 'Countries', 'DateEntered', 'DateEdited', 'StatusofStudy', 'ISRCTN']
        reordered = {key: result[key] for key in order}

        if return_details:
            reordered['details'] = [list({d['source_id']: d for d in debug_map[key]}.values()) for key in reordered['CRGStudyID']]

        sorted_indices = sorted(range(len(reordered['Relevance'])), key=lambda i: reordered['Relevance'][i], reverse=True)
        for k in reordered:
            reordered[k] = [reordered[k][i] for i in sorted_indices]

        # Add this right before "return reordered"
        for study_id, relevance in zip(reordered['CRGStudyID'], reordered['Relevance']):
            if isinstance(relevance, float) and math.isnan(relevance):
                print(f"CRITICAL: NaN detected for Study ID {study_id}")
                # Optionally look into debug_map for this ID to see the source
                print(f"Debug info for culprit: {debug_map.get(study_id)}")

        return reordered

    async def get_similar_studies_by_id(self, report_id : int, cutoff: str, k: int, negative_studies: List[int], negative_reports: List[int], return_details: bool):

        if not negative_studies:
            negative_studies = []

        report = await self.report_service.get_report(report_id)

        authors = [item.strip() for item in report.Authors.split("//")]
        trial_ids = await self.report_service.get_trial_ids(report_id, include_fulltext=True)

        query = self.vectorstore.build_recommandation_based_on_report_id(report.CRGReportID, negative_reports)
        

        result = await self.get_similar_study_by_query(query,cutoff,k,negative_studies, trial_ids, authors, return_details=return_details)

        # Check if there are any similar items in the same project which are more similar than already retrieved existing studies
        if result.get('Relevance'):
            min_score = min(result['Relevance'])
            project_studies = await self.project_repo.get_similar_report_studies(report.CRGReportID, min_score)
            
            # Create a map of existing study IDs to their positions and scores
            existing_study_map = {}
            for idx, study_id in enumerate(result.get('CRGStudyID', [])):
                existing_study_map[study_id] = {
                    'index': idx,
                    'score': result['Relevance'][idx]
                }
            
            for study, score in project_studies:
                study_dict = study.dict()
                study_id = study_dict.get('CRGStudyID')
                
                # If study already exists, update with higher score
                if study_id in existing_study_map:
                    existing_info = existing_study_map[study_id]
                    if score > existing_info['score']:
                        # Update the existing entry with the higher score
                        result['Relevance'][existing_info['index']] = score
                else:
                    # Add new study
                    result['Relevance'].append(score)
                    for key in result.keys():
                        if key == "Relevance":
                            continue
                        result[key].append(study_dict.get(key))
                    
                    # Track the new study in our map
                    existing_study_map[study_id] = {
                        'index': len(result['Relevance']) - 1,
                        'score': score
                    }
            
            # Reorder all results by relevance score (descending)
            if result['Relevance']:
                sorted_indices = sorted(
                    range(len(result['Relevance'])), 
                    key=lambda i: result['Relevance'][i], 
                    reverse=True
                )
                for key in result.keys():
                    result[key] = [result[key][i] for i in sorted_indices]

                # Truncate to k results if we have more
                if len(result['Relevance']) > k:
                    for key in result.keys():
                        result[key] = result[key][:k]

        return result
    

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
            return await self.tag_scoring_service.score_related_tags(related_ids, vectors["intervention"], TagCategories.interventions)
        elif aspect == TagCategories.conditions:
            related_tags = await self.study_repo.get_study_conditions(study_ids)
            related_ids = {item["ID"] for items in related_tags.values() for item in items}
            return await self.tag_scoring_service.score_related_tags(related_ids, vectors["condition"], TagCategories.conditions)
        elif aspect == TagCategories.outcomes:
            related_tags = await self.study_repo.get_study_outcomes(study_ids=s)
            related_ids = {item["ID"] for items in related_tags.values() for item in items}
            return await self.tag_scoring_service.score_related_tags(related_ids, vectors["outcome"], TagCategories.outcomes)
    
    async def search_related_tags_by_report_id(self, report_id: int, aspect: TagCategories, k : int, cutoff : str):
        
        #similar_studies = await self.study_similarity_service.get_similar_studies_by_id(report_id, TagCategories.default, cutoff, k, None, None, False)
        similar_studies = await self.study_similarity_service.get_similar_studies_by_id(report_id, cutoff, k, None, None, False)
        predicted_studies = similar_studies['CRGStudyID']

        vectors = await self.vectorstore.get_vectors_by_report_id(report_id)
        
        return await self.search_related_tags_by_study_ids(predicted_studies, aspect, vectors)
