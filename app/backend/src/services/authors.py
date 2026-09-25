from ..database.repositories.study import StudyRepository
from ..utils.postprocessing import normalize_author_names

from collections import Counter
from typing import List, Dict
import math

class AuthorFeatureService:
    _shared_cache = None

    def __init__(self, study_repo : StudyRepository):
        self.study_repo = study_repo

    async def compute_all_author_frequencies_global(self):
        if AuthorFeatureService._shared_cache is None:
            result = await self.study_repo.get_study_persons(study_ids=None,cutoff=None,normalize_names=True)

            all_authors = []
            for value in result.values():
                all_authors.extend(set(value))

            counts = Counter(all_authors)

            AuthorFeatureService._shared_cache = counts

            return counts
        return AuthorFeatureService._shared_cache

    async def get_author_frequencies(self, authors: List[str]) -> Dict[str, int]:
        normalized_author_names = normalize_author_names(authors=authors)
        
        author_frequencies = await self.compute_all_author_frequencies_global()

        result = {}
        for author in normalized_author_names:
            if author in author_frequencies:
                result[author] = author_frequencies[author]
            else:
                result[author] = 1

        return result
    
    async def get_author_scores(self, report_authors: List[str], study_ids: List[int], cutoff: str):
        study_persons = await self.study_repo.get_study_persons(study_ids, cutoff, normalize_names=True)
        current_persons = await self.get_author_frequencies(report_authors)

        report_authors = set(current_persons.keys())

        result = {}
        num_report_authors = len(report_authors)
        if num_report_authors == 0:
            return {}
        for study_id, study_authors in study_persons.items():
            total_score = 0
            num_total_authors = len(study_authors) + num_report_authors
            intersection = set(study_authors) & report_authors
            for matching_author in intersection:
                if matching_author in current_persons:
                    total_score += 1 / math.log(current_persons[matching_author] + 2)
            total_score = total_score / num_total_authors if num_total_authors > 0 else 0
            result[int(study_id)] = total_score

        return result
    
    async def build_features(self, report_authors, study_authors):
        #calculate simialrity features based on study_authors
        current_person_freq = await self.get_author_frequencies(report_authors)
        ra = set(current_person_freq.keys()) # report_authors
        sa = set(study_authors)

        overlap = ra & sa
        num_overlap = len(overlap)

        inv_freq_sum = sum(1 / current_person_freq[a] for a in overlap) if overlap else 0
        inv_freq_sum_log = sum(1 / math.log(current_person_freq[a] + 2) for a in overlap) if overlap else 0

        num_report = len(ra)
        num_study = len(sa)
        jaccard = num_overlap / len(ra | sa) if (ra | sa) else 0

        return {
            "num_overlap": num_overlap,
            "inv_freq_sum": inv_freq_sum,
            "inv_freq_sum_log": inv_freq_sum_log,
            "num_report": num_report,
            "num_study": num_study,
            "jaccard": jaccard,
        }