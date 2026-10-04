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
from typing import Dict, List, Optional, Tuple

import httpx

from ..context import RequestContext
from ..database.sessions import AsyncSessionLocal
from ..database.models import Report as DbReport
from ..services.crawler import OpenAlexWork, normalize_doi
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


async def _fetch_openalex_works(reports: List[DbReport], open_alex_service) -> Optional[Dict[str, OpenAlexWork]]:
    """One batched OpenAlex lookup (fulltext links + cited DOIs) for every report with a
    DOI, instead of one request per report. None means the lookup failed, which callers
    must tell apart from "OpenAlex doesn't know this DOI" (a missing key) so a transient
    failure isn't cached as "nothing found".
    """
    dois = [report.doi for report in reports if report.doi]
    if not dois:
        return {}
    try:
        return await open_alex_service.get_works_by_dois(dois)
    except Exception as exc:
        logger.warning("OpenAlex batch lookup failed for %d reports: %s", len(dois), exc)
        return None


async def _auto_search_report_pdf(
    client: httpx.AsyncClient, report: DbReport, works: Optional[Dict[str, OpenAlexWork]], crawler_service
) -> Tuple[Optional[_InMemoryPdfUpload], Optional[List[str]], Optional[List[str]]]:
    """Try to download one of a report's OpenAlex fulltext links (from the batched lookup
    in _fetch_openalex_works) as its PDF if it doesn't already have one. Returns
    (pdf, fulltext links, cited DOIs) for the caller to cache on report_added - see
    ProjectRepository.set_report_auto_searched_pdf. Links are returned even when a PDF
    already exists, since the report detail view wants them regardless of PDF status;
    both are None if the lookup failed (nothing to cache).
    """
    if report.report_number <= 0 and is_trial_registration(report.authors):
        # A bare trial registration has no DOI or published PDF - render its
        # registry record as the report's PDF instead.
        try:
            return _InMemoryPdfUpload(await crawler_service.get_pdf_for_trial_id(report.authors)), [], []
        except Exception as exc:
            logger.warning("Trial registry PDF failed for report %s: %s", report.id, exc)
            return None, [], []

    if not report.doi:
        return None, [], []
    if works is None:
        return None, None, None

    work = works.get(normalize_doi(report.doi), OpenAlexWork())
    links = work.pdf_links

    if report.report_number > 0:  # report already has a pdf, skip the download attempt
        return None, links, work.referenced_dois

    for link in links:
        payload = await _download_pdf_bytes(client, link)
        if payload is not None:
            return _InMemoryPdfUpload(payload), links, work.referenced_dois

    return None, links, work.referenced_dois


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

    openalex_works = asyncio.ensure_future(_fetch_openalex_works(reports, ctx.open_alex_service))

    async def load_pdf(report, client):
        works = await openalex_works
        async with _write_semaphore:
            async with AsyncSessionLocal() as write_session:
                write_ctx = RequestContext(db=write_session, user_id=ctx.user_id)
                project = await write_ctx.project_repo.get_project_by_id(project_id)
                if not project:  # project already deleted
                    return
                pdf_file, fulltext_links, referenced_dois = await _auto_search_report_pdf(client, report, works, write_ctx.crawler_service)
                if pdf_file:
                    await write_ctx.document_service.upload_pdf(report.id, pdf_file)
                await write_ctx.project_repo.set_report_auto_searched_pdf(
                    report.id, fulltext_links=fulltext_links, referenced_dois=referenced_dois
                )
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
