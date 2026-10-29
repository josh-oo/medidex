import asyncio
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Tuple

from ..database.repositories.aspects import AspectRepository
from ..database.repositories.database import DatabaseRepository
from ..database.repositories.report import ReportRepository
from .embedding import EmbeddingService
from .vectorstore import VectorstoreService, transform_to_uuid

logger = logging.getLogger(__name__)


class MaintenanceService:
    # The tag categories with vectors and the part of their point ids that tells them apart (transform_to_uuid);
    # that of reports is "0000".
    TAG_POINT_KINDS = {"interventions": "0001", "conditions": "0002", "outcomes": "0003"}
    # The points the sync owns; others (e.g. MeSH tags, "1000") are left alone.
    MANAGED_POINT = re.compile(r"^00000000-000[0-3]-4000-a000-")
    # Texts per request to the embedding service, and how long to wait for it while it starts.
    EMBEDDING_BATCH = 16
    EMBEDDING_ATTEMPTS = 90
    EMBEDDING_RETRY_SECONDS = 2.0

    def __init__(
        self,
        report_repo: ReportRepository,
        vectorstore: VectorstoreService,
        database_repo: DatabaseRepository,
        aspect_repo: AspectRepository,
        embedding_service: EmbeddingService,
    ):
        self.report_repo = report_repo
        self.vectorstore = vectorstore
        self.database_repo = database_repo
        self.aspect_repo = aspect_repo
        self.embedding_service = embedding_service

    async def sync_vectorstore(self) -> Dict[str, int]:
        """Brings the vectorstore in line with postgres: every report and every tag of the categories with vectors
        that has no point yet is embedded and added, and the points of reports and tags that no longer exist are
        removed. Only the points of the id scheme of transform_to_uuid for reports and those tags are touched, and
        existing points are kept as they are (their links per scope live in their payload). Run by the backend on
        start (src/background/startup.py); it also finishes the indexing of an imported database that was interrupted."""
        study_databases = await self.database_repo.get_study_database_ids()
        wanted = await self._wanted_points(study_databases)
        existing = await self.vectorstore.get_point_ids()
        stale = [point_id for point_id in existing if self.MANAGED_POINT.match(point_id) and point_id not in wanted]
        await self.vectorstore.delete_points(stale)
        missing = [point_id for point_id in wanted if point_id not in existing]
        logger.info("vectorstore sync: %d missing, %d stale of %d points", len(missing), len(stale), len(wanted))
        for start in range(0, len(missing), self.EMBEDDING_BATCH):
            batch = missing[start:start + self.EMBEDDING_BATCH]
            vectors = await self._embed([wanted[point_id][0] for point_id in batch])
            await self.vectorstore.upsert_points(
                [(point_id, vector, wanted[point_id][1]) for point_id, vector in zip(batch, vectors)]
            )
        return {"points": len(wanted), "added": len(missing), "removed": len(stale)}

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
                    "date_entered": report.date_entered,
                    "authors": [author.strip() for author in (report.authors or "").split("//") if author.strip()],
                    "title": report.title,
                    "abstract": report.abstract,
                    "belongs_to_trial_id": bool(studies),
                    **VectorstoreService.database_payload(studies, study_databases),
                },
            )
        for category, kind in self.TAG_POINT_KINDS.items():
            for tag in await self.aspect_repo.get_all_tags(category, []):
                points[transform_to_uuid(tag.id, kind)] = (
                    tag.description or "",
                    {
                        "tree_ids": [category],
                        "source": "internal",
                        "source_id": str(tag.id),
                        "display_name": tag.description,
                        "is_report": False,
                    },
                )
        return points

    async def _embed(self, texts: List[str]) -> List[List[float]]:
        """The vectors of the texts; waits for the embedding service while it is still starting."""
        for attempt in range(self.EMBEDDING_ATTEMPTS):
            try:
                return await self.embedding_service.embed_many(texts)
            except Exception:
                if attempt == self.EMBEDDING_ATTEMPTS - 1:
                    raise
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


