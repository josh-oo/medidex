import logging
from typing import Any, Dict, List, Sequence

from ..database.models import Project as DbProject, ReportArchive
from ..database.repositories.archive import DELETED, MERGED, ArchiveRepository
from ..database.repositories.project import ProjectRepository
from ..database.repositories.report import ReportRepository
from ..database.repositories.study import StudyRepository
from ..utils.mergehooks import MergeHookRegistry, merge_hook_registry
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
    """Finishes the reports of an update one by one: the owner merges a report into the core database or deletes it.
    A merge moves the report, the studies created in the update among those selected for it and its links to them into
    the core tables under their ids (see models.py), then runs the merge hooks of the extensions
    (src/utils/mergehooks.py). Either way what the update knew of the report goes to its archive (ReportArchive) and the
    report of the update is removed, its update data with it (the foreign keys of the tables of the updates) and in the
    storages of the extensions (src/utils/storage.py); studies of the update left without a link go as well. Reports
    not finished yet stay in the update, so an assignee added later only works on them.
    """

    def __init__(
        self,
        project_repo: ProjectRepository,
        report_repo: ReportRepository,
        study_repo: StudyRepository,
        archive_repo: ArchiveRepository,
        vectorstore: VectorstoreService,
        document_service: DocumentService,
        pubsub_service: ProjectPubSubService,
        storages: UpdateStorageRegistry = update_storage_registry,
        merge_hooks: MergeHookRegistry = merge_hook_registry,
    ):
        self.project_repo = project_repo
        self.report_repo = report_repo
        self.study_repo = study_repo
        self.archive_repo = archive_repo
        self.vectorstore = vectorstore
        self.document_service = document_service
        self.pubsub_service = pubsub_service
        self.storages = storages
        self.merge_hooks = merge_hooks

    async def merge_report(self, report_id: int, study_ids: Sequence[int]) -> List[int]:
        """Merges the report into the core database with the studies the owner selected for it among those the
        assignees linked it to, returning them. Raises ProjectNotFoundError if the report belongs to no update,
        ProjectAccessDeniedError unless the caller owns it, or ReportNotMergeableError while an assignee has not
        committed it, no study is selected or one the report is not linked to."""
        project = await self._owned_project(report_id)
        assignees = {user_id for user_id, _ in await self.project_repo.get_project_assignees(project.id)}
        missing = assignees - await self.project_repo.get_report_committers(report_id)
        if not assignees or missing:
            raise ReportNotMergeableError(f"Report {report_id} is not committed by every assignee yet")
        study_ids = list(dict.fromkeys(study_ids))
        if not study_ids:
            raise ReportNotMergeableError(f"No study is selected for report {report_id}")
        unlinked = set(study_ids) - set(await self.archive_repo.get_linked_study_ids(report_id))
        if unlinked:
            raise ReportNotMergeableError(f"Report {report_id} is not linked to the studies {sorted(unlinked)}")

        async def merge() -> None:
            await self.archive_repo.promote_report(report_id)
            for study_id in study_ids:
                await self.study_repo.promote(study_id)
            await self.archive_repo.add_core_links(report_id, study_ids)
            for hook in self.merge_hooks.all():
                await hook.on_merge(self.archive_repo.db, self.archive_repo.user_id, report_id, study_ids)

        await self._archive(report_id, project, MERGED, study_ids, merge)
        await self.vectorstore.merge_report(report_id, study_ids, {study_id: project.database_id for study_id in study_ids})
        await self.pubsub_service.publish_project_update(project.id)
        return study_ids

    async def delete_report(self, report_id: int) -> None:
        """Deletes the report: it goes to the archive only, never to the core database. Raises ProjectNotFoundError
        if it belongs to no update, ProjectAccessDeniedError unless the caller owns it."""
        project = await self._owned_project(report_id)
        await self._archive(report_id, project, DELETED, [])
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

    async def _archive(self, report_id: int, project: DbProject, outcome: str, study_ids: List[int], merge=None) -> None:
        """Archives the report, then runs `merge` (which still sees the update data) and removes the report of the
        update, all in one transaction; the storages of the extensions are purged once that is committed."""
        data: Dict[str, Any] = await self.archive_repo.collect(report_id)
        for storage in self.storages.all():
            archived = await storage.archive([report_id])
            if report_id in archived:
                data[storage.key] = archived[report_id]

        try:
            if merge is not None:
                await merge()
            drafts = await self.archive_repo.get_linked_study_ids(report_id)
            await self.archive_repo.remove_update_report(report_id)
            await self.report_repo.delete_orphaned_drafts(drafts)
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
