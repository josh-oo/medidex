"""MCP resources for Medidex report PDFs.

Unlike tools.py's tools (structured data returned from a function call),
resources are addressed by URI and read their content on demand - the right
fit for a binary attachment like a PDF that a chatbot can fetch and hand to
the model, rather than a query result. Reuses the same DocumentService.get_path
logic as the REST API's GET /reports/{report_id}/pdf (fastapi_app/resources.py)
and the same project-membership check as tools.py's get_report.
"""

import asyncio
from pathlib import Path

from mcp.server import MCPServer

from .context import current_user_id, request_context, require_report_access


def register(server: MCPServer) -> None:
    @server.resource(
        "medidex://reports/{report_id}/pdf",
        name="report-pdf",
        title="Report PDF",
        description="The full-text PDF for a report.",
        mime_type="application/pdf",
    )
    async def get_report_pdf(report_id: int) -> bytes:
        async with request_context(current_user_id()) as ctx:
            await require_report_access(report_id, ctx)

            try:
                pdf_path = await ctx.document_service.get_path(report_id)
            except Exception as exc:
                raise ValueError(f"PDF not found for report {report_id}") from exc

            return await asyncio.to_thread(Path(pdf_path).read_bytes)
