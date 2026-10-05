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
from ..database.models import Report as DbReport, ReportAdded
from ..services.crawler import OpenAlexWork, normalize_doi
from .postprocessing import PostprocessingOptions, postprocessor_registry
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


async def process_report(
    reports: List[DbReport], project_id: str, ctx: RequestContext, options: Optional[PostprocessingOptions] = None
) -> None:
    """Auto-search + download each report's PDF and compute its embedding, then
    finalize the project once every report has settled. Postprocessors enabled by
    `options` (see postprocessing.py) run per report once both are done; they don't
    delay finalizing the project, but are awaited before this returns.
    """
    options = options or {}
    postprocessors = postprocessor_registry.enabled_for(options)
    for postprocessor in postprocessors:
        await postprocessor.prepare(project_id, [report.id for report in reports], options, ctx)

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

    postprocess_tasks: List[asyncio.Future] = []

    async def postprocess(report):
        async with AsyncSessionLocal() as session:
            write_ctx = RequestContext(db=session, user_id=ctx.user_id)
            if not await write_ctx.project_repo.get_project_by_id(project_id):  # project already deleted
                return
            for postprocessor in postprocessors:
                try:
                    await postprocessor.process(report.id, project_id, options, write_ctx)
                except Exception:
                    logger.exception("Postprocessing failed for report %s", report.id)
                    await session.rollback()
            await ctx.pubsub_service.publish_project_update(project_id)

    async def has_pdf_file(report) -> bool:
        async with AsyncSessionLocal() as session:
            current = await RequestContext(db=session, user_id=ctx.user_id).report_repo.get_report_by_id(report.id)
            return current is not None and (current.report_number or 0) > 0

    async def settle(report, client):
        await asyncio.gather(prepare_vectorstore(report), load_pdf(report, client))
        # Without a PDF the postprocessing waits (stays pending) until one is uploaded manually,
        # which triggers it (see run_pending_postprocessing).
        if postprocessors and await has_pdf_file(report):
            postprocess_tasks.append(asyncio.ensure_future(postprocess(report)))

    async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
        await asyncio.gather(*(settle(report, client) for report in reports))

        # Finalize with a new session
        async with AsyncSessionLocal() as session:
            finalize_ctx = RequestContext(db=session, user_id=ctx.user_id)
            await _finalize_project_upload(
                project_id, finalize_ctx.project_repo, ctx.vectorstore_service, ctx.maintenance_service, ctx.pubsub_service
            )

    await asyncio.gather(*postprocess_tasks)


async def run_process_report_background(
    project_id: str,
    report_ids: List[int],
    user_id: str,
    options: Optional[PostprocessingOptions] = None,
) -> None:
    async with AsyncSessionLocal() as db:
        ctx = RequestContext(db=db, user_id=user_id)

        reports: List[DbReport] = []
        for report_id in report_ids:
            report = await ctx.report_repo.get_report_by_id(report_id)
            if report is not None:
                reports.append(report)

        await process_report(reports, project_id, ctx, options)


async def run_pending_postprocessing(report_id: int, user_id: str) -> None:
    """Runs the postprocessors that are still pending for a report whose PDF was just
    uploaded manually (they wait for the PDF, see process_report)."""
    async with AsyncSessionLocal() as session:
        ctx = RequestContext(db=session, user_id=user_id)
        report_added = await session.get(ReportAdded, report_id)
        if report_added is None:
            return
        project_id = report_added.project_id
        for postprocessor in postprocessor_registry.all():
            pending_select = postprocessor.pending_report_ids()
            rows = await session.execute(pending_select.where(pending_select.selected_columns[0] == report_id))
            if rows.first() is None:
                continue
            try:
                # The upload options are not stored; postprocessors only rely on their own pending marker here.
                await postprocessor.process(report_id, project_id, {}, ctx)
            except Exception:
                logger.exception("Postprocessing failed for report %s", report_id)
                await session.rollback()
        await ctx.pubsub_service.publish_project_update(project_id)
