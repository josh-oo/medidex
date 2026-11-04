from typing import Any, Optional

from ..database.repositories.project import ProjectRepository
from ..database.repositories.report import ReportRepository
from ..database.repositories.study import StudyRepository
from .authorization import get_authorized_project_id
from .pubsub import ProjectPubSubService
from .vectorstore import VectorstoreService
from ..utils.dto import StudyPayload


class StudyNotFoundError(Exception):
    """There is no such study, it was created in another scope and no report linked to it is merged yet (see README, "Scopes"), or it is a
    study of another database than the report's project."""


class ReportNotInProjectError(Exception):
    """The report is no report of an update (it is one of the core database): only the reports of an update are linked,
    and its project is the update a new study goes to."""


class LinksCommittedError(Exception):
    """The caller has committed their links of the report (see ProjectResourceService.commit_project_work) and cannot
    change them any more."""


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
        project_id = await self._authorized_open_project_id(report_id, user_id)
        study = await self.study_repo.get_study_by_id(study_id, databases=[await self.project_repo.get_database_id_by_report_id(report_id)])
        if study is None:
            raise StudyNotFoundError(f"Study {study_id} not found")

        try:
            await self.report_repo.link_study(report_id, study_id, user_id=user_id)
            await self.vectorstore.link_report_to_study_id(report_id, study_id, study.database_id, user_id)
            await self.report_repo.commit()
        except Exception as e:
            await self.report_repo.rollback()
            raise Exception(f"Failed to add link: {str(e)}")
        await self.pubsub_service.publish_project_update(project_id)

    async def unlink_study_from_report(
        self,
        report_id: int,
        study_id: int,
        user_id: Optional[str],
    ) -> None:
        project_id = await self._authorized_open_project_id(report_id, user_id)

        try:
            await self.report_repo.unlink_study(report_id, study_id, user_id=user_id)
            await self.vectorstore.unlink_report_from_study_id(report_id, study_id, user_id)
            await self.report_repo.commit()
        except Exception as e:
            await self.report_repo.rollback()
            raise Exception(f"Failed to delete report-study links: {str(e)}")
        await self.pubsub_service.publish_project_update(project_id)

    async def create_study_and_link_to_report(
        self,
        report_id: int,
        study: StudyPayload,
        user_id: Optional[str],
    ) -> Any:
        project_id = await self._authorized_open_project_id(report_id, user_id)
        # The new study goes to the update of the report, in the database of its project.
        database_id = await self.project_repo.get_database_id_by_report_id(report_id)

        try:
            new_study = await self.study_repo.add_study(study.model_dump(), project_id, database_id)
            await self.report_repo.link_study(report_id, new_study.id, user_id=user_id)
            await self.vectorstore.link_report_to_study_id(report_id, new_study.id, database_id, user_id)
            await self.report_repo.commit()
        except:
            await self.report_repo.rollback()
            raise
        await self.pubsub_service.publish_project_update(project_id)
        return new_study

    async def _authorized_open_project_id(self, report_id: int, user_id: Optional[str]) -> str:
        """The project of the report (see get_authorized_project_id), as long as the caller has not committed their
        links of the report. Raises ReportNotInProjectError for a report of the core database."""
        project_id = await get_authorized_project_id(report_id, self.report_repo, self.project_repo, user_id)
        if project_id is None:
            raise ReportNotInProjectError(f"Report {report_id} belongs to no update; only the reports of an update are linked")
        if await self.project_repo.has_committed_report(report_id):
            raise LinksCommittedError(f"Your links of report {report_id} are committed and cannot be changed")
        return project_id
