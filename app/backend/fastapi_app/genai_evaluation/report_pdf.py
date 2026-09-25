from __future__ import annotations

import asyncio
from pathlib import Path

from src.context import RequestContext
from src.database import AsyncSessionLocal

from .config import logger


async def _fetch_report_pdf(report_id: int) -> bytes | None:
    async with AsyncSessionLocal() as db:
        ctx = RequestContext(db=db, user_id=None)
        try:
            pdf_path = await ctx.document_service.get_path(report_id)
        except Exception as exc:
            logger.warning(
                "fetch_report_pdf: failed report_id=%s error=%s",
                report_id,
                exc,
            )
            return None
        return await asyncio.to_thread(Path(pdf_path).read_bytes)


def fetch_report_pdf(report_id: int) -> bytes | None:
    """Read a report's PDF straight from the shared domain layer.

    Was previously an HTTP call back into this same backend's own
    /reports/{id}/pdf endpoint (with its own BACKEND_API_URL/BACKEND_API_KEY
    config and retry logic) - a redundant network hop for a file already on
    this process's filesystem. This module runs from a sync FastAPI handler
    (see agent.py), which FastAPI already executes in a worker thread, so
    asyncio.run() here doesn't conflict with a running event loop.
    """
    return asyncio.run(_fetch_report_pdf(report_id))
