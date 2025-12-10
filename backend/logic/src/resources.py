from fastapi import APIRouter, File, UploadFile
from fastapi import Depends, HTTPException, Query, Path
from fastapi.responses import FileResponse
import os

from dotenv import load_dotenv

from .auth import is_verified_api_call, get_user_info
from typing import List, Optional
import enum
from pydantic import BaseModel

from dotenv import load_dotenv
from typing import List, Optional, Dict, Any

import re
import json

from nameparser import HumanName

from sqlmodel import select, func, text, delete
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

from .utils.database_models import Report, Study, StudyCondition, StudyDesign, StudyIntervention, StudyOutcome, StudyParticipant, StudyReport
from .utils.database_models import Condition, Intervention, Design, Outcome, Participant
from .utils.database_models import Batch, ReportAdded, StudyReportAdded

from .utils.pdf.processor import process_pdf
from .utils.trial_registration_id import extract_trial_id

from datetime import datetime, timezone
import unicodedata

load_dotenv()

DATABASE_VOLUME = os.getenv("DATABASE_VOLUME")
POSTGRES_USER = os.getenv("POSTGRES_USER")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
POSTGRES_DB_RESOURCES = os.getenv("POSTGRES_DB_RESOURCES")
POSTGRES_HOST = os.getenv("POSTGRES_HOST")
POSTGRES_PORT = os.getenv("POSTGRES_PORT")

router = APIRouter(tags=["resources"], dependencies=[Depends(is_verified_api_call)])

#DATABASE_URL = "sqlite+aiosqlite:///" + os.path.join(DATABASE_VOLUME,"resources","meerkat.db")
DATABASE_URL = f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB_RESOURCES}"
PDF_PATH = os.path.join(DATABASE_VOLUME,"resources", "pdfs")
METADATA_PATH = os.path.join(DATABASE_VOLUME,"resources", "pdf_metadata")

engine = create_async_engine(DATABASE_URL, echo=False)

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

async def get_session() -> AsyncSession:
    async with AsyncSession(engine) as session:
        yield session

def load_trial_id_mapping():
    file_path = os.path.join(DATABASE_VOLUME,"resources", "trial_id_mapping.json")
    if not os.path.exists(file_path):
        return {}
    with open(file_path, "r") as json_file:
        return json.load(json_file)

def load_trial_person_mapping():
    file_path = os.path.join(DATABASE_VOLUME,"resources", "trial_person_mapping.json")
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
    
trial_person_mapping = load_trial_person_mapping()
trial_id_mapping = load_trial_id_mapping()
author_frequencies = load_author_frequencies()

def convert_to_id_based_dict(rows, multi_values=True):
    result = {}
    for key, value in rows:
        if multi_values:
            if key not in result.keys():
                result[key] = []
            result[key].append(value)
        else:
            result[key] = value

    return result

cutoff_query = Query(None, description="Cutoff date: for example '2025-01-13 00:00:00' (do not retrieve items entered after that date). Usually only used for testing")
study_ids_query =  Query(None, description="List of CRGStudyIDs (used to filter your results)")
study_id_path = Path(..., description="CRGStudyID")
report_ids_query = Query(None, description="List of CRGReportIDs (used to filter your results)")
report_id_path = Path(..., description="CRGReportIDs")

"""
Study Endpoints
"""

@router.put("/studies", summary="Add new study to meerkat.")
async def add_study(study_params: StudyParams, session: AsyncSession = Depends(get_session)) -> Study:
    return await _add_study(study_params, session)

@router.get("/studies", summary="Get study details for all studies specified in the query.")
async def get_studies(study_ids: List[int] = study_ids_query, session: AsyncSession = Depends(get_session)) -> List[Study]:
    return await _get_studies(study_ids, session)

@router.get("/studies/reports", include_in_schema=False)
async def get_study_reports_by_ids(study_ids: List[int] = study_ids_query, cutoff: str = cutoff_query, fields: Optional[List[str]] = Query(None), session: AsyncSession = Depends(get_session)) -> Dict[int, List[Report]]:
    return await _get_study_reports_by_ids(study_ids, cutoff, fields, session)

@router.get("/studies/persons", include_in_schema=False)
async def get_study_persons(study_ids: List[int] = study_ids_query, cutoff: str = cutoff_query, normalize_names = Query(False), session: AsyncSession = Depends(get_session)) -> Dict[int, List[str]]:
    return await _get_study_persons(study_ids,cutoff,normalize_names,session)

@router.get("/studies/{study_id}", summary="Get study details for a specific study.")
async def get_study_by_id(study_id: int = study_id_path, session: AsyncSession = Depends(get_session)) -> Study:
    study = await session.get(Study, study_id)
    if study is None:
        raise HTTPException(status_code=404, detail=f"Study {study_id} not found")
    return study

@router.get("/studies/{study_id}/reports", summary="Get all reports (and corresponding data) already belonging to this study")
async def get_study_reports_by_id(study: Study = Depends(get_study_by_id), session: AsyncSession = Depends(get_session)) -> List[ReportResponse]:
    result = (await get_study_reports_by_ids(study_ids=[study.CRGStudyID], fields=None, cutoff=None, session=session))
    if study.CRGStudyID in result:
        return result[study.CRGStudyID]
    raise []

@router.get("/studies/{trial_id}/study_id", summary="Get the CRGStudyID given a matching trial registration id")
async def get_study_id_by_trial_id(trial_id: str = Path(..., description="A regular trial id (e.g. ACTRN12605000202662, NCT00034892)"), cutoff: str = cutoff_query, session: AsyncSession = Depends(get_session)) -> List[int]:
    result = (await _get_study_id_by_trial_ids([trial_id],cutoff,session))
    if trial_id in result:
        return result[trial_id]
    raise HTTPException(status_code=404, detail=f"Trial {trial_id} not found")

@router.get("/studies/{study_id}/date_entered", summary="Get the date when the study was entered into the database")
async def get_study_date_by_id(study_id: int = study_id_path, session: AsyncSession = Depends(get_session)) -> str:
    stmt = select(Study.DateEntered).where(Study.CRGStudyID == study_id)
    result = (await session.execute(stmt)).scalar_one_or_none()
    if result is None:
        raise HTTPException(status_code=404, detail=f"Study {study_id} not found")
    return result

@router.get("/studies/{study_id}/interventions", summary="Get interventions for a specific study (e.g. 'Placebo', 'Group Therapy', ...)")
async def get_study_interventions_single(study: Study = Depends(get_study_by_id), session: AsyncSession = Depends(get_session)) -> List[str]:
    result = await get_study_interventions(study_ids=[study.CRGStudyID], session=session)
    if study.CRGStudyID in result.keys():
        return result[study.CRGStudyID]
    raise []

@router.get("/studies/{study_id}/conditions", summary="Get the health conditions of participants in a specific study (e.g., 'COVID-19', 'Diabetes', ...).")
async def get_study_conditions_single(study: Study = Depends(get_study_by_id), session: AsyncSession = Depends(get_session)) -> List[str]:
    result =await get_study_conditions(study_ids=[study.CRGStudyID], session=session)
    if study.CRGStudyID in result.keys():
        return result[study.CRGStudyID]
    raise []

@router.get("/studies/{study_id}/outcomes", summary="Get outcomes for a specific study (e.g. 'Mortality', 'Hospitalization', ...)")
async def get_study_outcomes_single(study: Study = Depends(get_study_by_id), session: AsyncSession = Depends(get_session)) -> List[str]:
    result =await get_study_outcomes(study_ids=[study.CRGStudyID], session=session)
    if study.CRGStudyID in result.keys():
        return result[study.CRGStudyID]
    raise []

@router.get("/studies/{study_id}/participants", summary="Get participant description for a specific study (e.g. Male, Female, Adult, Child, ...)")
async def get_study_participants_single(study: Study = Depends(get_study_by_id), session: AsyncSession = Depends(get_session)) -> List[str]:
    result = await get_study_participants(study_ids=[study.CRGStudyID], session=session)
    if study.CRGStudyID in result.keys():
        return result[study.CRGStudyID]
    raise []

@router.get("/studies/{study_id}/design", summary="Get the study design of the corresponding study ('Randomized Controlled Trial', 'Controlled Clinical Trial')")
async def get_study_design_single(study: Study = Depends(get_study_by_id), session: AsyncSession = Depends(get_session)) -> List[str]:
    result = await get_study_design(study_ids=[study.CRGStudyID], session=session)
    if study.CRGStudyID in result.keys():
        return result[study.CRGStudyID]
    raise []

@router.get("/studies/{study_id}/persons", summary="Get all persons (usually only authors) associated with a specific study")
async def get_study_persons_single(study: Study = Depends(get_study_by_id), cutoff: str = cutoff_query, session: AsyncSession = Depends(get_session)) -> List[str]:
    result = await get_study_persons(study_ids=[study.CRGStudyID], cutoff=cutoff, session=session)
    if study.CRGStudyID in result:
        return result[study.CRGStudyID]
    return []


"""
Report Endpoints
"""

@router.get("/reports", summary="Get all report details specified by id.")
async def get_all_reports(
    report_ids: List[int] = report_ids_query,
    date_from: Optional[str] = Query(None, description="Filter reports with Dateentered >= this ISO datetime (e.g. '2025-01-13 00:00:00')"),
    date_to: Optional[str] = Query(None, description="Filter reports with Dateentered <= this ISO datetime (e.g. '2025-01-31 23:59:59')"),
    session: AsyncSession = Depends(get_session)
) -> List[Report]:
    stmt = select(Report).where((Report.Title.isnot(None)) | (Report.Abstract.isnot(None)))
    if report_ids:
        stmt = stmt.where(Report.CRGReportID.in_(report_ids))
    # Dateentered filtering (string compare works with ISO-like 'YYYY-MM-DD HH:MM:SS')
    if date_from:
        stmt = stmt.where(Report.Dateentered >= date_from)
    if date_to:
        stmt = stmt.where(Report.Dateentered <= date_to)
    return (await session.execute(stmt)).scalars().all()

@router.put("/reports/pdf", summary="Upload the fulltext pdf for a given report", responses={200: {"description": "PDF file uploaded successfully"}})
async def uploaed_pdf(file: UploadFile = File(..., description="PDF file to upload"), session: AsyncSession = Depends(get_session)) -> Dict[str, Any]:
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
    stmt = select(Report.CRGReportID).where(Report.ReportNumber == report_number)
    result = await session.execute(stmt)
    report_id = result.scalar_one_or_none()
    
    if report_id is None:
        raise HTTPException(status_code=404, detail=f"Report number {report_number} not found in database")
    
    # Ensure PDF directory exists
    os.makedirs(PDF_PATH, exist_ok=True)
    
    # Use the original filename from the upload
    file_path = os.path.join(PDF_PATH, filename)
    
    try:
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)
        process_pdf(file_path)
        return {
            "report_id": report_id,
            "report_number": report_number,
            "filename": filename,
            "file_path": file_path,
            "size_bytes": len(content)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save PDF: {str(e)}")

@router.get("/reports/pdf_number", include_in_schema=False)
async def get_pdf_numbers_by_report_ids(report_ids: List[int] = report_ids_query, session: AsyncSession = Depends(get_session)) -> Dict[int, int]:
    stmt = select(Report.CRGReportID, Report.ReportNumber).where(Report.CRGReportID.in_(report_ids))
    rows = (await session.execute(stmt)).all()
    return {row[0]: row[1] for row in rows}

@router.get("/reports/{report_id}", summary="Get details for a specific report.")
async def get_reports_by_id(report_id: int = report_id_path, session: AsyncSession = Depends(get_session)) -> Report:
    return await _get_report_by_id(report_id, session)

@router.get("/reports/{report_id}/studies", summary="Get the studies linked to this specific report.")
async def get_report_studies_by_id(
    report_id: int = report_id_path,
    date_from: Optional[str] = Query(None, description="Filter studies with DateEntered >= this ISO datetime (e.g. '2025-01-13 00:00:00')"),
    date_to: Optional[str] = Query(None, description="Filter studies with DateEntered <= this ISO datetime (e.g. '2025-01-31 23:59:59')"),
    session: AsyncSession = Depends(get_session),
    user = Depends(get_user_info),
) -> List[Study]:
    user_id = None
    if user:
        user_id = user['id']
    return await _get_report_studies_by_id(report_id, date_from, date_to, user_id, session)

@router.get("/reports/{report_id}/pdf_number", summary="Get the associated pdf number (which is not tze CRGReportID) for a certain report.")
async def get_pdf_number_by_report_id(report_id: int = report_id_path, session: AsyncSession = Depends(get_session)) -> int:
    result = await get_pdf_numbers_by_report_ids(report_ids=[report_id], session=session)
    if report_id not in result:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")
    return result[report_id]

@router.get("/reports/{report_id}/pdf", summary="Get the fulltext pdf for a given report", responses={200: {"description": "The PDF file of the report.","content": {"application/pdf": {"schema": {"type": "string","format": "binary"}}}}})
async def get_pdf(report_number = Depends(get_pdf_number_by_report_id)) -> FileResponse:
    pdf_name = str(report_number).zfill(5) + ".pdf"
    file_name = os.path.join(PDF_PATH, pdf_name)

    if not os.path.exists(file_name):
        raise HTTPException(status_code=404, detail="PDF file not found.")
    return FileResponse(file_name, media_type="application/pdf")

@router.get("/reports/{report_id}/pdf/metadata", summary="Get pdf metadata.")
async def get_pdf_metadata(report_number = Depends(get_pdf_number_by_report_id)) -> FileResponse:
    report_number = str(report_number).zfill(5) 
    file_name_json = os.path.join(METADATA_PATH, report_number + ".json")
    file_name_pdf = os.path.join(PDF_PATH, report_number + ".pdf")

    if os.path.exists(file_name_json):
        with open(file_name_json, "r") as f:
            return json.load(f)
    elif os.path.exists(file_name_pdf ):
        return await process_pdf(PDF_PATH, METADATA_PATH, report_number)
    raise HTTPException(status_code=404, detail="PDF file not found.")

@router.get("/reports/{report_id}/trial_ids", summary="Get related trial ids.")
async def get_report_trial_ids(report = Depends(get_reports_by_id), include_fulltext : bool = Query(False, description="Also consider the fulltext for the trial id search.")) -> List[str]:
    if not report:
        raise HTTPException(status_code=404, detail="Report not found.")
    if include_fulltext:
        meta_data = await get_pdf_metadata(report.ReportNumber)
        return meta_data['trial_id']
    authors = [item.strip() for item in report.Authors.split("//")]
    all_ids = extract_trial_id(report.Title, report.Abstract, authors)
    return all_ids
    
"""
Aspect Endpoints
"""

@router.get("/participants/by_studies", summary="Get participant attributes grouped by studies.", include_in_schema=False)
async def get_study_participants(study_ids: List[int] = study_ids_query, session: AsyncSession = Depends(get_session)) -> Dict[int, List[str]]:
    return await _get_study_participants(study_ids, session)

@router.get("/participants", summary="Get all participant attributes or filter them by id.", include_in_schema=False)
async def get_all_participants(ids: List[int] = Query(None,description="If you are only interested in specific participant attributes. Leave this blank for retrieving all participant attributes."),session: AsyncSession = Depends(get_session)) -> List[Participant]:
    stmt = select(Participant)
    if ids:
        stmt = stmt.where(Participant.ParticipantsID.in_(ids))
    return (await session.execute(stmt)).all()

@router.get("/design/by_studies", summary="Get study designs grouped by studies.", include_in_schema=False)
async def get_study_design(study_ids: List[int] = study_ids_query, session: AsyncSession = Depends(get_session)) -> Dict[int, List[str]]:
    return await _get_study_design(study_ids, session)

@router.get("/design", summary="Get all study design items or filter them by id.", include_in_schema=False)
async def get_all_design(ids: List[int] = Query(None,description="If you are only interested in specific design items. Leave this blank for retrieving all design items."),session: AsyncSession = Depends(get_session)) -> List[Design]:
    stmt = select(Design)
    if ids:
        stmt = stmt.where(Design.DesignID.in_(ids))
    return (await session.execute(stmt)).all()

@router.get("/interventions/by_studies", summary="Get interventions grouped by studies.")
async def get_study_interventions(study_ids: List[int] = study_ids_query, session: AsyncSession = Depends(get_session)) -> Dict[int, List[Dict[str, Any]]]:
    return await _get_study_interventions(study_ids,session)

@router.get("/interventions", summary="Get all intervention items or filter them by id." )
async def get_all_interventions(ids: List[int] = Query(None,description="If you are only interested in specific interventions. Leave this blank for retrieving all interventions."),session: AsyncSession = Depends(get_session)) -> List[Intervention]:
    return await _get_all_interventions(ids, session)

@router.get("/conditions/by_studies", summary="Get conditions grouped by studies.")
async def get_study_conditions(study_ids: List[int] = study_ids_query, session: AsyncSession = Depends(get_session)):
    return await _get_study_conditions(study_ids, session)

@router.get("/conditions", summary="Get all condition items or filter them by id.", description="Conditions might be for example 'Diabetes', 'Schizophrenia', ... ") 
async def get_all_conditions(ids: List[int] = Query(None, description="If you are only interested in specific conditions. Leave this blank for retrieving all conditions."), session: AsyncSession = Depends(get_session)) -> List[Condition]:
    return await _get_all_conditions(ids, session)

@router.get("/outcomes/by_studies", summary="Get outcomes grouped by studies.")
async def get_study_outcomes(study_ids: List[int] = study_ids_query, session: AsyncSession = Depends(get_session)):
    return await _get_study_outcomes(study_ids, session)

@router.get("/outcomes", summary="Get all study outcome items or filter them by id.", description="Outcomes might be for example 'Mortality', 'Quality of Life', etc. These items are linked to studies.")
async def get_all_outcomes(ids: List[int] = Query(None,description="If you are only interested in specific outcomes. Leave this blank for retrieving all outcomes."), session: AsyncSession = Depends(get_session)) -> List[Outcome]:
    return await _get_all_outcomes(ids, session)


"""
Other Endpoints
"""

@router.get("/mappings/report_study", summary="Get the mapping from CRGReportIDs to CRGStudyIds.")
async def get_mapping_report_study(session: AsyncSession = Depends(get_session)) -> Dict[int, List[int]]:
    stmt = select(StudyReport.CRGReportID, StudyReport.CRGStudyID)
    rows = (await session.execute(stmt)).all()
    return convert_to_id_based_dict(rows)

@router.get("/mappings/study_report", summary="Get the mapping from CRGStudyIDs to CRGReportIds.")
async def get_mapping_report_study(session: AsyncSession = Depends(get_session)) -> Dict[int, List[int]]:
    stmt = select(StudyReport.CRGStudyID, StudyReport.CRGReportID)
    rows = (await session.execute(stmt)).all()
    return convert_to_id_based_dict(rows)


def normalize_author_names(authors: List[str]) -> List[str]:
    def get_person_from_trial_id(author):
        author = author.strip()
        trial_id = author.replace("/", "-")
    
        if trial_id not in trial_person_mapping:
            return [author]
        authors = trial_person_mapping[trial_id]

        processed_authors = []
        for author in authors:
            hn = HumanName(author)
            # Get last name
            last = hn.last
    
            # Get initials (first and middle names)
            initials = ''.join(part[0].upper() for part in [hn.first, hn.middle] if part)

            processed_authors.append(f"{last} {initials}")

        return list(set(processed_authors))
    
    def normalize_author_name(name):
        # Basic prep
        name = name.strip()
        name = unicodedata.normalize('NFKC', name)

        if re.search(r'\d', name):
            return None

        # Transform: Remove everything except letters
        clean_name = re.sub(r'[^a-zA-Z]', '', name)

        if not clean_name:
            return None

        # Validate: Start Upper, End Upper, Contains Lower
        if (clean_name[0].isupper() and 
            clean_name[-1].isupper() and 
            any(c.islower() for c in clean_name)):
            
            return clean_name
        
        return None

    normalized_authors = []
    for author in authors:
        current_authors = [author]
        if author in trial_person_mapping:
            current_authors = get_person_from_trial_id(author)
        for current_author in current_authors:
            normalized_author = normalize_author_name(current_author)
            if normalized_author:
                normalized_authors.append(normalized_author)
    
    return normalized_authors

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
async def get_possible_trial_ids_by_report(session: AsyncSession = Depends(get_session)):
    # Register REGEXP for SQLite
    session.connection().connection.create_function("REGEXP", 2, lambda expr, item: 1 if item and re.search(expr, item) else 0)

    # Define the reusable regex pattern block
    query_regex = """
        (COLUMN_NAME REGEXP 'ISRCTN[0-9]{8}'
        OR COLUMN_NAME REGEXP 'ChiCTR[0-9]{10}'
        OR COLUMN_NAME REGEXP 'ChiCTR\\.TRC\\.[0-9]{8}'
        OR COLUMN_NAME REGEXP 'ChiCTR\\.IOR\\.[0-9]{8}'
        OR COLUMN_NAME REGEXP 'ChiCTR-(INR|IPR|POC|IIR|IOQ|OPC)-[0-9]{8}'
        OR COLUMN_NAME REGEXP 'ACTR(N|[0-9])[0-9]{14}'
        OR COLUMN_NAME REGEXP 'CTRI(/|-)[0-9]{4}(/|-)[0-9]{2,3}(/|-)[0-9]{6}'
        OR COLUMN_NAME REGEXP 'NCT[0-9]{8}'
        OR COLUMN_NAME REGEXP 'DRKS[0-9]{8}'
        OR COLUMN_NAME REGEXP 'NL-OMON[0-9]{5}'
        OR COLUMN_NAME REGEXP 'NL[0-9]{4}'
        OR COLUMN_NAME REGEXP 'IRCT[0-9]{11,13}N[0-9]+'
        OR COLUMN_NAME REGEXP 'KCT[0-9]{7}'
        OR COLUMN_NAME REGEXP 'TCTR[0-9]{11}'
        OR COLUMN_NAME REGEXP 'RBR-.{7}'
        OR COLUMN_NAME REGEXP 'CTIS[0-9]{4}-[0-9]{6}-[0-9]{2}-[0-9]{2}'
        OR COLUMN_NAME REGEXP '(JPRN-)?UMIN[0-9]{9}'
        OR COLUMN_NAME REGEXP '(JPRN-)?JapicCTI-[0-9]{6}'
        OR COLUMN_NAME REGEXP 'JPRN-jRCTs?[0-9]{9,10}'
        OR COLUMN_NAME REGEXP 'EUCTR[0-9]{4}-[0-9]{6}-[0-9]{2}'
        OR COLUMN_NAME REGEXP 'ITMCTR[0-9]{10}'
        OR COLUMN_NAME REGEXP 'PACTR[0-9]{15}'
        OR COLUMN_NAME REGEXP 'NTR[0-9]{4,5}'
        OR COLUMN_NAME REGEXP 'UKCRNID[0-9]{4,5}'
        OR COLUMN_NAME REGEXP 'SLCTR-[0-9]{4}-[0-9]{3}'
        OR COLUMN_NAME REGEXP 'HKCTR-[0-9]{4}'
        OR COLUMN_NAME REGEXP 'M[0-9]{2}-[0-9]{3}'
        OR COLUMN_NAME REGEXP 'MCT-[0-9]{5}')
    """

    # --- Query 1: studies with trial IDs in ShortName ---
    query_studies = text(f"""
        SELECT CRGStudyID
        FROM tblStudy
        WHERE FALSE OR {query_regex.replace("COLUMN_NAME", "ShortName")}
    """)
    result_studies = (await session.execute(query_studies)).fetchall()
    all_studies = [row[0] for row in result_studies]

    # --- Query 2: reports with single-trial studies in Authors field ---
    query_reports = text(f"""
        SELECT sr.CRGStudyID
        FROM tblReport r
        JOIN tblStudyReport sr ON r.CRGReportID = sr.CRGReportID
        WHERE r.Authors NOT LIKE '%//%'
          AND sr.CRGReportID IN (
              SELECT CRGReportID
              FROM tblStudyReport
              GROUP BY CRGReportID
              HAVING COUNT(DISTINCT CRGStudyID) = 1
          )
          AND {query_regex.replace("COLUMN_NAME", "r.Authors")}
    """)
    result_reports = (await session.execute(query_reports)).fetchall()
    all_reports = [row[0] for row in result_reports]

    return all_studies + all_reports
    


"""
Helper functions
"""

async def get_study_reports_by_ids_internal(study_ids: List[int], cutoff: str, fields: Optional[List[str]]):
    async with AsyncSession(engine) as session:
        return await _get_study_reports_by_ids(study_ids, cutoff, fields, session)

async def _get_study_reports_by_ids(study_ids: List[int], cutoff: str, fields: Optional[List[str]], session: AsyncSession) -> Dict[int, List[Report]]:
    #cutoff = cutoff or date.today().isoformat()

    # If no fields are specified, select all columns from Report
    if fields is None:
        # Use Report.__table__.columns to dynamically get all field names
        selected_fields = [col.name for col in Report.__table__.columns]
    else:
        # Validate provided field names exist on the Report model
        report_columns = {col.name for col in Report.__table__.columns}
        invalid_fields = [f for f in fields if f not in report_columns]
        if invalid_fields:
            raise HTTPException(status_code=400,detail=f"Invalid field(s): {', '.join(invalid_fields)}")
        selected_fields = fields

    # --- Optimized Query ---
    stmt = (
        select(StudyReport.CRGStudyID, *[getattr(Report, f) for f in selected_fields])
        .join(Report, Report.CRGReportID == StudyReport.CRGReportID)
    )

    if study_ids:
        stmt = stmt.where(StudyReport.CRGStudyID.in_(study_ids))

    if cutoff:
        stmt = stmt.where(Report.Dateentered < cutoff)


    rows = (await session.execute(stmt)).all()

    grouped = {}
    for row in rows:
        study_id = row[0]  # first item is StudyID
        report_data = dict(zip(selected_fields, row[1:]))  # remaining fields as dict
        grouped.setdefault(study_id, []).append(report_data)
    return grouped

async def get_study_persons_internal(study_ids: List[int], cutoff: str, normalize_names : bool):
    async with AsyncSession(engine) as session:
        return await _get_study_persons(study_ids, cutoff, normalize_names, session)

async def _get_study_persons(study_ids: List[int], cutoff: str, normalize_names : bool, session: AsyncSession) -> Dict[int, List[str]]:
    stmt = (
        select(StudyReport.CRGStudyID.label("StudyID"), Report.Authors)
        .join(Report, Report.CRGReportID == StudyReport.CRGReportID)
    )

    if cutoff:
        stmt = stmt.where(Report.Dateentered < cutoff)

    if study_ids is not None:
        stmt = stmt.where(StudyReport.CRGStudyID.in_(study_ids))

    rows = (await session.execute(stmt)).all()


    final_result = {}

    for item in rows:
        key = item[0]
        value = item[1]
        authors = [author.strip() for author in value.split("//")]
        if normalize_names:
            authors = normalize_author_names(authors=authors)

        final_result[key] = authors

    return final_result

async def get_study_id_by_trial_ids_internal(trial_id: List[str], cutoff: str) ->  Dict[str, List[int]]:
    async with AsyncSession(engine) as session:
        return await _get_study_id_by_trial_ids(trial_id,cutoff, session)

async def _get_study_id_by_trial_ids(trial_ids: List[str], cutoff: str, session: AsyncSession) -> Dict[str, List[int]]:
    trial_ids_norm = [trial_id.replace("/", "-") for trial_id in trial_ids]
    result_map = {}

    for orig_trial_id, trial_id in zip(trial_ids, trial_ids_norm):
        alternative_ids = [trial_id]
        if trial_id in trial_id_mapping.keys():
            alternative_ids.extend(trial_id_mapping[trial_id])
        alternative_ids = [current_id.replace("/", "-") for current_id in alternative_ids]

        # Build dynamic LIKE conditions for Authors
        authors_filter = func.replace(Report.Authors, "/", "-").like(f"%{alternative_ids[0]}%")
        for current_id in alternative_ids[1:]:
            authors_filter = authors_filter | func.replace(Report.Authors, "/", "-").like(f"%{current_id}%")

        trial_filter = func.replace(Report.TrialRegistrationID, "/", "-").in_(alternative_ids)

        stmt_study = select(Study.CRGStudyID, text("'study' as source")).where(
            (Study.ShortName.in_(alternative_ids)) |
            (Study.TrialRegistrationID.in_(alternative_ids))
        )

        stmt_reports = (
            select(StudyReport.CRGStudyID, text("'report' as source"))
            .join(Report, Report.CRGReportID == StudyReport.CRGReportID)
            .where(authors_filter | trial_filter)
        )

        if cutoff is not None:
            stmt_study = stmt_study.where(Study.DateEntered < cutoff)
            stmt_reports = stmt_reports.where(Report.Dateentered < cutoff)

        combined_stmt = stmt_study.union_all(stmt_reports)
        rows = (await session.execute(combined_stmt)).all()  # [(CRGStudyID, source), ...]

        # Sort: 'study' source first, then 'report'
        sorted_rows = sorted(rows, key=lambda x: 0 if x[1] == 'study' else 1)

        # Remove duplicates, preserving order (study > report)
        seen = set()
        ordered_ids = []
        for study_id, _ in sorted_rows:
            if study_id not in seen:
                seen.add(study_id)
                ordered_ids.append(study_id)
        result_map[orig_trial_id] = ordered_ids

    return result_map

async def get_studies_internal(study_ids):
    async with AsyncSession(engine) as session:
        return await _get_studies(study_ids, session)

async def _get_studies(study_ids, session):
    stmt = select(Study)
    if study_ids:
        stmt = stmt.where(Study.CRGStudyID.in_(study_ids))
    return (await session.execute(stmt)).scalars().all()

async def add_study_internal(study_params):
    async with AsyncSession(engine) as session:
        return await _add_study(study_params, session)

async def _add_study(study_params: StudyParams, session: AsyncSession):
    #TODO add more sophisticated checks
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    
    new_study = Study(
        ShortName=study_params.short_name,
        StatusofStudy=study_params.status_of_study.value,
        Countries="//".join(study_params.countries),
        CENTRALSubmissionStatus=study_params.central_submission_status.value,
        Duration=study_params.duration,
        NumberofParticipants=study_params.number_of_participants,
        Comparison=study_params.comparison,
        DateEntered=timestamp,
        DateEdited=timestamp,
    )
    
    session.add(new_study)
    await session.commit()
    await session.refresh(new_study)
    return new_study

async def _get_study_aspect(stmt, session):
    rows = (await session.execute(stmt)).all()  # -> [(StudyID, ID, Description), ...]

    # --- Group results by StudyID ---
    final_result: Dict[int, List[Dict[str, Any]]] = {}
    for study_id, intervention_id, description in rows:
        item = {"ID": intervention_id, "Description": description}
        final_result.setdefault(study_id, []).append(item)

    return final_result

async def get_study_interventions_internal(study_ids: List[int]):
    async with AsyncSession(engine) as session:
        return await _get_study_interventions(study_ids, session)

async def _get_study_interventions(study_ids: List[int], session: AsyncSession) -> Dict[int, List[Dict[str, Any]]]:
    stmt = (
        select(
            StudyIntervention.CRGStudyID.label("StudyID"),
            StudyIntervention.InterventionID.label("ID"),
            Intervention.InterventionDescription.label("Description"),
        )
        .join(Intervention, Intervention.InterventionID == StudyIntervention.InterventionID)
        .where(StudyIntervention.CRGStudyID.in_(study_ids))
    )

    return await _get_study_aspect(stmt,session)

async def get_study_conditions_internal(study_ids: List[int]):
    async with AsyncSession(engine) as session:
        return await _get_study_conditions(study_ids, session)

async def _get_study_conditions(study_ids: List[int], session: AsyncSession):
    stmt = (
        select(
            StudyCondition.CRGStudyID.label("StudyID"),
            StudyCondition.HealthCareConditionID.label("ID"),
            Condition.HealthCareConditionDescription.label("Description"),
        )
        .join(Condition, Condition.HealthCareConditionID == StudyCondition.HealthCareConditionID)
        .where(StudyCondition.CRGStudyID.in_(study_ids))
    )

    return await _get_study_aspect(stmt,session)

async def get_study_outcomes_internal(study_ids: List[int]):
    async with AsyncSession(engine) as session:
        return await _get_study_outcomes(study_ids, session)

async def _get_study_outcomes(study_ids: List[int] = study_ids_query, session: AsyncSession = Depends(get_session)):
    stmt = (
        select(
            StudyOutcome.CRGStudyID.label("StudyID"),
            StudyOutcome.OutcomeID.label("ID"),
            Outcome.OutcomeDescription.label("Description"),
        )
        .join(Outcome, Outcome.OutcomeID == StudyOutcome.OutcomeID)
    )

    if study_ids:
        stmt = stmt.where(StudyOutcome.CRGStudyID.in_(study_ids))

    return await _get_study_aspect(stmt,session)

async def get_study_design_internal(study_ids: List[int]):
   async with AsyncSession(engine) as session:
        return await _get_study_design(study_ids, session)

async def _get_study_design(study_ids: List[int], session: AsyncSession) -> Dict[int, List[str]]:
    stmt = (
        select(StudyDesign.CRGStudyID, Design.DesignDescription)
        .join(Design, Design.DesignID == StudyDesign.DesignID)
    )

    if study_ids:
        stmt = stmt.where(StudyDesign.CRGStudyID.in_(study_ids))

    rows = (await session.execute(stmt)).all()  # list of tuples [(StudyID, DesignDescription), ...]

    # Group by StudyID
    final_result: Dict[int, List[str]] = {}
    for study_id, description in rows:
        final_result.setdefault(study_id, []).append(description)

    return final_result

async def get_study_participants_internal(study_ids: List[int]):
    async with AsyncSession(engine) as session:
        return await _get_study_participants(study_ids, session)

async def _get_study_participants(study_ids: List[int], session: AsyncSession) -> Dict[int, List[str]]:
    stmt = (
        select(StudyParticipant.CRGStudyID, Participant.ParticipantDescription)
        .join(Participant, Participant.ParticipantsID == StudyParticipant.ParticipantsID)
    )

    if study_ids:
        stmt = stmt.where(StudyParticipant.CRGStudyID.in_(study_ids))

    rows = (await session.execute(stmt)).all()  # list of tuples [(StudyID, ParticipantDescription), ...]

    # Convert to dictionary grouped by StudyID
    final_result: Dict[int, List[str]] = {}
    for study_id, description in rows:
        final_result.setdefault(study_id, []).append(description)

    return final_result

async def get_all_interventions_internal(ids: List[int]):
    async with AsyncSession(engine) as session:
        return await _get_all_interventions(ids, session)

async def _get_all_interventions(ids: List[int],session) -> List[Intervention]:
    stmt = select(Intervention)
    if ids:
        stmt = stmt.where(Intervention.InterventionID.in_(ids))
    return (await session.execute(stmt)).scalars().all()

async def get_all_conditions_internal(ids: List[int]):
    async with AsyncSession(engine) as session:
        return await _get_all_conditions(ids, session)

async def _get_all_conditions(ids: List[int], session: AsyncSession) -> List[Condition]:
    stmt = select(Condition)
    if ids:
        stmt = stmt.where(Condition.HealthCareConditionID.in_(ids))
    return (await session.execute(stmt)).scalars().all()

async def get_all_outcomes_internal(ids: List[int]):
    async with AsyncSession(engine) as session:
        return await _get_all_outcomes(ids, session)

async def _get_all_outcomes(ids: List[int], session) -> List[Outcome]:
    stmt = select(Outcome)
    if ids:
        stmt = stmt.where(Outcome.OutcomeID.in_(ids))
    return (await session.execute(stmt)).scalars().all()

async def get_report_by_id_internal(report_id):
    async with AsyncSession(engine) as session:
        return await _get_report_by_id(report_id, session)

async def _get_report_by_id(report_id, session):
    result = await session.get(Report, report_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")
    return result

async def get_report_studies_by_id_internal(report_id, date_from=None, date_to=None, user=None):
    async with AsyncSession(engine) as session:
        return await _get_report_studies_by_id(report_id, date_from, date_to, user, session)

async def _get_report_studies_by_id(report_id, date_from, date_to, user, session):
    user = str(user) if user is not None else None #TODO remove later
    report = await session.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")
    
    stmt = (
        select(Study)
        .join(StudyReport, StudyReport.CRGStudyID == Study.CRGStudyID)
        .outerjoin(StudyReportAdded, StudyReport.StudyReportID == StudyReportAdded.StudyReportID)
        .where(StudyReport.CRGReportID == report_id)
    )
    
    # If user is provided, filter by CreatedBy
    if user:
        stmt = stmt.where((StudyReportAdded.CreatedBy == user) | (StudyReportAdded.CreatedBy.is_(None)))
    
    if date_from:
        stmt = stmt.where(Study.DateEntered >= date_from)
    if date_to:
        stmt = stmt.where(Study.DateEntered <= date_to)
    
    return (await session.execute(stmt)).scalars().all()

async def add_report_studies_by_id_internal(report_id: int, study_ids: List[int], user : str) -> Dict[str, Any]:
    """
    Create StudyReport links for the given report_id to the provided study_ids.
    """
    async with AsyncSession(engine) as session:
        return await _add_report_studies_by_id(report_id, study_ids, user, session)

async def _add_report_studies_by_id(report_id: int, study_ids: List[int], user: str, session: AsyncSession) -> Dict[str, Any]:
    """
    Internal implementation to link a report to multiple studies.

    Returns:
        {
          "report_id": int,
          "created_count": int,
          "invalid_study_ids": List[int],
          "created_links": List[Dict[str, int]]
        }
    """
    user = str(user) if user is not None else None #TODO remove later
    study_ids = study_ids or []
    if not study_ids:
        return {
            "report_id": report_id,
            "created_count": 0,
            "invalid_study_ids": [],
            "created_links": []
        }

    try:
        # Validate report exists
        report = await session.get(Report, report_id)
        if not report:
            raise HTTPException(status_code=404, detail=f"Report {report_id} not found")

        # Validate studies exist
        valid_id_rows = await session.execute(
            select(Study.CRGStudyID).where(Study.CRGStudyID.in_(study_ids))
        )
        valid_ids = set(valid_id_rows.scalars().all())
        invalid_ids = [sid for sid in study_ids if sid not in valid_ids]

        # Only delete existing links created by this user (or with no creator)
        if user:
            # Get StudyReportIDs that match the user filter
            stmt = (
                select(StudyReport.StudyReportID)
                .outerjoin(StudyReportAdded, StudyReport.StudyReportID == StudyReportAdded.StudyReportID)
                .where(StudyReport.CRGReportID == report_id)
                .where(StudyReportAdded.CreatedBy == user)
            )
            rows = (await session.execute(stmt)).scalars().all()
            if rows:
                await session.execute(
                    delete(StudyReport).where(StudyReport.StudyReportID.in_(rows))
                )
        else:
            # If no user specified, delete all existing links for this report
            await session.execute(delete(StudyReport).where(StudyReport.CRGReportID == report_id))

        # Create new links and track them in StudyReportAdded
        created_links: List[Dict[str, int]] = []
        for sid in valid_ids:
            new_study_report = StudyReport(CRGReportID=report_id, CRGStudyID=sid)
            session.add(new_study_report)
            await session.flush()  # Flush to get the StudyReportID
            
            print(f"Add user: {new_study_report.StudyReportID}", user)
            # Track who created this link
            session.add(StudyReportAdded(
                StudyReportID=new_study_report.StudyReportID,
                CreatedBy=user
            ))
            
            created_links.append({"CRGReportID": report_id, "CRGStudyID": sid})

        await session.commit()

        return {
            "report_id": report_id,
            "created_count": len(valid_ids),
            "invalid_study_ids": invalid_ids,
            "created_links": created_links
        }
    
    except HTTPException:
        await session.rollback()
        raise
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update report-study links: {str(e)}")

async def delete_report_studies_by_id_internal(report_id: int, user: str) -> Dict[str, Any]:
    """
    Delete all StudyReport links for the given report_id.
    """
    async with AsyncSession(engine) as session:
        return await _delete_report_studies_by_id(report_id, user, session)

async def _delete_report_studies_by_id(report_id: int, user: str, session: AsyncSession) -> Dict[str, Any]:
    """
    Internal implementation to delete all links between a report and studies.
    Only deletes links created by the specified user or links with no creator.
    """
    user = str(user) if user is not None else None #TODO remove later
    try:
        # Validate report exists
        report = await session.get(Report, report_id)
        if not report:
            raise HTTPException(status_code=404, detail=f"Report {report_id} not found")

        # Build query joining StudyReport with StudyReportAdded
        stmt = (
            select(StudyReport, StudyReportAdded.CreatedBy)
            .outerjoin(StudyReportAdded, StudyReport.StudyReportID == StudyReportAdded.StudyReportID)
            .where(StudyReport.CRGReportID == report_id)
        )
        
        # If user is provided, filter by CreatedBy
        if user:
            stmt = stmt.where(StudyReportAdded.CreatedBy == user)

        # Fetch all matching links
        rows = (await session.execute(stmt)).all()

        deleted_links: List[Dict[str, int]] = [
            {"CRGReportID": sr.CRGReportID, "CRGStudyID": sr.CRGStudyID}
            for sr, _ in rows
        ]

        # Bulk delete matching links
        if rows:
            study_report_ids = [sr.StudyReportID for sr, _ in rows]
            await session.execute(
                delete(StudyReport).where(StudyReport.StudyReportID.in_(study_report_ids))
            )
            await session.commit()

        return {
            "report_id": report_id,
            "deleted_count": len(rows),
            "deleted_links": deleted_links
        }
    
    except HTTPException:
        await session.rollback()
        raise
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete report-study links: {str(e)}")
    
async def add_new_report_batch(batch_hash, batch_description, reports, user, session: AsyncSession = Depends(get_session)):
    new_batch = Batch(
        BatchHash=batch_hash,
        BatchDescription=batch_description,
        UploadedBy=user
    )
    session.add(new_batch)

    # Add all reports at once
    session.add_all(reports)
    await session.flush()  # Flush once to get all IDs
    
    # Create all ReportAdded entries
    report_added_entries = [
        ReportAdded(CRGReportID=report.CRGReportID, BatchHash=batch_hash)
        for report in reports
    ]
    session.add_all(report_added_entries)
    
    await session.commit()

    for report in reports:
        await session.refresh(report)

    return reports