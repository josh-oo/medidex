from ..database.repositories.report import ReportRepository
from .vectorstore import VectorstoreService
from .embedding import EmbeddingService
from datetime import datetime

from typing import Dict, Any

import asyncio

class MaintenanceService:
    def __init__(self, report_repo : ReportRepository, vectorstore : VectorstoreService):
        self.report_repo = report_repo
        self.vectorstore = vectorstore

    async def vectorstore_clean_up(self):
        all_report_ids_vectorstore, all_report_ids_db = await asyncio.gather(
            self.vectorstore.get_all_saved_report_ids(),
            self.report_repo.get_all_reports()
        )

        all_report_ids_vectorstore = set(all_report_ids_vectorstore)
        all_report_ids_db = set([item.CRGReportID for item in all_report_ids_db])

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


