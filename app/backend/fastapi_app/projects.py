
from fastapi import APIRouter, Request
from fastapi import Query, Path, UploadFile, File, HTTPException, Depends, BackgroundTasks, Body, Form
from fastapi.responses import Response, StreamingResponse
from typing import Dict, List, Any, Optional
import logging

from src.utils.ris_parser import parse_file, RisParseError
from src.utils.logger import setup_logging

from .auth import is_verified_api_call, is_admin, get_roles

from src.context import RequestContext
from .deps import get_context

from src.database.models import Project as DbProject

from src.background.wrapper import (
    run_process_report_background,
    run_start_automation_background,
)

from src.services.authorization import ProjectAccessDeniedError, check_project_access
from src.utils.dto import FilterMode, IntakeReportPage, Project, ProjectAssignee, ProjectDetails, ProjectReportPage, ProjectTask
from src.utils.pagination import InvalidCursorError

router = APIRouter(tags=["projects"])

setup_logging("events.log")
logger = logging.getLogger(__name__)

project_id_path = Path(..., description="The projects's id")


async def get_project_by_id(project_id: str, ctx: RequestContext = Depends(get_context)) -> DbProject:
    project = await ctx.project_repo.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project

async def require_project_access(
    project_id: str = project_id_path,
    ctx: RequestContext = Depends(get_context),
    roles: List[str] = Depends(get_roles),
) -> None:
    """FastAPI-facing wrapper around services.authorization.check_project_access -
    translates its plain exception into an HTTP response. The MCP server would call
    that function directly instead, since it isn't a FastAPI app.
    """
    if "APPROVED" not in roles:
        raise HTTPException(status_code=401, detail="Not allowed")
    try:
        await check_project_access(project_id, roles, ctx.project_repo)
    except ProjectAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

async def get_project_stats(
    project: DbProject = Depends(get_project_by_id),
    ctx: RequestContext = Depends(get_context),
) -> ProjectDetails:
    return await ctx.project_service.get_project_stats(project)


@router.get("/tasks",dependencies=[Depends(is_verified_api_call)], summary="Get pending review tasks for the authenticated user.", description="Returns all projects the user is assigned to along with their personal study-link counts.")
async def get_user_tasks(ctx: RequestContext = Depends(get_context)) -> List[ProjectTask]:
    return await ctx.project_service.get_user_tasks()

@router.post("/projects", dependencies=[Depends(is_admin)], summary="Upload a project (batch of new reports that need to be assigned to studies) (usually in the .ris file format)", status_code=201)
async def upload_file(background_tasks: BackgroundTasks, file: UploadFile = File(..., description="The .ris file containing all the articles you want to process."), projectName: str = Form(...), ctx: RequestContext = Depends(get_context)):

    try:
        entries = await parse_file(file)
    except RisParseError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    project_id, reports, trial_ids = ctx.project_service.build_reports_from_entries(entries)

    reports = await ctx.project_repo.add_new_project(project_id,projectName,reports,trial_ids)
    if reports is None:
        raise HTTPException(status_code=409, detail="Project already exists")
    # schedule background tasks
    #for report in reports:
    #    print("Report provcess appended")
    report_ids = [report.id for report in reports]
    background_tasks.add_task(run_process_report_background, project_id, report_ids, ctx.user_id)

    await ctx.pubsub_service.publish_project_update(project_id)

    #TODO disabled for legacy reasons
    #reports_dict = [report.dict() for report in reports]
    #JSONResponse(content={"project_id": project_id, "project_description": file.filename, "reports": reports_dict}, status_code=201)

    return Response(status_code=201)

@router.get("/projects", dependencies=[Depends(is_admin)], summary="Get an overview of all current projects.", description="For each project the current progress of embedding calculation and the number of already assigned reports is returned")
async def get_available_projects(ctx: RequestContext = Depends(get_context)) -> List[ProjectDetails]:
    return await ctx.project_service.get_all_project_stats()

@router.get("/projects/{project_id}", dependencies=[Depends(is_admin)], summary="Get a specific project by id.",description="Returns details and progress information for a single project identified by project id.")
async def get_project_stats_by_id(project_stats : Project = Depends(get_project_stats)) -> Project:
    return project_stats

@router.delete("/projects/{project_id}", dependencies=[Depends(is_admin)], summary="Delete a project and all its associated reports (including calculated embedding vectors) from the temporary storage.", status_code=204)
async def delete_project(project_id : str, ctx: RequestContext = Depends(get_context)):
    #Deletes the project and through cascade and triggers everythig related to it
    project = await ctx.project_repo.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    report_ids = await ctx.project_repo.get_project_associated_report_ids(project_id)

    await ctx.project_repo.delete_project(project_id)

    await ctx.vectorstore_service.delete_vectors_by_report_ids(report_ids)

    await ctx.pubsub_service.publish_project_update(project_id)

    return Response(status_code=204)

@router.post("/projects/{project_id}/assignees", dependencies=[Depends(is_admin)],summary="Assign a user to a project",status_code=201,)
async def assign_user_to_project(
    background_tasks: BackgroundTasks,
    project_id: str = project_id_path,
    assignee_user_id: str = Body(..., embed=False, description="User ID to assign"),
    model: str = Query("gpt-5-nano", description="LLM model name to use for study prediction"),
    ctx: RequestContext = Depends(get_context),
):
    try:
        project = await ctx.project_repo.get_project_by_id(project_id)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        created = await ctx.project_repo.add_project_assignee(project_id, assignee_user_id)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    if not created:
        raise HTTPException(status_code=409, detail="User already assigned to project")

    await ctx.pubsub_service.publish_project_update(project_id)

    if assignee_user_id == "bot":
        background_tasks.add_task(run_start_automation_background, project_id, ctx.user_id, model)

    return ProjectAssignee(userId=assignee_user_id, numberReportsLinked=0)

@router.delete("/projects/{project_id}/assignees/{user_id}", dependencies=[Depends(is_admin)],summary="Remove a user assignment from a project",status_code=204,)
async def remove_user_from_project(
    project_id: str = project_id_path,
    user_id: str = Path(..., description="The user ID to remove from the project"),
    ctx: RequestContext = Depends(get_context),
):
    try:
        project = await ctx.project_repo.get_project_by_id(project_id)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        removed = await ctx.project_repo.remove_project_assignee(project_id, user_id)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    if not removed:
        raise HTTPException(status_code=404, detail="User is not assigned to this project")

    await ctx.pubsub_service.publish_project_update(project_id)

    return Response(status_code=204)

_search_query = Query(None, description="Filter reports by title, abstract or report id (case-insensitive substring match).")
_cursor_query = Query(None, description="Opaque cursor from a previous response's nextCursor; omit to fetch the first page.")
_limit_query = Query(50, ge=1, le=200, description="Maximum number of reports to return in this page.")


@router.get(
    "/projects/{project_id}/reports",
    dependencies=[Depends(require_project_access)],
    summary="Get all fully-processed reports in a project - the normal curation view.",
    description="Never returns reports that are still being processed (not yet embedded/PDF-ready); "
                "see /reports/intake for that. Available to project assignees, not just admins.",
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
) -> ProjectReportPage:
    try:
        return await ctx.project_service.get_reports_page(
            project_id,
            search=search,
            processed=processed,
            flagged=flagged,
            new_study=new_study,
            cursor=cursor,
            limit=limit,
        )
    except InvalidCursorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
) -> IntakeReportPage:
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
) -> ProjectReportPage:
    try:
        return await ctx.project_service.get_review_reports_page(
            project_id,
            search=search,
            consensus=consensus,
            reviewed=reviewed,
            cursor=cursor,
            limit=limit,
        )
    except InvalidCursorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@router.get( "/projects/{project_id}/annotations",dependencies=[Depends(is_admin)],summary="Get reports annotated by all assigned users in a project.")
async def get_project_annotations(project: DbProject = Depends(get_project_by_id), ctx: RequestContext = Depends(get_context)) -> Dict[int, Dict[str, List[Dict[str, Any]]]]:
    return await ctx.project_service.get_project_annotations(project.id)

@router.get("/projects/{project_id}/stream",dependencies=[], summary="Stream updated batch information.")
async def stream_project_updates(
    project_id: str,
    request: Request,
    ctx: RequestContext = Depends(get_context),
) -> StreamingResponse:
    async def event_stream():
        pubsub = await ctx.pubsub_service.subscribe_to_project(project_id)
        try:
            while True:
                if await request.is_disconnected():
                    break

                data = await ctx.pubsub_service.get_next_project_update(pubsub)
                yield f"data: {data}\n\n"
        finally:
            await ctx.pubsub_service.unsubscribe_from_project(project_id, pubsub)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
