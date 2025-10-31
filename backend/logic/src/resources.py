from fastapi import APIRouter
from fastapi import Depends, HTTPException, Query, Path
import os

from dotenv import load_dotenv

from .auth import is_verified
from typing import List, Optional

from pydantic import BaseModel

from googleapiclient.discovery import build
from google.oauth2 import service_account
from pydantic import BaseModel
from dotenv import load_dotenv
from typing import List, Optional, Dict, Any
import os

from datetime import date
import re
import json

from nameparser import HumanName

from sqlmodel import create_engine, select, func, text, SQLModel, Session
from .utils.database_models import Report, Study, StudyCondition, StudyDesign, StudyIntervention, StudyOutcome, StudyParticipant, StudyReport
from .utils.database_models import Condition, Intervention, Design, Outcome, Participant

load_dotenv()

router = APIRouter(tags=["resources"], dependencies=[Depends(is_verified)])

class FulltextLink(BaseModel):
    report_id: int
    link: str

class ReportResponse(Report):
    PDFLinks: Optional[str] = None


DATABASE_VOLUME = os.getenv("DATABASE_VOLUME")

DATABASE_URL = "sqlite:///" + os.path.join(DATABASE_VOLUME,"resources","meerkat.db")

engine = create_engine(DATABASE_URL, echo=True)

def get_session():
    with Session(engine) as session:
        yield session

def init_db():
    SQLModel.metadata.create_all(engine)

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
    
@router.on_event("startup")
async def startup_event():
    init_db()

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
report_ids_query = Query(..., description="List of CRGReportIDs (used to filter your results)")
report_id_path = Path(..., description="CRGReportIDs")

"""
Study Endpoints
"""

@router.get("/studies", summary="Get study details for all studies specified in the query.")
def get_studies(study_ids: List[int] = study_ids_query, session: Session = Depends(get_session)) -> List[Study]:
    return _get_studies(study_ids, session)

@router.get("/studies/reports", include_in_schema=False)
def get_study_reports_by_ids(study_ids: List[int] = study_ids_query, cutoff: str = cutoff_query, fields: Optional[List[str]] = Query(None), session: Session = Depends(get_session)) -> Dict[int, List[Report]]:
    return _get_study_reports_by_ids(study_ids, cutoff, fields, session)

@router.get("/studies/persons", include_in_schema=False)
def get_study_persons(study_ids: List[int] = study_ids_query, cutoff: str = cutoff_query, session: Session = Depends(get_session)) -> Dict[int, List[str]]:
    _get_study_persons(study_ids,cutoff,session)

@router.get("/studies/{study_id}", summary="Get study details for a specific study.")
def get_studies_single(study_id: int = study_id_path, session: Session = Depends(get_session)) -> List[Study]:
    stmt = select(Study).where(Study.CRGStudyID == study_id)
    return session.exec(stmt).first()

@router.get("/studies/{study_id}/reports", summary="Get all reports (and corresponding data) already belonging to this study")
def get_study_reports_by_id(study_id: int = study_id_path, include_pdf_links : bool = Query(None), session: Session = Depends(get_session)) -> List[ReportResponse]:
    data = get_study_reports_by_ids(study_ids=[study_id], fields=None, cutoff=None, session=session)[study_id]
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
def get_study_id_by_trial_id(trial_id: str = Path(..., description="A regular trial id (e.g. ACTRN12605000202662, NCT00034892)"), cutoff: str = cutoff_query, session: Session = Depends(get_session)) -> List[int]:
    return _get_study_id_by_trial_id(trial_id,cutoff,session)

@router.get("/studies/{study_id}/date_entered", summary="Get the date when the study was entered into the database")
def get_study_date_by_id(study_id: int = study_id_path, session: Session = Depends(get_session)) -> str:
    stmt = select(Study.DateEntered).where(Study.CRGStudyID == study_id)
    return session.exec(stmt).first()

@router.get("/studies/{study_id}/interventions", summary="Get interventions for a specific study (e.g. 'Placebo', 'Group Therapy', ...)")
def get_study_interventions_single(study_id: int = study_id_path, session: Session = Depends(get_session)):
    return get_study_interventions(study_ids=[study_id], session=session)[study_id]

@router.get("/studies/{study_id}/conditions", summary="Get the health conditions of participants in a specific study (e.g., 'COVID-19', 'Diabetes', ...).")
def get_study_conditions_single(study_id: int = study_id_path, session: Session = Depends(get_session)):
    return get_study_conditions(study_ids=[study_id], session=session)[study_id]

@router.get("/studies/{study_id}/outcomes", summary="Get outcomes for a specific study (e.g. 'Mortality', 'Hospitalization', ...)")
def get_study_outcomes_single(study_id: int = study_id_path, session: Session = Depends(get_session)):
    return get_study_outcomes(study_ids=[study_id], session=session)[study_id]

@router.get("/studies/{study_id}/participants", summary="Get participant description for a specific study (e.g. Male, Female, Adult, Child, ...)")
def get_study_participants_single(study_id: int = study_id_path, session: Session = Depends(get_session)) -> List[str]:
    return get_study_participants(study_ids=[study_id], session=session)[study_id]

@router.get("/studies/{study_id}/design", summary="Get the study design of the corresponding study ('Randomized Controlled Trial', 'Controlled Clinical Trial')")
def get_study_design_single(study_id: int = study_id_path, session: Session = Depends(get_session)) -> List[str]:
    return get_study_design(study_ids=[study_id], session=session)[study_id]

@router.get("/studies/{study_id}/persons", summary="Get all persons (usually only authors) associated with a specific study")
def get_study_persons_single(study_id: int = study_id_path, cutoff: str = cutoff_query, session: Session = Depends(get_session)) -> Dict[int, List[str]]:
    return get_study_persons(study_ids=[study_id], cutoff=cutoff, session=session)


"""
Report Endpoints
"""

@router.get("/reports", summary="Get all report details specified by id.")
def get_all_reports(report_ids: List[int] = report_ids_query, session: Session = Depends(get_session)) -> List[Report]:
    stmt = select(Report).where((Report.Title.isnot(None)) | (Report.Abstract.isnot(None)))
    if report_ids:
        stmt = stmt.where(Report.CRGReportID.in_(report_ids))
    return session.exec(stmt).all()

@router.get("/reports/pdf_number", include_in_schema=False)
def get_pdf_numbers_by_report_ids(report_ids: List[int] = report_ids_query, session: Session = Depends(get_session)) -> Dict[int, int]:
    stmt = select(Report.CRGReportID, Report.ReportNumber).where(Report.CRGReportID.in_(report_ids))
    rows = session.exec(stmt).all()
    return {row[0]: row[1] for row in rows}

@router.get("/reports/pdf_links", include_in_schema=False)
def get_pdf_links_by_report_ids(report_ids: List[int] = report_ids_query,session: Session = Depends(get_session)) -> Dict[int, Optional[str]]:

    pdf_numbers = get_pdf_numbers_by_report_ids(report_ids, session)
    return get_pdf_links_by_report_numbers(pdf_numbers)

def get_pdf_links_by_report_numbers(pdf_numbers: Dict[int, int]) -> Dict[int, Optional[str]]:
    results = {}

    SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
    creds = service_account.Credentials.from_service_account_file(
        os.path.join(DATABASE_VOLUME,"resources", 'service-account.json'), scopes=SCOPES
    )
    service = build('drive', 'v3', credentials=creds)

    folder_name = "Meerkat_PDFs"
    folder_results = service.files().list(
        q=f"sharedWithMe and mimeType='application/vnd.google-apps.folder' and name='{folder_name}' and trashed=false",
        includeItemsFromAllDrives=True,
        supportsAllDrives=True,
        fields="files(id, name)"
    ).execute()

    folders = folder_results.get('files', [])
    if not folders:
        return {rid: None for rid in pdf_numbers.keys()}

    folder_id = folders[0]['id']

    for rid, report_number in pdf_numbers.items():
        if not report_number:
            results[rid] = None
            continue

        pdf_name = str(report_number).zfill(5) + ".pdf"
        pdf_results = service.files().list(
            q=f"'{folder_id}' in parents and name='{pdf_name}' and mimeType='application/pdf' and trashed=false",
            includeItemsFromAllDrives=True,
            supportsAllDrives=True,
            fields="files(id, name, owners)",
        ).execute()

        pdfs = pdf_results.get('files', [])
        if not pdfs:
            results[rid] = None
        else:
            f = pdfs[0]
            results[rid] = f"https://drive.google.com/file/d/{f['id']}/view"
            #results[rid] = f"https://drive.google.com/uc?export=download&id={f['id']}"

    return results

@router.get("/reports/{report_id}", summary="Get details for a specific report.")
def get_study_reports_by_id(report_id: int = report_id_path, session: Session = Depends(get_session)) -> Report:
    stmt = select(Report).where(Report.CRGReportID == report_id)
    return session.exec(stmt).first()

@router.get("/reports/{report_id}/pdf_number", summary="Get the associated pdf number (which is not tze CRGReportID) for a certain report.")
def get_pdf_number_by_report_id(report_id: int = report_id_path, session: Session = Depends(get_session)) -> int:
    return get_pdf_numbers_by_report_ids(report_ids=[report_id], session=session)[report_id]

@router.get("/reports/{report_id}/pdf_link", summary="Get the link to the fulltext pdf for a given report")
def get_pdf_link_by_reports(report_id: int = report_id_path, session : Session = Depends(get_session)) -> str:

    return get_pdf_links_by_report_ids([report_id],session)[report_id]



"""
Aspect Endpoints
"""

@router.get("/participants/by_studies", summary="Get participant attributes grouped by studies.", include_in_schema=False)
def get_study_participants(study_ids: List[int] = study_ids_query, session: Session = Depends(get_session)) -> Dict[int, List[str]]:
    return _get_study_participants(study_ids, session)

@router.get("/participants", summary="Get all participant attributes or filter them by id.", include_in_schema=False)
def get_all_participants(ids: List[int] = Query(None,description="If you are only interested in specific participant attributes. Leave this blank for retrieving all participant attributes."),session: Session = Depends(get_session)) -> List[Participant]:
    stmt = select(Participant)
    if ids:
        stmt = stmt.where(Participant.ParticipantsID.in_(ids))
    return session.exec(stmt).all()

@router.get("/design/by_studies", summary="Get study designs grouped by studies.", include_in_schema=False)
def get_study_design(study_ids: List[int] = study_ids_query, session: Session = Depends(get_session)) -> Dict[int, List[str]]:
    return _get_study_design(study_ids, session)

@router.get("/design", summary="Get all study design items or filter them by id.", include_in_schema=False)
def get_all_design(ids: List[int] = Query(None,description="If you are only interested in specific design items. Leave this blank for retrieving all design items."),session: Session = Depends(get_session)) -> List[Design]:
    stmt = select(Design)
    if ids:
        stmt = stmt.where(Design.DesignID.in_(ids))
    return session.exec(stmt).all()

@router.get("/interventions/by_studies", summary="Get interventions grouped by studies.")
def get_study_interventions(study_ids: List[int] = study_ids_query, session: Session = Depends(get_session)) -> Dict[int, List[Dict[str, Any]]]:
    return _get_study_interventions(study_ids,session)

@router.get("/interventions", summary="Get all intervention items or filter them by id." )
def get_all_interventions(ids: List[int] = Query(None,description="If you are only interested in specific interventions. Leave this blank for retrieving all interventions."),session: Session = Depends(get_session)) -> List[Intervention]:
    return _get_all_interventions(ids, session)

@router.get("/conditions/by_studies", summary="Get conditions grouped by studies.")
def get_study_conditions(study_ids: List[int] = study_ids_query, session: Session = Depends(get_session)):
    return _get_study_conditions(study_ids, session)

@router.get("/conditions", summary="Get all condition items or filter them by id.", description="Conditions might be for example 'Diabetes', 'Schizophrenia', ... ") 
def get_all_conditions(ids: List[int] = Query(None, description="If you are only interested in specific conditions. Leave this blank for retrieving all conditions."), session: Session = Depends(get_session)) -> List[Condition]:
    return _get_all_conditions(ids, session)

@router.get("/outcomes/by_studies", summary="Get outcomes grouped by studies.")
def get_study_outcomes(study_ids: List[int] = study_ids_query, session: Session = Depends(get_session)):
    return _get_study_outcomes(study_ids, session)

@router.get("/outcomes", summary="Get all study outcome items or filter them by id.", description="Outcomes might be for example 'Mortality', 'Quality of Life', etc. These items are linked to studies.")
def get_all_outcomes(ids: List[int] = Query(None,description="If you are only interested in specific outcomes. Leave this blank for retrieving all outcomes."), session: Session = Depends(get_session)) -> List[Outcome]:
    return _get_all_outcomes(ids, session)


"""
Other Endpoints
"""

@router.get("/mappings/report_study", summary="Get the mapping from CRGReportIDs to CRGStudyIds.")
def get_mapping_report_study(session: Session = Depends(get_session)) -> Dict[int, List[int]]:
    stmt = select(StudyReport.CRGReportID, StudyReport.CRGStudyID)
    rows = session.exec(stmt).all()
    return convert_to_id_based_dict(rows)

@router.get("/mappings/study_report", summary="Get the mapping from CRGStudyIDs to CRGReportIds.")
def get_mapping_report_study(session: Session = Depends(get_session)) -> Dict[int, List[int]]:
    stmt = select(StudyReport.CRGStudyID, StudyReport.CRGReportID)
    rows = session.exec(stmt).all()
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
def get_possible_trial_ids_by_report(session: Session = Depends(get_session)):
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
    result_studies = session.exec(query_studies).fetchall()
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
    result_reports = session.exec(query_reports).fetchall()
    all_reports = [row[0] for row in result_reports]

    return all_studies + all_reports
    


"""
Helper functions
"""

def get_study_reports_by_ids_internal(study_ids: List[int], cutoff: str, fields: Optional[List[str]]):
    with Session(engine) as session:
        return _get_study_reports_by_ids(study_ids, cutoff, fields, session)

def _get_study_reports_by_ids(study_ids: List[int], cutoff: str, fields: Optional[List[str]], session: Session) -> Dict[int, List[Report]]:
    cutoff = cutoff or date.today().isoformat()

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
        .where(
            StudyReport.CRGStudyID.in_(study_ids),
            Report.Dateentered < cutoff
        )
    )

    rows = session.exec(stmt).all()

    grouped = {}
    for row in rows:
        study_id = row[0]  # first item is StudyID
        report_data = dict(zip(selected_fields, row[1:]))  # remaining fields as dict
        grouped.setdefault(study_id, []).append(report_data)
    return grouped

def get_study_persons_internal(study_ids: List[int], cutoff: str):
    with Session(engine) as session:
        return _get_study_persons(study_ids, cutoff, session)

def _get_study_persons(study_ids: List[int], cutoff: str, session: Session) -> Dict[int, List[str]]:
    cutoff_date = cutoff or date.today().isoformat()

    stmt = (
        select(StudyReport.CRGStudyID.label("StudyID"), Report.Authors)
        .join(Report, Report.CRGReportID == StudyReport.CRGReportID)
        .where(Report.Dateentered < cutoff_date)
    )

    if study_ids is not None:
        stmt = stmt.where(StudyReport.CRGStudyID.in_(study_ids))

    rows = session.exec(stmt).all()


    final_result = {}

    for item in rows:
        key = item[0]
        value = item[1]
        authors = [author.strip() for author in value.split("//")]
        normalized_authors = normalize_author_names(authors=authors)

        final_result[key] = normalized_authors

    return final_result

def get_study_id_by_trial_id_internal(trial_id: str, cutoff: str) -> List[int]:
    with Session(engine) as session:
        return _get_study_id_by_trial_id(trial_id,cutoff, session)

def _get_study_id_by_trial_id(trial_id: str, cutoff: str, session: Session) -> List[int]:
    
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

    rows_study = session.exec(stmt_study).all()
    

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

    rows_reports = session.exec(stmt_reports).all()
    rows_study.extend(rows_reports)

    return list(set(rows_study))

def get_studies_internal(study_ids):
    with Session(engine) as session:
        return _get_studies(study_ids, session)

def _get_studies(study_ids, session):
    stmt = select(Study).where(Study.CRGStudyID.in_(study_ids))
    return session.exec(stmt).all()

def _get_study_aspect(stmt, session):
    rows = session.exec(stmt).all()  # -> [(StudyID, ID, Description), ...]

    # --- Group results by StudyID ---
    final_result: Dict[int, List[Dict[str, Any]]] = {}
    for study_id, intervention_id, description in rows:
        item = {"ID": intervention_id, "Description": description}
        final_result.setdefault(study_id, []).append(item)

    return final_result

def get_study_interventions_internal(study_ids: List[int]):
    with Session(engine) as session:
        return _get_study_interventions(study_ids, session)

def _get_study_interventions(study_ids: List[int], session: Session) -> Dict[int, List[Dict[str, Any]]]:
    stmt = (
        select(
            StudyIntervention.CRGStudyID.label("StudyID"),
            StudyIntervention.InterventionID.label("ID"),
            Intervention.InterventionDescription.label("Description"),
        )
        .join(Intervention, Intervention.InterventionID == StudyIntervention.InterventionID)
        .where(StudyIntervention.CRGStudyID.in_(study_ids))
    )

    return _get_study_aspect(stmt,session)

def get_study_conditions_internal(study_ids: List[int]):
    with Session(engine) as session:
        return _get_study_conditions(study_ids, session)

def _get_study_conditions(study_ids: List[int], session: Session):
    stmt = (
        select(
            StudyCondition.CRGStudyID.label("StudyID"),
            StudyCondition.HealthCareConditionID.label("ID"),
            Condition.HealthCareConditionDescription.label("Description"),
        )
        .join(Condition, Condition.HealthCareConditionID == StudyCondition.HealthCareConditionID)
        .where(StudyCondition.CRGStudyID.in_(study_ids))
    )

    return _get_study_aspect(stmt,session)

def get_study_outcomes_internal(study_ids: List[int]):
    with Session(engine) as session:
        return _get_study_outcomes(study_ids, session)

def _get_study_outcomes(study_ids: List[int] = study_ids_query, session: Session = Depends(get_session)):
    stmt = (
        select(
            StudyOutcome.CRGStudyID.label("StudyID"),
            StudyOutcome.OutcomeID.label("ID"),
            Outcome.OutcomeDescription.label("Description"),
        )
        .join(Outcome, Outcome.OutcomeID == StudyOutcome.OutcomeID)
        .where(StudyOutcome.CRGStudyID.in_(study_ids))
    )

    return _get_study_aspect(stmt,session)

def get_study_design_internal(study_ids: List[int]):
    with Session(engine) as session:
        return _get_study_design(study_ids, session)

def _get_study_design(study_ids: List[int], session: Session) -> Dict[int, List[str]]:
    stmt = (
        select(StudyDesign.CRGStudyID, Design.DesignDescription)
        .join(Design, Design.DesignID == StudyDesign.DesignID)
        .where(StudyDesign.CRGStudyID.in_(study_ids))
    )

    rows = session.exec(stmt).all()  # list of tuples [(StudyID, DesignDescription), ...]

    # Group by StudyID
    final_result: Dict[int, List[str]] = {}
    for study_id, description in rows:
        final_result.setdefault(study_id, []).append(description)

    return final_result

def get_study_participants_internal(study_ids: List[int]):
    with Session(engine) as session:
        return _get_study_participants(study_ids, session)

def _get_study_participants(study_ids: List[int], session: Session) -> Dict[int, List[str]]:
    stmt = (
        select(StudyParticipant.CRGStudyID, Participant.ParticipantDescription)
        .join(Participant, Participant.ParticipantsID == StudyParticipant.ParticipantsID)
        .where(StudyParticipant.CRGStudyID.in_(study_ids))
    )

    rows = session.exec(stmt).all()  # list of tuples [(StudyID, ParticipantDescription), ...]

    # Convert to dictionary grouped by StudyID
    final_result: Dict[int, List[str]] = {}
    for study_id, description in rows:
        final_result.setdefault(study_id, []).append(description)

    return final_result

def get_all_interventions_internal(ids: List[int]):
    with Session(engine) as session:
        return _get_all_interventions(ids, session)

def _get_all_interventions(ids: List[int],session) -> List[Intervention]:
    stmt = select(Intervention.InterventionID, Intervention.InterventionDescription)
    if ids:
        stmt = stmt.where(Intervention.InterventionID.in_(ids))
    return session.exec(stmt).all()

def get_all_conditions_internal(ids: List[int]):
    with Session(engine) as session:
        return _get_all_conditions(ids, session)

def _get_all_conditions(ids: List[int], session: Session) -> List[Condition]:
    stmt = select(Condition)
    if ids:
        stmt = stmt.where(Condition.HealthCareConditionID.in_(ids))
    return session.exec(stmt).all()

def get_all_outcomes_internal(ids: List[int]):
    with Session(engine) as session:
        return _get_all_outcomes(ids, session)

def _get_all_outcomes(ids: List[int], session) -> List[Outcome]:
    stmt = select(Outcome)
    if ids:
        stmt = stmt.where(Outcome.OutcomeID.in_(ids))
    return session.exec(stmt).all()