import logging
from typing import Any, Dict, List

from ..database.models import Project as DbProject, ReportArchive
from ..database.repositories.archive import DELETED, MERGED, ArchiveRepository
from ..database.repositories.project import ProjectRepository
from ..database.repositories.report import ReportRepository
from ..utils.storage import UpdateStorageRegistry, update_storage_registry
from .authorization import ProjectAccessDeniedError
from .project import ProjectNotFoundError
from .pubsub import ProjectPubSubService
from .report import DocumentService
from .vectorstore import VectorstoreService

logger = logging.getLogger(__name__)


class ReportNotMergeableError(Exception):
    """The report cannot be merged yet: not every assignee has committed their links of it, or no study is selected."""


class UpdateMergeService:
    """Finishes the reports of an update one by one: the owner merges a report into the core database (its selected
    links become links of every scope) or deletes it. Either way what the update knew of the report goes to its archive
    (ReportArchive) and the update data of the report is removed, in the tables and in the storages of the extensions
    (src/utils/storage.py). Reports not finished yet stay in the update, so an assignee added later only works on them.
    """

    def __init__(
        self,
        project_repo: ProjectRepository,
        report_repo: ReportRepository,
        archive_repo: ArchiveRepository,
        vectorstore: VectorstoreService,
        document_service: DocumentService,
        pubsub_service: ProjectPubSubService,
        storages: UpdateStorageRegistry = update_storage_registry,
    ):
        self.project_repo = project_repo
        self.report_repo = report_repo
        self.archive_repo = archive_repo
        self.vectorstore = vectorstore
        self.document_service = document_service
        self.pubsub_service = pubsub_service
        self.storages = storages

    async def merge_report(self, report_id: int) -> List[int]:
        """Merges the report into the core database with the studies the owner selected for it, returning them.
        Raises ProjectNotFoundError if the report belongs to no update, ProjectAccessDeniedError unless the caller owns
        it, or ReportNotMergeableError while an assignee has not committed it or no study is selected."""
        project = await self._owned_project(report_id)
        assignees = {user_id for user_id, _ in await self.project_repo.get_project_assignees(project.id)}
        missing = assignees - await self.project_repo.get_report_committers(report_id)
        if not assignees or missing:
            raise ReportNotMergeableError(f"Report {report_id} is not committed by every assignee yet")
        study_ids = await self.archive_repo.get_selected_study_ids(report_id)
        if not study_ids:
            raise ReportNotMergeableError(f"No study is selected for report {report_id}")

        await self._archive(report_id, project, MERGED, study_ids, lambda: self.archive_repo.merge_links(report_id, study_ids))
        await self.vectorstore.merge_report(report_id, study_ids, {study_id: project.database_id for study_id in study_ids})
        await self.pubsub_service.publish_project_update(project.id)
        return study_ids

    async def delete_report(self, report_id: int) -> None:
        """Deletes the report: it goes to the archive only, never to the core database. Raises ProjectNotFoundError
        if it belongs to no update, ProjectAccessDeniedError unless the caller owns it."""
        project = await self._owned_project(report_id)

        async def remove() -> None:
            study_ids = await self.archive_repo.get_linked_study_ids(report_id)
            await self.report_repo.delete_report(report_id)
            await self.archive_repo.delete_orphaned_studies(study_ids)

        await self._archive(report_id, project, DELETED, [], remove)
        await self.vectorstore.delete_vectors_by_report_ids([report_id])
        await self.document_service.delete_pdf_files([report_id])
        await self.pubsub_service.publish_project_update(project.id)

    async def _owned_project(self, report_id: int) -> DbProject:
        project_id = await self.project_repo.get_project_id_by_report_id(report_id)
        if project_id is None:
            raise ProjectNotFoundError(f"Report {report_id} belongs to no update")
        project = await self.project_repo.get_project_by_id(project_id)
        if project is None:
            raise ProjectAccessDeniedError(f"Only the owner of project {project_id} finishes its reports")
        return project

    async def _archive(self, report_id: int, project: DbProject, outcome: str, study_ids: List[int], change) -> None:
        """Archives the report, then applies `change` and removes its update data in one transaction; the storages of
        the extensions are purged once that is committed."""
        data: Dict[str, Any] = await self.archive_repo.collect(report_id)
        for storage in self.storages.all():
            archived = await storage.archive([report_id])
            if report_id in archived:
                data[storage.key] = archived[report_id]

        try:
            await self.archive_repo.purge_update_data(report_id)
            await change()
            self.archive_repo.add(ReportArchive(
                report_id=report_id,
                project_id=project.id,
                project_name=project.description,
                database_id=project.database_id,
                outcome=outcome,
                study_ids=study_ids,
                archived_by=self.archive_repo.user_id,
                data=data,
            ))
            await self.archive_repo.commit()
        except Exception:
            await self.archive_repo.rollback()
            raise

        for storage in self.storages.all():
            try:
                await storage.purge([report_id])
            except Exception:
                logger.exception("Purging the %s of report %s failed", storage.label, report_id)
