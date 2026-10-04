"""Background jobs kicked off after a request/tool call already returned its
response: each opens its own DB session(s) via AsyncSessionLocal rather than
reusing the caller's (which closes once the request/tool call itself
returns). Framework-agnostic on purpose - both fastapi_app (via Starlette's
BackgroundTasks) and mcp_server (via a bare asyncio.create_task) schedule
these as fire-and-forget, without either needing to know how the other does
it.
"""

import asyncio
import io
import logging
from typing import List, Optional, Tuple

import httpx

from ..context import RequestContext
from ..database.sessions import AsyncSessionLocal
from ..database.models import Report as DbReport
from ..utils.trial_registration_id import is_trial_registration

logger = logging.getLogger(__name__)

# Bounds concurrent PDF-upload writes / vectorstore work across a project's
# reports; per-process, so shared across every project being processed at once.
_write_semaphore = asyncio.Semaphore(1)
_vectorstore_semaphore = asyncio.Semaphore(8)


class _InMemoryPdfUpload:
    """Duck-typed stand-in for an uploaded PDF file (mirrors
    src/utils/ris_parser.py's UploadedFile protocol), used to hand an
    auto-downloaded PDF to DocumentService.upload_pdf() the same way a real
    upload would.
    """

    def __init__(self, content: bytes, filename: str = "autosearch.pdf"):
        self._buffer = io.BytesIO(content)
        self.filename = filename
        self.content_type = "application/pdf"

    async def read(self) -> bytes:
        self._buffer.seek(0)
        return self._buffer.read()


def _looks_like_pdf(content: bytes, content_type: str) -> bool:
    if not content:
        return False
    if content.startswith(b"%PDF-"):
        return True
    return "application/pdf" in (content_type or "").lower()


async def _download_pdf_bytes(client: httpx.AsyncClient, url: str) -> Optional[bytes]:
    try:
        response = await client.get(url)
        response.raise_for_status()
    except Exception:
        return None

    payload = response.content
    if _looks_like_pdf(payload, response.headers.get("content-type", "")):
        return payload
    return None


async def _auto_search_report_pdf(client: httpx.AsyncClient, report: DbReport, open_alex_service, crawler_service) -> Tuple[Optional[_InMemoryPdfUpload], List[str]]:
    """Look up a report's OpenAlex fulltext links by DOI, and try to download one as
    the report's PDF if it doesn't already have one. Links are looked up (and
    returned for the caller to cache on report_added.fulltext_links - see
    ProjectRepository.set_report_auto_searched_pdf) even when a PDF already exists,
    since the report detail view wants them regardless of PDF status.
    """
    if report.report_number <= 0 and is_trial_registration(report.authors):
        # A bare trial registration has no DOI or published PDF - render its
        # registry record as the report's PDF instead.
        try:
            return _InMemoryPdfUpload(await crawler_service.get_pdf_for_trial_id(report.authors)), []
        except Exception as exc:
            logger.warning("Trial registry PDF failed for report %s: %s", report.id, exc)
            return None, []

    if not report.doi:
        return None, []

    try:
        links = list(await open_alex_service.get_pdf_links_by_doi(report.doi))
    except Exception as exc:
        logger.warning("OpenAlex lookup failed for report %s: %s", report.id, exc)
        return None, []

    if report.report_number > 0:  # report already has a pdf, skip the download attempt
        return None, links

    for link in links:
        payload = await _download_pdf_bytes(client, link)
        if payload is not None:
            return _InMemoryPdfUpload(payload), links

    return None, links


async def _finalize_project_upload(project_id: str, project_repo, vectorstore, maintenance_service, pubsub_service) -> None:
    """Once every report's PDF search and vectorstore embedding has settled,
    compute pairwise similarity scores for the project and notify subscribers
    that it's ready to review.
    """
    report_ids = await project_repo.get_project_associated_report_ids(project_id)
    if not report_ids:
        # Project not available (e.g. deleted mid-processing)
        await maintenance_service.vectorstore_clean_up()
        return

    score_pairs = await vectorstore.calculate_score_pairs(report_ids)
    await project_repo.insert_project_scores(score_pairs)
    await pubsub_service.publish_project_update(project_id)


async def process_report(reports: List[DbReport], project_id: str, ctx: RequestContext) -> None:
    """Auto-search + download each report's PDF and compute its embedding, then
    finalize the project once every report has settled.
    """
    timeout = httpx.Timeout(30.0, connect=10.0)

    async def load_pdf(report, client):
        async with _write_semaphore:
            async with AsyncSessionLocal() as write_session:
                write_ctx = RequestContext(db=write_session, user_id=ctx.user_id)
                project = await write_ctx.project_repo.get_project_by_id(project_id)
                if not project:  # project already deleted
                    return
                pdf_file, fulltext_links = await _auto_search_report_pdf(client, report, write_ctx.open_alex_service, write_ctx.crawler_service)
                if pdf_file:
                    await write_ctx.document_service.upload_pdf(report.id, pdf_file)
                await write_ctx.project_repo.set_report_auto_searched_pdf(report.id, fulltext_links=fulltext_links)
                await write_session.commit()
                await ctx.pubsub_service.publish_project_update(project_id)

    async def prepare_vectorstore(report):
        async with _vectorstore_semaphore:
            async with AsyncSessionLocal() as session:
                write_ctx = RequestContext(db=session, user_id=ctx.user_id)
                project = await write_ctx.project_repo.get_project_by_id(project_id)
                if not project:  # project already deleted
                    return
                await ctx.vectorstore_service.add_report_to_vectorstore(report)
                # Keep report_added.embedded in sync (see its comment in models.py) -
                # written through this call's own session/write_ctx, not the outer
                # request-scoped ctx, since several of these run concurrently via
                # asyncio.gather() below and a single AsyncSession isn't safe to share
                # across concurrently-running coroutines.
                await write_ctx.report_repo.set_embedded(report.id, True)
                await session.commit()
                await ctx.pubsub_service.publish_project_update(project_id)

    async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
        await asyncio.gather(
            *(prepare_vectorstore(report) for report in reports),
            *(load_pdf(report, client) for report in reports),
        )

        # Finalize with a new session
        async with AsyncSessionLocal() as session:
            finalize_ctx = RequestContext(db=session, user_id=ctx.user_id)
            await _finalize_project_upload(
                project_id, finalize_ctx.project_repo, ctx.vectorstore_service, ctx.maintenance_service, ctx.pubsub_service
            )


async def run_process_report_background(
    project_id: str,
    report_ids: List[int],
    user_id: str,
) -> None:
    async with AsyncSessionLocal() as db:
        ctx = RequestContext(db=db, user_id=user_id)

        reports: List[DbReport] = []
        for report_id in report_ids:
            report = await ctx.report_repo.get_report_by_id(report_id)
            if report is not None:
                reports.append(report)

        await process_report(reports, project_id, ctx)
