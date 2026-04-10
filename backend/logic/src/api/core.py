from fastapi import APIRouter, Request
from fastapi import Query, Path, UploadFile, File, HTTPException, Depends, BackgroundTasks, Body, Form
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from typing import Dict, List, Optional, Any, Tuple, Set
import os
import logging

from datetime import datetime

from ..utils.trial_registration_id import extract_trial_id
from ..utils.ris_parser import parse_file
from ..utils.logger import setup_logging

import hashlib
import asyncio

import enum
import grpc

from .auth import is_verified_api_call, get_user_id, get_roles

from ..database import get_study_repo, get_project_repo, get_report_repo, db_ready

from ..database import StudyRepository
from ..database import ReportRepository
from ..database import ProjectRepository

from ..database.models import Report as DbReport, Batch as DbProject

from ..services import get_tag_similarity_service, TagSimilaritySearchService
from ..services import get_related_tag_service, RelatedTagSearchService
from ..services import get_tag_scoring_service, TagScoringService
from ..services import get_study_similarity_service, get_study_similarity_service_project, StudySimilaritySearchService

from ..services import get_vectorstore_service, VectorstoreService

from ..services import get_embedding_service, EmbeddingService

from ..services import get_maintenance_service, MaintenanceService

from ..services import project_path_to_report_id

from .resources import Report, Study, StudyCreate, transform_to_output_studies

load_dotenv()

MODEL_HOST = os.getenv("EMBEDDING_SERVICE_HOST")
MODEL_PORT = os.getenv("EMBEDDING_SERVICE_PORT")
COLLECTION_NAME = os.getenv("VECTORSTORE_COLLECTION_NAME")

DEBUG = os.getenv("DEBUG", None) == "true"

setup_logging("events.log")
logger = logging.getLogger(__name__)

router = APIRouter(tags=["logic"])

cutoff_query = Query(None, description="Cutoff date: for example '2025-01-13 00:00:00' (do not retrieve items entered after that date). Usually only used for testing")
report_index_path = Path(..., description="The target report's index within the project (starting with 0)")
project_id_path = Path(..., description="The projects's id")

k_query = Query(10, description="Maximum number of returned results.")

# Simple in-process pub/sub to allow multiple subscribers per project
project_subscribers: Dict[str, List[asyncio.Queue]] = {}
project_subscribers_lock = asyncio.Lock()

# Track background tasks to prevent resource leaks
background_tasks: set = set()

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

class SimilarStudy(BaseModel):
    relevance: float
    study: Study

class TagResponse(BaseModel):
    id: str
    keyword: str
    relevance: str

class RawReport(BaseModel):
    title: str
    abstract: Optional[str]
    authors: Optional[List[str]]

class TagCategories(str, enum.Enum):
    default = 'default'
    interventions = 'interventions'
    conditions = 'conditions'
    outcomes = 'outcomes'
    participants = 'participants'

def transform_raw_similar_studies(studies):
    results = []
    for i in range(0, len(studies['Relevance'])):
        study = Study(
            studyId=studies['CRGStudyID'][i],
            shortName=studies['ShortName'][i],
            numberParticipants=studies['NumberParticipants'][i],
            duration=studies['Duration'][i],
            comparison=studies['Comparison'][i],
            countries=studies['Countries'][i].split("//"),
            createdAt=studies['DateEntered'][i],
            updatedAt=studies['DateEdited'][i],
            status=studies['StatusofStudy'][i],
            trialId=studies['ISRCTN'][i],
        )
        results.append(SimilarStudy(relevance=studies['Relevance'][i], study=study))
    return results

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

@router.get("/readyz", summary="Health check endpoint for readiness probe", tags=["health"])
async def readyz(db_ready: str = Depends(db_ready), vectorstore : VectorstoreService = Depends(get_vectorstore_service), embedding_service : EmbeddingService = Depends(get_embedding_service)) -> Dict[str, Any]:
    """
    Check if the service is ready to accept requests.
    
    Returns:
        - status: "ready" or "not_ready"
        - checks: detailed status of each dependency
    """
    checks = {}
    overall_status = "ready"
    
    # Check database connectivity
    if db_ready == "ready":
        checks["database"] = {"status": "healthy", "message": "Database connection successful"}
    else:
        checks["database"] = {"status": "unhealthy", "message": f"Database error: {db_ready}"}
        overall_status = "not_ready"
    
    # Check vector store connectivity
    try:
        collections = await vectorstore.get_collections()
        checks["vectorstore"] = {
            "status": "healthy",
            "message": f"Vector store accessible, {len(collections.collections)} collections found"
        }
    except Exception as e:
        checks["vectorstore"] = {"status": "unhealthy", "message": f"Vector store error: {str(e)}"}
        overall_status = "not_ready"
    
    # Check gRPC embedding service connectivity
    try:
        channel = embedding_service.get_channel()
        # Simple connectivity check - channel state
        state = channel.get_state(try_to_connect=True)
        if state == grpc.ChannelConnectivity.READY:
            checks["embedding_service"] = {"status": "healthy", "message": "gRPC channel ready"}
        else:
            checks["embedding_service"] = {
                "status": "degraded",
                "message": f"gRPC channel state: {state.name}"
            }
            overall_status = "not_ready"
    except Exception as e:
        checks["embedding_service"] = {"status": "unhealthy", "message": f"gRPC error: {str(e)}"}
        overall_status = "not_ready"
    
    # Check background task health
    checks["background_tasks"] = {
        "status": "healthy",
        "active_tasks": len(background_tasks),
        "message": f"{len(background_tasks)} active background tasks"
    }
    
    # Check project subscribers
    async with project_subscribers_lock:
        total_subscribers = sum(len(queues) for queues in project_subscribers.values())
        checks["project_subscribers"] = {
            "status": "healthy",
            "active_projects": len(project_subscribers),
            "total_subscribers": total_subscribers,
            "message": f"{len(project_subscribers)} projects with {total_subscribers} subscribers"
        }
    
    response = {
        "status": overall_status,
        "timestamp": datetime.now().isoformat(),
        "checks": checks
    }
    
    # Return 503 if not ready
    if overall_status != "ready":
        raise HTTPException(status_code=503, detail=response)
    
    return response

@router.post("/projects", dependencies=[Depends(is_verified_api_call)], summary="Upload a project (batch of new reports that need to be assigned to studies) (usually in the .ris file format)", status_code=201) 
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

async def get_project_by_id(project_id: str, project_repo: ProjectRepository = Depends(get_project_repo)) -> DbProject:
    project = await project_repo.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project

async def get_project_associated_report_ids(project: DbProject = Depends(get_project_by_id), project_repo: ProjectRepository = Depends(get_project_repo)):
    return await project_repo.get_project_associated_report_ids(project.BatchHash)

async def calculate_processing_progress(
    report_ids: List[int],
    report_repo: ReportRepository,
    vectorstore: VectorstoreService,
) -> Tuple[int, int]:
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

@router.get(
    "/tasks",
    dependencies=[Depends(is_verified_api_call)],
    summary="Get pending review tasks for the authenticated user.",
    description="Returns all projects the user is assigned to along with their personal study-link counts.",
)
async def get_user_tasks(
    project_repo: ProjectRepository = Depends(get_project_repo),
    report_repo: ReportRepository = Depends(get_report_repo),
    vectorstore: VectorstoreService = Depends(get_vectorstore_service),
) -> List[ProjectTask]:
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

@router.get("/projects", dependencies=[Depends(is_verified_api_call)], summary="Get an overview of all current projects.", description="For each project the current progress of embedding calculation and the number of already assigned reports is returned")
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

@router.get("/projects/{project_id}", dependencies=[Depends(is_verified_api_call)], summary="Get a specific project by id.",description="Returns details and progress information for a single project identified by project id.")
async def get_project_stats_by_id(project_stats : Project = Depends(get_project_stats)) -> Project:
    return project_stats

@router.delete("/projects/{project_id}", dependencies=[Depends(is_verified_api_call)], summary="Delete a project and all its associated reports (including calculated embedding vectors) from the temporary storage.", status_code=204)
async def delete_project(project_id : str, report_ids : List[int] = Depends(get_project_associated_report_ids), project_repo: ProjectRepository = Depends(get_project_repo), vectorstore: VectorstoreService = Depends(get_vectorstore_service)):
    
    #Deletes the project and through cascade and triggers everythig related to it
    await project_repo.delete_project(project_id)

    await vectorstore.delete_vectors_by_report_ids(report_ids)

    await publish_project_update(project_id)
    
    return Response(status_code=204)

@router.post(
    "/projects/{project_id}/assignees",
    dependencies=[Depends(is_verified_api_call)],
    summary="Assign a user to a project",
    status_code=201,
)
async def assign_user_to_project(
    user_id: str = Body(..., embed=False, description="User ID to assign"),
    project_id: str = project_id_path,
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    project = await project_repo.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    created = await project_repo.add_project_assignee(project_id, user_id)
    if not created:
        raise HTTPException(status_code=409, detail="User already assigned to project")

    await publish_project_update(project_id)

    return ProjectAssignee(userId=user_id, numberReportsLinked=0)

@router.delete(
    "/projects/{project_id}/assignees/{user_id}",
    dependencies=[Depends(is_verified_api_call)],
    summary="Remove a user assignment from a project",
    status_code=204,
)
async def remove_user_from_project(
    project_id: str = project_id_path,
    user_id: str = Path(..., description="The user ID to remove from the project"),
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    project = await project_repo.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    removed = await project_repo.remove_project_assignee(project_id, user_id)
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

@router.get("/projects/{project_id}/subscribe",dependencies=[Depends(is_verified_api_call)], summary="Stream updated batch information.")
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

@router.get("/projects/{project_id}/{report_index}", dependencies=[Depends(is_verified_api_call)], summary="Get the data and embedding vectors for a specific report in a project.", description="Retrieve the title, abstract, authors, trial ID, embedding vectors, and assigned studies for a specific report identified by its project id and index (starting with 0) within the project.")
async def get_project_report(report_id : int = Depends(project_path_to_report_id), report_repo : ReportRepository = Depends(get_report_repo), vectorstore: VectorstoreService = Depends(get_vectorstore_service)):

    # Run DB/vectorstore calls in parallel
    vectors_task = vectorstore.get_vectors_by_report_id(report_id)
    report_task =  report_repo.get_report_by_id(report_id)
    assigned_studies_task = report_repo.get_linked_studies(report_id)

    report_obj, vectors, assigned_studies = await asyncio.gather(
        report_task, vectors_task, assigned_studies_task
    )

    # Convert Report model to dict
    report = report_obj.dict()

    # Normalize keys to lowercase
    report = {key.lower(): value for key, value in report.items()}


    # Normalize vectors key for legacy
    vectors['embedding'] = vectors.pop("default")

    # Normalize authors
    report["authors"] = report["authors"].split("//") if report.get("authors") else []

    # Assigned studies from DB (not JSON field)
    report["assigned_studies"] = [s.CRGStudyID for s in assigned_studies]

    report["vectors"] = vectors

    return report

@router.put("/projects/{project_id}/{report_index}/studies", dependencies=[Depends(is_verified_api_call)], summary="Assign studies to a specific report in a project.", status_code=200)
async def assign_studies(project_id: str = project_id_path, study_ids: List[int] = Query(..., description="The study ids you want to assign to the specified report."), report_id : int = Depends(project_path_to_report_id), report_repo : ReportRepository = Depends(get_report_repo), user_id: Optional[str] = Depends(get_user_id), vectorstore: VectorstoreService = Depends(get_vectorstore_service)):
    await asyncio.gather(
        report_repo.link_studies(report_id, study_ids),
        vectorstore.link_report_to_study_ids(report_id, study_ids, user_id)
    )

    await publish_project_update(project_id)
    
    payload = {"user": user_id, "event_type": "study::links::changed", "report_id": report_id, "original_timestamp": "-"}
    logger.info("ReportInteraction", extra={"payload": payload})

    return await get_project_report(report_id, report_repo, vectorstore)

@router.delete("/projects/{project_id}/{report_index}/studies", dependencies=[Depends(is_verified_api_call)], summary="Remove assigned studies from a specific report in a project.", status_code=200)
async def delete_assigned_studies(project_id: str = project_id_path, report_id : int = Depends(project_path_to_report_id), report_repo : ReportRepository = Depends(get_report_repo), user_id: Optional[str] = Depends(get_user_id), vectorstore: VectorstoreService = Depends(get_vectorstore_service)):
    await asyncio.gather(
        report_repo.unlink_studies(report_id),
        vectorstore.link_report_to_study_ids(report_id, [], user_id)
    )

    await publish_project_update(project_id)

    payload = {"user": user_id, "event_type": "study::links::changed", "report_id": report_id, "original_timestamp": "-"}
    logger.info("ReportInteraction", extra={"payload": payload})

    return await get_project_report(report_id, report_repo, vectorstore)

@router.get("/projects/{project_id}/{report_index}/similar-tags", dependencies=[Depends(is_verified_api_call)], summary="Get related tags (interventions, outcomes, ...) for a specific report in a project based on its embedding vectors.")
async def similar_tags(sources: List[str] = Query(..., description="Which source of tags do you want to search ('mesh', 'meerkat' or both)"), aspect: TagCategories = Query(TagCategories.interventions, description="The tag category which you are interested in"), k : int = k_query, report_id : int = Depends(project_path_to_report_id), tag_similarity_service : TagSimilaritySearchService = Depends(get_tag_similarity_service)) -> List[TagResponse]:
    if aspect == TagCategories.default:
        raise HTTPException(status_code=400, detail="No tags for 'default' embedding.")
    return await tag_similarity_service.get_similar_tags_by_id(report_id, aspect, sources, k)

@router.get("/projects/{project_id}/{report_index}/similar-studies", dependencies=[Depends(is_verified_api_call)], summary="Get related studies for a specific report in a project based on its embedding vectors.", description="Retrieve studies that are similar to a specific report identified by its project id and index (starting with 0) within the project. Similarity is determined based on the embedding vectors of the report. The similarity search is done at runtime. You can optionally search for similarity based on a specific aspect (e.g., interventions, outcomes) or apply a cutoff date to only consider studies entered before a certain date.")
async def similar_studies(aspect: TagCategories = Query(TagCategories.default, description="This value is rarely needed. Just if you want to search studies based on a certain aspect."), cutoff: str = cutoff_query, k : int = k_query, report_id : int = Depends(project_path_to_report_id), user_id : str = Depends(get_user_id), study_similarity_service : StudySimilaritySearchService = Depends(get_study_similarity_service_project), return_details : bool = False) -> List[SimilarStudy]:
    result = await study_similarity_service.get_similar_studies_by_id(report_id,aspect, cutoff,k, None, None, return_details=return_details)
    payload = {"user": user_id, "event_type": f"similar::studies::k::{k}", "report_id": report_id, "original_timestamp": "-"}
    logger.info("ReportInteraction", extra={"payload": payload})
    return transform_raw_similar_studies(result)


@router.get("/{tag_category}/{tag_value}/related_studies", dependencies=[Depends(is_verified_api_call)], summary="Get studies related to a specific tag (intervention, outcome, ...) currently only vector-similarity search is available.", description="Retrieve studies that are related to a specific tag value (e.g., 'Placebo' for interventions) using vector similarity search based on the embedding of the tag value. The similarity search is done at runtime.")
async def get_aspect_related_studies(tag_category: TagCategories = Path(..., description="The tags category (e.g. 'interventions', 'conditions', ...)"), tag_value: str = Path(..., description="The specific tags value (e.g. 'Placebo' for interventions)"), k : int = k_query, study_similarity_service : StudySimilaritySearchService = Depends(get_study_similarity_service), embedding_service : EmbeddingService = Depends(get_embedding_service)):
    embeddings = await embedding_service.embed_aspect(tag_value)

    aspect = tag_category
    aspect_mapping = {'interventions': 'intervention', 'conditions': 'condition', 'outcomes': 'outcome'}
    if tag_category in aspect_mapping.keys():
        aspect = aspect_mapping[tag_category]

    return await study_similarity_service.get_similar_study_by_query(embeddings['embedding'],aspect, None, k, [], [], [], return_details=False)

@router.get("/{tag_category}/{tag_value}/similar-tags", dependencies=[Depends(is_verified_api_call)], summary="Get related tags (interventions, outcomes, ...) for a specific report in a project based on its embedding vectors.")
async def similar_tags(tag_category: TagCategories =Path(..., description="The tags category (e.g. 'interventions', 'conditions', ...)"), tag_value : str = Path(..., description="The specific tags value (e.g. 'Placebo' for interventions)"), sources: List[str] = Query(..., description="Which source of tags do you want to search ('mesh', 'meerkat' or both)"), k : int = k_query, tag_similarity_service : TagSimilaritySearchService = Depends(get_tag_similarity_service)) -> List[TagResponse]:
    if tag_category == TagCategories.default:
        raise HTTPException(status_code=400, detail="No tags for 'default' embedding.")
    return await tag_similarity_service.get_similar_tags_by_string(tag_value, tag_category, sources, k)

"""
Only used for internal API key protected embedding analysis
"""

class RetrievalInputText(BaseModel):
    title: str
    abstract: Optional[str]
    authors: Optional[List[str]]
    topK: int

class RetrievalInputEmbedding(BaseModel):
    basic_input: RetrievalInputText
    embeddings: dict
    model_id: str
    
@router.post("/processing/analyze_embedding", dependencies=[Depends(is_verified_api_call)], include_in_schema=False)
async def analyze_embedding(input: RetrievalInputEmbedding, cutoff: str = Query(None), study_repo : StudyRepository = Depends(get_study_repo), tag_scoring_service : TagScoringService = Depends(get_tag_scoring_service), study_similarity_service : StudySimilaritySearchService = Depends(get_study_similarity_service)):
    return await analyze(input.embeddings, input.model_id, input.basic_input.topK, input.basic_input.title, input.basic_input.abstract, input.basic_input.authors, cutoff, study_repo, tag_scoring_service, study_similarity_service)

async def analyze(embeddings, top_k : int, title : str, abstract : str, authors, cutoff : str, study_repo : StudyRepository, tag_scoring_service : TagScoringService, study_similarity_service : StudySimilaritySearchService):
    
    trial_id = extract_trial_id(RawReport(title=title,abstract=abstract, authors=[]))
    trial_id = [trial_id[0]] if len(trial_id) == 1 else None
    pre_result = await study_similarity_service.get_similar_study_by_query(embeddings['embedding'], "default", cutoff, top_k, [], trial_id, authors, return_details=True)

    found_study_ids = {}
    for key, score, details in zip(pre_result['CRGStudyID'], pre_result['Relevance'], pre_result['details']):
        found_study_ids[key] = {'score': score, 'report_hit': details[0]['source_id']}

    result = {}
    result['related_studies'] = []

    all_related_interventions = []
    all_related_conditions = []
    all_related_outcomes = []

    scores = [item['score'] for item in found_study_ids.values()]
    report_hits = [item['report_hit'] for item in found_study_ids.values()]

    (related_studies, study_interventions, study_conditions, study_outcomes, study_participants_desc, study_design, study_reports) = await asyncio.gather(
        study_repo.get_studies(list(found_study_ids.keys())),
        study_repo.get_study_interventions(list(found_study_ids.keys())),
        study_repo.get_study_conditions(list(found_study_ids.keys())),
        study_repo.get_study_outcomes(list(found_study_ids.keys())),
        study_repo.get_study_participants(list(found_study_ids.keys())),
        study_repo.get_study_design(list(found_study_ids.keys())),
        study_repo.get_study_reports_by_study_ids(list(found_study_ids.keys()), ['CRGReportID', 'Title', 'Abstract', 'Authors'], cutoff)
    )

    for id, name, num_participants, countries, durations,report_hit, score in zip(related_studies['CRGStudyID'], related_studies['ShortName'], related_studies['NumberParticipants'], related_studies['Countries'], related_studies['Duration'], report_hits, scores):            
        study_item = {}
        study_item['study_id'] =  id
        study_item['study_name'] = name
        study_item['score'] = score
        study_item['report_hit'] = report_hit

        study_item['attributes'] = {}
        study_item['attributes']['countries'] = [country.strip() for country in countries.split("//")] if countries else None
        study_item['attributes']['duration'] = [duration.strip() for duration in durations.split("//")] if durations else None
        study_item['attributes']['participants_num'] = [p_num.strip() for p_num in num_participants.split("//")] if num_participants else None

        study_item['assigned_reports'] = {}

        study_item['attributes']['participants_desc'] = study_participants_desc.get(str(id), [])
        study_item['attributes']['study_design'] = study_design.get(str(id), [])

        related_interventions = study_interventions.get(str(id), [])
        study_item['assigned_interventions'] = [item['Description'] for item in related_interventions]
        all_related_interventions.extend([item['ID'] for item in related_interventions])

        related_conditions = study_conditions.get(str(id), [])
        study_item['assigned_conditions'] = [item['Description'] for item in related_conditions]
        all_related_conditions.extend([item['ID'] for item in related_conditions])

        related_outcomes = study_outcomes.get(str(id), [])
        study_item['assigned_outcomes'] = [item['Description'] for item in related_outcomes]
        all_related_outcomes.extend([item['ID'] for item in related_outcomes])
    
        related_reports = study_reports.get(str(id), [])#responses[2].json()
        for related_report_item in related_reports:
            report_item = {}
            report_item['title'] = related_report_item['Title']
            report_item['abstract'] =related_report_item['Abstract']
            report_item['authors'] = [author.strip() for author in related_report_item['Authors'].split("//")]
            study_item['assigned_reports'][related_report_item['CRGReportID']] = report_item
    
        result['related_studies'].append(study_item)

    result['related_interventions'] = await tag_scoring_service.score_related_tags(all_related_interventions, embeddings["intervention"], "intervention")
    result['related_conditions'] = await tag_scoring_service.score_related_tags(all_related_conditions,  embeddings["condition"], "condition")
    result['related_outcomes'] = await tag_scoring_service.score_related_tags(all_related_outcomes, embeddings["outcome"], "outcome")

    return result

class ReportEmbedding(BaseModel):
    model_id: str
    main_embedding: List[float]
    author_embedding: Optional[List[float]]

class AspectEmbedding(BaseModel):
    model_id: str
    embedding: List[float]

@router.get("/reports/{report_id}/similar-studies", dependencies=[Depends(is_verified_api_call)], summary="")
async def similarity_search_studies_by_id(
    report_id: int,
    aspect: TagCategories = Query(TagCategories.default, description="This value is rarely needed. Just if you want to search studies based on a certain aspect."),
    cutoff: str = Query(None),
    k: int = Query(10),
    source: str = Query(None),
    negative_studies: List[int] = Query(None),
    negative_reports: List[int] = Query(None),
    return_details: bool = False,
    study_similarity_service: StudySimilaritySearchService = Depends(get_study_similarity_service),
    project_repo: ProjectRepository = Depends(get_project_repo),
    report_repo: ReportRepository = Depends(get_report_repo),
    vectorstore: VectorstoreService = Depends(get_vectorstore_service),
) -> List[SimilarStudy]:
    _,_, ready_report_ids = await get_vectorized_and_ready_report_ids(
        [report_id], report_repo, vectorstore
    )
    if report_id not in ready_report_ids:
        raise HTTPException(status_code=409, detail="Report is not ready for processing")

    if source is None:
        result = await study_similarity_service.get_similar_studies_by_id(
            report_id,
            aspect,
            cutoff,
            k,
            negative_studies,
            negative_reports,
            return_details,
        )
    else:
        project_id = await project_repo.get_project_id_by_report_id(report_id)
        if project_id != source:
            raise HTTPException(status_code=404, detail="Report not found in project")

        result = await study_similarity_service.get_similar_studies_by_id(
            report_id,
            aspect,
            cutoff,
            k,
            negative_studies,
            negative_reports,
            return_details,
        )
    studies = transform_raw_similar_studies(result)
    return studies

@router.get("/reports/{report_id}/similar-studies/tags", dependencies=[Depends(is_verified_api_call)], summary="")
async def search_related_tags(report_id: int, aspect: TagCategories = Query(TagCategories.interventions, description="The tag category which you are interested in"), cutoff: str = Query(None), k : int = Query(..., description="The number of related studies considered for retrieving relevant tags."), related_tag_service : RelatedTagSearchService = Depends(get_related_tag_service)):
    if aspect not in [TagCategories.interventions, TagCategories.conditions, TagCategories.outcomes]:
         raise HTTPException(status_code=501, detail="Not implemented")
    return await related_tag_service.search_related_tags_by_report_id(report_id, aspect, k, cutoff)

@router.put("/reports/{report_id}/studies/{study_id}", dependencies=[Depends(is_verified_api_call)], summary="Assign studies to a specific report in a project.", status_code=200)
async def assign_studies(report_id : int, study_id: int, report_repo : ReportRepository = Depends(get_report_repo), user_id: Optional[str] = Depends(get_user_id), vectorstore: VectorstoreService = Depends(get_vectorstore_service)):
    #TODO get corresponding project and check access rights
    await asyncio.gather(
        report_repo.append_study_link(report_id, study_id),
        vectorstore.link_report_to_study_id(report_id, study_id, user_id)
    )

    #await publish_project_update(project_id)
    
    payload = {"user": user_id, "event_type": "study::links::changed", "report_id": report_id, "original_timestamp": "-"}
    logger.info("ReportInteraction", extra={"payload": payload})

    return Response(content=None, status_code=200)

@router.delete("/reports/{report_id}/studies/{study_id}", dependencies=[Depends(is_verified_api_call)], summary="Remove assigned studies from a specific report.", status_code=200)
async def delete_assigned_studies(report_id : int, study_id: int, report_repo : ReportRepository = Depends(get_report_repo), user_id: Optional[str] = Depends(get_user_id), vectorstore: VectorstoreService = Depends(get_vectorstore_service)):
    #TODO get corresponding project and check access rights

    await asyncio.gather(
        report_repo.unlink_studies(report_id, study_id),
        vectorstore.unlink_report_from_study_id(report_id, study_id, user_id)
    )

    #await publish_project_update(project_id)

    payload = {"user": user_id, "event_type": "study::links::changed", "report_id": report_id, "original_timestamp": "-"}
    logger.info("ReportInteraction", extra={"payload": payload})

    return Response(content=None, status_code=200)

@router.post("/reports/{report_id}/studies", dependencies=[Depends(is_verified_api_call)], summary="Remove assigned studies from a specific report.", status_code=200)
async def link_to_new_study(report_id : int, study: StudyCreate, report_repo : ReportRepository = Depends(get_report_repo), study_repo : StudyRepository = Depends(get_study_repo), user_id: Optional[str] = Depends(get_user_id), vectorstore: VectorstoreService = Depends(get_vectorstore_service)):
    #TODO get corresponding project and check access rights
    new_study = await study_repo.add_study(short_name=study.shortName, study_status=study.status, countries=study.countries, duration =study.duration, number_of_participants = study.numberParticipants, comparison = study.comparison)
    study_id = new_study.CRGStudyID

    #TODO if already dailed stop here

    await asyncio.gather(
        report_repo.append_study_link(report_id, study_id),
        vectorstore.link_report_to_study_id(report_id, study_id, user_id)
    )

    #TODO orphan removal -> return error if needed

    #await publish_project_update(project_id)
    
    payload = {"user": user_id, "event_type": "study::links::changed::new", "report_id": report_id, "original_timestamp": "-"}
    logger.info("ReportInteraction", extra={"payload": payload})

    output_study = transform_to_output_studies([new_study])[0]

    return output_study