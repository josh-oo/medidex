from fastapi import APIRouter
from fastapi import Query, Path, HTTPException, Depends
from fastapi.responses import Response
from dotenv import load_dotenv
from typing import List, Optional, Tuple, Set
import os
import logging

from src.utils.logger import setup_logging

import asyncio

import enum
from .auth import is_verified_api_call, is_admin

from src.context import RequestContext
from .deps import get_context

from src.database.repositories.study import DuplicateShortNameError
from src.database import ReportRepository
from src.services.vectorstore import VectorstoreService

from src.services.authorization import (
    get_authorized_project_id,
    ReportNotFoundError,
    AuthenticationRequiredError,
    ReportAccessDeniedError,
)

from src.utils.dto import StudyCreate, Study, Tag, SimilarStudy, studies_to_dto, similar_studies_to_dto
from datetime import datetime

load_dotenv()

DEBUG = os.getenv("DEBUG", None) == "true"

setup_logging("events.log")
logger = logging.getLogger(__name__)

router = APIRouter(tags=["logic"])

cutoff_query : Optional[datetime] = Query(None, description="Cutoff date: for example '2025-01-13 00:00:00' (do not retrieve items entered after that date). Usually only used for testing")

k_query : int = Query(10, description="Maximum number of returned results.")

# Track background tasks to prevent resource leaks
background_tasks: set = set()

class TagCategories(str, enum.Enum):
    default = 'default'
    interventions = 'interventions'
    conditions = 'conditions'
    outcomes = 'outcomes'
    participants = 'participants'

async def get_vectorized_and_ready_report_ids(
    report_ids: List[int],
    report_repo: ReportRepository,
    vectorstore: VectorstoreService,
) -> Tuple[Set[int], Set[int], Set[int]]:
    if not report_ids:
        return set(), set(), set()

    reports_with_embedding, reports_with_pdf = await asyncio.gather(
        vectorstore.reports_exist(report_ids),
        report_repo.get_pdf_availabilities(report_ids),
    )
    embedded_reports = set(reports_with_embedding)
    pdf_ready_reports = set(reports_with_pdf)

    ready_report_ids =  embedded_reports & pdf_ready_reports
    return embedded_reports, pdf_ready_reports, ready_report_ids

async def check_report_access(
    report_id: int = Path(...),
    ctx: RequestContext = Depends(get_context),
) -> Optional[str]:
    """FastAPI-facing wrapper around services.authorization.get_authorized_project_id -
    translates its plain exceptions into HTTP responses. The MCP server calls
    that function directly instead (see mcp_server/context.py), since it isn't
    a FastAPI app and shouldn't depend on this router module.
    """
    try:
        return await get_authorized_project_id(report_id, ctx.report_repo, ctx.project_repo, ctx.user_id)
    except ReportNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except AuthenticationRequiredError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    except ReportAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))

@router.get("/reports/{report_id}/similar-tags", dependencies=[Depends(is_verified_api_call)], summary="Get related tags (interventions, outcomes, ...) for a specific report in a project based on its embedding vectors.")
async def similar_tags_by_report(report_id: int, tag_category: TagCategories =Query(TagCategories.default), sources: List[str] = Query(..., description="Which source of tags do you want to search ('mesh', 'internal' or both)"), k : int = k_query, ctx: RequestContext = Depends(get_context)) -> List[Tag]:
    if tag_category == TagCategories.default:
        raise HTTPException(status_code=400, detail="No tags for 'default' embedding.")
    return await ctx.tag_similarity_service.get_similar_tags_by_id(report_id, tag_category, sources, k)

@router.get("/{tag_category}/{tag_value}/similar-tags", dependencies=[Depends(is_verified_api_call)], summary="Get related tags (interventions, outcomes, ...) for a specific report in a project based on its embedding vectors.")
async def similar_tags(tag_category: TagCategories =Path(..., description="The tags category (e.g. 'interventions', 'conditions', ...)"), tag_value : str = Path(..., description="The specific tags value (e.g. 'Placebo' for interventions)"), sources: List[str] = Query(..., description="Which source of tags do you want to search ('mesh', 'internal' or both)"), k : int = k_query, ctx: RequestContext = Depends(get_context)) -> List[Tag]:
    if tag_category == TagCategories.default:
        raise HTTPException(status_code=400, detail="No tags for 'default' embedding.")
    return await ctx.tag_similarity_service.get_similar_tags_by_string(tag_value, tag_category, sources, k)

@router.get("/reports/{report_id}/similar-studies", dependencies=[Depends(is_verified_api_call), Depends(check_report_access)], summary="")
async def similarity_search_studies_by_id(
    report_id: int,
    cutoff: str = Query(None),
    k: int = Query(10),
    source: str = Query(None),
    negative_studies: List[int] = Query(None),
    negative_reports: List[int] = Query(None),
    return_details: bool = False,
    ctx: RequestContext = Depends(get_context),
) -> List[SimilarStudy]:
    _,_, ready_report_ids = await get_vectorized_and_ready_report_ids(
        [report_id], ctx.report_repo, ctx.vectorstore_service
    )
    if report_id not in ready_report_ids and not cutoff:
        raise HTTPException(status_code=409, detail="Report is not ready for processing")

    if source is not None:
        project_id = await ctx.project_repo.get_project_id_by_report_id(report_id)
        if project_id != source:
            raise HTTPException(status_code=404, detail="Report not found in project")

    result = await ctx.study_similarity_service.get_similar_studies_by_id(
        report_id,
        cutoff,
        k,
        negative_studies,
        negative_reports,
        return_details,
    )
    studies = similar_studies_to_dto(result)
    return studies

@router.get("/reports/{report_id}/similar-studies/tags", dependencies=[Depends(is_verified_api_call), Depends(check_report_access)], summary="")
async def search_related_tags(report_id: int, aspect: TagCategories = Query(TagCategories.interventions, description="The tag category which you are interested in"), cutoff: str = Query(None), k : int = Query(10, description="The number of related studies considered for retrieving relevant tags."), ctx: RequestContext = Depends(get_context)):
    if aspect not in [TagCategories.interventions, TagCategories.conditions, TagCategories.outcomes]:
         raise HTTPException(status_code=501, detail="Not implemented")
    return await ctx.related_tag_service.search_related_tags_by_report_id(report_id, aspect, k, cutoff)

@router.put("/reports/{report_id}/studies/{study_id}", dependencies=[Depends(is_verified_api_call), Depends(check_report_access)], summary="Assign studies to a specific report in a project.", status_code=200)
async def assign_studies(
    report_id: int,
    study_id: int,
    ctx: RequestContext = Depends(get_context),
    project_id: str = Depends(check_report_access),
):
    await ctx.linkage_service.link_existing_study_to_report(report_id, study_id, ctx.user_id)

    payload = {"user": ctx.user_id, "event_type": "study::links::changed", "report_id": report_id, "original_timestamp": "-"}
    logger.info("ReportInteraction", extra={"payload": payload})

    await ctx.pubsub_service.publish_project_update(project_id)

    return Response(content=None, status_code=200)

@router.delete("/reports/{report_id}/studies/{study_id}", dependencies=[Depends(is_verified_api_call), Depends(check_report_access)], summary="Remove assigned studies from a specific report.", status_code=200)
async def delete_assigned_studies(
    report_id: int,
    study_id: int,
    ctx: RequestContext = Depends(get_context),
    project_id: str = Depends(check_report_access),
):

    await ctx.linkage_service.unlink_study_from_report(report_id, study_id, ctx.user_id)

    payload = {"user": ctx.user_id, "event_type": "study::links::changed", "report_id": report_id, "original_timestamp": "-"}
    logger.info("ReportInteraction", extra={"payload": payload})

    await ctx.pubsub_service.publish_project_update(project_id)

    return Response(content=None, status_code=200)

@router.post("/reports/{report_id}/studies", dependencies=[Depends(is_verified_api_call)], summary="Remove assigned studies from a specific report.", status_code=200)
async def link_to_new_study(
    report_id: int,
    study: StudyCreate,
    ctx: RequestContext = Depends(get_context),
    project_id: str = Depends(check_report_access),
) -> Study:
    try:
        new_study = await ctx.linkage_service.create_study_and_link_to_report(report_id, study, ctx.user_id)

        payload = {"user": ctx.user_id, "event_type": "study::links::changed::new", "report_id": report_id, "original_timestamp": "-"}
        logger.info("ReportInteraction", extra={"payload": payload})

        study_dto = studies_to_dto([new_study])[0]

        await ctx.pubsub_service.publish_project_update(project_id)

        return study_dto
    except DuplicateShortNameError:
        raise HTTPException(status_code=409, detail="Study shortName already exists")

@router.put("/reports/{report_id}/studies/{study_id}/confirmation", dependencies=[Depends(is_admin)], summary="After reviewing the annotations the admin uses this endpoint to confirm that the report belongs to the study.", status_code=200)
async def confirm_report_study_link(report_id : int, study_id: int, ctx: RequestContext = Depends(get_context)):
    project_id = await ctx.project_repo.get_project_id_by_report_id(report_id)
    if not project_id:
        raise HTTPException(status_code=404, detail="Report not found in project")

    project = await ctx.project_repo.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=403, detail="You can only confirm links for reports in your own projects")

    try:
        updated = await ctx.report_repo.set_study_report_confirmation(report_id, study_id, True)
        await ctx.report_repo.commit()
        if not updated:
            raise HTTPException(status_code=404, detail="Tracked report-study link not found")
    except:
        await ctx.report_repo.rollback()

    payload = {"user": ctx.user_id, "event_type": "study::links::confirmed", "report_id": report_id, "original_timestamp": "-"}
    logger.info("ReportInteraction", extra={"payload": payload})

    return Response(content=None, status_code=200)

@router.delete("/reports/{report_id}/studies/{study_id}/confirmation", dependencies=[Depends(is_admin)], summary="After reviewing the annotations the admin uses this endpoint to confirm that the report belongs to the study.", status_code=200)
async def unconfirm_report_study_link(report_id : int, study_id: int, ctx: RequestContext = Depends(get_context)):
    project_id = await ctx.project_repo.get_project_id_by_report_id(report_id)
    if not project_id:
        raise HTTPException(status_code=404, detail="Report not found in project")

    project = await ctx.project_repo.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=403, detail="You can only confirm links for reports in your own projects")

    updated = await ctx.report_repo.set_study_report_confirmation(report_id, study_id, False)
    if not updated:
        raise HTTPException(status_code=404, detail="Tracked report-study link not found")

    payload = {"user": ctx.user_id, "event_type": "study::links::unconfirmed", "report_id": report_id, "original_timestamp": "-"}
    logger.info("ReportInteraction", extra={"payload": payload})

    return Response(content=None, status_code=200)
