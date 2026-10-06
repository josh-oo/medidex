
from fastapi import APIRouter, Request
from fastapi import Query, Path, UploadFile, File, HTTPException, Depends, BackgroundTasks, Body, Form
from fastapi.responses import Response, StreamingResponse
from typing import Dict, List, Any, Optional
import json
import logging

from src.utils.ris_parser import RisParseError
from src.utils.logger import setup_logging

from .auth import is_verified_api_call, is_admin
from .enrichment import report_enrichers

from src.context import RequestContext
from .deps import get_context

from src.background.wrapper import run_process_report_background

from src.services.authorization import ProjectAccessDeniedError
from src.services.project import (
    ProjectAssigneeAlreadyExistsError,
    ProjectAssigneeNotFoundError,
    ProjectNotFoundError,
)
from src.utils.dto import FilterMode, ReportIntake, Assignee, Project, ReportCuration, Task, Page
from src.utils.pagination import InvalidCursorError

router = APIRouter(tags=["projects"])

setup_logging("events.log")
logger = logging.getLogger(__name__)

project_id_path = Path(..., description="The projects's id")

@router.get("/tasks",dependencies=[Depends(is_verified_api_call)], summary="Get pending review tasks for the authenticated user.", description="Returns all projects the user is assigned to along with their personal study-link counts.")
async def get_user_tasks(ctx: RequestContext = Depends(get_context)) -> List[Task]:
    return await ctx.project_service.get_user_tasks()

@router.post("/projects", dependencies=[Depends(is_admin)], summary="Upload a project (batch of new reports that need to be assigned to studies) (usually in the .ris file format)", status_code=201)
async def upload_file(background_tasks: BackgroundTasks, file: UploadFile = File(..., description="The .ris file containing all the articles you want to process."), projectName: str = Form(...), options: str = Form("{}", description="JSON object of upload options; each registered report postprocessor reads its own keys (see src/background/postprocessing.py)."), ctx: RequestContext = Depends(get_context)) -> Project:

    # dependencies=[Depends(is_admin)] above is the actual (and only) admin check -
    # who's allowed to create a project is an API-layer permission, not a business
    # rule, so ProjectResourceService.create_project doesn't re-check it.
    try:
        parsed_options = json.loads(options)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="options must be a JSON object") from exc
    if not isinstance(parsed_options, dict):
        raise HTTPException(status_code=400, detail="options must be a JSON object")

    try:
        result = await ctx.project_service.create_project(projectName, file)
    except RisParseError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=409, detail="Project already exists")
    project, report_ids = result

    background_tasks.add_task(run_process_report_background, project.projectId, report_ids, ctx.user_id, parsed_options)

    return project

@router.get("/projects", dependencies=[Depends(is_admin)], summary="Get an overview of all current projects.", description="For each project the current progress of embedding calculation and the number of already assigned reports is returned")
async def get_available_projects(ctx: RequestContext = Depends(get_context)) -> List[Project]:
    return await ctx.project_service.get_all_project_stats()

@router.delete("/projects/{project_id}", dependencies=[Depends(is_admin)], summary="Delete a project and all its associated reports (including calculated embedding vectors) from the temporary storage.", status_code=204)
async def delete_project(project_id : str, ctx: RequestContext = Depends(get_context)):
    try:
        await ctx.project_service.delete_project(project_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return Response(status_code=204)

@router.post("/projects/{project_id}/assignees", dependencies=[Depends(is_admin)],summary="Assign a user to a project",status_code=201,)
async def assign_user_to_project(
    project_id: str = project_id_path,
    assignee_user_id: str = Body(..., embed=False, description="User ID to assign"),
    ctx: RequestContext = Depends(get_context),
) -> Assignee:
    try:
        assignee = await ctx.project_service.assign_user_to_project(project_id, assignee_user_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ProjectAssigneeAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    return assignee

@router.delete("/projects/{project_id}/assignees/{user_id}", dependencies=[Depends(is_admin)],summary="Remove a user assignment from a project",status_code=204,)
async def remove_user_from_project(
    project_id: str = project_id_path,
    user_id: str = Path(..., description="The user ID to remove from the project"),
    ctx: RequestContext = Depends(get_context),
):
    try:
        await ctx.project_service.remove_user_from_project(project_id, user_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ProjectAssigneeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    return Response(status_code=204)

_search_query = Query(None, description="Filter reports by title, abstract or report id (case-insensitive substring match).")
_cursor_query = Query(None, description="Opaque cursor from a previous response's nextCursor; omit to fetch the first page.")
_limit_query = Query(50, ge=1, le=200, description="Maximum number of reports to return in this page.")
_include_query = Query([], description="Keys of optional extension data to attach to each report's `extensions` (see fastapi_app/enrichment.py); omit for the plain response.")


@router.get(
    "/projects/{project_id}/reports",
    summary="Get all fully-processed reports in a project - the normal curation view.",
    description="Never returns reports that are still being processed (not yet embedded/PDF-ready); "
                "see /reports/intake for that. Restricted to project assignees.",
)
async def get_project_reports(
    project_id: str,
    ctx: RequestContext = Depends(get_context),
    search: Optional[str] = _search_query,
    processed: FilterMode = Query(FilterMode.any, description="Only/exclude reports that have at least one linked study."),
    flagged: FilterMode = Query(FilterMode.any, description="Only/exclude flagged reports."),
    new_study: FilterMode = Query(FilterMode.any, description="Only/exclude reports where a linked study was created after the report itself."),
    cursor: Optional[str] = _cursor_query,
    limit: int = _limit_query,
    include: List[str] = _include_query,
) -> Page[ReportCuration]:
    try:
        page = await ctx.project_service.get_reports_page(
            project_id,
            search=search,
            processed=processed,
            flagged=flagged,
            new_study=new_study,
            cursor=cursor,
            limit=limit,
        )
        return await report_enrichers.apply(page, include, ctx)
    except InvalidCursorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ProjectAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get(
    "/projects/{project_id}/reports/intake",
    dependencies=[Depends(is_admin)],
    summary="Get incoming reports for a project, including still-processing ones - the admin intake view.",
    description="Unlike /reports, always includes reports that have been auto-searched for a PDF but "
                "aren't fully processed yet, so an admin can watch reports as they arrive.",
)
async def get_project_reports_intake(
    project_id: str,
    ctx: RequestContext = Depends(get_context),
    search: Optional[str] = _search_query,
    with_pdf: FilterMode = Query(FilterMode.any, description="Only/exclude reports that have a PDF available."),
    cursor: Optional[str] = _cursor_query,
    limit: int = _limit_query,
) -> Page[ReportIntake]:
    try:
        return await ctx.project_service.get_intake_reports_page(
            project_id,
            search=search,
            with_pdf=with_pdf,
            cursor=cursor,
            limit=limit,
        )
    except InvalidCursorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/projects/{project_id}/reports/review",
    dependencies=[Depends(is_admin)],
    summary="Get fully-annotated reports for a project - the admin annotator-review view.",
    description="Always restricted to reports every project assignee has completed annotating, "
                "regardless of search/filter - this used to be a client-side pre-filter that only "
                "applied before any filter was touched.",
)
async def get_project_reports_review(
    project_id: str,
    ctx: RequestContext = Depends(get_context),
    search: Optional[str] = _search_query,
    consensus: FilterMode = Query(FilterMode.any, description="Only/exclude reports where annotators agree on the linked study."),
    reviewed: FilterMode = Query(FilterMode.any, description="Only/exclude reports where an annotator has confirmed their annotation."),
    cursor: Optional[str] = _cursor_query,
    limit: int = _limit_query,
    include: List[str] = _include_query,
) -> Page[ReportCuration]:
    try:
        page = await ctx.project_service.get_review_reports_page(
            project_id,
            search=search,
            consensus=consensus,
            reviewed=reviewed,
            cursor=cursor,
            limit=limit,
        )
        return await report_enrichers.apply(page, include, ctx)
    except InvalidCursorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@router.get( "/projects/{project_id}/annotations",dependencies=[Depends(is_admin)],summary="Get reports annotated by all assigned users in a project.")
async def get_project_annotations(project_id: str, ctx: RequestContext = Depends(get_context)) -> Dict[int, Dict[str, List[Dict[str, Any]]]]:
    return await ctx.project_service.get_project_annotations(project_id)

@router.get("/projects/{project_id}/stream", summary="Stream updated batch information.")
async def stream_project_updates(
    project_id: str,
    request: Request,
    ctx: RequestContext = Depends(get_context),
) -> StreamingResponse:
    try:
        await ctx.project_service.ensure_project_access(project_id)
    except ProjectAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    return StreamingResponse(
        ctx.project_service.stream_project_updates(project_id, request.is_disconnected),
        media_type="text/event-stream",
    )
