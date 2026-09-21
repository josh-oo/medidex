from typing import Any, Optional

from ..database.repositories.report import ReportRepository
from ..database.repositories.study import StudyRepository
from .vectorstore import VectorstoreService
from ..services.study import StudyCreate


class LinkageService:
    def __init__(
        self,
        report_repo: ReportRepository,
        study_repo: StudyRepository,
        vectorstore: VectorstoreService,
    ):
        self.report_repo = report_repo
        self.study_repo = study_repo
        self.vectorstore = vectorstore

    async def link_existing_study_to_report(
        self,
        report_id: int,
        study_id: int,
        user_id: Optional[str],
    ) -> None:
        try:
            await self.report_repo.link_study(report_id, study_id, user_id=user_id)
            await self.vectorstore.link_report_to_study_id(report_id, study_id, user_id)
            await self.report_repo.commit()
        except Exception as e:
            await self.report_repo.rollback()
            raise Exception(f"Failed to add link: {str(e)}")

    async def unlink_study_from_report(
        self,
        report_id: int,
        study_id: int,
        user_id: Optional[str],
    ) -> None:
        try:
            await self.report_repo.unlink_study(report_id, study_id, user_id=user_id)
            await self.vectorstore.unlink_report_from_study_id(report_id, study_id, user_id)
            await self.report_repo.commit()
        except Exception as e:
            await self.report_repo.rollback()
            raise Exception(f"Failed to delete report-study links: {str(e)}")

    async def create_study_and_link_to_report(
        self,
        report_id: int,
        study: StudyCreate,
        user_id: Optional[str],
    ) -> Any:
        try:
            new_study = await self.study_repo.add_study(
                short_name=study.shortName,
                study_status=study.status,
                countries=study.countries,
                duration=study.duration,
                number_of_participants=study.numberParticipants,
                comparison=study.comparison,
            )
            await self.report_repo.link_study(report_id, new_study.CRGStudyID, user_id=user_id)
            await self.vectorstore.link_report_to_study_id(report_id, new_study.CRGStudyID, user_id)
            await self.report_repo.commit()
            return new_study
        except:
            await self.report_repo.rollback()
            raise
