from fastapi import APIRouter, File, UploadFile
from fastapi import BackgroundTasks, Depends, HTTPException, Query, Path
from src.background.wrapper import reset_pdf_postprocessing, run_pending_postprocessing
from fastapi.responses import FileResponse
from starlette.responses import Response
import enum
import logging

from typing import List, Optional, Union
from datetime import datetime, timezone
from pydantic import BaseModel

from typing import List, Optional, Dict, Any

from .auth import is_verified_api_call, is_admin

from src.database.models import Report as DbReport, Study as DbStudy

from src.database.repositories.study import DuplicateShortNameError
from src.utils.query_parser import QuerySyntaxError, SEARCH_QUERY_DESCRIPTION
from src.context import RequestContext
from src.services.authorization import ProjectAccessDeniedError
from src.services.project import ProjectNotFoundError
from .deps import get_context

from src.utils.dto import Study, StudyFull, StudySchema, StudyFieldSchema, StudyMetaSchema, StudyGraph, GraphSchema, GraphEntitySchema, GraphRelationSchema, TagCategorySchema, StudyPayload, ReportPreview, ReportSources, Page, FlagPayload, Flag, Tag, tags_to_dto, studies_to_dto, reports_to_dto, reports_to_base_dto, report_flag_to_dto
from src.database.tagstorage import TAG_TABLES
from src.utils.studyconfig import STUDY_CONFIG
from src.utils.tagconfig import TAG_CATEGORIES
from src.utils.pagination import encode_cursor, decode_cursor, InvalidCursorError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["resources"], dependencies=[Depends(is_verified_api_call)])

class Event(BaseModel):
    timestamp: str
    event_type: str

    class Config:
        json_schema_extra = {
            "example": {
                "timestamp": "2025-12-13T10:30:00Z",
                "event_type": "start"
            }
        }

DEFAULT_PAGE_LIMIT = 10

cutoff_query = Query(None, description="Cutoff date: for example '2025-01-13 00:00:00' (do not retrieve items entered after that date). Usually only used for testing")
study_ids_query =  Query(None, description="List of study IDs (used to filter your results)")
study_id_path = Path(..., description="Study ID")
report_ids_query = Query(None, description="List of ReportIDs (used to filter your results)")
report_id_path = Path(..., description="ReportID")
databases_query = Query([], description="Search only: the ids of the study databases to search in; all of them if omitted.")

"""
Study Endpoints
"""

async def _search_studies_or_400(ctx: RequestContext, q: str, limit: int, cursor: Optional[str], databases: Optional[List[int]] = None) -> Page[Study]:
    try:
        return await ctx.study_service.search_studies_page(q, limit, cursor, databases)
    except (InvalidCursorError, QuerySyntaxError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@router.put("/studies", summary="Add new study to a study database.")
async def add_study(
    study_params: StudyPayload,
    databaseId: int = Query(..., description="The study database the study belongs to."),
    ctx: RequestContext = Depends(get_context),
) -> Study:
    if await ctx.database_repo.get_database(databaseId) is None:
        raise HTTPException(status_code=404, detail=f"Database {databaseId} not found")
    try:
        return await ctx.study_service.add_study(study_params, databaseId)
    except DuplicateShortNameError:
        raise HTTPException(status_code=409, detail="Shortname already exists")

@router.get("/studies", summary="Get study details for all studies specified in the query, or - if `q` is given - search studies by name, trial ID, author or intervention (free-text, or advanced AND/OR field matching).")
async def get_studies(
    study_ids: List[int] = study_ids_query,
    q: Optional[str] = Query(None, min_length=3, description=SEARCH_QUERY_DESCRIPTION),
    limit: int = Query(25, ge=1, le=100, description="Search only: maximum number of results to return per page."),
    cursor: Optional[str] = Query(None, description="Search only: opaque pagination cursor from a previous response's nextCursor. Omit for the first page."),
    databases: List[int] = databases_query,
    ctx: RequestContext = Depends(get_context),
) -> Union[List[Study], Page[Study]]:
    if q is not None:
        return await _search_studies_or_400(ctx, q, limit, cursor, databases)
    return await ctx.study_service.get_studies(study_ids)

@router.get("/studies/search", summary="Search studies by name, trial ID, author or intervention - free-text, or advanced AND/OR field matching.")
async def search_studies(
    q: str = Query(..., min_length=3, description=SEARCH_QUERY_DESCRIPTION),
    limit: int = Query(25, ge=1, le=100, description="Maximum number of results to return per page."),
    cursor: Optional[str] = Query(None, description="Opaque pagination cursor from a previous response's nextCursor. Omit for the first page."),
    databases: List[int] = databases_query,
    ctx: RequestContext = Depends(get_context),
) -> Page[Study]:
    return await _search_studies_or_400(ctx, q, limit, cursor, databases)

@router.get("/studies/graphs", summary="The graph of config/medidex-study.yaml (the arms of a study and their comparisons) of the specified studies, with their tags named.")
async def get_study_graphs(study_ids: List[int] = study_ids_query, ctx: RequestContext = Depends(get_context)) -> Dict[int, StudyGraph]:
    if not study_ids:
        return {}
    studies = await ctx.study_repo.get_studies(study_ids)
    return await ctx.study_repo.get_graphs(studies)

@router.get("/studies/reports", include_in_schema=False)
async def get_study_reports_by_study_ids(study_ids: List[int] = study_ids_query, cutoff: str = cutoff_query, ctx: RequestContext = Depends(get_context)) -> Dict[int, List[DbReport]]:
    return await ctx.study_repo.get_study_reports_by_study_ids(study_ids, cutoff)

@router.get("/studies/persons", include_in_schema=False)
async def get_study_persons(study_ids: List[int] = study_ids_query, cutoff: str = cutoff_query, normalize_names : bool = Query(False), ctx: RequestContext = Depends(get_context)) -> Dict[int, List[str]]:
    return await ctx.study_repo.get_study_persons(study_ids, cutoff, normalize_names)

async def get_study_by_id(study_id: int = study_id_path, ctx: RequestContext = Depends(get_context)) -> DbStudy:
    study = await ctx.study_repo.get_study_by_id(study_id)
    if study is None:
        raise HTTPException(status_code=404, detail=f"Study {study_id} not found")
    return study

@router.get("/studies/{study_id}/reports", summary="Get reports (id + title only) already belonging to this study, paginated.")
async def get_study_reports_by_id(
    study_id: int = study_id_path,
    cutoff: str = cutoff_query,
    limit: int = Query(DEFAULT_PAGE_LIMIT, ge=1, le=100, description="Maximum number of results to return per page."),
    cursor: Optional[str] = Query(None, description="Opaque pagination cursor from a previous response's nextCursor. Omit for the first page."),
    ctx: RequestContext = Depends(get_context),
) -> Page[ReportPreview]:
    try:
        offset = decode_cursor(cursor) if cursor else 0
    except InvalidCursorError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    reports, has_more = await ctx.study_repo.get_study_reports_by_study_id_page(study_id, limit=limit, offset=offset, cutoff=cutoff)
    next_cursor = encode_cursor(offset + limit) if has_more else None
    return Page[ReportPreview](items=reports_to_base_dto(reports), nextCursor=next_cursor)


@router.get("/studies/{study_id}/date_entered", summary="Get the date when the study was entered into the database")
async def get_study_date_by_id(study_id: int = study_id_path, ctx: RequestContext = Depends(get_context)) -> str:
    result = await ctx.study_repo.get_study_date_by_id(study_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Study {study_id} not found")
    return result

async def _decode_cursor_or_400(cursor: Optional[str]) -> int:
    try:
        return decode_cursor(cursor) if cursor else 0
    except InvalidCursorError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@router.get("/studies/{study_id}/persons", summary="Get all persons (usually only authors) associated with a specific study")
async def get_study_persons_single(study_id : int = study_id_path, cutoff: str = cutoff_query, normalize_names : bool = Query(False), ctx: RequestContext = Depends(get_context)) -> List[str]:
    return await ctx.study_repo.get_study_persons_single(study_id=study_id, cutoff=cutoff, normalize_names=normalize_names)

_unknown = [key for key in (*STUDY_CONFIG.fields, *STUDY_CONFIG.meta) if key not in Study.model_fields]
if _unknown:
    raise RuntimeError(f"config/medidex-study.yaml names fields that a study does not have: {_unknown}")

@router.get("/study-schema", summary="What a study consists of and how it is presented: its primitive fields, its graph (entities such as arms and populations, and the relations between them), its tag categories (with icons and colors) and its database metadata, as configured in config/medidex-study.yaml.")
async def get_study_schema() -> StudySchema:
    return StudySchema(
        fields=[StudyFieldSchema(key=key, **field.model_dump()) for key, field in STUDY_CONFIG.fields.items()],
        meta=[StudyMetaSchema(key=key, **meta.model_dump()) for key, meta in STUDY_CONFIG.meta.items()],
        graph=GraphSchema(
            entities=[GraphEntitySchema(key=key, **entity.model_dump(exclude={"description"})) for key, entity in STUDY_CONFIG.graph.entities.items()],
            relations=[
                GraphRelationSchema(key=key, attribute=STUDY_CONFIG.graph.is_attribute(key), **relation.model_dump(exclude={"description"}))
                for key, relation in STUDY_CONFIG.graph.relations.items()
            ],
        ),
        tags=[
            TagCategorySchema(key=name, label=config.label, icon=config.icon, color=config.color, searchField=config.search_field, freeTextSearch=config.free_text_search, description=config.description)
            for name, config in TAG_CATEGORIES.categories.items()
        ],
    )

@router.get("/studies/{study_id}", summary="Get full study details for a specific study, including its linked reports and aspects (each as a first page, paginated).")
async def get_study_by_id(
    study: DbStudy = Depends(get_study_by_id),
    limit: int = Query(DEFAULT_PAGE_LIMIT, ge=1, le=100, description="Maximum number of items per page for each nested list (reports, interventions, conditions, outcomes, participants, design). Page further through any one of them via its own /studies/{study_id}/* endpoint."),
    ctx: RequestContext = Depends(get_context),
) -> StudyFull:
    await post_report_event(-1, Event(event_type=f"study::{study.id}::visted", timestamp=datetime.now(timezone.utc).isoformat()), ctx)

    reports, reports_more = await ctx.study_repo.get_study_reports_by_study_id_page(study.id, limit=limit, offset=0)
    tag_pages = {
        category: await ctx.study_repo.get_study_tags_single_page(category, study.id, limit=limit, offset=0)
        for category in TAG_CATEGORIES
    }

    next_cursor = encode_cursor(limit)
    study_dto = studies_to_dto([study])[0]
    graph = (await ctx.study_repo.get_graphs([study]))[study.id]
    return StudyFull(
        **study_dto.model_dump(),
        graph=graph,
        reports=Page[ReportPreview](items=reports_to_base_dto(reports), nextCursor=next_cursor if reports_more else None),
        tags={
            category: Page[Tag](items=items, nextCursor=next_cursor if has_more else None)
            for category, (items, has_more) in tag_pages.items()
        },
    )


"""
Report Endpoints
"""

@router.get("/reports", summary="Get all report details specified by id.")
async def get_all_reports(
    report_ids: List[int] = report_ids_query,
    date_from: Optional[str] = Query(None, description="Filter reports with Dateentered >= this ISO datetime (e.g. '2025-01-13 00:00:00')"),
    date_to: Optional[str] = Query(None, description="Filter reports with Dateentered <= this ISO datetime (e.g. '2025-01-31 23:59:59')"),
    ctx: RequestContext = Depends(get_context),
) -> List[DbReport]:
    return await ctx.report_repo.get_all_reports(report_ids, date_from, date_to)

@router.get("/reports/{report_id}", summary="Get full details for a specific report, including its DOI and OpenAlex fulltext links.")
async def get_report_by_id(report_id: int = report_id_path, ctx: RequestContext = Depends(get_context)) -> ReportSources:
    report = await ctx.report_repo.get_report_by_id(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")
    base = reports_to_dto([report])[0]
    links = await ctx.report_service.get_fulltext_links(report_id)
    return ReportSources(**base.model_dump(), doi=report.doi, fulltextLinks=links)

@router.delete("/reports/{report_id}", status_code=204, summary="Delete a report of an update. Only the owner of the update can delete it.", description="The report goes to the archive of the update only, never to the core database (see POST /reports/{report_id}/merge).")
async def delete_report(
    report_id: int = report_id_path,
    ctx: RequestContext = Depends(get_context),
):
    if await ctx.report_repo.get_report_by_id(report_id) is None:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")
    try:
        await ctx.merge_service.delete_report(report_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ProjectAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return Response(status_code=204)


@router.get("/reports/{report_id}/studies", summary="Get the studies linked to this specific report.")
async def get_report_studies_by_id(
    report_id: int = report_id_path,
    date_from: Optional[str] = Query(None, description="Filter studies with DateEntered >= this ISO datetime (e.g. '2025-01-13 00:00:00')"),
    date_to: Optional[str] = Query(None, description="Filter studies with DateEntered <= this ISO datetime (e.g. '2025-01-31 23:59:59')"),
    ctx: RequestContext = Depends(get_context),
) -> List[Study]:
    result = await ctx.report_repo.get_linked_studies(report_id, date_from, date_to)
    return studies_to_dto(result)

@router.put("/reports/{report_id}/pdf", dependencies=[Depends(is_admin)], summary="Upload the fulltext pdf for a given report", responses={200: {"description": "PDF file uploaded successfully"}})
async def uploaed_pdf(background_tasks: BackgroundTasks, report_id: int = report_id_path, file: UploadFile = File(None, description="PDF file to upload"), ctx: RequestContext = Depends(get_context)) -> Dict[str, Any]:
    # Validate file is a PDF
    if file:
        if not file.content_type == "application/pdf":
            raise HTTPException(status_code=400, detail="File must be a PDF")
        if not file.filename.endswith(".pdf"):
            raise HTTPException(status_code=400, detail="File must have .pdf extension.")

    try:
        result = await ctx.document_service.upload_pdf(report_id, file)
        await ctx.report_repo.db.commit()
        await ctx.pubsub_service.publish_report_update(report_id)
        # Postprocessing of a report without an auto-retrieved PDF waits for this upload.
        background_tasks.add_task(run_pending_postprocessing, report_id, ctx.user_id)
        return result
    except:
        await ctx.report_repo.db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to save PDF.")

@router.get("/reports/{report_id}/pdf", summary="Get the fulltext pdf for a given report", responses={200: {"description": "The PDF file of the report.","content": {"application/pdf": {"schema": {"type": "string","format": "binary"}}}}})
async def get_pdf(report_id : int, ctx: RequestContext = Depends(get_context)) -> FileResponse:
    try:
        pdf_path = await ctx.document_service.get_path(report_id)
        await post_report_event(-1, Event(event_type=f"report::{report_id}::downloaded", timestamp=datetime.now(timezone.utc).isoformat()), ctx)
        return FileResponse(pdf_path, media_type="application/pdf", filename=f"{report_id}.pdf")
    except:
        raise HTTPException(status_code=404, detail="PDF file not found.")

@router.delete("/reports/{report_id}/pdf", dependencies=[Depends(is_admin)], summary="Delete the fulltext pdf for a given report")
async def delete_pdf(report_id : int, ctx: RequestContext = Depends(get_context)) -> Dict[str, Any]:
    try:
        result = await ctx.document_service.delete_pdf(report_id)
        await ctx.report_repo.db.commit()
        await ctx.pubsub_service.publish_report_update(report_id)
    except Exception as e:
        await ctx.report_repo.db.rollback()
        if str(e) == "Report not found":
            raise HTTPException(status_code=404, detail=f"Report {report_id} not found")
        raise HTTPException(status_code=500, detail="Failed to delete PDF.")
    # Nothing made of the PDF outlives it (e.g. its parsed fulltext); the PDF is gone even if this fails.
    try:
        await reset_pdf_postprocessing(report_id, ctx)
    except Exception:
        logger.exception("Resetting the postprocessing of report %s failed", report_id)
        await ctx.report_repo.db.rollback()
        raise HTTPException(status_code=500, detail="The PDF was deleted, but not what was extracted from it.")
    return result

@router.get("/reports/{report_id}/flag", summary="Get your report flag for a specific report.")
async def get_report_flag(report_id: int = report_id_path, ctx: RequestContext = Depends(get_context)) -> Optional[Flag]:
    report = await ctx.report_repo.get_report_by_id(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")

    flag = await ctx.report_repo.get_report_flag(report_id)
    if flag is None:
        return None

    return report_flag_to_dto(flag)

@router.put("/reports/{report_id}/flag", summary="Create or edit your report flag for a specific report.")
async def upsert_report_flag(
    payload: FlagPayload,
    report_id: int = report_id_path,
    ctx: RequestContext = Depends(get_context),
) -> Flag:
    try:
        flag = await ctx.report_repo.upsert_report_flag(
            report_id=report_id,
            message=payload.message,
            public=payload.public,
        )
        await ctx.report_repo.commit()
        return report_flag_to_dto(flag)
    except:
        await ctx.report_repo.rollback()
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")

@router.delete("/reports/{report_id}/flag", status_code=204, summary="Delete your report flag for a specific report.")
async def delete_report_flag(report_id: int = report_id_path, ctx: RequestContext = Depends(get_context)):
    report = await ctx.report_repo.get_report_by_id(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")

    try:
        await ctx.report_repo.delete_report_flag(report_id)
        await ctx.report_repo.commit()
    except:
        await ctx.report_repo.rollback()
        raise HTTPException(status_code=501, detail=f"Failed delting report flag")

async def post_report_event(report_id : int, event: Event, ctx: RequestContext = Depends(get_context)):
    """Log a report-related UI event. Used internally (e.g. study-visited, pdf-downloaded)
    - not exposed as its own route anymore, event tracking now goes through server-side
    logging at the point of interest instead of a client-called endpoint."""
    if report_id != -1 and await ctx.report_repo.get_report_by_id(report_id) is None:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")

    user_id = ctx.user_id or "anonymous"
    payload = {"user": user_id, "event_type": event.event_type, "report_id": report_id, "original_timestamp": event.timestamp}
    logger.info("ReportInteraction", extra={"payload": payload})

    return payload

"""
Aspect Endpoints
"""

def _register_tag_routes(category: str) -> None:
    """The endpoints of one tag category of config/medidex-study.yaml: all its tags and the tags of one study."""
    config = TAG_CATEGORIES[category]

    async def get_study_tags_single(
        study_id: int = study_id_path,
        limit: int = Query(DEFAULT_PAGE_LIMIT, ge=1, le=100, description="Maximum number of results to return per page."),
        cursor: Optional[str] = Query(None, description="Opaque pagination cursor from a previous response's nextCursor. Omit for the first page."),
        ctx: RequestContext = Depends(get_context),
    ) -> Page[Tag]:
        offset = await _decode_cursor_or_400(cursor)
        result, has_more = await ctx.study_repo.get_study_tags_single_page(category, study_id, limit=limit, offset=offset)
        next_cursor = encode_cursor(offset + limit) if has_more else None
        return Page[Tag](items=result, nextCursor=next_cursor)

    async def get_all_tags(
        ids: List[int] = Query(None, description=f"If you are only interested in specific {category}. Leave this blank for retrieving all {category}."),
        databases: List[int] = Query([], description=f"Only the {category} of studies of these study databases; the whole vocabulary if omitted."),
        ctx: RequestContext = Depends(get_context),
    ) -> List[Tag]:
        return tags_to_dto(await ctx.aspect_repo.get_all_tags(category, ids, databases))

    router.add_api_route(f"/studies/{{study_id}}/{category}", get_study_tags_single, methods=["GET"], name=f"get_study_{category}_single",
                         summary=f"Get the {config.description[0].lower()}{config.description[1:]}, paginated.")
    if category not in TAG_TABLES:
        return  # tags kept in a column of the study (countries): listed by their own endpoint
    router.add_api_route(f"/{category}", get_all_tags, methods=["GET"], name=f"get_all_{category}", response_model_exclude_none=True,
                         summary=f"Get all {category} or filter them by id.", description=config.description)

for _category in TAG_CATEGORIES:
    _register_tag_routes(_category)

@router.get("/countries", summary="Get all study countries or filter them by prefix.")
async def get_all_countries(
    prefix: Optional[str] = Query(None, description="Filter countries by prefix (case-insensitive)."),
    databases: List[int] = Query([], description="Only the countries of studies of these study databases; all if omitted."),
    ctx: RequestContext = Depends(get_context),
) -> List[str]:
    return await ctx.aspect_repo.get_all_countries(prefix, databases)

"""
Other Endpoints
"""

@router.get("/trial/studies", include_in_schema=False)
async def get_possible_trial_ids_by_report(ctx: RequestContext = Depends(get_context)):
    return await ctx.study_repo.get_all_studies_connected_to_trial_id()
