from fastapi import APIRouter, File, UploadFile
from fastapi import Depends, HTTPException, Query, Path
from fastapi.responses import FileResponse
import os

from dotenv import load_dotenv

from .auth import is_verified_api_call
from typing import List, Optional
import enum
from pydantic import BaseModel

from dotenv import load_dotenv
from typing import List, Optional, Dict, Any

from datetime import date
import re
import json
import asyncio

from nameparser import HumanName

from sqlmodel import select, func, text, delete
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import event

from .utils.database_models import Report, Study, StudyCondition, StudyDesign, StudyIntervention, StudyOutcome, StudyParticipant, StudyReport
from .utils.database_models import Condition, Intervention, Design, Outcome, Participant
from .utils.database_models import metadata_resources

from datetime import datetime, timezone

load_dotenv()

DATABASE_VOLUME = os.getenv("DATABASE_VOLUME")

router = APIRouter(tags=["resources"], dependencies=[Depends(is_verified_api_call)])

DATABASE_URL = "sqlite+aiosqlite:///" + os.path.join(DATABASE_VOLUME,"resources","meerkat.db")
PDF_PATH = os.path.join(DATABASE_VOLUME,"resources", "pdfs")

engine = create_async_engine(DATABASE_URL, echo=True)

write_lock = asyncio.Lock()

class ReportResponse(Report):
    PDFLinks: Optional[str] = None

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


@event.listens_for(engine.sync_engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON;")
    cursor.close()
    
@router.on_event("startup")
async def startup_event():
    async with engine.begin() as conn:
        await conn.run_sync(metadata_resources.create_all)
        await conn.execute(text("PRAGMA journal_mode=WAL"))
        await conn.execute(text("PRAGMA synchronous=NORMAL"))
        await conn.execute(text("PRAGMA foreign_keys = ON;"))


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
study_ids_query =  Query(..., description="List of CRGStudyIDs (used to filter your results)")
study_id_path = Path(..., description="CRGStudyID")
report_ids_query = Query(None, description="List of CRGReportIDs (used to filter your results)")
report_id_path = Path(..., description="CRGReportIDs")

"""
Study Endpoints
"""

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
async def get_study_persons(study_ids: List[int] = study_ids_query, cutoff: str = cutoff_query, session: AsyncSession = Depends(get_session)) -> Dict[int, List[str]]:
    return await _get_study_persons(study_ids,cutoff,session)

@router.get("/studies/{study_id}", summary="Get study details for a specific study.")
async def get_studies_single(study_id: int = study_id_path, session: AsyncSession = Depends(get_session)) -> List[Study]:
    stmt = select(Study).where(Study.CRGStudyID == study_id)
    return (await session.execute(stmt)).first()

@router.get("/studies/{study_id}/reports", summary="Get all reports (and corresponding data) already belonging to this study")
async def get_study_reports_by_id(study_id: int = study_id_path, include_pdf_links : bool = Query(None), session: AsyncSession = Depends(get_session)) -> List[ReportResponse]:
    data = (await get_study_reports_by_ids(study_ids=[study_id], fields=None, cutoff=None, session=session))[study_id]
    if not include_pdf_links:
        return data

    pdf_numbers = {item['CRGReportID']:item['ReportNumber'] for item in data}
    
    pdf_links = get_pdf_links_by_report_numbers(pdf_numbers)

    for i in range(0, len(data)):
        key = data[i]['CRGReportID']
        if key in pdf_links.keys():
            data[i]['PDFLinks'] = pdf_links[key]
        else:
            data[i]['PDFLinks'] = None

    return data

@router.get("/studies/{trial_id}/study_id", summary="Get the CRGStudyID given a matching trial registration id")
async def get_study_id_by_trial_id(trial_id: str = Path(..., description="A regular trial id (e.g. ACTRN12605000202662, NCT00034892)"), cutoff: str = cutoff_query, session: AsyncSession = Depends(get_session)) -> List[int]:
    result = await _get_study_id_by_trial_id(trial_id,cutoff,session)
    return result

@router.get("/studies/{study_id}/date_entered", summary="Get the date when the study was entered into the database")
async def get_study_date_by_id(study_id: int = study_id_path, session: AsyncSession = Depends(get_session)) -> str:
    stmt = select(Study.DateEntered).where(Study.CRGStudyID == study_id)
    return (await session.execute(stmt)).scalars().first()

@router.get("/studies/{study_id}/interventions", summary="Get interventions for a specific study (e.g. 'Placebo', 'Group Therapy', ...)")
async def get_study_interventions_single(study_id: int = study_id_path, session: AsyncSession = Depends(get_session)):
    result = await get_study_interventions(study_ids=[study_id], session=session)
    if study_id in result.keys():
        return result[study_id]
    return None

@router.get("/studies/{study_id}/conditions", summary="Get the health conditions of participants in a specific study (e.g., 'COVID-19', 'Diabetes', ...).")
async def get_study_conditions_single(study_id: int = study_id_path, session: AsyncSession = Depends(get_session)):
    result =await get_study_conditions(study_ids=[study_id], session=session)
    if study_id in result.keys():
        return result[study_id]
    return None

@router.get("/studies/{study_id}/outcomes", summary="Get outcomes for a specific study (e.g. 'Mortality', 'Hospitalization', ...)")
async def get_study_outcomes_single(study_id: int = study_id_path, session: AsyncSession = Depends(get_session)):
    result =await get_study_outcomes(study_ids=[study_id], session=session)
    if study_id in result.keys():
        return result[study_id]
    return None

@router.get("/studies/{study_id}/participants", summary="Get participant description for a specific study (e.g. Male, Female, Adult, Child, ...)")
async def get_study_participants_single(study_id: int = study_id_path, session: AsyncSession = Depends(get_session)) -> Optional[List[str]]:
    result = await get_study_participants(study_ids=[study_id], session=session)
    if study_id in result.keys():
        return result[study_id]
    return None

@router.get("/studies/{study_id}/design", summary="Get the study design of the corresponding study ('Randomized Controlled Trial', 'Controlled Clinical Trial')")
async def get_study_design_single(study_id: int = study_id_path, session: AsyncSession = Depends(get_session)) -> Optional[List[str]]:
    result = await get_study_design(study_ids=[study_id], session=session)
    if study_id in result.keys():
        return result[study_id]
    return None

@router.get("/studies/{study_id}/persons", summary="Get all persons (usually only authors) associated with a specific study")
async def get_study_persons_single(study_id: int = study_id_path, cutoff: str = cutoff_query, session: AsyncSession = Depends(get_session)) -> Dict[int, List[str]]:
    return await get_study_persons(study_ids=[study_id], cutoff=cutoff, session=session)


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
    session: AsyncSession = Depends(get_session)
) -> List[Study]:
    return await _get_report_studies_by_id(report_id, session, date_from, date_to)

@router.get("/reports/{report_id}/pdf_number", summary="Get the associated pdf number (which is not tze CRGReportID) for a certain report.")
async def get_pdf_number_by_report_id(report_id: int = report_id_path, session: AsyncSession = Depends(get_session)) -> int:
    return (await get_pdf_numbers_by_report_ids(report_ids=[report_id], session=session))[report_id]

@router.get("/reports/{report_id}/pdf", summary="Get the fulltext pdf for a given report", responses={200: {"description": "The PDF file of the report.","content": {"application/pdf": {"schema": {"type": "string","format": "binary"}}}}})
async def get_pdf_by_report(report_id: int = report_id_path, session : AsyncSession = Depends(get_session)) -> FileResponse:

    report_number = (await get_pdf_numbers_by_report_ids(report_ids=[report_id], session=session))[report_id]
    pdf_name = str(report_number).zfill(5) + ".pdf"
    file_name = os.path.join(PDF_PATH, pdf_name)

    if not os.path.exists(file_name):
        raise HTTPException(status_code=404, detail="PDF file not found.")
    return FileResponse(file_name, media_type="application/pdf")

@router.put("/reports/pdf", summary="Upload the fulltext pdf for a given report", responses={200: {"description": "PDF file uploaded successfully"}})
async def uploaed_pdf(
    file: UploadFile = File(..., description="PDF file to upload"),
    session: AsyncSession = Depends(get_session)
) -> Dict[str, Any]:
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
        async with write_lock:
            with open(file_path, "wb") as f:
                content = await file.read()
                f.write(content)
        
        return {
            "report_id": report_id,
            "report_number": report_number,
            "filename": filename,
            "file_path": file_path,
            "size_bytes": len(content)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save PDF: {str(e)}")
    
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
    
    def normalize_author_names(name):  
        name = re.sub(r'\bvan\b\s+\bden\b', 'Van Den', name, flags=re.IGNORECASE)     
        name = re.sub(r'(?<=\b[A-Z])-(?=[A-Z]\b)', '', name)

        name_check = re.match(r"\b([A-Z][a-z]+ )+[A-Z]+\b", name)

        if not name_check:
            return None
        
        #name = name.split()
        #name = name[0] + " " + name[0][0] #if there are multiple initials just use the first one
        return name#.lower()

    normalized_authors = []
    for author in authors:
        current_authors = [author]
        if author in trial_person_mapping:
            current_authors = get_person_from_trial_id(author)
        for current_author in current_authors:
            normalized_author = normalize_author_names(current_author)
            if normalized_author:
                normalized_authors.append(normalized_author)
    
    return normalized_authors

def get_author_frequencies(authors: List[str]) -> Dict[str, int]:
    normalized_author_names = normalize_author_names(authors=authors)
    
    result = {}
    for author in normalized_author_names:
        if author in author_frequencies:
            result[author] = author_frequencies[author]

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
            raise HTTPException(
                status_code=400,
                detail=f"Invalid field(s): {', '.join(invalid_fields)}"
            )
        selected_fields = fields

    # --- Optimized Query ---
    stmt = (
        select(StudyReport.CRGStudyID, *[getattr(Report, f) for f in selected_fields])
        .join(Report, Report.CRGReportID == StudyReport.CRGReportID)
        .where(StudyReport.CRGStudyID.in_(study_ids))
    )

    if cutoff:
        stmt = stmt.where(Report.Dateentered < cutoff)


    rows = (await session.execute(stmt)).all()

    grouped = {}
    for row in rows:
        study_id = row[0]  # first item is StudyID
        report_data = dict(zip(selected_fields, row[1:]))  # remaining fields as dict
        grouped.setdefault(study_id, []).append(report_data)
    return grouped

async def get_study_persons_internal(study_ids: List[int], cutoff: str):
    async with AsyncSession(engine) as session:
        return await _get_study_persons(study_ids, cutoff, session)

async def _get_study_persons(study_ids: List[int], cutoff: str, session: AsyncSession) -> Dict[int, List[str]]:
    cutoff_date = cutoff or date.today().isoformat()

    stmt = (
        select(StudyReport.CRGStudyID.label("StudyID"), Report.Authors)
        .join(Report, Report.CRGReportID == StudyReport.CRGReportID)
        .where(Report.Dateentered < cutoff_date)
    )

    if study_ids is not None:
        stmt = stmt.where(StudyReport.CRGStudyID.in_(study_ids))

    rows = (await session.execute(stmt)).all()


    final_result = {}

    for item in rows:
        key = item[0]
        value = item[1]
        authors = [author.strip() for author in value.split("//")]
        normalized_authors = normalize_author_names(authors=authors)

        final_result[key] = normalized_authors

    return final_result

async def get_study_id_by_trial_id_internal(trial_id: str, cutoff: str) -> List[int]:
    async with AsyncSession(engine) as session:
        return await _get_study_id_by_trial_id(trial_id,cutoff, session)

async def _get_study_id_by_trial_id(trial_id: str, cutoff: str, session: AsyncSession) -> List[int]:
    
    cutoff = cutoff or date.today().isoformat()

    trial_id = trial_id.replace("/", "-")
    alternative_ids = []
    if trial_id in trial_id_mapping:
        alternative_ids = trial_id_mapping[trial_id]

    alternative_ids += [trial_id]
    alternative_ids = [current_id.replace("/", "-") for current_id in alternative_ids]

    # --- First query: tblStudy ---
    stmt_study = select(func.distinct(Study.CRGStudyID)).where(
        (func.replace(Study.ShortName, "/", "-").in_(alternative_ids)) |
        (func.replace(Study.TrialRegistrationID, "/", "-").in_(alternative_ids)),
        Study.DateEntered < cutoff
    )

    rows_study = (await session.execute(stmt_study)).scalars().all()
    

    # --- Second query: tblStudyReport JOIN tblReport ---
    # Build dynamic LIKE conditions for Authors
    authors_filter = func.replace(Report.Authors, "/", "-").like(f"%{trial_id}%")
    for current_id in alternative_ids[1:]:
        authors_filter = authors_filter | func.replace(Report.Authors, "/", "-").like(f"%{current_id}%")

    trial_filter = func.replace(Report.TrialRegistrationID, "/", "-").in_(alternative_ids)

    stmt_reports = (
        select(func.distinct(StudyReport.CRGStudyID))
        .join(Report, Report.CRGReportID == StudyReport.CRGReportID)
        .where(
            (authors_filter | trial_filter),
            Report.Dateentered < cutoff
        )
    )

    rows_reports = (await session.execute(stmt_reports)).scalars().all()
    rows_study.extend(rows_reports)

    return list(set(rows_study))

async def get_studies_internal(study_ids):
    async with AsyncSession(engine) as session:
        return await _get_studies(study_ids, session)

async def _get_studies(study_ids, session):
    stmt = select(Study).where(Study.CRGStudyID.in_(study_ids))
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
    
    async with write_lock:
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
        .where(StudyOutcome.CRGStudyID.in_(study_ids))
    )

    return await _get_study_aspect(stmt,session)

async def get_study_design_internal(study_ids: List[int]):
   async with AsyncSession(engine) as session:
        return await _get_study_design(study_ids, session)

async def _get_study_design(study_ids: List[int], session: AsyncSession) -> Dict[int, List[str]]:
    stmt = (
        select(StudyDesign.CRGStudyID, Design.DesignDescription)
        .join(Design, Design.DesignID == StudyDesign.DesignID)
        .where(StudyDesign.CRGStudyID.in_(study_ids))
    )

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
        .where(StudyParticipant.CRGStudyID.in_(study_ids))
    )

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
    return result

async def get_report_studies_by_id_internal(report_id, date_from=None, date_to=None):
    async with AsyncSession(engine) as session:
        return await _get_report_studies_by_id(report_id, session, date_from, date_to)

async def _get_report_studies_by_id(report_id, session, date_from=None, date_to=None):
    stmt = (
        select(Study)
        .join(StudyReport, StudyReport.CRGStudyID == Study.CRGStudyID)
        .where(StudyReport.CRGReportID == report_id)
    )
    
    if date_from:
        stmt = stmt.where(Study.DateEntered >= date_from)
    if date_to:
        stmt = stmt.where(Study.DateEntered <= date_to)
    
    return (await session.execute(stmt)).scalars().all()

async def add_report_studies_by_id_internal(report_id: int, study_ids: List[int]) -> Dict[str, Any]:
    """
    Create StudyReport links for the given report_id to the provided study_ids.
    Uses write_lock to serialize writes.
    """
    async with write_lock:
        async with AsyncSession(engine) as session:
            return await _add_report_studies_by_id(report_id, study_ids, session)

async def _add_report_studies_by_id(
    report_id: int,
    study_ids: List[int],
    session: AsyncSession
) -> Dict[str, Any]:
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

        # Delete existing links for this report
        await session.execute(delete(StudyReport).where(StudyReport.CRGReportID == report_id))

        # Create new links
        created_links: List[Dict[str, int]] = []
        for sid in valid_ids:
            session.add(StudyReport(CRGReportID=report_id, CRGStudyID=sid))
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

async def delete_report_studies_by_id_internal(report_id: int) -> Dict[str, Any]:
    """
    Delete all StudyReport links for the given report_id.
    Uses write_lock to serialize writes.
    """
    async with write_lock:
        async with AsyncSession(engine) as session:
            return await _delete_report_studies_by_id(report_id, session)

async def _delete_report_studies_by_id(
    report_id: int,
    session: AsyncSession
) -> Dict[str, Any]:
    """
    Internal implementation to delete all links between a report and studies.
    """
    try:
        # Validate report exists
        report = await session.get(Report, report_id)
        if not report:
            raise HTTPException(status_code=404, detail=f"Report {report_id} not found")

        # Fetch all links for response
        rows = (
            await session.execute(
                select(StudyReport).where(StudyReport.CRGReportID == report_id)
            )
        ).scalars().all()

        deleted_links: List[Dict[str, int]] = [
            {"CRGReportID": sr.CRGReportID, "CRGStudyID": sr.CRGStudyID}
            for sr in rows
        ]

        # Bulk delete all links
        if rows:
            await session.execute(
                delete(StudyReport).where(StudyReport.CRGReportID == report_id)
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

async def add_new_report(report: dict):
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    title = report['title']
    abstract = report['abstract']
    authors = report['authors']

    year = report['year']
    report_number = report['report_number']
    journal = report['journal']
    pages = report['pages']
    place = report['place']
    language = report['language']
    issue = report['issue']
    volume = report['volume']
    doi = report['doi']
    publisher = report['publisher']
    trial_registration_id = report['trial_registration_id']

    new_report = Report(
            Title=title,
            ReportNumber=report_number,
            Authors="//".join(authors),
            Journal=journal,
            Year=year,
            Volume=volume,
            Issue=issue,
            Pages=pages,
            Language=language,
            Abstract=abstract,
            Dateentered=timestamp,
            DateEdited=timestamp,
            City=place,
            DOI=doi,
            TrialRegistrationID=trial_registration_id,
            CopyStatus= "Copy Obtained" if report_number != 0 else "Seeking Source",
            Publisher=publisher,
            TypeofReportID=0, #TODO ask alessandro
            PublicationTypeID=1, #TODO ask alessandro
            #TODO Dupstring missing
        )
    
    #TODO double check CRGReportID creation (Alessandro/Farhad)
    async with write_lock:
        async with AsyncSession(engine) as session:
            
            session.add(new_report)
            await session.commit()
            await session.refresh(new_report)
            return new_report.CRGReportID
        

async def delete_reports_by_ids(report_ids: List[int]) -> Dict[str, Any]:
    async with write_lock:
        async with AsyncSession(engine) as session:
            try:                
                # Bulk delete reports
                result = await session.execute(
                    delete(Report).where(Report.CRGReportID.in_(report_ids))
                )
                
                await session.commit()
                
                return {
                    "deleted_count": result.rowcount,
                    "failed_deletions": [],
                    "total_requested": len(report_ids)
                }
            except Exception as e:
                await session.rollback()
                raise HTTPException(status_code=500, detail=f"Failed to delete reports: {str(e)}")