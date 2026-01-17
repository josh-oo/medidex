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

from .auth import is_verified_api_call, get_user_id

from ..database.models import Report, Study
from ..database.models import Condition, Intervention, Design, Outcome, Participant

from ..utils.pdf.processor import process_pdf
from ..utils.postprocessing import normalize_author_names
from ..utils.logger import setup_logging

from ..database.repositories.study import StudyRepository
from ..database.repositories.aspects import AspectRepository
from ..database.repositories.report import ReportRepository
from ..database import get_study_repo, get_aspect_repo, get_report_repo

load_dotenv()

DATABASE_VOLUME = os.getenv("DATABASE_VOLUME")
PDF_PATH = os.path.join(DATABASE_VOLUME,"resources", "pdfs")

setup_logging("events.log")
logger = logging.getLogger(__name__)

router = APIRouter(tags=["resources"], dependencies=[Depends(is_verified_api_call)])

class ReportResponse(Report):
    PDFLinks: Optional[str] = None

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

class StudyParams(BaseModel):
    short_name: str
    status_of_study: StudyStatus
    countries: List[str]
    central_submission_status :CENTRALSubmissionStatus
    duration: str
    number_of_participants : int
    comparison : str

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
    
def load_author_frequencies():
    file_path = os.path.join(DATABASE_VOLUME, "resources", "author_frequencies.json")
    if not os.path.exists(file_path):
        return {}
    with open(file_path, "r") as json_file:
        return json.load(json_file)
    
trial_id_mapping = load_trial_id_mapping()
author_frequencies = load_author_frequencies()

cutoff_query = Query(None, description="Cutoff date: for example '2025-01-13 00:00:00' (do not retrieve items entered after that date). Usually only used for testing")
study_ids_query =  Query(None, description="List of CRGStudyIDs (used to filter your results)")
study_id_path = Path(..., description="CRGStudyID")
report_ids_query = Query(None, description="List of CRGReportIDs (used to filter your results)")
report_id_path = Path(..., description="CRGReportIDs")

"""
Study Endpoints
"""

@router.put("/studies", summary="Add new study to meerkat.", response_model=Study)
async def add_study(study_params: StudyParams, user_id = Depends(get_user_id), study_repo : StudyRepository = Depends(get_study_repo)) -> Study:
    result = await study_repo.add_study(short_name=study_params.short_name, study_status=study_params.status_of_study, countries=study_params.countries, duration =study_params.duration, central_submission_status = study_params.central_submission_status, number_of_participants = study_params.number_of_participants, comparison = study_params.comparison) #_add_study(study_params, user_id, session)
    await post_report_event(-1, Event(event_type=f"study::{result.CRGStudyID}::created", timestamp=datetime.now(timezone.utc).isoformat()),user_id)
    return result

@router.get("/studies", summary="Get study details for all studies specified in the query.")
async def get_studies(study_ids: List[int] = study_ids_query, user_id = Depends(get_user_id), study_repo : StudyRepository = Depends(get_study_repo)) -> List[Study]:
    result = await study_repo.get_studies(study_ids)# _get_studies(study_ids, session)
    await asyncio.gather(*[post_report_event(-1, Event(event_type=f"study::{study_id}::visited", timestamp=datetime.now(timezone.utc).isoformat()), user_id) for study_id in study_ids])
    return result

@router.get("/studies/reports", include_in_schema=False)
async def get_study_reports_by_study_ids(study_ids: List[int] = study_ids_query, cutoff: str = cutoff_query, fields: Optional[List[str]] = Query(None), study_repo : StudyRepository = Depends(get_study_repo)) -> Dict[int, List[Report]]:
    return await study_repo.get_study_reports_by_study_ids(study_ids, cutoff, fields)

@router.get("/studies/persons", include_in_schema=False)
async def get_study_persons(study_ids: List[int] = study_ids_query, cutoff: str = cutoff_query, normalize_names = Query(False), study_repo : StudyRepository = Depends(get_study_repo)) -> Dict[int, List[str]]:
    return await study_repo.get_study_persons(study_ids, cutoff, normalize_names)

async def get_study_by_id(study_id: int = study_id_path, study_repo : StudyRepository = Depends(get_study_repo)) -> Study:
    study = await study_repo.get_study_by_id(study_id)
    if study is None:
        raise HTTPException(status_code=404, detail=f"Study {study_id} not found")
    return study

@router.get("/studies/{study_id}/reports", summary="Get all reports (and corresponding data) already belonging to this study")
async def get_study_reports_by_id(study_id : int = study_id_path, study_repo : StudyRepository = Depends(get_study_repo)) -> List[ReportResponse]:
    return await study_repo.get_study_reports_by_study_id(study_id)

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
async def get_study_persons_single(study_id : int = study_id_path, cutoff: str = cutoff_query, normalize_names = Query(False), study_repo : StudyRepository = Depends(get_study_repo)) -> List[str]:
    return await study_repo.get_study_persons_single(study_id=study_id, cutoff=cutoff, normalize_names=normalize_names)

#LEGACY
@router.get("/studies/{study_id}", summary="Get study details for a specific study.")
async def get_study_by_id_legacy(study: Study = Depends(get_study_by_id), user_id = Depends(get_user_id)) -> List[Study]:
    #TODO remove this
    await post_report_event(-1, Event(event_type=f"study::{study.CRGStudyID}::visted", timestamp=datetime.now(timezone.utc).isoformat()), user_id)
    return [study]


"""
Report Endpoints
"""

@router.get("/reports", summary="Get all report details specified by id.")
async def get_all_reports(
    report_ids: List[int] = report_ids_query,
    date_from: Optional[str] = Query(None, description="Filter reports with Dateentered >= this ISO datetime (e.g. '2025-01-13 00:00:00')"),
    date_to: Optional[str] = Query(None, description="Filter reports with Dateentered <= this ISO datetime (e.g. '2025-01-31 23:59:59')"),
    report_repo: ReportRepository = Depends(get_report_repo)
) -> List[Report]:
    return await report_repo.get_all_reports(report_ids, date_from, date_to)

@router.put("/reports/pdf", summary="Upload the fulltext pdf for a given report", responses={200: {"description": "PDF file uploaded successfully"}})
async def uploaed_pdf(file: UploadFile = File(..., description="PDF file to upload"), report_repo : ReportRepository = Depends(get_report_repo)) -> Dict[str, Any]:
    # Validate file is a PDF
    if not file.content_type == "application/pdf":
        raise HTTPException(status_code=400, detail="File must be a PDF")
    
    # Extract report number from filename (e.g., "00123.pdf" -> 123)
    filename = file.filename
    if not filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must have .pdf extension")
    
    try:
        report_number = int(filename.replace(".pdf", "").lstrip("0") or "0")
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Filename '{filename}' does not contain a valid report number")
    
    # Check if report number exists in database
    report = await report_repo.get_report_by_id()
    
    if report is None:
        raise HTTPException(status_code=404, detail=f"Report number {report_number} not found in database")
    
    # Ensure PDF directory exists
    os.makedirs(PDF_PATH, exist_ok=True)
    
    # Use the original filename from the upload
    file_path = os.path.join(PDF_PATH, filename)
    
    try:
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)
        #Extract and save metadata
        process_pdf(file_path)
        return {
            "report_id": report.CRGReportID,
            "report_number": report_number,
            "filename": filename,
            "file_path": file_path,
            "size_bytes": len(content)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save PDF: {str(e)}")

@router.get("/reports/pdf_number", include_in_schema=False)
async def get_pdf_numbers_by_report_ids(report_ids: List[int] = report_ids_query, report_repo: ReportRepository = Depends(get_report_repo)) -> Dict[int, int]:
    return await report_repo.get_pdf_numbers_by_report_ids(report_ids)

@router.get("/reports/{report_id}", summary="Get details for a specific report.")
async def get_report_by_id(report_id: int = report_id_path, report_repo: ReportRepository = Depends(get_report_repo)) -> Report:
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
    return await report_repo.get_linked_studies(report_id, date_from, date_to)

@router.get("/reports/{report_id}/pdf_number", summary="Get the associated pdf number (which is not tze CRGReportID) for a certain report.")
async def get_pdf_number_by_report_id(report_id: int = report_id_path, report_repo: ReportRepository = Depends(get_report_repo)) -> int:
    result = await report_repo.get_pdf_numbers_by_report_ids(report_ids=[report_id])
    if report_id not in result:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")
    return result[report_id]

@router.get("/reports/{report_id}/pdf", summary="Get the fulltext pdf for a given report", responses={200: {"description": "The PDF file of the report.","content": {"application/pdf": {"schema": {"type": "string","format": "binary"}}}}})
async def get_pdf(report_id : int, report_repo : ReportRepository = Depends(get_report_repo),user_id = Depends(get_user_id)) -> FileResponse:
    pdf_path = await report_repo.get_pdf_path(report_id)

    if not pdf_path:
        raise HTTPException(status_code=404, detail="PDF file not found.")
    await post_report_event(-1, Event(event_type=f"report::{report_id}::downloaded", timestamp=datetime.now(timezone.utc).isoformat()), user_id)
    return FileResponse(pdf_path, media_type="application/pdf")

@router.get("/reports/{report_id}/pdf/metadata", summary="Get pdf metadata.")
async def get_pdf_metadata(report_id:int, report_repo: ReportRepository = Depends(get_report_repo)) -> Dict:
    result = await report_repo.get_pdf_metadata(report_id)
    if not result:
        raise HTTPException(status_code=404, detail="PDF file not found.")
    return result

@router.get("/reports/{report_id}/trial_ids", summary="Get related trial ids.")
async def get_report_trial_ids(report_id : int, include_fulltext : bool = Query(False, description="Also consider the fulltext for the trial id search."), report_repo : ReportRepository = Depends(get_report_repo)) -> List[str]:
    result = await report_repo.get_report_trial_ids(report_id, include_fulltext)
    if result is None:
        raise HTTPException(status_code=404, detail="Report not found.")
    return result

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
async def get_all_participants(ids: List[int] = Query(None,description="If you are only interested in specific participant attributes. Leave this blank for retrieving all participant attributes."), aspect_repo : AspectRepository = Depends(get_aspect_repo)) -> List[Participant]:
    return await aspect_repo.get_all_participants(ids)

@router.get("/design/by_studies", summary="Get study designs grouped by studies.", include_in_schema=False)
async def get_study_design(study_ids: List[int] = study_ids_query, study_repo : StudyRepository = Depends(get_study_repo)) -> Dict[int, List[str]]:
    return await study_repo.get_study_design(study_ids)

@router.get("/design", summary="Get all study design items or filter them by id.", include_in_schema=False)
async def get_all_design(ids: List[int] = Query(None,description="If you are only interested in specific design items. Leave this blank for retrieving all design items."), aspect_repo : AspectRepository = Depends(get_aspect_repo)) -> List[Design]:
    return await aspect_repo.get_all_designs(ids)

@router.get("/interventions/by_studies", summary="Get interventions grouped by studies.")
async def get_study_interventions(study_ids: List[int] = study_ids_query, study_repo : StudyRepository = Depends(get_study_repo)) -> Dict[int, List[Dict[str, Any]]]:
    return await study_repo.get_study_interventions(study_ids)

@router.get("/interventions", summary="Get all intervention items or filter them by id." )
async def get_all_interventions(ids: List[int] = Query(None,description="If you are only interested in specific interventions. Leave this blank for retrieving all interventions."),aspect_repo : AspectRepository = Depends(get_aspect_repo)) -> List[Intervention]:
    return await aspect_repo.get_all_interventions(ids)

@router.get("/conditions/by_studies", summary="Get conditions grouped by studies.")
async def get_study_conditions(study_ids: List[int] = study_ids_query, study_repo : StudyRepository = Depends(get_study_repo)):
    return await study_repo.get_study_conditions(study_ids)

@router.get("/conditions", summary="Get all condition items or filter them by id.", description="Conditions might be for example 'Diabetes', 'Schizophrenia', ... ") 
async def get_all_conditions(ids: List[int] = Query(None, description="If you are only interested in specific conditions. Leave this blank for retrieving all conditions."), aspect_repo : AspectRepository = Depends(get_aspect_repo)) -> List[Condition]:
    return await aspect_repo.get_all_conditions(ids)

@router.get("/outcomes/by_studies", summary="Get outcomes grouped by studies.")
async def get_study_outcomes(study_ids: List[int] = study_ids_query, study_repo : StudyRepository = Depends(get_study_repo)):
    return await study_repo.get_study_outcomes(study_ids)

@router.get("/outcomes", summary="Get all study outcome items or filter them by id.", description="Outcomes might be for example 'Mortality', 'Quality of Life', etc. These items are linked to studies.")
async def get_all_outcomes(ids: List[int] = Query(None,description="If you are only interested in specific outcomes. Leave this blank for retrieving all outcomes."), aspect_repo : AspectRepository = Depends(get_aspect_repo)) -> List[Outcome]:
    return await aspect_repo.get_all_outcomes(ids)

@router.get("/countries", summary="Get all study countries or filter them by prefix.")
async def get_all_countries(prefix: Optional[str] = Query(None, description="Filter countries by prefix (case-insensitive)."), aspect_repo : AspectRepository = Depends(get_aspect_repo)) -> List[str]:    
    return await aspect_repo.get_all_countries(prefix)
    
"""
Other Endpoints
"""

def get_author_frequencies(authors: List[str]) -> Dict[str, int]:
    normalized_author_names = normalize_author_names(authors=authors)
    
    result = {}
    for author in normalized_author_names:
        if author in author_frequencies:
            result[author] = author_frequencies[author]
        else:
            result[author] = 1

    return result

@router.get("/trial/studies", include_in_schema=False)
async def get_possible_trial_ids_by_report(study_repo: StudyRepository = Depends(get_study_repo)):
    await study_repo.get_all_studies_connected_to_trial_id()
