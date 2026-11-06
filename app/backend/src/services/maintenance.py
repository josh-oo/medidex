import asyncio
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Set, Tuple

from ..database.repositories.aspects import AspectRepository
from ..database.repositories.database import DatabaseRepository
from ..database.repositories.report import ReportRepository
from ..utils.dto import DatabaseStage, DatabaseStatus
from .embedding import EmbeddingService
from .pubsub import DatabaseProgress, DatabaseStatusService
from .vectorstore import VectorstoreService, transform_to_uuid

logger = logging.getLogger(__name__)


class MaintenanceService:
    # The tag categories with vectors and the part of their point ids that tells them apart (transform_to_uuid);
    # that of reports is "0000".
    TAG_POINT_KINDS = {"interventions": "0001", "conditions": "0002", "outcomes": "0003", "participants": "0004", "design": "0005"}
    # The points the sync owns; others (e.g. MeSH tags, "1000") are left alone.
    MANAGED_POINT = re.compile(r"^00000000-000[0-5]-4000-a000-")
    # How long to wait for the embedding service while it starts.
    EMBEDDING_ATTEMPTS = 90
    EMBEDDING_RETRY_SECONDS = 2.0

    def __init__(
        self,
        report_repo: ReportRepository,
        vectorstore: VectorstoreService,
        database_repo: DatabaseRepository,
        aspect_repo: AspectRepository,
        embedding_service: EmbeddingService,
        status_service: DatabaseStatusService,
    ):
        self.status_service = status_service
        self.report_repo = report_repo
        self.vectorstore = vectorstore
        self.database_repo = database_repo
        self.aspect_repo = aspect_repo
        self.embedding_service = embedding_service
        # Whether the wait for the embedding service was logged: once, not for every text that waits.
        self._embedding_wait_logged = False

    async def sync_vectorstore(self) -> Dict[str, int]:
        """Brings the vectorstore in line with postgres: every report and every tag of the categories with vectors
        that has no point yet is embedded and added, and the points of reports and tags that no longer exist are
        removed. Only the points of the id scheme of transform_to_uuid for reports and those tags are touched, and
        existing points are kept as they are (their links per scope live in their payload). Run by the backend on
        start (src/background/startup.py); it also finishes the indexing of an imported database that was interrupted,
        and publishes how far that is (DatabaseStatusService)."""
        study_databases = await self.database_repo.get_study_database_ids()
        wanted = await self._wanted_points(study_databases)
        existing = await self.vectorstore.get_point_ids()
        stale = [point_id for point_id in existing if self.MANAGED_POINT.match(point_id) and point_id not in wanted]
        await self.vectorstore.delete_points(stale)
        missing = [point_id for point_id in wanted if point_id not in existing]
        logger.info("vectorstore sync: %d missing, %d stale of %d points", len(missing), len(stale), len(wanted))
        report_databases = await self._report_databases(study_databases)
        progress = await self._indexing_progress(report_databases, set(missing))

        async def add(point_id):
            text, payload = wanted[point_id]
            await self.vectorstore.upsert_points([(point_id, await self._embed(text), payload)])
            for database_id in report_databases.get(point_id, ()):
                await progress[database_id].advance()

        try:
            await EmbeddingService.for_each(missing, add)
        except Exception as exc:
            # The databases it was indexing say why it stopped, instead of waiting at where it was.
            for database_id in progress:
                await self.status_service.fail_indexing(database_id, exc)
            raise
        for database_id in progress:
            await self.status_service.publish(DatabaseStatus(databaseId=database_id, stage=DatabaseStage.ready))
        return {"points": len(wanted), "added": len(missing), "removed": len(stale)}

    async def _report_databases(self, study_databases: Dict[int, int]) -> Dict[str, Set[int]]:
        """The databases of the studies of every report linked to one, by the id of its point."""
        return {
            transform_to_uuid(report_id): {study_databases[study_id] for study_id in study_ids if study_id in study_databases}
            for report_id, study_ids in (await self.database_repo.get_all_report_study_ids()).items()
        }

    async def _indexing_progress(self, report_databases: Dict[str, Set[int]], missing: Set[str]) -> Dict[int, DatabaseProgress]:
        """The progress of the indexing of each database some of whose reports have no point yet, started."""
        progress: Dict[int, DatabaseProgress] = {}
        for database_id in sorted({database_id for point_id in missing for database_id in report_databases.get(point_id, ())}):
            points = [point_id for point_id, databases in report_databases.items() if database_id in databases]
            done = sum(1 for point_id in points if point_id not in missing)
            progress[database_id] = await self.status_service.progress(database_id, DatabaseStage.indexing, None, len(points), done).start()
        return progress

    async def _wanted_points(self, study_databases: Dict[int, int]) -> Dict[str, Tuple[str, Dict[str, Any]]]:
        """The text to embed and the payload of every point there should be, by point id."""
        study_ids = await self.database_repo.get_all_report_study_ids()
        points: Dict[str, Tuple[str, Dict[str, Any]]] = {}
        for report in await self.report_repo.get_all_reports():
            studies = study_ids.get(report.id, [])
            points[transform_to_uuid(report.id)] = (
                "\n".join(part for part in (report.title, report.abstract) if part).strip(),
                {
                    "is_report": True,
                    "belongs_to_study": studies,
                    "report_id": report.id,
                    "created_at": report.created_at.isoformat(),
                    "authors": list(report.authors),
                    "title": report.title,
                    "abstract": report.abstract,
                    "belongs_to_trial_id": bool(studies),
                    **VectorstoreService.database_payload(studies, study_databases),
                },
            )
        for category, kind in self.TAG_POINT_KINDS.items():
            for tag in await self.aspect_repo.get_all_tags(category, []):
                points[transform_to_uuid(tag.id, kind)] = (
                    tag.embedded_text,
                    {
                        "tree_ids": [category],
                        "source": "internal",
                        "source_id": str(tag.id),
                        "display_name": tag.name,
                        "is_report": False,
                    },
                )
        return points

    async def _embed(self, text: str) -> List[float]:
        """The vector of the text; waits for the embedding service while it is still starting. An error that waiting
        does not mend (e.g. a missing API key or an unknown model) is raised at once."""
        for attempt in range(self.EMBEDDING_ATTEMPTS):
            try:
                return await self.embedding_service.embed(text)
            except Exception as exc:
                if attempt == self.EMBEDDING_ATTEMPTS - 1 or not EmbeddingService.is_transient(exc):
                    raise
                if not self._embedding_wait_logged:
                    self._embedding_wait_logged = True
                    logger.warning(
                        "embedding service not usable yet, retrying for up to %ds: %s",
                        self.EMBEDDING_ATTEMPTS * self.EMBEDDING_RETRY_SECONDS,
                        DatabaseStatusService.describe(exc),
                    )
                await asyncio.sleep(self.EMBEDDING_RETRY_SECONDS)
        return []

    async def vectorstore_clean_up(self):
        all_report_ids_vectorstore, all_report_ids_db = await asyncio.gather(
            self.vectorstore.get_all_saved_report_ids(),
            self.report_repo.get_all_reports()
        )

        all_report_ids_vectorstore = set(all_report_ids_vectorstore)
        all_report_ids_db = set([item.id for item in all_report_ids_db])

        # Find orphan IDs (in vectorstore but not in database)
        orphan_ids =  all_report_ids_vectorstore - all_report_ids_db
        
        # Delete orphan vectors
        if orphan_ids:
            await self.vectorstore.delete_vectors_by_report_ids(list(orphan_ids))
        
        return {
            "unique_vectorstore_points": len(all_report_ids_vectorstore),
            "unique_report_ids": len(all_report_ids_db),
            "orphan_ids_found": len(orphan_ids),
            "orphan_ids_deleted": list(orphan_ids)
        }
    
class ReadinessService:
    def __init__(self, db_ready : str, vectorstore : VectorstoreService, embedding_service : EmbeddingService):
        self.db_ready = db_ready
        self.vectorstore = vectorstore
        self.embedding_service = embedding_service

    async def readyz(self) -> Dict[str, Any]:
        """
        Check if the service is ready to accept requests.
        
        Returns:
            - status: "ready" or "not_ready"
            - checks: detailed status of each dependency
        """
        checks = {}
        overall_status = "ready"
        
        # Check database connectivity
        if self.db_ready == "ready":
            checks["database"] = {"status": "healthy", "message": "Database connection successful"}
        else:
            checks["database"] = {"status": "unhealthy", "message": f"Database error: {self.db_ready}"}
            overall_status = "not_ready"
        
        checks["vectorstore"] = await self.vectorstore.readyz()
        if checks["vectorstore"]['status'] != "healthy":
            overall_status = "not_ready"
        
        checks["embedding_service"] = self.embedding_service.readyz()
        if checks["embedding_service"]['status'] != "healthy":
            overall_status = "not_ready"
        
        """
        # Check background task health
        checks["background_tasks"] = {
            "status": "healthy",
            "active_tasks": len(background_tasks),
            "message": f"{len(background_tasks)} active background tasks"
        }
        
        # Check project subscribers
        async with project_subscribers_lock:
            total_subscribers = sum(len(queues) for queues in project_subscribers.values())
            checks["project_subscribers"] = {
                "status": "healthy",
                "active_projects": len(project_subscribers),
                "total_subscribers": total_subscribers,
                "message": f"{len(project_subscribers)} projects with {total_subscribers} subscribers"
            }
        """
            
        response = {
            "status": overall_status,
            "timestamp": datetime.now().isoformat(),
            "checks": checks
        }

        return response


