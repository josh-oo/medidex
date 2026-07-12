from ..database.repositories.study import StudyRepository

from typing import List, Optional
from pydantic import BaseModel

class Study(BaseModel):
    studyId: int
    shortName: str
    status: str
    countries: List[str]
    numberParticipants: Optional[str]
    duration: Optional[str]
    comparison: Optional[str]
    trialId: Optional[str]
    createdAt: Optional[str]
    updatedAt: Optional[str]

class StudyCreate(BaseModel):
    shortName: str
    status: str
    countries: List[str]
    numberParticipants: Optional[str]
    duration: Optional[str]
    comparison: Optional[str]
    trialId: Optional[str] = None

def transform_to_output_studies(studies):
    result = []
    for study in studies:
        output_study = Study(
            studyId=study.CRGStudyID,
            shortName=study.ShortName,
            numberParticipants=study.NumberParticipants,
            duration=study.Duration,
            comparison=study.Comparison,
            countries=study.Countries.split("//"),
            createdAt=study.DateEntered,
            updatedAt=study.DateEdited,
            status=study.StatusofStudy,
            trialId=study.ISRCTN,
        )
        result.append(output_study)
    return result

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
            return transform_to_output_studies([new_study])[0]
        except:
            await self.study_repo.rollback()
            raise

    async def get_studies(self, study_ids : List[int], query : Optional[str] = None):
        if query:
            result = await self.study_repo.search_studies(query, study_ids)
        else:
            result = await self.study_repo.get_studies(study_ids)
        return transform_to_output_studies(result)