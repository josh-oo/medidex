
from fastapi import APIRouter, Request
from fastapi import Query, Path, UploadFile, File, HTTPException, Depends, BackgroundTasks, Body, Form
from fastapi.responses import Response, StreamingResponse
from typing import Dict, List, Optional, Any, Tuple, Set
import json
import logging
import io

import httpx

from ..utils.trial_registration_id import extract_trial_id
from ..utils.ris_parser import parse_file
from ..utils.logger import setup_logging

import hashlib
import asyncio

from .auth import is_verified_api_call, is_admin, get_user_id

from ..database import get_project_repo, get_report_repo

from ..database import ReportRepository
from ..database import ProjectRepository
from ..database.repositories.study import DuplicateShortNameError

from ..database.models import Report as DbReport, Project as DbProject

from ..services import get_vectorstore_service, VectorstoreService
from ..services import MaintenanceService
from ..services import AutomationService
from ..services import LinkageService
from ..services import get_project_pubsub_service, ProjectPubSubService
from ..services.report import DocumentService
from ..services.crawler import OpenAlexService
from ..services.report import CrawlerService, DoclingService

from ..database.sessions import AsyncSessionLocal, AsyncSession

from ..background.wrapper import (
    run_process_report_background,
    run_start_automation_background,
)

from ..utils.dto import Report, StudyCreate,BatchedReport, Project, ProjectAssignee, ProjectDetails, ProjectTask, studies_to_dto

router = APIRouter(tags=["projects"])

setup_logging("events.log")
logger = logging.getLogger(__name__)

# Limit concurrent bot processing across reports
agent_process_semaphore = asyncio.Semaphore(10)
pdf_semaphore = asyncio.Semaphore(1)
write_semaphore = asyncio.Semaphore(1)
vectorstore_semaphore = asyncio.Semaphore(8)

project_id_path = Path(..., description="The projects's id")

class _InMemoryPdfUpload:
    def __init__(self, content: bytes, filename: str = "autosearch.pdf"):
        self._buffer = io.BytesIO(content)
        self.filename = filename
        self.content_type = "application/pdf"

    async def read(self) -> bytes:
        self._buffer.seek(0)
        return self._buffer.read()


def _looks_like_pdf(content: bytes, content_type: str) -> bool:
    if not content:
        return False
    if content.startswith(b"%PDF-"):
        return True
    return "application/pdf" in (content_type or "").lower()


async def _download_pdf_bytes(client: httpx.AsyncClient, url: str) -> Optional[bytes]:
    try:
        response = await client.get(url)
        response.raise_for_status()
    except Exception:
        return None

    payload = response.content
    if _looks_like_pdf(payload, response.headers.get("content-type", "")):
        return payload
    return None

import traceback

async def process_report_pdf(
    client,
    report : DbReport,
    document_service: DocumentService,
) -> None:
    #async with pdf_semaphore:

    if report.report_number > 0: #if report already has pdf
        return None

    try:
        service = OpenAlexService()
        links = await service.get_pdf_links_by_doi(report.doi)

        for link in links:
            print("Link: ", link)
            payload = await _download_pdf_bytes(client, link)
            if payload is None:
                continue

            upload_file = _InMemoryPdfUpload(payload)
            print("Success download: ", report.id,flush=True)
            #await document_service.upload_pdf(report.id, upload_file)
            #print("Success upload: ", report.id,flush=True)
            return upload_file

    except Exception as exc:
        #print(f"Upload failed: {report_id} Exc {exc}")
        print(f"Upload failed: {report.id} Exc {exc}\n{traceback.format_exc()}",flush=True)
        logger.warning(
            "Auto PDF processing failed for report %s in project %s: %s",
            report.id,
            exc,
        )
    return None

async def process_report(reports : List[DbReport], project_id : str, vectorstore : VectorstoreService, maintenance_service : MaintenanceService, pubsub_service: ProjectPubSubService, document_service : DocumentService, user_id : str):    
    timeout = httpx.Timeout(30.0, connect=10.0)

    async def load_pdf(report, client):
        async with write_semaphore:
            async with AsyncSessionLocal() as write_session:
                project_repo = ProjectRepository(db=write_session,user_id=user_id)
                report_repo = ReportRepository(db=write_session,user_id=user_id)
                document_service = DocumentService(report_repo=report_repo,crawler_service=CrawlerService(), docling_service=DoclingService())
                project = await project_repo.get_project_by_id(project_id)
                if not project: #if project already deleted
                    return
                pdf_file = await process_report_pdf(client, report, document_service)
                if pdf_file:
                    print("Start upload: ", report.id,flush=True)
                    await document_service.upload_pdf(report.id, pdf_file)
                print("Start Set auto searched: ", report.id,flush=True)
                await project_repo.set_report_auto_searched_pdf(report.id)
                await write_session.commit()
                await pubsub_service.publish_project_update(project_id)

    async def prepare_vectorstore(report):
        async with vectorstore_semaphore:
            async with AsyncSessionLocal() as session:
                project_repo = ProjectRepository(db=session, user_id=user_id)
                project = await project_repo.get_project_by_id(project_id)
                if not project: #if project already deleted
                    return
                await vectorstore.add_report_to_vectorstore(report)
                await pubsub_service.publish_project_update(project_id)

    async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
        load_pdf_tasks = [load_pdf(report, client) for report in reports]
        prepare_vectorstore_tasks = [prepare_vectorstore(report) for report in reports]
        await asyncio.gather(*prepare_vectorstore_tasks + load_pdf_tasks)

        # Finalize with a new session
        async with AsyncSessionLocal() as session:
            project_repo = ProjectRepository(db=session, user_id=user_id)
            await finalize_project_upload(project_id, project_repo, vectorstore, maintenance_service, pubsub_service)

async def finalize_project_upload(project_id : str, project_repo : ProjectRepository, vectorstore : VectorstoreService, maintenance_service : MaintenanceService, pubsub_service: ProjectPubSubService):
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
    await pubsub_service.publish_project_update(project_id)


async def get_project_by_id(project_id: str, project_repo: ProjectRepository = Depends(get_project_repo)) -> DbProject:
    project = await project_repo.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project

async def get_vectorized_and_ready_report_ids(project_id, project_repo : ProjectRepository, report_repo: ReportRepository, vectorstore: VectorstoreService) -> Tuple[Set[int], Set[int], Set[int]]:
    
    report_ids = await project_repo.get_project_associated_report_ids(project_id)
    if not report_ids:
        return set(), set(), set()

    # Run database query first, then vectorstore query to avoid concurrent session usage
    reports_with_pdf = await report_repo.get_pdf_availabilities(report_ids)
    reports_with_embedding = await vectorstore.reports_exist(report_ids)
    
    embedded_reports = set(reports_with_embedding)
    pdf_ready_reports = set(reports_with_pdf)
    ready_reports = embedded_reports & pdf_ready_reports
    return embedded_reports, pdf_ready_reports, ready_reports

async def get_project_report_status(
    project_id,
    project_repo: ProjectRepository,
    report_repo: ReportRepository,
    vectorstore: VectorstoreService,
) -> Dict[int, Dict[str, bool]]:

    report_ids = await project_repo.get_project_associated_report_ids(project_id)
    if not report_ids:
        return {}

    embedded_reports, pdf_ready_reports, _ = await get_vectorized_and_ready_report_ids(
        project_id,
        project_repo,
        report_repo,
        vectorstore,
    )

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
    linkage_service: LinkageService,
    agent_service: AutomationService,
    pubsub_service: ProjectPubSubService,
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
            await linkage_service.link_existing_study_to_report(report_id, int(predicted_study_id), "bot")
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
                    await linkage_service.create_study_and_link_to_report(report_id, study_payload, "bot")
                    break
                except DuplicateShortNameError:
                    study_payload.shortName = study_payload.shortName + appendix #if the name is already taken try the next name

        await pubsub_service.publish_project_update(project_id)
        logger.info("Agent processing completed for report %s in project %s", report_id, project_id)

async def get_project_stats(
    project: DbProject = Depends(get_project_by_id),
    report_repo: ReportRepository = Depends(get_report_repo),
    vectorstore: VectorstoreService = Depends(get_vectorstore_service),
    project_repo: ProjectRepository = Depends(get_project_repo),
) -> ProjectDetails:
    
    report_ids = await project_repo.get_project_associated_report_ids(project.id)
    auto_searched_pdf_count = await project_repo.get_auto_searched_pdf_count_for_project(project.id)
    confirmed_report_count = await project_repo.get_confirmed_report_count_for_project(project.id)

    embedded_reports, reports_with_pdf, ready_reports = await get_vectorized_and_ready_report_ids(project.id, project_repo, report_repo, vectorstore)

    assignees = await project_repo.get_project_assignees(project.id)
    assignee_ids = [user_id for user_id, _ in assignees if user_id]

    ready_for_review_count = 0
    if assignee_ids:
        completion_map = await project_repo.get_report_completion_by_users(project.id)
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
        projectId=project.id,
        name=project.description,
        createdAt=project.date_created,
        numberReportsTotal=len(report_ids),
        numberReportsPreProcessed=len(embedded_reports),
        numberReportsReadyForProcessing=len(ready_reports),
        numberReportsWithPdf=len(reports_with_pdf),
        numberReportsReadyForReview=ready_for_review_count,
        numberReportsAutoSearchedPdf=auto_searched_pdf_count,
        numberReportsConfirmed=confirmed_report_count,
        owner=project.uploaded_by,
        assignees=assignee_payload,
    )

async def start_automation(
    project_id: str,
    project_repo: ProjectRepository,
    report_repo: ReportRepository,
    vectorstore: VectorstoreService,
    linkage_service: LinkageService,
    agent_service: AutomationService,
    pubsub_service: ProjectPubSubService,
) -> None:
    pubsub = await pubsub_service.subscribe_to_project(project_id)
    try:
        while True:
            report_ids = await project_repo.get_project_associated_report_ids(project_id)
            if not report_ids:
                return

            report_status = await get_project_report_status(project_id, project_repo, report_repo, vectorstore)
            completion_map = await project_repo.get_report_completion_by_users(project_id)
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
                await pubsub_service.get_next_project_update(pubsub)
                continue

            processing_tasks = [
                agent_process_report(
                    project_id,
                    report_id,
                    linkage_service,
                    agent_service,
                    pubsub_service,
                )
                for report_id in ready_report_ids
            ]
            await asyncio.gather(*processing_tasks)
    finally:
        await pubsub_service.unsubscribe_from_project(project_id, pubsub)


@router.get("/tasks",dependencies=[Depends(is_verified_api_call)], summary="Get pending review tasks for the authenticated user.", description="Returns all projects the user is assigned to along with their personal study-link counts.")
async def get_user_tasks(project_repo: ProjectRepository = Depends(get_project_repo), report_repo: ReportRepository = Depends(get_report_repo), vectorstore: VectorstoreService = Depends(get_vectorstore_service),) -> List[ProjectTask]:
    user_id = getattr(project_repo, "user_id", None)
    if not user_id:
        return []

    projects = await project_repo.get_assigned_projects()
    if not projects:
        return []

    user_link_counts = await project_repo.get_user_link_counts_by_project()

    # Pre-fetch all report IDs sequentially to avoid concurrent database access
    #project_report_ids = {}
    #for project in projects:
    #    report_ids = await project_repo.get_project_associated_report_ids(project.id)
    #    project_report_ids[project.id] = report_ids or set()

    # Now run vectorstore queries concurrently (no database session conflicts)
    progress_tasks = [
        get_vectorized_and_ready_report_ids(project.id, project_repo, report_repo, vectorstore)
        for project in projects
    ]
    progress_results = await asyncio.gather(*progress_tasks)

    tasks: List[ProjectTask] = []
    for project, (_,_, ready_for_processing) in zip(projects, progress_results):
        project_payload = Project(
            projectId=project.id,
            name=project.description,
            owner=project.uploaded_by or "",
            createdAt=project.date_created,
            numberReportsReadyForProcessing=len(ready_for_processing),
        )
        tasks.append(
            ProjectTask(
                project=project_payload,
                numberReportsProcessed=user_link_counts.get(project.id, 0),
            )
        )

    return tasks

@router.post("/projects", dependencies=[Depends(is_admin)], summary="Upload a project (batch of new reports that need to be assigned to studies) (usually in the .ris file format)", status_code=201) 
async def upload_file(background_tasks: BackgroundTasks, file: UploadFile = File(..., description="The .ris file containing all the articles you want to process."), projectName: str = Form(...), project_repo : ProjectRepository = Depends(get_project_repo), pubsub_service: ProjectPubSubService = Depends(get_project_pubsub_service), user_id : str = Depends(get_user_id)):

    entries = await parse_file(file)

    reports = []
    fingerprint_string = ""
    for entry in entries:
        title = entry.get('primary_title', None)
        if not title:
            title = entry.get('title', "")

        authors = entry.get('authors', [])
        abstract = entry.get('abstract', None)
        report_number = int(entry.get('research_notes', -1))

        trial_ids = extract_trial_id(title=title, abstract=abstract, authors=authors)
        if len(trial_ids) == 1:
            trial_ids = trial_ids[0]
        else:
            trial_ids = None

        authors_str = "//".join(authors)

        safe_title = title.replace("\n", " ")

        try:
            safe_abstract = abstract.replace("\n", " ") if abstract is not None else ""
        except AttributeError as e:
            print(f"UPLOAD FILE: Error replacing in abstract for entry: {entry}\nException: {e}")
            safe_abstract = str(abstract) if abstract is not None else ""

        report = DbReport(
            title=safe_title,
            abstract=safe_abstract,
            authors=authors_str,
            report_number=report_number,
            journal=entry.get('secondary_title', None),
            year=int(entry.get('year', None)),
            volume= entry.get('volume', None),
            issue=entry.get('note', None),
            pages=entry.get('start_page', None),
            language=entry.get('language', None),
            publisher=entry.get('publisher', None),
            city=entry.get('place_published', None),
            doi=entry.get('doi', None),
            trial_registration_id=trial_ids,
            copy_status= "Copy Obtained" if report_number != 0 else "Seeking Source",
            report_type_id=0, #TODO ask alessandro
            publication_type_id=1, #TODO ask alessandro
            #TODO dup_string missing
            #original_title: Optional[str] TODO
        )

        fingerprint_string += "|".join([
            safe_title or "",
            safe_abstract or "",
            authors_str or "",
        ])

        reports.append(report)

    project_id = hashlib.sha256(fingerprint_string.encode()).hexdigest()

    reports = await project_repo.add_new_project(project_id,projectName,reports)
    if reports is None:
        raise HTTPException(status_code=409, detail="Project already exists")
    # schedule background tasks
    #for report in reports:
    #    print("Report provcess appended")
    report_ids = [report.id for report in reports]
    background_tasks.add_task(run_process_report_background, project_id, report_ids, user_id, process_report)
    
    await pubsub_service.publish_project_update(project_id)

    #TODO disabled for legacy reasons
    #reports_dict = [report.dict() for report in reports]
    #JSONResponse(content={"project_id": project_id, "project_description": file.filename, "reports": reports_dict}, status_code=201)

    return Response(status_code=201)

@router.get("/projects", dependencies=[Depends(is_admin)], summary="Get an overview of all current projects.", description="For each project the current progress of embedding calculation and the number of already assigned reports is returned")
async def get_available_projects(project_repo: ProjectRepository = Depends(get_project_repo), report_repo: ReportRepository = Depends(get_report_repo), vectorstore : VectorstoreService = Depends(get_vectorstore_service)) -> List[ProjectDetails]:
    # Get all projects
    projects = await project_repo.get_all_projects()

    # Process all projects in parallel
    tasks = [
        get_project_stats(
            project=project,
            report_repo=report_repo,
            vectorstore=vectorstore,
            project_repo=project_repo,
        )
        for project in projects
    ]
    project_responses = await asyncio.gather(*tasks)

    return project_responses

@router.get("/projects/{project_id}", dependencies=[Depends(is_admin)], summary="Get a specific project by id.",description="Returns details and progress information for a single project identified by project id.")
async def get_project_stats_by_id(project_stats : Project = Depends(get_project_stats)) -> Project:
    return project_stats

@router.delete("/projects/{project_id}", dependencies=[Depends(is_admin)], summary="Delete a project and all its associated reports (including calculated embedding vectors) from the temporary storage.", status_code=204)
async def delete_project(project_id : str, project_repo: ProjectRepository = Depends(get_project_repo), vectorstore: VectorstoreService = Depends(get_vectorstore_service), pubsub_service: ProjectPubSubService = Depends(get_project_pubsub_service)):
    #Deletes the project and through cascade and triggers everythig related to it
    project = await project_repo.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    report_ids = await project_repo.get_project_associated_report_ids(project_id)

    await project_repo.delete_project(project_id)
    
    await vectorstore.delete_vectors_by_report_ids(report_ids)

    await pubsub_service.publish_project_update(project_id)
    
    return Response(status_code=204)

@router.post("/projects/{project_id}/assignees", dependencies=[Depends(is_admin)],summary="Assign a user to a project",status_code=201,)
async def assign_user_to_project(
    background_tasks: BackgroundTasks,
    project_id: str = project_id_path,
    assignee_user_id: str = Body(..., embed=False, description="User ID to assign"),
    model: str = Query("gpt-5-nano", description="LLM model name to use for study prediction"),
    project_repo: ProjectRepository = Depends(get_project_repo),
    pubsub_service: ProjectPubSubService = Depends(get_project_pubsub_service),
    user_id : str = Depends(get_user_id)
):
    try:
        project = await project_repo.get_project_by_id(project_id)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        created = await project_repo.add_project_assignee(project_id, assignee_user_id)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    if not created:
        raise HTTPException(status_code=409, detail="User already assigned to project")

    await pubsub_service.publish_project_update(project_id)

    if assignee_user_id == "bot":
        background_tasks.add_task(run_start_automation_background, project_id, user_id, model, start_automation)

    return ProjectAssignee(userId=assignee_user_id, numberReportsLinked=0)

@router.delete("/projects/{project_id}/assignees/{user_id}", dependencies=[Depends(is_admin)],summary="Remove a user assignment from a project",status_code=204,)
async def remove_user_from_project(
    project_id: str = project_id_path,
    user_id: str = Path(..., description="The user ID to remove from the project"),
    project_repo: ProjectRepository = Depends(get_project_repo),
    pubsub_service: ProjectPubSubService = Depends(get_project_pubsub_service),
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

    await pubsub_service.publish_project_update(project_id)

    return Response(status_code=204)

@router.get("/projects/{project_id}/reports", dependencies=[Depends(is_verified_api_call)], summary="Get all reports in a project by project id.")
async def get_project_reports(
    project_id : str,
    project_repo: ProjectRepository = Depends(get_project_repo),
    report_repo: ReportRepository = Depends(get_report_repo),
    vectorstore: VectorstoreService = Depends(get_vectorstore_service),
    raw: bool = Query(False, description="Include unprocessed items."),
) -> List[BatchedReport]:
    
    project = await project_repo.get_project_by_id(project_id)
    report_ids = await project_repo.get_project_associated_report_ids(project_id)
    _, reports_with_pdf, ready_report_ids = await get_vectorized_and_ready_report_ids(
            project_id, project_repo, report_repo, vectorstore
    )

    if raw and project is not None: #if the current user is the owner allow everything except for items not yet autosearched
        ready_report_ids = await project_repo.get_auto_searched_pdf_for_project(project_id)

    reports = await report_repo.get_all_reports(report_ids)
    all_linked_studies = await report_repo.get_linked_studies_for_reports(report_ids)
    report_flags = await report_repo.get_report_flags_for_reports(report_ids)

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
async def get_project_annotations(project: DbProject = Depends(get_project_by_id), project_repo: ProjectRepository = Depends(get_project_repo)) -> Dict[int, Dict[str, List[Dict[str, Any]]]]:
    
    report_ids = await project_repo.get_project_associated_report_ids(project.id)

    if not report_ids:
        return {}

    assignees = await project_repo.get_project_assignees(project.id)
    assignee_ids = {user_id for user_id, _ in assignees if user_id}
    if not assignee_ids:
        return {}

    completion_map = await project_repo.get_report_completion_by_users(project.id)
    annotated_report_ids = [
        report_id
        for report_id in report_ids
        if assignee_ids.issubset(completion_map.get(report_id, set()))
    ]

    if not annotated_report_ids:
        return {}

    return await project_repo.get_project_annotations_by_assignees(
        project.id,
        assignee_ids,
        annotated_report_ids,
    )

@router.get("/projects/{project_id}/stream",dependencies=[], summary="Stream updated batch information.")
async def stream_project_updates(
    project_id: str,
    request: Request,
    pubsub_service: ProjectPubSubService = Depends(get_project_pubsub_service),
) -> StreamingResponse:
    async def event_stream():
        pubsub = await pubsub_service.subscribe_to_project(project_id)
        try:
            while True:
                if await request.is_disconnected():
                    break

                data = await pubsub_service.get_next_project_update(pubsub)
                yield f"data: {data}\n\n"
        finally:
            await pubsub_service.unsubscribe_from_project(project_id, pubsub)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
