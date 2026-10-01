from typing import Any, Optional

from ..database.repositories.project import ProjectRepository
from ..database.repositories.report import ReportRepository
from ..database.repositories.study import StudyRepository
from .authorization import get_authorized_project_id
from .pubsub import ProjectPubSubService
from .vectorstore import VectorstoreService
from ..services.study import StudyPayload


class ReportNotInProjectError(Exception):
    """The report has no project association to confirm/unconfirm links within."""


class ReportProjectAccessError(Exception):
    """The report's project could not be verified as accessible."""


class ReportStudyLinkNotFoundError(Exception):
    """No tracked report-study link exists between this report and study."""


class LinkageService:
    def __init__(
        self,
        report_repo: ReportRepository,
        study_repo: StudyRepository,
        project_repo: ProjectRepository,
        vectorstore: VectorstoreService,
        pubsub_service: ProjectPubSubService,
    ):
        self.report_repo = report_repo
        self.study_repo = study_repo
        self.project_repo = project_repo
        self.vectorstore = vectorstore
        self.pubsub_service = pubsub_service

    async def link_existing_study_to_report(
        self,
        report_id: int,
        study_id: int,
        user_id: Optional[str],
    ) -> None:
        """`user_id` doubles as the access-check caller (see
        get_authorized_project_id, src/services/authorization.py) and the
        attribution recorded on the link - previously enforced by a separate
        check_report_access FastAPI dependency ahead of this call.
        """
        project_id = await get_authorized_project_id(report_id, self.report_repo, self.project_repo, user_id)

        try:
            await self.report_repo.link_study(report_id, study_id, user_id=user_id)
            await self.vectorstore.link_report_to_study_id(report_id, study_id, user_id)
            await self.report_repo.commit()
        except Exception as e:
            await self.report_repo.rollback()
            raise Exception(f"Failed to add link: {str(e)}")
        if project_id:
            await self.pubsub_service.publish_project_update(project_id)

    async def unlink_study_from_report(
        self,
        report_id: int,
        study_id: int,
        user_id: Optional[str],
    ) -> None:
        project_id = await get_authorized_project_id(report_id, self.report_repo, self.project_repo, user_id)

        try:
            await self.report_repo.unlink_study(report_id, study_id, user_id=user_id)
            await self.vectorstore.unlink_report_from_study_id(report_id, study_id, user_id)
            await self.report_repo.commit()
        except Exception as e:
            await self.report_repo.rollback()
            raise Exception(f"Failed to delete report-study links: {str(e)}")
        if project_id:
            await self.pubsub_service.publish_project_update(project_id)

    async def create_study_and_link_to_report(
        self,
        report_id: int,
        study: StudyPayload,
        user_id: Optional[str],
    ) -> Any:
        project_id = await get_authorized_project_id(report_id, self.report_repo, self.project_repo, user_id)

        try:
            new_study = await self.study_repo.add_study(
                short_name=study.shortName,
                study_status=study.status,
                countries=study.countries,
                duration=study.duration,
                number_of_participants=study.numberParticipants,
                comparison=study.comparison,
            )
            await self.report_repo.link_study(report_id, new_study.id, user_id=user_id)
            await self.vectorstore.link_report_to_study_id(report_id, new_study.id, user_id)
            await self.report_repo.commit()
        except:
            await self.report_repo.rollback()
            raise
        if project_id:
            await self.pubsub_service.publish_project_update(project_id)
        return new_study

    async def set_report_study_link_confirmation(
        self,
        report_id: int,
        study_id: int,
        confirmed: bool,
    ) -> None:
        """Confirm or unconfirm a tracked report-study link (the StudyReportAdded row),
        used by the admin annotation-review flow. Raises ReportNotInProjectError if the
        report has no project association, ReportProjectAccessError if that project
        can't be resolved, or ReportStudyLinkNotFoundError if no tracked link exists
        between the two - none of these mutate anything, so only a failure inside the
        actual update needs a rollback.
        """
        project_id = await self.project_repo.get_project_id_by_report_id(report_id)
        if not project_id:
            raise ReportNotInProjectError(f"Report {report_id} not found in project")

        project = await self.project_repo.get_project_by_id(project_id)
        if not project:
            raise ReportProjectAccessError(
                "You can only confirm links for reports in your own projects"
            )

        try:
            updated = await self.report_repo.set_study_report_confirmation(report_id, study_id, confirmed)
            await self.report_repo.commit()
        except Exception:
            await self.report_repo.rollback()
            raise

        if not updated:
            raise ReportStudyLinkNotFoundError("Tracked report-study link not found")
