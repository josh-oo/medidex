from fastapi import APIRouter
from fastapi import Depends, FastAPI, HTTPException, Query
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
import sqlite3
import os

from datetime import date
import re
import json

from contextlib import contextmanager

from nameparser import HumanName

from sqlmodel import create_engine, select, func, SQLModel, Session, Field

load_dotenv()

router = APIRouter(tags=["resources"], dependencies=[Depends(is_verified)])

class FulltextLink(BaseModel):
    report_id: int
    link: str

class Report(SQLModel, table=True):
    __tablename__ = "tblReport"

    CENTRALReportID: Optional[int]
    CRGReportID: int = Field(primary_key=True)
    Title: str
    Notes: Optional[str]
    ReportNumber: int
    OriginalTitle: Optional[str]
    Authors: str
    Journal: str
    Year: int
    Volume: Optional[int]
    Issue: Optional[str]
    Pages: Optional[str]
    Language: Optional[str]
    Abstract: Optional[str]
    CENTRALSubmissionStatus : Optional[str]
    CopyStatus: Optional[str]
    DatetoCENTRAL: Optional[str]
    Dateentered: str
    DateEdited: Optional[str]
    Editors: Optional[str]
    Publisher: Optional[str]
    City: Optional[str]
    DupString: Optional[str]
    TypeofReportID: Optional[int]
    PublicationTypeID: int
    Edition: Optional[str]
    Medium: Optional[str]
    StudyDesign: Optional[str]
    DOI: Optional[str]
    UDef3: Optional[str]
    ISBN: Optional[str]
    UDef5: Optional[str]
    PMID: Optional[str]
    TrialRegistrationID: Optional[str]
    UDef9 : Optional[str]
    UDef10: Optional[str]
    UDef8: Optional[str]
    #PDFLinks: Optional[str]

class Study(SQLModel, table=True):
    __tablename__ = "tblStudy"

    CENTRALStudyID: Optional[int]
    CRGStudyID: int = Field(primary_key=True)
    ShortName: str
    StatusofStudy: str
    TrialistContactDetails: Optional[str]
    CENTRALSubmissionStatus: Optional[str]
    Notes: Optional[str]
    DateEntered: str
    DateToCENTRAL: Optional[str]
    DateEdited: Optional[str]
    Search_Tagged: Optional[bool]
    NumberParticipants: Optional[str]
    Countries: Optional[str]
    Duration: Optional[str]
    UDef4: Optional[str]
    Comparison: Optional[str]
    ISRCTN: Optional[str]
    UDef6: Optional[str]
    TrialRegistrationID: Optional[str]

class StudyReport(SQLModel, table=True):
    __tablename__ = "tblStudyReport"

    StudyReportID: int = Field(primary_key=True)
    CRGStudyID: int 
    CRGReportID: int

class Participant(SQLModel, table=True):
    __tablename__ = "tblParticipant"

    ParticipantsID: int = Field(primary_key=True)
    ParticipantDescription: str

class StudyParticipant(SQLModel, table=True):
    __tablename__ = "tblStudyParticipant"

    CRGStudyID: int = Field(primary_key=True)
    ParticipantsID: int = Field(primary_key=True)

class Design(SQLModel, table=True):
    __tablename__ = "tblDesign"

    DesignID: int = Field(primary_key=True)
    DesignDescription: Optional[str] = None

class StudyDesign(SQLModel, table=True):
    __tablename__ = "tblStudyDesign"

    CRGStudyID: int = Field(primary_key=True)
    DesignID: int = Field(primary_key=True)

class Intervention(SQLModel, table=True):
    __tablename__ = "tblIntervention"

    InterventionID: int = Field(primary_key=True)
    InterventionDescription: Optional[str] = None

class StudyIntervention(SQLModel, table=True):
    __tablename__ = "tblStudyIntervention"

    CRGStudyID: int = Field(primary_key=True)
    InterventionID: int = Field(primary_key=True)

class Condition(SQLModel, table=True):
    __tablename__ = "tblHealthCareCondition"

    HealthCareConditionID: int = Field(primary_key=True)
    HealthCareConditionDescription: Optional[str] = None

class StudyCondition(SQLModel, table=True):
    __tablename__ = "tblStudyHealthCareCondition"

    CRGStudyID: int = Field(primary_key=True)
    HealthCareConditionID: int = Field(primary_key=True)

class Outcome(SQLModel, table=True):
    __tablename__ = "tblOutcome"

    OutcomeID: int = Field(primary_key=True)
    OutcomeDescription: Optional[str] = None

class StudyOutcome(SQLModel, table=True):
    __tablename__ = "tblStudyOutcome"

    CRGStudyID: int = Field(primary_key=True)
    OutcomeID: int = Field(primary_key=True)


DATABASE_VOLUME = os.getenv("DATABASE_VOLUME")

DATABASE_URL = "sqlite:///" + os.path.join(DATABASE_VOLUME,"resources","meerkat.db")

engine = create_engine(DATABASE_URL, echo=True)

def get_session():
    with Session(engine) as session:
        yield session

def init_db():
    SQLModel.metadata.create_all(engine)

def get_db():
    conn = sqlite3.connect("file:" + os.path.join(DATABASE_VOLUME,"resources","meerkat.db") + "?mode=ro",uri=True, check_same_thread=False)
    #conn.execute("PRAGMA journal_mode=DELETE;")  # avoid WAL writes
    try:
        yield conn
    finally:
        conn.close()

@contextmanager
def get_db_external():
    conn = sqlite3.connect("file:" + os.path.join(DATABASE_VOLUME,"resources","meerkat.db") + "?mode=ro",uri=True, check_same_thread=False)
    #conn.execute("PRAGMA journal_mode=DELETE;")  # avoid WAL writes
    try:
        yield conn
    finally:
        conn.close()

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


def convert_to_dict_list(description, rows):
    column_names = [description[0] for description in description]
    result = []
    for row in rows:
        item = {}
        for i, value in enumerate(row):
            item[column_names[i]] = value
        result.append(item)
    return result

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

def convert_to_column_based_dict(description, rows):
    column_names = [description[0] for description in description]

    # Transpose row-wise data to column-wise dictionary
    result = {col: [] for col in column_names}
    for row in rows:
        for col, val in zip(column_names, row):
            result[col].append(val)

    return result

def convert_to_column_based_dict_ordered(description, rows, ids, id_colummn):
    column_names = [description[0] for description in description]

    # Map CRGStudyID to its row
    row_map = {row[column_names.index(id_colummn)]: row for row in rows}

    # Build ordered result based on id_input.ids
    result = {col: [] for col in column_names}
    for study_id in ids:
        row = row_map.get(study_id)
        for col, val in zip(column_names, row):
            result[col].append(val)

    return result

@router.get("/studies")
def get_studies(study_ids: List[int] = Query(...), session: Session = Depends(get_session)) -> List[Study]:
    statement = select(Study).where(Study.CRGStudyID.in_(study_ids))
    return session.exec(statement).all()

@router.get("/study/{study_id}/reports")
def get_study_reports_by_id(study_id: int, session: Session = Depends(get_session)) -> List[Report]:
    return get_study_reports_by_ids(study_ids=[study_id], fields=None, cutoff=None, session=session)[study_id]

@router.get("/study/reports")
def get_study_reports_by_ids(study_ids: List[int] = Query(...), cutoff: str = Query(None), fields: Optional[List[str]] = Query(None), session: Session = Depends(get_session)) -> Dict[int, List[Report]]:
    cutoff = cutoff or date.today().isoformat()

    allowed_fields = {"CRGReportID", "Title", "Abstract", "Authors", "Dateentered"}

    # Filter and validate selected fields
    if fields:
        selected_fields = [f for f in fields if f in allowed_fields]
        if not selected_fields:
            raise HTTPException(status_code=400, detail="No valid fields specified.")
    else:
        selected_fields = list(allowed_fields)

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


@router.get("/study/{study_id}/date_entered")
def get_study_date_by_id(study_id: int, session: Session = Depends(get_session)) -> str:
    stmt = select(Study.DateEntered).where(Study.CRGStudyID == study_id)
    return session.exec(stmt).first()

@router.get("/report/pdf_number")
def get_pdf_numbers_by_report_ids(report_ids: List[int] = Query(...), session: Session = Depends(get_session)) -> Dict[int, int]:
    stmt = select(Report.CRGReportID, Report.ReportNumber).where(Report.CRGReportID.in_(report_ids))
    rows = session.exec(stmt).all()
    return {row[0]: row[1] for row in rows}

@router.get("/report/{report_id}/pdf_number")
def get_pdf_number_by_report_id(report_id: int, session: Session = Depends(get_session)) -> int:
    return get_pdf_numbers_by_report_ids(report_ids=[report_id], session=session)[report_id]

@router.get("/mapping/report_study")
def get_mapping_report_study(session: Session = Depends(get_session)) -> Dict[int, List[int]]:
    stmt = select(StudyReport.CRGReportID, StudyReport.CRGStudyID)
    rows = session.exec(stmt).all()
    return convert_to_id_based_dict(rows)

@router.get("/mapping/study_report")
def get_mapping_report_study(session: Session = Depends(get_session)) -> Dict[int, List[int]]:
    stmt = select(StudyReport.CRGStudyID, StudyReport.CRGReportID)
    rows = session.exec(stmt).all()
    return convert_to_id_based_dict(rows)

@router.get("/reports/all")
def get_all_reports(session: Session = Depends(get_session)) -> List[Report]:
    stmt = select(Report).where((Report.Title.isnot(None)) | (Report.Abstract.isnot(None)))
    return session.exec(stmt).all()

@router.get("/reports/{report_id}")
def get_study_reports_by_id(report_id: int, session: Session = Depends(get_session)) -> Report:
    stmt = select(Report).where(Report.CRGReportID == report_id)
    return session.exec(stmt).first()

@router.get("/studies")
def get_studies(study_ids: List[int] = Query(...), session: Session = Depends(get_session)) -> List[Study]:
    stmt = select(Study).where(Study.CRGStudyID.in_(study_ids))
    return session.exec(stmt).all()


def normalize_author_names_(authors: List[str]) -> List[str]:
    def get_person_from_trial_id(author, data):
        author = author.strip()
        trial_id = author.replace("/", "-")
    
        if trial_id not in data:
            return [author]
        authors = data[trial_id]

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

@router.get("/authors/normalize")
def normalize_author_names(authors: List[str] = Query(...)) -> List[str]:
    
    return normalize_author_names_(authors=authors)

def get_author_frequencies_(authors: List[str]) -> Dict[str, int]:
    normalized_author_names = normalize_author_names(authors=authors)
    
    result = {}
    for author in normalized_author_names:
        if author in author_frequencies:
            result[author] = author_frequencies[author]

    return result

@router.get("/authors/frequencies")
def get_author_frequencies(authors: List[str] = Query(...)) -> Dict[str, int]:
    return get_author_frequencies_(authors=authors)

def get_study_persons_(study_ids: List[int], cutoff: str, session: Session) -> Dict[int, List[str]]:

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

@router.get("/study/persons")
def get_study_persons(study_ids: List[int] = Query(None), cutoff: str = Query(None), session: Session = Depends(get_session)) -> Dict[int, List[str]]:
    return get_study_persons_(study_ids=study_ids, cutoff=cutoff, session=session)

@router.get("/study_id")
def get_study_id_by_trial_id(trial_id: str = Query(...), cutoff: str = Query(None), session: Session = Depends(get_session)) -> List[int]:
    
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

@router.get("/trial/studies")
def get_possible_trial_ids_by_report(db: sqlite3.Connection = Depends(get_db)):

    def regexp(expr, item):
        return 1 if item and re.search(expr, item) else 0

    db.create_function("REGEXP", 2, regexp)

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
        OR COLUMN_NAME REGEXP 'MCT-[0-9]{5}');
    """

    query = """
        SELECT CRGStudyID
        FROM tblStudy
        WHERE FALSE 
        OR """ + query_regex.replace("COLUMN_NAME", "ShortName")

    cursor = db.execute(query)
    rows_studies = cursor.fetchall()
    all_studies = []
    for row in rows_studies:
        all_studies.append(row[0])

    #get all study ids where at least one report has a single trial id in its authors field
    query = """
        SELECT sr.CRGStudyID
        FROM tblReport r
        JOIN tblStudyReport sr
            ON r.CRGReportID = sr.CRGReportID
        WHERE r.Authors NOT LIKE '%//%'
        AND sr.CRGReportID IN (
            SELECT CRGReportID
            FROM tblStudyReport
            GROUP BY CRGReportID
            HAVING COUNT(DISTINCT CRGStudyID) = 1
        )
        AND """ + query_regex.replace("COLUMN_NAME", "r.Authors")

    cursor = db.execute(query)
    rows_reports = cursor.fetchall()
    all_reports = []
    for row in rows_reports:
        all_reports.append(row[0])

    return all_studies + all_reports

@router.get("/study/{study_id}/participants")
def get_study_participants(study_id: int, session: Session = Depends(get_session)) -> List[str]:
    return get_study_participants_(study_ids=[study_id], session=session)[study_id]

@router.get("/study/participants")
def get_study_participants_(study_ids: List[int] = Query(...), session: Session = Depends(get_session)) -> Dict[int, List[str]]:
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

@router.get("/study/{study_id}/design")
def get_study_design(study_id: int, session: Session = Depends(get_session)) -> List[str]:
    return get_study_design_(study_ids=[study_id], session=session)[study_id]

@router.get("/study/design")
def get_study_design_(study_ids: List[int] = Query(...), session: Session = Depends(get_session)) -> Dict[int, List[str]]:
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

@router.get("/study/{study_id}/tags/interventions")
def get_study_interventions(study_id: int, session: Session = Depends(get_session)):
    return get_study_interventions_(study_ids=[study_id], session=session)[study_id]

@router.get("/study/tags/interventions")
def get_study_interventions_(study_ids: List[int] = Query(...), session: Session = Depends(get_session)) -> Dict[int, List[Dict[str, Any]]]:
    stmt = (
        select(
            StudyIntervention.CRGStudyID.label("StudyID"),
            StudyIntervention.InterventionID.label("ID"),
            Intervention.InterventionDescription.label("Description"),
        )
        .join(Intervention, Intervention.InterventionID == StudyIntervention.InterventionID)
        .where(StudyIntervention.CRGStudyID.in_(study_ids))
    )

    rows = session.exec(stmt).all()  # -> [(StudyID, ID, Description), ...]

    # --- Group results by StudyID ---
    final_result: Dict[int, List[Dict[str, Any]]] = {}
    for study_id, intervention_id, description in rows:
        item = {"ID": intervention_id, "Description": description}
        final_result.setdefault(study_id, []).append(item)

    return final_result

@router.get("/tags/interventions/all")
def get_all_interventions(session: Session = Depends(get_session)) -> List[Intervention]:
    stmt = select(Intervention.InterventionID, Intervention.InterventionDescription)
    return session.exec(stmt).all()

@router.get("/tags/interventions")
def get_interventions_by_ids(ids: List[int] = Query(...), session: Session = Depends(get_session)) -> List[Intervention]:
    stmt = select(Intervention).where(Intervention.InterventionID.in_(ids))
    return session.exec(stmt).all()


@router.get("/study/{study_id}/tags/conditions")
def get_study_conditions(study_id: int, session: Session = Depends(get_session)):
    return get_study_conditions_(study_ids=[study_id], session=session)[study_id]

@router.get("/study/tags/conditions")
def get_study_conditions_(study_ids: List[int] = Query(...), session: Session = Depends(get_session)):
    stmt = (
        select(
            StudyCondition.CRGStudyID.label("StudyID"),
            StudyCondition.HealthCareConditionID.label("ID"),
            Condition.HealthCareConditionDescription.label("Description"),
        )
        .join(Condition, Condition.HealthCareConditionID == StudyCondition.HealthCareConditionID)
        .where(StudyCondition.CRGStudyID.in_(study_ids))
    )

    rows = session.exec(stmt).all()  # -> [(StudyID, ID, Description), ...]

    # --- Group results by StudyID ---
    final_result: Dict[int, List[Dict[str, Any]]] = {}
    for study_id, intervention_id, description in rows:
        item = {"ID": intervention_id, "Description": description}
        final_result.setdefault(study_id, []).append(item)

    return final_result

@router.get("/tags/conditions/all")
def get_all_conditions(session: Session = Depends(get_session)) -> List[Condition]:
    stmt = select(Condition.HealthCareConditionID, Condition.HealthCareConditionDescription)
    return session.exec(stmt).all()

@router.get("/tags/conditions")
def get_conditions_by_ids(ids: List[int] = Query(...), session: Session = Depends(get_session)) -> List[Condition]:
    stmt = select(Condition).where(Condition.HealthCareConditionID.in_(ids))
    return session.exec(stmt).all()

@router.get("/study/{study_id}/tags/outcomes")
def get_study_outcomes(study_id: int, session: Session = Depends(get_session)):
    return get_study_outcomes_(study_ids=[study_id], session=session)[study_id]

@router.get("/study/tags/outcomes")
def get_study_outcomes_(study_ids: List[int] = Query(...), session: Session = Depends(get_session)):
    stmt = (
        select(
            StudyOutcome.CRGStudyID.label("StudyID"),
            StudyOutcome.OutcomeID.label("ID"),
            Outcome.OutcomeDescription.label("Description"),
        )
        .join(Outcome, Outcome.OutcomeID == StudyOutcome.OutcomeID)
        .where(StudyOutcome.CRGStudyID.in_(study_ids))
    )

    rows = session.exec(stmt).all()  # -> [(StudyID, ID, Description), ...]

    # --- Group results by StudyID ---
    final_result: Dict[int, List[Dict[str, Any]]] = {}
    for study_id, intervention_id, description in rows:
        item = {"ID": intervention_id, "Description": description}
        final_result.setdefault(study_id, []).append(item)

    return final_result

@router.get("/tags/outcomes/all")
def get_all_outcomes(session: Session = Depends(get_session)) -> List[Outcome]:
    stmt = select(Outcome.OutcomeID, Outcome.OutcomeDescription)
    return session.exec(stmt).all()

@router.get("/tags/outcomes")
def get_outcomes_by_ids(ids: List[int] = Query(...), session: Session = Depends(get_session)) -> List[Outcome]:
    stmt = select(Outcome).where(Outcome.OutcomeID.in_(ids))
    return session.exec(stmt).all()

@router.get("/report/{report_id}/pdf_link")
def get_pdf_by_report_id(report_id: str, session: Session = Depends(get_session)) -> str:
    return get_pdf_links_by_report_ids(report_ids=[report_id], session=session)[report_id]

@router.get("/report/pdf_links")
def get_pdf_links_by_report_ids(report_ids: List[int] = Query(..., description="List of report IDs"),session: Session = Depends(get_session)) -> Dict[int, Optional[str]]:

    pdf_numbers = get_pdf_numbers_by_report_ids(report_ids, session=session)
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
        return {rid: None for rid in report_ids}

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

@router.get("/studies/{study_id}/reports", summary="Get all reports (and corresponding data) already belonging to this study")
def get_all_reports_by_study(study_id: int, session : Session = Depends(get_session)) -> List[Report]:
    
    data = get_study_reports_by_id(study_id, session)

    report_ids = [item['CRGReportID'] for item in data]
    
    pdf_links = get_pdf_links_by_report_ids(report_ids,session)

    for i in range(0, len(data)):
        key = str(data[i]['CRGReportID'])
        if key in pdf_links.keys():
            data[i]['PDFLinks'] = pdf_links[key]
        else:
            data[i]['PDFLinks'] = None

    return data

@router.get("/studies/{study_id}/reports/pdf_links", summary="Get all links to all fulltext pdfs belonging to this study")
def get_pdf_links_by_study(study_id: int, session : Session = Depends(get_session)) -> List[FulltextLink]:
    data = get_study_reports_by_id(study_id, session)
    report_ids = [item['CRGReportID'] for item in data]#data['CRGReportID']

    data = get_pdf_links_by_report_ids(report_ids,session)

    result = [{"report_id": k, "link": v} for k, v in data.items()]
    return result


@router.get("/reports/{report_id}/pdf_link", summary="Get the link to the fulltext pdf for a given report")
def get_pdf_link_by_reports(report_id: int, session : Session = Depends(get_session)) -> str:

    return get_pdf_links_by_report_ids([report_id],session)[report_id]
    
