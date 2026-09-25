"""MCP resources for Medidex report PDFs.

Unlike tools.py's tools (structured data returned from a function call),
resources are addressed by URI and read their content on demand - the right
fit for a binary attachment like a PDF that a chatbot can fetch and hand to
the model, rather than a query result. Reuses the same DocumentService.get_path
logic as the REST API's GET /reports/{report_id}/pdf (src/api/resources.py)
and the same project-membership check as tools.py's get_report.
"""

import asyncio
from pathlib import Path

from fastapi import HTTPException

from mcp.server import MCPServer

from src.database.repositories.report import ReportRepository
from src.database.repositories.project import ProjectRepository
from src.services.report import DocumentService
from src.services.crawler import CrawlerService, DoclingService
from src.api.core import check_report_access

from .context import current_user_id, session_scope


def register(server: MCPServer) -> None:
    @server.resource(
        "medidex://reports/{report_id}/pdf",
        name="report-pdf",
        title="Report PDF",
        description="The full-text PDF for a report.",
        mime_type="application/pdf",
    )
    async def get_report_pdf(report_id: int) -> bytes:
        user_id = current_user_id()
        async with session_scope() as db:
            report_repo = ReportRepository(db=db, user_id=user_id)
            project_repo = ProjectRepository(db=db, user_id=user_id)
            try:
                await check_report_access(report_id, report_repo=report_repo, project_repo=project_repo, user_id=user_id)
            except HTTPException as exc:
                raise ValueError(exc.detail) from exc

            document_service = DocumentService(
                report_repo=report_repo,
                crawler_service=CrawlerService(),
                docling_service=DoclingService(),
            )
            try:
                pdf_path = await document_service.get_path(report_id)
            except Exception as exc:
                raise ValueError(f"PDF not found for report {report_id}") from exc

            return await asyncio.to_thread(Path(pdf_path).read_bytes)
