
from fastapi import APIRouter, Request
from fastapi import Query, Path, UploadFile, File, HTTPException, Depends, BackgroundTasks, Body, Form
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any, Tuple, Set
import os
import logging

from datetime import datetime

from ..utils.trial_registration_id import extract_trial_id
from ..utils.ris_parser import parse_file
from ..utils.logger import setup_logging

import hashlib
import asyncio

from .auth import is_verified_api_call, is_admin, get_roles

from ..database import get_project_repo, get_report_repo

from ..database import ReportRepository
from ..database import ProjectRepository

from ..database.models import Report as DbReport, Project as DbProject

from ..services import get_vectorstore_service, VectorstoreService

from ..services import get_maintenance_service, MaintenanceService

from .resources import Report, Study, transform_to_output_studies

router = APIRouter(tags=["projects"])

setup_logging("events.log")
logger = logging.getLogger(__name__)

# Simple in-process pub/sub to allow multiple subscribers per project
project_subscribers: Dict[str, List[asyncio.Queue]] = {}
project_subscribers_lock = asyncio.Lock()

# Track background tasks to prevent resource leaks
background_tasks: set = set()

project_id_path = Path(..., description="The projects's id")

class ProjectAssignee(BaseModel):
    userId : str
    numberReportsLinked: int = 0

class Project(BaseModel):
    projectId: str
    name: str
    owner: str
    createdAt: datetime
    numberReportsReadyForProcessing: int = 0

class ProjectDetails(Project):
    numberReportsTotal: int
    numberReportsPreProcessed: int = 0
    numberReportsReadyForReview: int = 0
    assignees: List[ProjectAssignee] = Field(default_factory=list)

class ProjectTask(BaseModel):
    project: Project
    numberReportsProcessed: int

class BatchedReport(BaseModel):
    report: Report
    hasPdf: Optional[bool]
    assignedStudies: List[Study] = Field(default_factory=list)

async def publish_project_update(project_id: str):
    """Publish an update for a specific project to all subscribers.
    The published value is the project_id (keeps compatibility with existing handlers).
    """
    async with project_subscribers_lock:
        queues = list(project_subscribers.get(project_id, []))

    for q in queues:
        try:
            q.put_nowait(project_id)
        except Exception:
            # If put_nowait fails for whatever reason, schedule an async put.
            task = asyncio.create_task(q.put(project_id))
            # Track the task to prevent resource leaks and add cleanup callback
            background_tasks.add(task)
            # Use lambda to be explicit and handle potential exceptions in cleanup
            task.add_done_callback(lambda t: background_tasks.discard(t))

async def process_report(reports : List[DbReport], project_id : str, project_repo : ProjectRepository, vectorstore : VectorstoreService, maintenance_service : MaintenanceService):
    async def process(report):
        project = await project_repo.get_project_by_id(project_id)
        if not project:
            return  # Skip processing if project was deleted
        await vectorstore.add_report_to_vectorstore(report)
        await publish_project_update(project_id)
    
    all_tasks = [process(report) for report in reports]
    await asyncio.gather(*all_tasks)

    await finalize_project_upload(project_id, project_repo, vectorstore, maintenance_service)

async def finalize_project_upload(project_id : str, project_repo : ProjectRepository, vectorstore : VectorstoreService, maintenance_service : MaintenanceService):
    """
    Finalize a project upload by checking if all reports have been processed.
    Updates project status and notifies subscribers when complete.
    """
    # Get all reports in the project
    report_ids = await project_repo.get_project_associated_report_ids(project_id)
    
    if not report_ids:
        #Project not available
        await maintenance_service.vectorstore_clean_up()
        return
    
    score_pairs = await vectorstore.calculate_score_pairs(report_ids)
    await project_repo.insert_project_scores(score_pairs)

    #print("Project finalized")
    # Notify all subscribers that project is complete
    await publish_project_update(project_id)

async def subscribe_to_project(project_id: str) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue()
    async with project_subscribers_lock:
        project_subscribers.setdefault(project_id, []).append(q)
    return q

async def unsubscribe_from_project(project_id: str, q: asyncio.Queue):
    async with project_subscribers_lock:
        lst = project_subscribers.get(project_id)
        if not lst:
            return
        if q in lst:
            lst.remove(q)
        if not lst:
            project_subscribers.pop(project_id, None)


async def get_project_by_id(project_id: str, project_repo: ProjectRepository = Depends(get_project_repo)) -> DbProject:
    project = await project_repo.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project

async def get_project_associated_report_ids(project: DbProject = Depends(get_project_by_id), project_repo: ProjectRepository = Depends(get_project_repo)):
    return await project_repo.get_project_associated_report_ids(project.BatchHash)

async def calculate_processing_progress(report_ids: List[int],report_repo: ReportRepository, vectorstore: VectorstoreService) -> Tuple[int, int]:
    report_ids = report_ids or []
    if not report_ids:
        return 0, 0

    vectorized_report_ids, _, ready_report_ids = await get_vectorized_and_ready_report_ids(
        report_ids, report_repo, vectorstore
    )

    generated_embeddings = len(vectorized_report_ids)
    ready_for_processing_count = len(ready_report_ids)

    return generated_embeddings, ready_for_processing_count

async def get_vectorized_and_ready_report_ids(
    report_ids: List[int],
    report_repo: ReportRepository,
    vectorstore: VectorstoreService,
) -> Tuple[Set[int], Set[int]]:
    if not report_ids:
        return set(), set()

    vectorized_report_ids_raw, report_numbers = await asyncio.gather(
        vectorstore.reports_exist(report_ids),
        report_repo.get_report_numbers(report_ids),
    )
    embedded_report_ids = set(vectorized_report_ids_raw)
    pdf_ready_reports = {
        report_id
        for report_id, report_number in report_numbers.items()
        if report_number is not None and report_number >= 0
    }
    ready_report_ids = embedded_report_ids & pdf_ready_reports
    return embedded_report_ids, pdf_ready_reports, ready_report_ids

async def get_project_stats(
    project: DbProject = Depends(get_project_by_id),
    report_ids: List[int] = Depends(get_project_associated_report_ids),
    report_repo: ReportRepository = Depends(get_report_repo),
    vectorstore: VectorstoreService = Depends(get_vectorstore_service),
    project_repo: ProjectRepository = Depends(get_project_repo),
) -> ProjectDetails:

    generated_embeddings, ready_for_processing_count = await calculate_processing_progress(
        report_ids, report_repo, vectorstore
    )

    assignees = await project_repo.get_project_assignees(project.BatchHash)
    assignee_ids = [user_id for user_id, _ in assignees if user_id]

    ready_for_review_count = 0
    if assignee_ids:
        completion_map = await project_repo.get_report_completion_by_users(project.BatchHash)
        assignee_set = set(assignee_ids)
        ready_for_review_count = sum(
            1 for report_id in report_ids
            if assignee_set.issubset(completion_map.get(report_id, set()))
        )

    assignee_payload = [
        ProjectAssignee(userId=user_id, numberReportsLinked=linked_count)
        for user_id, linked_count in assignees
    ]

    return ProjectDetails(
        projectId=project.BatchHash,
        name=project.BatchDescription,
        createdAt=project.DateCreated,
        numberReportsTotal=len(report_ids),
        numberReportsPreProcessed=generated_embeddings,
        numberReportsReadyForProcessing=ready_for_processing_count,
        numberReportsReadyForReview=ready_for_review_count,
        owner=project.UploadedBy,
        assignees=assignee_payload,
    )

@router.get("/tasks",dependencies=[Depends(is_verified_api_call)], summary="Get pending review tasks for the authenticated user.", description="Returns all projects the user is assigned to along with their personal study-link counts.")
async def get_user_tasks(project_repo: ProjectRepository = Depends(get_project_repo), report_repo: ReportRepository = Depends(get_report_repo), vectorstore: VectorstoreService = Depends(get_vectorstore_service),) -> List[ProjectTask]:
    user_id = getattr(project_repo, "user_id", None)
    if not user_id:
        return []

    projects = await project_repo.get_assigned_projects()
    if not projects:
        return []

    user_link_counts = await project_repo.get_user_link_counts_by_project()

    report_id_tasks = [
        project_repo.get_project_associated_report_ids(project.BatchHash) for project in projects
    ]
    project_report_ids = await asyncio.gather(*report_id_tasks)

    progress_tasks = [
        calculate_processing_progress(report_ids, report_repo, vectorstore)
        for report_ids in project_report_ids
    ]
    progress_results = await asyncio.gather(*progress_tasks)

    tasks: List[ProjectTask] = []
    for project, (_, ready_for_processing_count) in zip(projects, progress_results):
        project_payload = Project(
            projectId=project.BatchHash,
            name=project.BatchDescription,
            owner=project.UploadedBy or "",
            createdAt=project.DateCreated,
            numberReportsReadyForProcessing=ready_for_processing_count,
        )
        tasks.append(
            ProjectTask(
                project=project_payload,
                numberReportsProcessed=user_link_counts.get(project.BatchHash, 0),
            )
        )

    return tasks

@router.post("/projects", dependencies=[Depends(is_admin)], summary="Upload a project (batch of new reports that need to be assigned to studies) (usually in the .ris file format)", status_code=201) 
async def upload_file(background_tasks: BackgroundTasks, file: UploadFile = File(..., description="The .ris file containing all the articles you want to process."), projectName: str = Form(...), project_repo : ProjectRepository = Depends(get_project_repo), vectorstore : VectorstoreService = Depends(get_vectorstore_service), maintenance_service: MaintenanceService = Depends(get_maintenance_service)):

    entries = await parse_file(file)

    reports = []
    fingerprint_string = ""
    for entry in entries:
        title = entry.get('primary_title', None)
        if not title:
            title = entry.get('title', None)

        authors = entry.get('authors', None)
        abstract = entry.get('abstract', None)
        report_number = int(entry.get('research_notes', -1))

        trial_ids = extract_trial_id(title=title, abstract=abstract, authors=authors)
        if len(trial_ids) == 1:
            trial_ids = trial_ids[0]
        else:
            trial_ids = None

        try:
            authors_str = "//".join(authors)
        except Exception as e:
            print(f"UPLOAD FILE: Error joining authors for entry: {entry}\nException: {e}")
            authors_str = str(authors) if authors is not None else ""

        try:
            safe_title = title.replace("\n", " ") if title is not None else ""
        except AttributeError as e:
            print(f"UPLOAD FILE: Error replacing in title for entry: {entry}\nException: {e}")
            safe_title = str(title) if title is not None else ""

        try:
            safe_abstract = abstract.replace("\n", " ") if abstract is not None else ""
        except AttributeError as e:
            print(f"UPLOAD FILE: Error replacing in abstract for entry: {entry}\nException: {e}")
            safe_abstract = str(abstract) if abstract is not None else ""

        report = DbReport(
            Title=safe_title,
            Abstract=safe_abstract,
            Authors=authors_str,
            ReportNumber=report_number,
            Journal=entry.get('secondary_title', None),
            Year=int(entry.get('year', None)),
            Volume= entry.get('volume', None),
            Issue=entry.get('note', None),
            Pages=entry.get('start_page', None),
            Language=entry.get('language', None),
            Publisher=entry.get('publisher', None),
            City=entry.get('place_published', None),
            DOI=entry.get('doi', None),
            TrialRegistrationID=trial_ids,
            CopyStatus= "Copy Obtained" if report_number != 0 else "Seeking Source",
            TypeofReportID=0, #TODO ask alessandro
            PublicationTypeID=1, #TODO ask alessandro
            #TODO Dupstring missing
            #OriginalTitle: Optional[str] TODO
        )

        fingerprint_string += safe_title if safe_title else "" + safe_abstract if safe_abstract else "" + authors_str if authors_str else ""

        reports.append(report)

    project_id = hashlib.sha256(fingerprint_string.encode()).hexdigest()

    reports = await project_repo.add_new_project(project_id,projectName,reports)
    # schedule background tasks
    #for report in reports:
    #    print("Report provcess appended")
    background_tasks.add_task(process_report, reports, project_id, project_repo, vectorstore, maintenance_service)

    await publish_project_update(project_id)

    #TODO disabled for legacy reasons
    #reports_dict = [report.dict() for report in reports]
    #JSONResponse(content={"project_id": project_id, "project_description": file.filename, "reports": reports_dict}, status_code=201)

    return Response(status_code=201)

@router.get("/projects", dependencies=[Depends(is_admin)], summary="Get an overview of all current projects.", description="For each project the current progress of embedding calculation and the number of already assigned reports is returned")
async def get_available_projects(project_repo: ProjectRepository = Depends(get_project_repo), report_repo: ReportRepository = Depends(get_report_repo), vectorstore : VectorstoreService = Depends(get_vectorstore_service)) -> List[ProjectDetails]:
    # Get all projects
    projects = await project_repo.get_all_projects()

    # Process all projects in parallel
    tasks = []
    for project in projects:
        report_ids = await project_repo.get_project_associated_report_ids(project.BatchHash)
        tasks.append(
            get_project_stats(
                project=project,
                report_ids=report_ids,
                report_repo=report_repo,
                vectorstore=vectorstore,
                project_repo=project_repo,
            )
        )
    project_responses = await asyncio.gather(*tasks)

    return project_responses

@router.get("/projects/{project_id}", dependencies=[Depends(is_admin)], summary="Get a specific project by id.",description="Returns details and progress information for a single project identified by project id.")
async def get_project_stats_by_id(project_stats : Project = Depends(get_project_stats)) -> Project:
    return project_stats

@router.delete("/projects/{project_id}", dependencies=[Depends(is_admin)], summary="Delete a project and all its associated reports (including calculated embedding vectors) from the temporary storage.", status_code=204)
async def delete_project(project_id : str, report_ids : List[int] = Depends(get_project_associated_report_ids), project_repo: ProjectRepository = Depends(get_project_repo), vectorstore: VectorstoreService = Depends(get_vectorstore_service)):
    #Deletes the project and through cascade and triggers everythig related to it
    await project_repo.delete_project(project_id)

    await vectorstore.delete_vectors_by_report_ids(report_ids)

    await publish_project_update(project_id)
    
    return Response(status_code=204)

@router.post("/projects/{project_id}/assignees", dependencies=[Depends(is_admin)],summary="Assign a user to a project",status_code=201,)
async def assign_user_to_project(
    user_id: str = Body(..., embed=False, description="User ID to assign"),
    project_id: str = project_id_path,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    try:
        project = await project_repo.get_project_by_id(project_id)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        created = await project_repo.add_project_assignee(project_id, user_id)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    if not created:
        raise HTTPException(status_code=409, detail="User already assigned to project")

    await publish_project_update(project_id)

    return ProjectAssignee(userId=user_id, numberReportsLinked=0)

@router.delete("/projects/{project_id}/assignees/{user_id}", dependencies=[Depends(is_admin)],summary="Remove a user assignment from a project",status_code=204,)
async def remove_user_from_project(
    project_id: str = project_id_path,
    user_id: str = Path(..., description="The user ID to remove from the project"),
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    try:
        project = await project_repo.get_project_by_id(project_id)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        removed = await project_repo.remove_project_assignee(project_id, user_id)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    if not removed:
        raise HTTPException(status_code=404, detail="User is not assigned to this project")

    await publish_project_update(project_id)

    return Response(status_code=204)

@router.get("/projects/{project_id}/reports", dependencies=[Depends(is_verified_api_call)], summary="Get all reports in a project by project id.")
async def get_project_reports(
    ready_only: bool = Query(False, description="Only include reports that have generated embeddings and a linked PDF."),
    report_ids: List[int] = Depends(get_project_associated_report_ids),
    report_repo: ReportRepository = Depends(get_report_repo),
    vectorstore: VectorstoreService = Depends(get_vectorstore_service),
    roles: List[str] = Depends(get_roles)
) -> List[BatchedReport]:
    ready_report_ids: Optional[Set[int]] = None
    _, reports_with_pdf, ready_report_ids = await get_vectorized_and_ready_report_ids(
        report_ids, report_repo, vectorstore
    )
    if not ready_only and "ADMIN" in roles:
        ready_report_ids = None

    reports = await report_repo.get_all_reports(report_ids)
    all_linked_studies = await report_repo.get_linked_studies_for_reports(report_ids)

    result = []
    for report in reports:
        if ready_report_ids is not None and report.CRGReportID not in ready_report_ids:
            continue
        authors = report.Authors.split("//") if report.Authors else []
        linked_studies = []
        if report.CRGReportID in all_linked_studies.keys():
            linked_studies = transform_to_output_studies(all_linked_studies[report.CRGReportID])

        result.append(
            BatchedReport(
                report=Report(
                    reportId=report.CRGReportID,
                    year=report.Year,
                    title=report.Title,
                    abstract=report.Abstract,
                    authors=authors,
                    trialId=report.TrialRegistrationID,
                    createdAt=report.Dateentered,
                    updatedAt=report.DateEdited
                ),
                hasPdf=report.CRGReportID in reports_with_pdf,
                assignedStudies=linked_studies,
            )
        )
    return result

@router.get( "/projects/{project_id}/annotations",dependencies=[Depends(is_admin)],summary="Get reports annotated by all assigned users in a project.")
async def get_project_annotations(
    project: DbProject = Depends(get_project_by_id),
    report_ids: List[int] = Depends(get_project_associated_report_ids),
    project_repo: ProjectRepository = Depends(get_project_repo),
) -> Dict[int, List[Dict[str, Any]]]:
    if not report_ids:
        return {}

    assignees = await project_repo.get_project_assignees(project.BatchHash)
    assignee_ids = {user_id for user_id, _ in assignees if user_id}
    if not assignee_ids:
        return {}

    completion_map = await project_repo.get_report_completion_by_users(project.BatchHash)
    annotated_report_ids = [
        report_id
        for report_id in report_ids
        if assignee_ids.issubset(completion_map.get(report_id, set()))
    ]

    if not annotated_report_ids:
        return {}

    return await project_repo.get_project_annotations_by_assignees(
        project.BatchHash,
        assignee_ids,
        annotated_report_ids,
    )

@router.get("/projects/{project_id}/stream",dependencies=[Depends(is_admin)], summary="Stream updated batch information.")
async def stream_project_updates(
    project_id: str,
    request: Request,
    project_repo: ProjectRepository = Depends(get_project_repo),
    report_repo: ReportRepository = Depends(get_report_repo),
    vectorstore: VectorstoreService = Depends(get_vectorstore_service),
) -> StreamingResponse:
    async def event_stream():
        HEARTBEAT_INTERVAL = 10  # seconds

        # subscribe this client to the project
        q = await subscribe_to_project(project_id)
        try:
            while True:
                # Check for client disconnect
                if await request.is_disconnected():
                    break

                # Check if project still exists
                project_obj = None
                try:
                    project_obj = await get_project_by_id(project_id, project_repo)
                except HTTPException as e:
                    if e.status_code == 404:
                        yield f"event: project_deleted\ndata: Project deleted\n\n"
                        break
                    else:
                        raise

                try:
                    data = await asyncio.wait_for(q.get(), timeout=HEARTBEAT_INTERVAL)
                    if data == project_id:
                        try:
                            report_ids = await project_repo.get_project_associated_report_ids(project_id)
                            project = await get_project_stats(
                                project=project_obj,
                                report_ids=report_ids,
                                report_repo=report_repo,
                                vectorstore=vectorstore,
                                project_repo=project_repo,
                            )
                            yield f"data: {project.json()}\n\n"
                        except HTTPException as e:
                            if e.status_code == 404:
                                yield f"event: project_deleted\ndata: Project deleted\n\n"
                                break
                            else:
                                raise
                except asyncio.TimeoutError:
                    # Send heartbeat
                    yield f": heartbeat\n\n"
        finally:
            await unsubscribe_from_project(project_id, q)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
