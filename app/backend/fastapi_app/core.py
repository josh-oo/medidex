from fastapi import APIRouter
from fastapi import Query, Path, HTTPException, Depends
from fastapi.responses import Response
from typing import List, Optional
import logging

from src.utils.logger import setup_logging

from .auth import is_verified_api_call, is_admin

from src.context import RequestContext
from .deps import get_context
from .errors import raise_for_report_access

from src.database.repositories.study import DuplicateShortNameError

from src.services.authorization import (
    ReportNotFoundError,
    AuthenticationRequiredError,
    ReportAccessDeniedError,
)
from src.services.aspects import TagCategories, UnsupportedAspectError
from src.services.core import ReportNotReadyError
from src.services.linkage import (
    ReportNotInProjectError,
    ReportProjectAccessError,
    ReportStudyLinkNotFoundError,
)

from src.utils.dto import StudyPayload, Study, StudyCandidate, TagCandidate, Page, studies_to_dto
from src.utils.pagination import InvalidCursorError
from src.utils.query_parser import QuerySyntaxError, SEARCH_QUERY_DESCRIPTION
from datetime import datetime

router = APIRouter(tags=["logic"])

setup_logging("events.log")
logger = logging.getLogger(__name__)

cutoff_query : Optional[datetime] = Query(None, description="Cutoff date: for example '2025-01-13 00:00:00' (do not retrieve items entered after that date). Usually only used for testing")
k_query : int = Query(10, description="Maximum number of returned results.")

@router.get("/reports/{report_id}/similar-tags", dependencies=[Depends(is_verified_api_call)], summary="Get related tags (interventions, outcomes, ...) for a specific report in a project based on its embedding vectors.")
async def similar_tags_by_report(report_id: int, tag_category: TagCategories =Query(TagCategories.default), sources: List[str] = Query(..., description="Which source of tags do you want to search ('mesh', 'internal' or both)"), k : int = k_query, ctx: RequestContext = Depends(get_context)) -> List[TagCandidate]:
    try:
        return await ctx.tag_similarity_service.get_similar_tags_by_id(report_id, tag_category, sources, k)
    except UnsupportedAspectError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@router.get("/{tag_category}/{tag_value}/similar-tags", dependencies=[Depends(is_verified_api_call)], summary="Get related tags (interventions, outcomes, ...) for a specific report in a project based on its embedding vectors.")
async def similar_tags(tag_category: TagCategories =Path(..., description="The tags category (e.g. 'interventions', 'conditions', ...)"), tag_value : str = Path(..., description="The specific tags value (e.g. 'Placebo' for interventions)"), sources: List[str] = Query(..., description="Which source of tags do you want to search ('mesh', 'internal' or both)"), k : int = k_query, ctx: RequestContext = Depends(get_context)) -> List[TagCandidate]:
    try:
        return await ctx.tag_similarity_service.get_similar_tags_by_string(tag_value, tag_category, sources, k)
    except UnsupportedAspectError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

async def _search_studies_with_relevance(ctx: RequestContext, report_id: int, q: str, limit: int, cursor: Optional[str]) -> Page[StudyCandidate]:
    try:
        page = await ctx.study_service.search_studies_page(q, limit, cursor)
    except (InvalidCursorError, QuerySyntaxError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        items = await ctx.study_similarity_service.add_relevance(report_id, page.items, ctx.user_id)
    except (ReportNotFoundError, AuthenticationRequiredError, ReportAccessDeniedError) as exc:
        raise_for_report_access(exc)
    return Page[StudyCandidate](items=items, nextCursor=page.nextCursor)

@router.get("/reports/{report_id}/similar-studies", dependencies=[Depends(is_verified_api_call)], summary="")
async def similarity_search_studies_by_id(
    report_id: int,
    cutoff: str = Query(None),
    limit: int = Query(10, ge=1, description="Maximum number of results to return per page."),
    cursor: Optional[str] = Query(None, description="Opaque pagination cursor from a previous response's nextCursor. Omit for the first page."),
    q: Optional[str] = Query(None, min_length=3, description="If given, searches studies instead of recommending them and returns the matches with their relevance for this report. cutoff only applies to the recommendation. " + SEARCH_QUERY_DESCRIPTION),
    ctx: RequestContext = Depends(get_context),
) -> Page[StudyCandidate]:
    if q is not None:
        return await _search_studies_with_relevance(ctx, report_id, q, limit, cursor)
    try:
        return await ctx.study_similarity_service.get_similar_studies_page(
            report_id,
            cutoff,
            limit,
            cursor,
            ctx.user_id,
        )
    except (ReportNotFoundError, AuthenticationRequiredError, ReportAccessDeniedError) as exc:
        raise_for_report_access(exc)
    except ReportNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except InvalidCursorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@router.get("/reports/{report_id}/referenced-studies", dependencies=[Depends(is_verified_api_call)], summary="Get the studies belonging to reports in the database whose DOI the given report cites (according to OpenAlex).")
async def referenced_studies_by_report(report_id: int, ctx: RequestContext = Depends(get_context)) -> List[StudyCandidate]:
    try:
        return await ctx.study_similarity_service.get_referenced_studies(report_id, ctx.user_id)
    except (ReportNotFoundError, AuthenticationRequiredError, ReportAccessDeniedError) as exc:
        raise_for_report_access(exc)

@router.get("/reports/{report_id}/similar-studies/tags", dependencies=[Depends(is_verified_api_call)], summary="")
async def search_related_tags(report_id: int, aspect: TagCategories = Query(TagCategories.interventions, description="The tag category which you are interested in"), cutoff: str = Query(None), k : int = Query(10, description="The number of related studies considered for retrieving relevant tags."), ctx: RequestContext = Depends(get_context)):
    try:
        return await ctx.related_tag_service.search_related_tags_by_report_id(report_id, aspect, k, cutoff, ctx.user_id)
    except (ReportNotFoundError, AuthenticationRequiredError, ReportAccessDeniedError) as exc:
        raise_for_report_access(exc)
    except UnsupportedAspectError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc

@router.put("/reports/{report_id}/studies/{study_id}", dependencies=[Depends(is_verified_api_call)], summary="Assign studies to a specific report in a project.", status_code=200)
async def assign_studies(
    report_id: int,
    study_id: int,
    ctx: RequestContext = Depends(get_context),
):
    try:
        await ctx.linkage_service.link_existing_study_to_report(report_id, study_id, ctx.user_id)
    except (ReportNotFoundError, AuthenticationRequiredError, ReportAccessDeniedError) as exc:
        raise_for_report_access(exc)

    payload = {"user": ctx.user_id, "event_type": "study::links::changed", "report_id": report_id, "original_timestamp": "-"}
    logger.info("ReportInteraction", extra={"payload": payload})

    return Response(content=None, status_code=200)

@router.delete("/reports/{report_id}/studies/{study_id}", dependencies=[Depends(is_verified_api_call)], summary="Remove assigned studies from a specific report.", status_code=200)
async def delete_assigned_studies(
    report_id: int,
    study_id: int,
    ctx: RequestContext = Depends(get_context),
):
    try:
        await ctx.linkage_service.unlink_study_from_report(report_id, study_id, ctx.user_id)
    except (ReportNotFoundError, AuthenticationRequiredError, ReportAccessDeniedError) as exc:
        raise_for_report_access(exc)

    payload = {"user": ctx.user_id, "event_type": "study::links::changed", "report_id": report_id, "original_timestamp": "-"}
    logger.info("ReportInteraction", extra={"payload": payload})

    return Response(content=None, status_code=200)

@router.post("/reports/{report_id}/studies", dependencies=[Depends(is_verified_api_call)], summary="Remove assigned studies from a specific report.", status_code=200)
async def link_to_new_study(
    report_id: int,
    study: StudyPayload,
    ctx: RequestContext = Depends(get_context),
) -> Study:
    try:
        new_study = await ctx.linkage_service.create_study_and_link_to_report(report_id, study, ctx.user_id)
    except (ReportNotFoundError, AuthenticationRequiredError, ReportAccessDeniedError) as exc:
        raise_for_report_access(exc)
    except DuplicateShortNameError:
        raise HTTPException(status_code=409, detail="Study shortName already exists")

    payload = {"user": ctx.user_id, "event_type": "study::links::changed::new", "report_id": report_id, "original_timestamp": "-"}
    logger.info("ReportInteraction", extra={"payload": payload})

    return studies_to_dto([new_study])[0]

@router.put("/reports/{report_id}/studies/{study_id}/confirmation", dependencies=[Depends(is_admin)], summary="After reviewing the annotations the admin uses this endpoint to confirm that the report belongs to the study.", status_code=200)
async def confirm_report_study_link(report_id : int, study_id: int, ctx: RequestContext = Depends(get_context)):
    try:
        await ctx.linkage_service.set_report_study_link_confirmation(report_id, study_id, True)
    except ReportNotInProjectError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ReportProjectAccessError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ReportStudyLinkNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    payload = {"user": ctx.user_id, "event_type": "study::links::confirmed", "report_id": report_id, "original_timestamp": "-"}
    logger.info("ReportInteraction", extra={"payload": payload})

    return Response(content=None, status_code=200)

@router.delete("/reports/{report_id}/studies/{study_id}/confirmation", dependencies=[Depends(is_admin)], summary="After reviewing the annotations the admin uses this endpoint to confirm that the report belongs to the study.", status_code=200)
async def unconfirm_report_study_link(report_id : int, study_id: int, ctx: RequestContext = Depends(get_context)):
    try:
        await ctx.linkage_service.set_report_study_link_confirmation(report_id, study_id, False)
    except ReportNotInProjectError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ReportProjectAccessError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ReportStudyLinkNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    payload = {"user": ctx.user_id, "event_type": "study::links::unconfirmed", "report_id": report_id, "original_timestamp": "-"}
    logger.info("ReportInteraction", extra={"payload": payload})

    return Response(content=None, status_code=200)
