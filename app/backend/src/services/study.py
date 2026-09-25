from ..database.repositories.study import StudyRepository
from ..utils.dto import StudyCreate, studies_to_dto

from typing import List

class StudyResourceService:
    def __init__(self, study_repo : StudyRepository):
        self.study_repo = study_repo

    async def add_study(self, study : StudyCreate):
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