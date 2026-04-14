from fastapi import APIRouter, File, UploadFile
from fastapi import Depends, HTTPException, Query, Path
from fastapi.responses import FileResponse
import os
import json
import enum
import asyncio
import logging

from typing import List, Optional
from datetime import datetime, timezone
from pydantic import BaseModel

from dotenv import load_dotenv
from typing import List, Optional, Dict, Any

from .auth import is_verified_api_call, get_user_id, is_admin

from ..database.models import Report as DbReport, Study as DbStudy
from ..database.models import Condition as DbCondition, Intervention as DbIntervention, Design as DbDesign, Outcome as DbOutcome, Participant as DbParticipant
from ..database.models import ReportFlag as DbReportFlag

from ..utils.logger import setup_logging

from ..database.repositories.study import StudyRepository
from ..database.repositories.aspects import AspectRepository
from ..database.repositories.report import ReportRepository
from ..database import get_study_repo, get_aspect_repo, get_report_repo

from ..services import get_document_service, get_report_service, get_project_pubsub_service, DocumentService, ReportService, ProjectPubSubService
from ..services.crawler import OpenAlexService

load_dotenv()

DATABASE_VOLUME = os.getenv("DATABASE_VOLUME")
#PDF_PATH = os.path.join(DATABASE_VOLUME,"resources", "pdfs")

setup_logging("events.log")
logger = logging.getLogger(__name__)

router = APIRouter(tags=["resources"], dependencies=[Depends(is_verified_api_call)])

class ReportSources(BaseModel):
    doi: str
    links: List[str]

class Report(BaseModel):
    reportId: int
    year: int 
    title: str
    abstract: Optional[str]
    trialId: Optional[str]
    authors: List[str]
    createdAt: Optional[str]
    updatedAt: Optional[str]

class ReportFlagUpdate(BaseModel):
    message: str
    public: bool = False

class ReportFlag(BaseModel):
    reportId: int
    createdBy: str
    message: str
    public: bool
    createdAt: str

class Study(BaseModel):
    studyId: int
    shortName: str
    status: str
    countries: List[str]
    numberParticipants: Optional[str]
    duration: Optional[str]
    comparison: Optional[str]
    trialId: Optional[str]
    createdAt: Optional[str]
    updatedAt: Optional[str]

class StudyCreate(BaseModel):
    shortName: str
    status: str
    countries: List[str]
    numberParticipants: Optional[str]
    duration: Optional[str]
    comparison: Optional[str]
    trialId: Optional[str] = None

class StudyStatus(str, enum.Enum):
    closed = "Closed"
    stopped_early = "Stopped early"
    open = "Open/Ongoing"
    planned = "Planned"

class CENTRALSubmissionStatus(str, enum.Enum):
    accepted = "Accepted"
    pending = "Pending"
    rejected = "Rejected"
    not_cochrane = "Not Cochrane"

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

def load_trial_id_mapping():
    file_path = os.path.join(DATABASE_VOLUME,"resources", "trial_id_mapping.json")
    if not os.path.exists(file_path):
        return {}
    with open(file_path, "r") as json_file:
        return json.load(json_file)

cutoff_query = Query(None, description="Cutoff date: for example '2025-01-13 00:00:00' (do not retrieve items entered after that date). Usually only used for testing")
study_ids_query =  Query(None, description="List of CRGStudyIDs (used to filter your results)")
study_id_path = Path(..., description="CRGStudyID")
report_ids_query = Query(None, description="List of ReportIDs (used to filter your results)")
report_id_path = Path(..., description="ReportID")

"""
Study Endpoints
"""

def transform_to_output_studies(studies):
    result = []
    for study in studies:
        output_study = Study(
            studyId=study.CRGStudyID,
            shortName=study.ShortName,
            numberParticipants=study.NumberParticipants,
            duration=study.Duration,
            comparison=study.Comparison,
            countries=study.Countries.split("//"),
            createdAt=study.DateEntered,
            updatedAt=study.DateEdited,
            status=study.StatusofStudy,
            trialId=study.ISRCTN,
        )
        result.append(output_study)
    return result

def transform_to_output_report_flag(flag: DbReportFlag) -> ReportFlag:
    return ReportFlag(
        reportId=flag.CRGReportID,
        createdBy=flag.CreatedBy,
        message=flag.Message,
        public=flag.Public,
        createdAt=flag.DateCreated.isoformat(),
    )

@router.put("/studies", summary="Add new study to meerkat.")
async def add_study(study_params: StudyCreate, user_id = Depends(get_user_id), study_repo : StudyRepository = Depends(get_study_repo)) -> Study:
    result = await study_repo.add_study(short_name=study_params.shortName, study_status=study_params.status, countries=study_params.countries, duration =study_params.duration, number_of_participants = study_params.numberParticipants, comparison = study_params.comparison)
    return transform_to_output_studies([result])[0]

@router.get("/studies", summary="Get study details for all studies specified in the query.")
async def get_studies(study_ids: List[int] = study_ids_query, user_id = Depends(get_user_id), study_repo : StudyRepository = Depends(get_study_repo)) -> List[Study]:
    result = await study_repo.get_studies(study_ids)# _get_studies(study_ids, session)
    await asyncio.gather(*[post_report_event(-1, Event(event_type=f"study::{study_id}::visited", timestamp=datetime.now(timezone.utc).isoformat()), user_id) for study_id in study_ids])
    return transform_to_output_studies(result)

@router.get("/studies/reports", include_in_schema=False)
async def get_study_reports_by_study_ids(study_ids: List[int] = study_ids_query, cutoff: str = cutoff_query, fields: Optional[List[str]] = Query(None), study_repo : StudyRepository = Depends(get_study_repo)) -> Dict[int, List[DbReport]]:
    return await study_repo.get_study_reports_by_study_ids(study_ids, cutoff, fields)

@router.get("/studies/persons", include_in_schema=False)
async def get_study_persons(study_ids: List[int] = study_ids_query, cutoff: str = cutoff_query, normalize_names : bool = Query(False), study_repo : StudyRepository = Depends(get_study_repo)) -> Dict[int, List[str]]:
    return await study_repo.get_study_persons(study_ids, cutoff, normalize_names)

async def get_study_by_id(study_id: int = study_id_path, study_repo : StudyRepository = Depends(get_study_repo)) -> DbStudy:
    study = await study_repo.get_study_by_id(study_id)
    if study is None:
        raise HTTPException(status_code=404, detail=f"Study {study_id} not found")
    return study

@router.get("/studies/{study_id}/reports", summary="Get all reports (and corresponding data) already belonging to this study")
async def get_study_reports_by_id(study_id : int = study_id_path, study_repo : StudyRepository = Depends(get_study_repo)) -> List[Report]:

    db_reports = await study_repo.get_study_reports_by_study_id(study_id)
    result = []
    for db_report in db_reports:
        result.append(Report(
            reportId=db_report['CRGReportID'],
            year=db_report['Year'],
            title=db_report['Title'],
            abstract=db_report['Abstract'],
            trialId=db_report['TrialRegistrationID'],
            authors=db_report['Authors'].split("//"),
            createdAt=db_report['Dateentered'],
            updatedAt=db_report['DateEdited'],
        ))
    return result


@router.get("/studies/{trial_id}/study_id", summary="Get the CRGStudyID given a matching trial registration id")
async def get_study_id_by_trial_id(trial_id: str = Path(..., description="A regular trial id (e.g. ACTRN12605000202662, NCT00034892)"), cutoff: str = cutoff_query, study_repo : StudyRepository = Depends(get_study_repo)) -> List[int]:
    result = await study_repo.get_study_id_by_trial_id(trial_id, cutoff)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Trial {trial_id} not found")
    return result

@router.get("/studies/{study_id}/date_entered", summary="Get the date when the study was entered into the database")
async def get_study_date_by_id(study_id: int = study_id_path, study_repo : StudyRepository = Depends(get_study_repo)) -> str:
    result = await study_repo.get_study_date_by_id(study_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Study {study_id} not found")
    return result

@router.get("/studies/{study_id}/interventions", summary="Get interventions for a specific study (e.g. 'Placebo', 'Group Therapy', ...)")
async def get_study_interventions_single(study_id : int = study_id_path, study_repo : StudyRepository = Depends(get_study_repo)) -> List[Dict[str, Any]]:
    return await study_repo.get_study_interventions_single(study_id)

@router.get("/studies/{study_id}/conditions", summary="Get the health conditions of participants in a specific study (e.g., 'COVID-19', 'Diabetes', ...).")
async def get_study_conditions_single(study_id : int = study_id_path, study_repo : StudyRepository = Depends(get_study_repo)) -> List[Dict[str, Any]]:
    return await study_repo.get_study_conditions_single(study_id)

@router.get("/studies/{study_id}/outcomes", summary="Get outcomes for a specific study (e.g. 'Mortality', 'Hospitalization', ...)")
async def get_study_outcomes_single(study_id : int = study_id_path, study_repo : StudyRepository = Depends(get_study_repo)) -> List[Dict[str, Any]]:
    return await study_repo.get_study_outcomes_single(study_id)

@router.get("/studies/{study_id}/participants", summary="Get participant description for a specific study (e.g. Male, Female, Adult, Child, ...)")
async def get_study_participants_single(study_id : int = study_id_path, study_repo : StudyRepository = Depends(get_study_repo)) -> List[Dict[str, Any]]:
    return await study_repo.get_study_participants_single(study_id)

@router.get("/studies/{study_id}/design", summary="Get the study design of the corresponding study ('Randomized Controlled Trial', 'Controlled Clinical Trial')")
async def get_study_design_single(study_id : int = study_id_path, study_repo : StudyRepository = Depends(get_study_repo)) -> List[Dict[str, Any]]:
    return await study_repo.get_study_design_single(study_id)

@router.get("/studies/{study_id}/persons", summary="Get all persons (usually only authors) associated with a specific study")
async def get_study_persons_single(study_id : int = study_id_path, cutoff: str = cutoff_query, normalize_names : bool = Query(False), study_repo : StudyRepository = Depends(get_study_repo)) -> List[str]:
    return await study_repo.get_study_persons_single(study_id=study_id, cutoff=cutoff, normalize_names=normalize_names)

@router.get("/studies/{study_id}", summary="Get study details for a specific study.")
async def get_study_by_id_legacy(study: DbStudy = Depends(get_study_by_id), user_id = Depends(get_user_id)) -> Study:
    await post_report_event(-1, Event(event_type=f"study::{study.CRGStudyID}::visted", timestamp=datetime.now(timezone.utc).isoformat()), user_id)
    return transform_to_output_studies([study])[0]


"""
Report Endpoints
"""

@router.get("/reports", summary="Get all report details specified by id.")
async def get_all_reports(
    report_ids: List[int] = report_ids_query,
    date_from: Optional[str] = Query(None, description="Filter reports with Dateentered >= this ISO datetime (e.g. '2025-01-13 00:00:00')"),
    date_to: Optional[str] = Query(None, description="Filter reports with Dateentered <= this ISO datetime (e.g. '2025-01-31 23:59:59')"),
    report_repo: ReportRepository = Depends(get_report_repo)
) -> List[DbReport]:
    return await report_repo.get_all_reports(report_ids, date_from, date_to)

@router.get("/reports/{report_id}", summary="Get details for a specific report.")
async def get_report_by_id(report_id: int = report_id_path, report_repo: ReportRepository = Depends(get_report_repo)) -> DbReport:
    result = await report_repo.get_report_by_id(report_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")
    return result

@router.get("/reports/{report_id}/studies", summary="Get the studies linked to this specific report.")
async def get_report_studies_by_id(
    report_id: int = report_id_path,
    date_from: Optional[str] = Query(None, description="Filter studies with DateEntered >= this ISO datetime (e.g. '2025-01-13 00:00:00')"),
    date_to: Optional[str] = Query(None, description="Filter studies with DateEntered <= this ISO datetime (e.g. '2025-01-31 23:59:59')"),
    report_repo : ReportRepository = Depends(get_report_repo)
) -> List[Study]:
    result = await report_repo.get_linked_studies(report_id, date_from, date_to)
    return transform_to_output_studies(result)

@router.put("/reports/{report_id}/pdf", dependencies=[Depends(is_admin)], summary="Upload the fulltext pdf for a given report", responses={200: {"description": "PDF file uploaded successfully"}})
async def uploaed_pdf(report_id: int = report_id_path, file: UploadFile = File(None, description="PDF file to upload"), document_service : DocumentService = Depends(get_document_service), pubsub_service : ProjectPubSubService = Depends(get_project_pubsub_service)) -> Dict[str, Any]:
    # Validate file is a PDF
    if file:
        if not file.content_type == "application/pdf":
            raise HTTPException(status_code=400, detail="File must be a PDF")
        if not file.filename.endswith(".pdf"):
            raise HTTPException(status_code=400, detail="File must have .pdf extension.")
    
    try:
        result = await document_service.upload_pdf(report_id, file)
        await pubsub_service.publish_report_update(report_id)
        return result
    except:
        raise HTTPException(status_code=500, detail=f"Failed to save PDF.")
    
@router.get("/reports/{report_id}/pdf", summary="Get the fulltext pdf for a given report", responses={200: {"description": "The PDF file of the report.","content": {"application/pdf": {"schema": {"type": "string","format": "binary"}}}}})
async def get_pdf(report_id : int, document_service : DocumentService = Depends(get_document_service),user_id = Depends(get_user_id)) -> FileResponse:
    try:
        pdf_path = await document_service.get_path(report_id)
        await post_report_event(-1, Event(event_type=f"report::{report_id}::downloaded", timestamp=datetime.now(timezone.utc).isoformat()), user_id)
        return FileResponse(pdf_path, media_type="application/pdf", filename=f"{report_id}.pdf")
    except:
        raise HTTPException(status_code=404, detail="PDF file not found.")

@router.delete("/reports/{report_id}/pdf", dependencies=[Depends(is_admin)], summary="Delete the fulltext pdf for a given report")
async def delete_pdf(report_id : int, document_service : DocumentService = Depends(get_document_service)) -> Dict[str, Any]:
    try:
        return await document_service.delete_pdf(report_id)
    except Exception as e:
        if str(e) == "Report not found":
            raise HTTPException(status_code=404, detail=f"Report {report_id} not found")
        raise HTTPException(status_code=500, detail="Failed to delete PDF.")
    
@router.get("/reports/{report_id}/fulltext", summary="Get the parsed fulltext for a given report")
async def get_fulltext(report_id: int = report_id_path, document_service : DocumentService = Depends(get_document_service)) -> str:
    try:
        return await document_service.get_fulltext(report_id, fast=False)
    except Exception as e:
        if str(e) == "Upstream request timed out":
            raise HTTPException(status_code=504, detail="Upstream request timed out.")

@router.get("/reports/{report_id}/sources", summary="Get fulltext links for a report via OpenAlex (by DOI)")
async def get_report_fulltext_links(report_id: int = report_id_path, report_repo: ReportRepository = Depends(get_report_repo)) -> ReportSources:
    # Get the report from the database
    report = await report_repo.get_report_by_id(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")
    doi = report.DOI
    if not doi:
        return ReportSources(doi="", links=[])
    service = OpenAlexService()
    links = await service.get_pdf_links_by_doi(doi)
    return ReportSources(doi=doi, links=links)
    
@router.get("/reports/{report_id}/metadata", summary="Get pdf metadata.")
async def get_pdf_metadata(report_id: int = report_id_path, report_service : ReportService = Depends(get_report_service)) -> Dict:
    return await report_service.get_metadata(report_id)
    try:
        return await report_service.get_metadata(report_id)
    except Exception as e:
        if str(e) == "Upstream request timed out":
            raise HTTPException(status_code=504, detail="Upstream request timed out.")

@router.get("/reports/{report_id}/trial_ids", summary="Get related trial ids.")
async def get_report_trial_ids(report_id: int = report_id_path, include_fulltext : bool = Query(False, description="Also consider the fulltext for the trial id search."), report_service : ReportService = Depends(get_report_service)) -> List[str]:
    result = await report_service.get_trial_ids(report_id, include_fulltext)
    if result is None:
        raise HTTPException(status_code=404, detail="Report not found.")
    return result

@router.get("/reports/{report_id}/flag", summary="Get your report flag for a specific report.")
async def get_report_flag(report_id: int = report_id_path, report_repo: ReportRepository = Depends(get_report_repo)) -> Optional[ReportFlag]:
    report = await report_repo.get_report_by_id(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")

    flag = await report_repo.get_report_flag(report_id)
    if flag is None:
        return None

    return transform_to_output_report_flag(flag)

@router.put("/reports/{report_id}/flag", summary="Create or edit your report flag for a specific report.")
async def upsert_report_flag(
    payload: ReportFlagUpdate,
    report_id: int = report_id_path,
    report_repo: ReportRepository = Depends(get_report_repo),
) -> ReportFlag:
    try:
        flag = await report_repo.upsert_report_flag(
            report_id=report_id,
            message=payload.message,
            public=payload.public,
        )
        return transform_to_output_report_flag(flag)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")

@router.delete("/reports/{report_id}/flag", status_code=204, summary="Delete your report flag for a specific report.")
async def delete_report_flag(report_id: int = report_id_path, report_repo: ReportRepository = Depends(get_report_repo)):
    report = await report_repo.get_report_by_id(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")

    await report_repo.delete_report_flag(report_id)
    return None

@router.post("/reports/{report_id}/events", summary="Track UI events related to the corresponding report.", description="Attach UI events using a timestamp and reasonable event_types for example 'start' when the report is first clicked and 'end' when a final selection is made or 'ui_interaction' for report-related UI interactions. Feel free to use other descriptive event types.")
async def post_report_event(report_id : int, event: Event, user_id = Depends(get_user_id), report_repo : ReportRepository = Depends(get_report_repo)):
    if report_id != -1 and await report_repo.get_report_by_id(report_id) is None:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")
    
    if not user_id:
        user_id = "anonymous"
    payload = {"user": user_id, "event_type": event.event_type, "report_id": report_id, "original_timestamp": event.timestamp}
    logger.info("ReportInteraction", extra={"payload": payload})

    return payload

@router.post("/events", summary="Track general UI events.", description="Track general UI events using a timestamp and reasonable event_types for example 'login', 'logout', 'ui_interaction' or 'idle'. Feel free to use other descriptive event types.")
async def post_event(event: Event, user_id = Depends(get_user_id)):
     
    if not user_id:
        user_id = "anonymous"

    payload = {"user": user_id, "event_type": event.event_type, "original_timestamp": event.timestamp}
    logger.info("GeneralInteraction", extra={"payload": payload})

    return payload
    
"""
Aspect Endpoints
"""

@router.get("/participants/by_studies", summary="Get participant attributes grouped by studies.", include_in_schema=False)
async def get_study_participants(study_ids: List[int] = study_ids_query, study_repo : StudyRepository = Depends(get_study_repo)) -> Dict[int, List[str]]:
    return await study_repo.get_study_participants(study_ids)

@router.get("/participants", summary="Get all participant attributes or filter them by id.", include_in_schema=False)
async def get_all_participants(ids: List[int] = Query(None,description="If you are only interested in specific participant attributes. Leave this blank for retrieving all participant attributes."), aspect_repo : AspectRepository = Depends(get_aspect_repo)) -> List[DbParticipant]:
    return await aspect_repo.get_all_participants(ids)

@router.get("/design/by_studies", summary="Get study designs grouped by studies.", include_in_schema=False)
async def get_study_design(study_ids: List[int] = study_ids_query, study_repo : StudyRepository = Depends(get_study_repo)) -> Dict[int, List[str]]:
    return await study_repo.get_study_design(study_ids)

@router.get("/design", summary="Get all study design items or filter them by id.", include_in_schema=False)
async def get_all_design(ids: List[int] = Query(None,description="If you are only interested in specific design items. Leave this blank for retrieving all design items."), aspect_repo : AspectRepository = Depends(get_aspect_repo)) -> List[DbDesign]:
    return await aspect_repo.get_all_designs(ids)

@router.get("/interventions/by_studies", summary="Get interventions grouped by studies.")
async def get_study_interventions(study_ids: List[int] = study_ids_query, study_repo : StudyRepository = Depends(get_study_repo)) -> Dict[int, List[Dict[str, Any]]]:
    return await study_repo.get_study_interventions(study_ids)

@router.get("/interventions", summary="Get all intervention items or filter them by id." )
async def get_all_interventions(ids: List[int] = Query(None,description="If you are only interested in specific interventions. Leave this blank for retrieving all interventions."),aspect_repo : AspectRepository = Depends(get_aspect_repo)) -> List[DbIntervention]:
    return await aspect_repo.get_all_interventions(ids)

@router.get("/conditions/by_studies", summary="Get conditions grouped by studies.")
async def get_study_conditions(study_ids: List[int] = study_ids_query, study_repo : StudyRepository = Depends(get_study_repo)):
    return await study_repo.get_study_conditions(study_ids)

@router.get("/conditions", summary="Get all condition items or filter them by id.", description="Conditions might be for example 'Diabetes', 'Schizophrenia', ... ") 
async def get_all_conditions(ids: List[int] = Query(None, description="If you are only interested in specific conditions. Leave this blank for retrieving all conditions."), aspect_repo : AspectRepository = Depends(get_aspect_repo)) -> List[DbCondition]:
    return await aspect_repo.get_all_conditions(ids)

@router.get("/outcomes/by_studies", summary="Get outcomes grouped by studies.")
async def get_study_outcomes(study_ids: List[int] = study_ids_query, study_repo : StudyRepository = Depends(get_study_repo)):
    return await study_repo.get_study_outcomes(study_ids)

@router.get("/outcomes", summary="Get all study outcome items or filter them by id.", description="Outcomes might be for example 'Mortality', 'Quality of Life', etc. These items are linked to studies.")
async def get_all_outcomes(ids: List[int] = Query(None,description="If you are only interested in specific outcomes. Leave this blank for retrieving all outcomes."), aspect_repo : AspectRepository = Depends(get_aspect_repo)) -> List[DbOutcome]:
    return await aspect_repo.get_all_outcomes(ids)

@router.get("/countries", summary="Get all study countries or filter them by prefix.")
async def get_all_countries(prefix: Optional[str] = Query(None, description="Filter countries by prefix (case-insensitive)."), aspect_repo : AspectRepository = Depends(get_aspect_repo)) -> List[str]:    
    return await aspect_repo.get_all_countries(prefix)
    
"""
Other Endpoints
"""

@router.get("/trial/studies", include_in_schema=False)
async def get_possible_trial_ids_by_report(study_repo: StudyRepository = Depends(get_study_repo)):
    await study_repo.get_all_studies_connected_to_trial_id()
