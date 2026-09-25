
from fastapi import APIRouter, Request
from fastapi import Query, Path, UploadFile, File, HTTPException, Depends, BackgroundTasks, Body, Form
from fastapi.responses import Response, StreamingResponse
from typing import Dict, List, Any, Tuple, Set
import json
import logging

from src.utils.ris_parser import parse_file, RisParseError
from src.utils.logger import setup_logging

import asyncio

from .auth import is_verified_api_call, is_admin

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


async def get_project_by_id(project_id: str, ctx: RequestContext = Depends(get_context)) -> DbProject:
    project = await ctx.project_repo.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project

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

@router.get("/projects/{project_id}/reports", dependencies=[Depends(is_verified_api_call)], summary="Get all reports in a project by project id.")
async def get_project_reports(
    project_id : str,
    ctx: RequestContext = Depends(get_context),
    raw: bool = Query(False, description="Include unprocessed items."),
) -> List[BatchedReport]:

    project = await ctx.project_repo.get_project_by_id(project_id)
    report_ids = await ctx.project_repo.get_project_associated_report_ids(project_id)
    _, reports_with_pdf, ready_report_ids = await get_vectorized_and_ready_report_ids(project_id, ctx)

    if raw and project is not None: #if the current user is the owner allow everything except for items not yet autosearched
        ready_report_ids = await ctx.project_repo.get_auto_searched_pdf_for_project(project_id)

    reports = await ctx.report_repo.get_all_reports(report_ids)
    all_linked_studies = await ctx.report_repo.get_linked_studies_for_reports(report_ids)
    report_flags = await ctx.report_repo.get_report_flags_for_reports(report_ids)

    result = []
    for report in reports:
        if report.id not in ready_report_ids:
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
    return result

@router.get( "/projects/{project_id}/annotations",dependencies=[Depends(is_admin)],summary="Get reports annotated by all assigned users in a project.")
async def get_project_annotations(project: DbProject = Depends(get_project_by_id), ctx: RequestContext = Depends(get_context)) -> Dict[int, Dict[str, List[Dict[str, Any]]]]:

    report_ids = await ctx.project_repo.get_project_associated_report_ids(project.id)

    if not report_ids:
        return {}

    assignees = await ctx.project_repo.get_project_assignees(project.id)
    assignee_ids = {user_id for user_id, _ in assignees if user_id}
    if not assignee_ids:
        return {}

    completion_map = await ctx.project_repo.get_report_completion_by_users(project.id)
    annotated_report_ids = [
        report_id
        for report_id in report_ids
        if assignee_ids.issubset(completion_map.get(report_id, set()))
    ]

    if not annotated_report_ids:
        return {}

    return await ctx.project_repo.get_project_annotations_by_assignees(
        project.id,
        assignee_ids,
        annotated_report_ids,
    )

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
