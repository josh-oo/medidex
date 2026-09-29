from fastapi import APIRouter, File, UploadFile
from fastapi import Depends, HTTPException, Query, Path
from fastapi.responses import FileResponse
from starlette.responses import Response
import enum
import logging

from typing import List, Optional
from datetime import datetime, timezone
from pydantic import BaseModel

from typing import List, Optional, Dict, Any

from .auth import is_verified_api_call, is_admin

from src.database.models import Report as DbReport, Study as DbStudy
from src.database.models import Participant as DbParticipant, Design as DbDesign

from src.database.repositories.study import DuplicateShortNameError
from src.utils.query_parser import QuerySyntaxError
from src.context import RequestContext
from .deps import get_context

from src.utils.dto import Study, StudyFull, StudyPayload, ReportPreview, ReportSources, Page, FlagPayload, Flag, Tag, tags_to_dto, studies_to_dto, reports_to_dto, reports_to_base_dto, report_flag_to_dto
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

"""
Study Endpoints
"""

@router.put("/studies", summary="Add new study to the database.")
async def add_study(study_params: StudyPayload, ctx: RequestContext = Depends(get_context)) -> Study:
    try:
        return await ctx.study_service.add_study(study_params)
    except DuplicateShortNameError:
        raise HTTPException(status_code=409, detail="Shortname already exists")

@router.get("/studies", summary="Get study details for all studies specified in the query.")
async def get_studies(study_ids: List[int] = study_ids_query, ctx: RequestContext = Depends(get_context)) -> List[Study]:
    return await ctx.study_service.get_studies(study_ids)

@router.get("/studies/search", summary="Search studies by name, trial ID, author or intervention - free-text, or advanced AND/OR field matching.")
async def search_studies(
    q: str = Query(..., min_length=3, description="Search text. In free-text mode (default), matched against study name, trial ID, author and intervention. In advanced mode, a boolean expression of field==value (or field=value) comparisons combined with AND/OR (AND binds tighter than OR) and optional parentheses, e.g. 'intervention==Drug A AND condition==Sick OR condition==Healthy'. Quote a value (\"...\" or '...') to include literal AND/OR/)/whitespace. Valid fields: name/shortName, trialId, author, status, country, intervention, condition, outcome, participant, design (plurals accepted too, e.g. conditions)."),
    advanced: bool = Query(False, description="Parse q as an advanced AND/OR field==value expression instead of a free-text search."),
    limit: int = Query(25, ge=1, le=100, description="Maximum number of results to return per page."),
    cursor: Optional[str] = Query(None, description="Opaque pagination cursor from a previous response's nextCursor. Omit for the first page."),
    ctx: RequestContext = Depends(get_context),
) -> Page[Study]:
    try:
        offset = decode_cursor(cursor) if cursor else 0
    except InvalidCursorError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if advanced:
        try:
            studies, has_more = await ctx.study_service.search_studies_advanced(q, limit, offset)
        except QuerySyntaxError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    else:
        studies, has_more = await ctx.study_service.search_studies(q, limit, offset)

    next_cursor = encode_cursor(offset + limit) if has_more else None
    return Page[Study](items=studies, nextCursor=next_cursor)

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

@router.get("/studies/{study_id}/interventions", summary="Get interventions for a specific study (e.g. 'Placebo', 'Group Therapy', ...), paginated.")
async def get_study_interventions_single(
    study_id: int = study_id_path,
    limit: int = Query(DEFAULT_PAGE_LIMIT, ge=1, le=100, description="Maximum number of results to return per page."),
    cursor: Optional[str] = Query(None, description="Opaque pagination cursor from a previous response's nextCursor. Omit for the first page."),
    ctx: RequestContext = Depends(get_context),
) -> Page[Tag]:
    offset = await _decode_cursor_or_400(cursor)
    result, has_more = await ctx.study_repo.get_study_interventions_single_page(study_id, limit=limit, offset=offset)
    next_cursor = encode_cursor(offset + limit) if has_more else None
    return Page[Tag](items=result, nextCursor=next_cursor)

@router.get("/studies/{study_id}/conditions", summary="Get the health conditions of participants in a specific study (e.g., 'COVID-19', 'Diabetes', ...), paginated.")
async def get_study_conditions_single(
    study_id: int = study_id_path,
    limit: int = Query(DEFAULT_PAGE_LIMIT, ge=1, le=100, description="Maximum number of results to return per page."),
    cursor: Optional[str] = Query(None, description="Opaque pagination cursor from a previous response's nextCursor. Omit for the first page."),
    ctx: RequestContext = Depends(get_context),
) -> Page[Tag]:
    offset = await _decode_cursor_or_400(cursor)
    result, has_more = await ctx.study_repo.get_study_conditions_single_page(study_id, limit=limit, offset=offset)
    next_cursor = encode_cursor(offset + limit) if has_more else None
    return Page[Tag](items=result, nextCursor=next_cursor)

@router.get("/studies/{study_id}/outcomes", summary="Get outcomes for a specific study (e.g. 'Mortality', 'Hospitalization', ...), paginated.")
async def get_study_outcomes_single(
    study_id: int = study_id_path,
    limit: int = Query(DEFAULT_PAGE_LIMIT, ge=1, le=100, description="Maximum number of results to return per page."),
    cursor: Optional[str] = Query(None, description="Opaque pagination cursor from a previous response's nextCursor. Omit for the first page."),
    ctx: RequestContext = Depends(get_context),
) -> Page[Tag]:
    offset = await _decode_cursor_or_400(cursor)
    result, has_more = await ctx.study_repo.get_study_outcomes_single_page(study_id, limit=limit, offset=offset)
    next_cursor = encode_cursor(offset + limit) if has_more else None
    return Page[Tag](items=result, nextCursor=next_cursor)

@router.get("/studies/{study_id}/participants", summary="Get participant description for a specific study (e.g. Male, Female, Adult, Child, ...), paginated.")
async def get_study_participants_single(
    study_id: int = study_id_path,
    limit: int = Query(DEFAULT_PAGE_LIMIT, ge=1, le=100, description="Maximum number of results to return per page."),
    cursor: Optional[str] = Query(None, description="Opaque pagination cursor from a previous response's nextCursor. Omit for the first page."),
    ctx: RequestContext = Depends(get_context),
) -> Page[Tag]:
    offset = await _decode_cursor_or_400(cursor)
    result, has_more = await ctx.study_repo.get_study_participants_single_page(study_id, limit=limit, offset=offset)
    next_cursor = encode_cursor(offset + limit) if has_more else None
    return Page[Tag](items=result, nextCursor=next_cursor)

@router.get("/studies/{study_id}/design", summary="Get the study design of the corresponding study ('Randomized Controlled Trial', 'Controlled Clinical Trial'), paginated.")
async def get_study_design_single(
    study_id: int = study_id_path,
    limit: int = Query(DEFAULT_PAGE_LIMIT, ge=1, le=100, description="Maximum number of results to return per page."),
    cursor: Optional[str] = Query(None, description="Opaque pagination cursor from a previous response's nextCursor. Omit for the first page."),
    ctx: RequestContext = Depends(get_context),
) -> Page[Tag]:
    offset = await _decode_cursor_or_400(cursor)
    result, has_more = await ctx.study_repo.get_study_design_single_page(study_id, limit=limit, offset=offset)
    next_cursor = encode_cursor(offset + limit) if has_more else None
    return Page[Tag](items=result, nextCursor=next_cursor)

@router.get("/studies/{study_id}/persons", summary="Get all persons (usually only authors) associated with a specific study")
async def get_study_persons_single(study_id : int = study_id_path, cutoff: str = cutoff_query, normalize_names : bool = Query(False), ctx: RequestContext = Depends(get_context)) -> List[str]:
    return await ctx.study_repo.get_study_persons_single(study_id=study_id, cutoff=cutoff, normalize_names=normalize_names)

@router.get("/studies/{study_id}", summary="Get full study details for a specific study, including its linked reports and aspects (each as a first page, paginated).")
async def get_study_by_id(
    study: DbStudy = Depends(get_study_by_id),
    limit: int = Query(DEFAULT_PAGE_LIMIT, ge=1, le=100, description="Maximum number of items per page for each nested list (reports, interventions, conditions, outcomes, participants, design). Page further through any one of them via its own /studies/{study_id}/* endpoint."),
    ctx: RequestContext = Depends(get_context),
) -> StudyFull:
    await post_report_event(-1, Event(event_type=f"study::{study.id}::visted", timestamp=datetime.now(timezone.utc).isoformat()), ctx)

    reports, reports_more = await ctx.study_repo.get_study_reports_by_study_id_page(study.id, limit=limit, offset=0)
    interventions, interventions_more = await ctx.study_repo.get_study_interventions_single_page(study.id, limit=limit, offset=0)
    conditions, conditions_more = await ctx.study_repo.get_study_conditions_single_page(study.id, limit=limit, offset=0)
    outcomes, outcomes_more = await ctx.study_repo.get_study_outcomes_single_page(study.id, limit=limit, offset=0)
    participants, participants_more = await ctx.study_repo.get_study_participants_single_page(study.id, limit=limit, offset=0)
    design, design_more = await ctx.study_repo.get_study_design_single_page(study.id, limit=limit, offset=0)

    next_cursor = encode_cursor(limit)
    study_dto = studies_to_dto([study])[0]
    return StudyFull(
        **study_dto.model_dump(),
        reports=Page[ReportPreview](items=reports_to_base_dto(reports), nextCursor=next_cursor if reports_more else None),
        interventions=Page[Tag](items=interventions, nextCursor=next_cursor if interventions_more else None),
        conditions=Page[Tag](items=conditions, nextCursor=next_cursor if conditions_more else None),
        outcomes=Page[Tag](items=outcomes, nextCursor=next_cursor if outcomes_more else None),
        participants=Page[Tag](items=participants, nextCursor=next_cursor if participants_more else None),
        design=Page[Tag](items=design, nextCursor=next_cursor if design_more else None),
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

@router.delete("/reports/{report_id}", status_code=204, summary="Delete a report. Only the owner of the report's project can delete it.")
async def delete_report(
    report_id: int = report_id_path,
    ctx: RequestContext = Depends(get_context),
):
    try:
        report = await ctx.report_repo.get_report_by_id(report_id)
        if report is None:
            raise HTTPException(status_code=404, detail=f"Report {report_id} not found")

        project_id = await ctx.project_repo.get_project_id_by_report_id(report_id)
        if project_id is None:
            raise HTTPException(status_code=400, detail="Report is not associated with a project")

        project = await ctx.project_repo.get_project_by_hash(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")

        if project.uploaded_by != str(ctx.user_id):
            raise HTTPException(status_code=403, detail="Only the project owner can delete reports from this project")

        deleted = await ctx.report_repo.delete_report(report_id)
        await ctx.report_repo.commit()
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Report {report_id} not found")

        await ctx.vectorstore_service.delete_vectors_by_report_ids([report_id])
        await ctx.pubsub_service.publish_project_update(project_id)
        return Response(status_code=204)
    except:
        await ctx.report_repo.rollback()
        raise


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
async def uploaed_pdf(report_id: int = report_id_path, file: UploadFile = File(None, description="PDF file to upload"), ctx: RequestContext = Depends(get_context)) -> Dict[str, Any]:
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
        return await ctx.document_service.delete_pdf(report_id)
    except Exception as e:
        if str(e) == "Report not found":
            raise HTTPException(status_code=404, detail=f"Report {report_id} not found")
        raise HTTPException(status_code=500, detail="Failed to delete PDF.")

@router.get("/reports/{report_id}/fulltext", summary="Get the parsed fulltext for a given report")
async def get_fulltext(report_id: int = report_id_path, ctx: RequestContext = Depends(get_context)) -> str:
    try:
        return await ctx.document_service.get_fulltext(report_id, fast=False)
    except Exception as e:
        if str(e) == "Upstream request timed out":
            raise HTTPException(status_code=504, detail="Upstream request timed out.")

@router.get("/reports/{report_id}/metadata", summary="Get pdf metadata.")
async def get_pdf_metadata(report_id: int = report_id_path, ctx: RequestContext = Depends(get_context)) -> Dict:
    return await ctx.report_service.get_metadata(report_id)

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

@router.get("/participants/by_studies", summary="Get participant attributes grouped by studies.", include_in_schema=False)
async def get_study_participants(study_ids: List[int] = study_ids_query, ctx: RequestContext = Depends(get_context)) -> Dict[int, List[Tag]]:
    return await ctx.study_repo.get_study_participants(study_ids)

@router.get("/participants", summary="Get all participant attributes or filter them by id.", include_in_schema=False)
async def get_all_participants(ids: List[int] = Query(None,description="If you are only interested in specific participant attributes. Leave this blank for retrieving all participant attributes."), ctx: RequestContext = Depends(get_context)) -> List[DbParticipant]:
    return await ctx.aspect_repo.get_all_participants(ids)

@router.get("/design/by_studies", summary="Get study designs grouped by studies.", include_in_schema=False)
async def get_study_design(study_ids: List[int] = study_ids_query, ctx: RequestContext = Depends(get_context)) -> Dict[int, List[Tag]]:
    return await ctx.study_repo.get_study_design(study_ids)

@router.get("/design", summary="Get all study design items or filter them by id.", include_in_schema=False)
async def get_all_design(ids: List[int] = Query(None,description="If you are only interested in specific design items. Leave this blank for retrieving all design items."), ctx: RequestContext = Depends(get_context)) -> List[DbDesign]:
    return await ctx.aspect_repo.get_all_designs(ids)

@router.get("/interventions/by_studies", summary="Get interventions grouped by studies.")
async def get_study_interventions(study_ids: List[int] = study_ids_query, ctx: RequestContext = Depends(get_context)) -> Dict[int, List[Tag]]:
    return await ctx.study_repo.get_study_interventions(study_ids)

@router.get("/interventions", summary="Get all intervention items or filter them by id.", response_model_exclude_none=True)
async def get_all_interventions(ids: List[int] = Query(None,description="If you are only interested in specific interventions. Leave this blank for retrieving all interventions."), ctx: RequestContext = Depends(get_context)) -> List[Tag]:
    result = await ctx.aspect_repo.get_all_interventions(ids)
    return tags_to_dto(result)

@router.get("/conditions/by_studies", summary="Get conditions grouped by studies.")
async def get_study_conditions(study_ids: List[int] = study_ids_query, ctx: RequestContext = Depends(get_context)) -> Dict[int, List[Tag]]:
    return await ctx.study_repo.get_study_conditions(study_ids)

@router.get("/conditions", summary="Get all condition items or filter them by id.", description="Conditions might be for example 'Diabetes', 'Schizophrenia', ... ", response_model_exclude_none=True)
async def get_all_conditions(ids: List[int] = Query(None, description="If you are only interested in specific conditions. Leave this blank for retrieving all conditions."), ctx: RequestContext = Depends(get_context)) -> List[Tag]:
    result = await ctx.aspect_repo.get_all_conditions(ids)
    return tags_to_dto(result)

@router.get("/outcomes/by_studies", summary="Get outcomes grouped by studies.")
async def get_study_outcomes(study_ids: List[int] = study_ids_query, ctx: RequestContext = Depends(get_context)) -> Dict[int, List[Tag]]:
    return await ctx.study_repo.get_study_outcomes(study_ids)

@router.get("/outcomes", summary="Get all study outcome items or filter them by id.", description="Outcomes might be for example 'Mortality', 'Quality of Life', etc. These items are linked to studies.", response_model_exclude_none=True)
async def get_all_outcomes(ids: List[int] = Query(None,description="If you are only interested in specific outcomes. Leave this blank for retrieving all outcomes."), ctx: RequestContext = Depends(get_context)) -> List[Tag]:
    result = await ctx.aspect_repo.get_all_outcomes(ids)
    return tags_to_dto(result)

@router.get("/countries", summary="Get all study countries or filter them by prefix.")
async def get_all_countries(prefix: Optional[str] = Query(None, description="Filter countries by prefix (case-insensitive)."), ctx: RequestContext = Depends(get_context)) -> List[str]:
    return await ctx.aspect_repo.get_all_countries(prefix)

"""
Other Endpoints
"""

@router.get("/trial/studies", include_in_schema=False)
async def get_possible_trial_ids_by_report(ctx: RequestContext = Depends(get_context)):
    return await ctx.study_repo.get_all_studies_connected_to_trial_id()
