
from fastapi import APIRouter, Request
from fastapi import Query, Path, UploadFile, File, HTTPException, Depends, BackgroundTasks, Body, Form
from fastapi.responses import Response, StreamingResponse
from typing import Dict, List, Any, Tuple, Set, Optional
from enum import Enum
import json
import logging

from src.utils.ris_parser import parse_file, RisParseError
from src.utils.logger import setup_logging

import asyncio

from .auth import is_verified_api_call, is_admin, get_roles

from src.context import RequestContext
from .deps import get_context

from src.database.repositories.study import DuplicateShortNameError

from src.database.models import Project as DbProject

from src.services.agent import AutomationService

from src.background.wrapper import (
    run_process_report_background,
    run_start_automation_background,
)

from src.utils.dto import Report, StudyCreate,BatchedReport, Project, ProjectAssignee, ProjectDetails, ProjectTask, studies_to_dto

router = APIRouter(tags=["projects"])

setup_logging("events.log")
logger = logging.getLogger(__name__)

# Limit concurrent bot processing across reports
agent_process_semaphore = asyncio.Semaphore(10)

project_id_path = Path(..., description="The projects's id")


async def _get_project_annotations(
    project_id: str, ctx: RequestContext
) -> Dict[int, Dict[str, List[Dict[str, Any]]]]:
    report_ids = await ctx.project_repo.get_project_associated_report_ids(project_id)
    if not report_ids:
        return {}

    assignees = await ctx.project_repo.get_project_assignees(project_id)
    assignee_ids = {user_id for user_id, _ in assignees if user_id}
    if not assignee_ids:
        return {}

    completion_map = await ctx.project_repo.get_report_completion_by_users(project_id)
    annotated_report_ids = [
        report_id
        for report_id in report_ids
        if assignee_ids.issubset(completion_map.get(report_id, set()))
    ]

    if not annotated_report_ids:
        return {}

    return await ctx.project_repo.get_project_annotations_by_assignees(
        project_id,
        assignee_ids,
        annotated_report_ids,
    )


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
    """Admins can view any project; everyone else must be an assignee of this one.

    Distinct from is_admin/is_verified_api_call: this is the one place that grants access
    based on per-project membership rather than a global role, so a normal user's own
    projects work without making every project world-readable to every approved user.
    """
    if "APPROVED" not in roles:
        raise HTTPException(status_code=401, detail="Not allowed")
    if "ADMIN" in roles:
        return
    if not await ctx.project_repo.is_project_assignee(project_id):
        raise HTTPException(status_code=403, detail="Not assigned to this project")

async def get_vectorized_and_ready_report_ids(project_id, ctx: RequestContext) -> Tuple[Set[int], Set[int], Set[int]]:
    return await ctx.project_service.get_vectorized_and_ready_report_ids(project_id)

async def get_project_report_status(project_id, ctx: RequestContext) -> Dict[int, Dict[str, bool]]:

    report_ids = await ctx.project_repo.get_project_associated_report_ids(project_id)
    if not report_ids:
        return {}

    embedded_reports, pdf_ready_reports, _ = await get_vectorized_and_ready_report_ids(project_id, ctx)

    return {
        report_id: {
            "embedded": report_id in embedded_reports,
            "pdf": report_id in pdf_ready_reports,
        }
        for report_id in report_ids
    }

async def agent_process_report(
    project_id: str,
    report_id: int,
    ctx: RequestContext,
    agent_service: AutomationService,
) -> None:
    async with agent_process_semaphore:
        prediction = await agent_service.report_matching(report_id)

        if hasattr(prediction, "model_dump"):
            prediction_data = prediction.model_dump()
        elif isinstance(prediction, dict):
            prediction_data = prediction
        else:
            prediction_data = {}

        predicted_study_id = prediction_data.get("studyId")

        if predicted_study_id is not None:
            await ctx.linkage_service.link_existing_study_to_report(report_id, int(predicted_study_id), "bot")
        else:
            suggested_study = prediction_data.get("newStudySuggestion", prediction_data)

            countries = suggested_study.get("countries")
            if not isinstance(countries, list):
                countries = []

            short_name = suggested_study.get("shortName")
            status = suggested_study.get("status") or "Planned"
            number_participants = suggested_study.get("numberParticipants")

            duration = suggested_study.get("duration")
            if not duration:
                duration_value = suggested_study.get("durationValue")
                duration_unit = suggested_study.get("durationUnit")
                if duration_value is not None and duration_unit:
                    duration = f"{duration_value} {duration_unit}"

            comparison = suggested_study.get("comparison")
            if isinstance(comparison, list):
                comparison = json.dumps(comparison)

            study_payload = StudyCreate(
                shortName=short_name or f"bot-{report_id}",
                status=status,
                countries=countries,
                numberParticipants=str(number_participants),
                duration=duration,
                comparison=comparison,
                trialId=suggested_study.get("trialId"),
            )
            for appendix in ['a', 'b', 'c', 'd', 'f']:
                try:
                    await ctx.linkage_service.create_study_and_link_to_report(report_id, study_payload, "bot")
                    break
                except DuplicateShortNameError:
                    study_payload.shortName = study_payload.shortName + appendix #if the name is already taken try the next name

        await ctx.pubsub_service.publish_project_update(project_id)
        logger.info("Agent processing completed for report %s in project %s", report_id, project_id)

async def get_project_stats(
    project: DbProject = Depends(get_project_by_id),
    ctx: RequestContext = Depends(get_context),
) -> ProjectDetails:
    return await ctx.project_service.get_project_stats(project)

async def start_automation(
    project_id: str,
    ctx: RequestContext,
    agent_service: AutomationService,
) -> None:
    pubsub = await ctx.pubsub_service.subscribe_to_project(project_id)
    try:
        while True:
            report_ids = await ctx.project_repo.get_project_associated_report_ids(project_id)
            if not report_ids:
                return

            report_status = await get_project_report_status(project_id, ctx)
            completion_map = await ctx.project_repo.get_report_completion_by_users(project_id)
            bot_processed_report_ids = {
                report_id
                for report_id, completed_by_users in completion_map.items()
                if "bot" in completed_by_users
            }

            if len(bot_processed_report_ids.intersection(set(report_ids))) >= len(report_ids):
                logger.info("Automation completed for project %s", project_id)
                return

            ready_report_ids = [
                report_id
                for report_id in report_ids
                if report_status.get(report_id, {}).get("embedded", False)
                and report_status.get(report_id, {}).get("pdf", False)
                and report_id not in bot_processed_report_ids
            ]

            if not ready_report_ids:
                await ctx.pubsub_service.get_next_project_update(pubsub)
                continue

            processing_tasks = [
                agent_process_report(
                    project_id,
                    report_id,
                    ctx,
                    agent_service,
                )
                for report_id in ready_report_ids
            ]
            await asyncio.gather(*processing_tasks)
    finally:
        await ctx.pubsub_service.unsubscribe_from_project(project_id, pubsub)


@router.get("/tasks",dependencies=[Depends(is_verified_api_call)], summary="Get pending review tasks for the authenticated user.", description="Returns all projects the user is assigned to along with their personal study-link counts.")
async def get_user_tasks(ctx: RequestContext = Depends(get_context)) -> List[ProjectTask]:
    return await ctx.project_service.get_user_tasks()

@router.post("/projects", dependencies=[Depends(is_admin)], summary="Upload a project (batch of new reports that need to be assigned to studies) (usually in the .ris file format)", status_code=201)
async def upload_file(background_tasks: BackgroundTasks, file: UploadFile = File(..., description="The .ris file containing all the articles you want to process."), projectName: str = Form(...), ctx: RequestContext = Depends(get_context)):

    try:
        entries = await parse_file(file)
    except RisParseError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    project_id, reports = ctx.project_service.build_reports_from_entries(entries)

    reports = await ctx.project_repo.add_new_project(project_id,projectName,reports)
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
        background_tasks.add_task(run_start_automation_background, project_id, ctx.user_id, model, start_automation)

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

class FilterMode(str, Enum):
    """How one filter dimension (e.g. "processed") should narrow the report list.

    `any` (the default) means "don't filter on this dimension at all" - it's not one of the
    two categories, it's an explicit no-op. `only` keeps just the reports matching this
    dimension, `exclude` keeps everything else. This replaces the older, less intuitive
    "two booleans that both default true, and setting exactly one to false narrows things
    down" pairing - the equivalent of "only" used to require knowing to leave the *other*
    field at its default rather than being a single, self-contained choice.
    """
    any = "any"
    only = "only"
    exclude = "exclude"


def _matches_filter(value: bool, mode: FilterMode) -> bool:
    if mode is FilterMode.any:
        return True
    if mode is FilterMode.only:
        return value
    return not value


async def _list_project_reports(
    project_id: str,
    ctx: RequestContext,
    *,
    allow_unready: bool,
    search: Optional[str] = None,
    processed: FilterMode = FilterMode.any,
    with_pdf: FilterMode = FilterMode.any,
    flagged: FilterMode = FilterMode.any,
    new_study: FilterMode = FilterMode.any,
    consensus: FilterMode = FilterMode.any,
    reviewed: FilterMode = FilterMode.any,
    only_fully_annotated: bool = False,
) -> List[BatchedReport]:
    report_ids = await ctx.project_repo.get_project_associated_report_ids(project_id)
    _, reports_with_pdf, ready_report_ids = await get_vectorized_and_ready_report_ids(project_id, ctx)
    # ready_report_ids is always a subset of auto_searched_report_ids: a report can't be fully
    # processed before its PDF auto-search has run.
    auto_searched_report_ids = await ctx.project_repo.get_auto_searched_pdf_for_project(project_id)

    reports = await ctx.report_repo.get_all_reports(report_ids)
    all_linked_studies = await ctx.report_repo.get_linked_studies_for_reports(report_ids)
    report_flags = await ctx.report_repo.get_report_flags_for_reports(report_ids)

    result = []
    for report in reports:
        if report.id not in auto_searched_report_ids:
            continue
        if report.id not in ready_report_ids and not allow_unready:
            continue
        authors = report.authors.split("//") if report.authors else []
        linked_studies = []
        if report.id in all_linked_studies.keys():
            linked_studies = studies_to_dto(all_linked_studies[report.id])

        result.append(
            BatchedReport(
                report=Report(
                    reportId=report.id,
                    year=report.year,
                    title=report.title,
                    abstract=report.abstract,
                    authors=authors,
                    trialId=report.trial_registration_id,
                    createdAt=report.date_entered,
                    updatedAt=report.date_edited
                ),
                hasPdf=report.id in reports_with_pdf,
                flag=report_flags.get(report.id).message if report.id in report_flags else None,
                assignedStudies=linked_studies,
            )
        )

    if search and search.strip():
        query = search.strip().lower()
        result = [
            r for r in result
            if query in (r.report.title or "").lower()
            or query in (r.report.abstract or "").lower()
            or query in str(r.report.reportId)
        ]

    result = [r for r in result if _matches_filter(len(r.assignedStudies) > 0, processed)]
    result = [r for r in result if _matches_filter(bool(r.hasPdf), with_pdf)]
    result = [r for r in result if _matches_filter(bool(r.flag and r.flag.strip()), flagged)]
    result = [
        r for r in result
        if _matches_filter(
            bool(
                r.report.createdAt and any(
                    study.createdAt and study.createdAt > r.report.createdAt
                    for study in r.assignedStudies
                )
            ),
            new_study,
        )
    ]

    # consensus/reviewed both default to "any" (no-op) on the common, unfiltered request, and
    # only_fully_annotated is only ever true for the review endpoint - skip the extra
    # annotations query entirely unless one of them actually needs it.
    if consensus is not FilterMode.any or reviewed is not FilterMode.any or only_fully_annotated:
        annotations = await _get_project_annotations(project_id, ctx)

        def _annotated_studies(report_id: int) -> List[Dict[str, Any]]:
            return annotations.get(report_id, {}).get("studies", [])

        if only_fully_annotated:
            result = [r for r in result if r.report.reportId in annotations]

        if consensus is not FilterMode.any:
            # Fewer than two annotators can't disagree, so treat that as consensus too.
            result = [
                r for r in result
                if _matches_filter(
                    len(_annotated_studies(r.report.reportId)) < 2
                    or len({s["studyId"] for s in _annotated_studies(r.report.reportId)}) == 1,
                    consensus,
                )
            ]

        if reviewed is not FilterMode.any:
            result = [
                r for r in result
                if _matches_filter(
                    any(s["confirmed"] for s in _annotated_studies(r.report.reportId)),
                    reviewed,
                )
            ]

    return result


_search_query = Query(None, description="Filter reports by title, abstract or report id (case-insensitive substring match).")


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
) -> List[BatchedReport]:
    return await _list_project_reports(
        project_id,
        ctx,
        allow_unready=False,
        search=search,
        processed=processed,
        flagged=flagged,
        new_study=new_study,
    )


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
) -> List[BatchedReport]:
    return await _list_project_reports(
        project_id,
        ctx,
        allow_unready=True,
        search=search,
        with_pdf=with_pdf,
    )


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
) -> List[BatchedReport]:
    return await _list_project_reports(
        project_id,
        ctx,
        allow_unready=False,
        search=search,
        consensus=consensus,
        reviewed=reviewed,
        only_fully_annotated=True,
    )

@router.get( "/projects/{project_id}/annotations",dependencies=[Depends(is_admin)],summary="Get reports annotated by all assigned users in a project.")
async def get_project_annotations(project: DbProject = Depends(get_project_by_id), ctx: RequestContext = Depends(get_context)) -> Dict[int, Dict[str, List[Dict[str, Any]]]]:
    return await _get_project_annotations(project.id, ctx)

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
