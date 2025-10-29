from fastapi import APIRouter
from fastapi import Depends
import httpx
import os

from dotenv import load_dotenv

from .auth import is_verified
from typing import List, Optional

from pydantic import BaseModel

from googleapiclient.discovery import build
from google.oauth2 import service_account
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from typing import List, Optional
import sqlite3
import os

from datetime import date
import re
import json

from contextlib import contextmanager

from nameparser import HumanName

load_dotenv()

router = APIRouter(tags=["resources"], dependencies=[Depends(is_verified)])

#DATABASE_HOST = os.getenv("DATABASE_HOST")
#DATABASE_PORT = os.getenv("DATABASE_PORT")

class FulltextLink(BaseModel):
    report_id: int
    link: str

class ReportData(BaseModel):
    CENTRALReportID: Optional[int]
    CRGReportID: int
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
    CENTRALSubmissionStatus : Optional[str] = None
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
    UDef9 : Optional[str] = None
    UDef10: Optional[str] = None
    UDef8: Optional[str] = None
    PDFLinks: Optional[str]


DATABASE_VOLUME = os.getenv("DATABASE_VOLUME")

# Initialize FastAPI
app = FastAPI()

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
    
trial_person_mapping = {}
author_frequencies = {}
    
@router.on_event("startup")
async def startup_event():
    # Start background worker
    trial_person_mapping = load_trial_person_mapping()
    author_frequencies = load_author_frequencies()


# Request schema
class IdInput(BaseModel):
    ids: List[int]

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
def get_studies(study_ids: List[int] = Query(...), db: sqlite3.Connection = Depends(get_db)):
    placeholders = ','.join(['?'] * len(study_ids))
    query = f"""
        SELECT * FROM tblStudy
        WHERE CRGStudyID IN ({placeholders})
    """
    cursor = db.execute(query, study_ids)
    rows = cursor.fetchall()
    return convert_to_column_based_dict_ordered(cursor.description, rows, study_ids, 'CRGStudyID')

@router.get("/study/{study_id}/reports")
def get_study_reports_by_id(study_id: int, db: sqlite3.Connection = Depends(get_db)):
    return get_study_reports_by_ids(study_ids=[study_id], fields=None, cutoff=None, db=db)[study_id]

@router.get("/study/reports")
def get_study_reports_by_ids(
    study_ids: List[int] = Query(...),
    cutoff: str = Query(None),
    fields: Optional[List[str]] = Query(None),
    db: sqlite3.Connection = Depends(get_db)
):
    # Default: select all fields
    select_clause = "r.*"

    if cutoff is None:
        cutoff = date.today().isoformat()
    
    if fields:
        # Sanitize field names to avoid SQL injection
        allowed_fields = {
            "CRGReportID",
            "Title",
            "Abstract",
            "Authors",
            "DateEntered",
        }
        selected_fields = [field for field in fields if field in allowed_fields]
        if not selected_fields:
            raise HTTPException(status_code=400, detail="No valid fields specified.")
        select_clause = ", ".join([f"r.{field} AS {field}" for field in selected_fields])

    placeholders = ','.join(['?'] * len(study_ids))
    query = f"""
        SELECT sr.CRGStudyID AS StudyID, {select_clause}
        FROM tblStudyReport sr
        JOIN tblReport r ON sr.CRGReportID = r.CRGReportID
        WHERE sr.CRGStudyID IN ({placeholders})
        AND r.Dateentered < ?
    """
    cursor = db.execute(query, study_ids + [cutoff])
    rows = cursor.fetchall()
    result = convert_to_dict_list(cursor.description, rows)

    final_result = {}
    for item in result:
        if item['StudyID'] not in final_result.keys():
            final_result[item['StudyID']] = []
        final_result[item.pop('StudyID')].append(item)

    return final_result

@router.get("/study/{study_id}/date_entered")
def get_study_date_by_id(study_id: int, db: sqlite3.Connection = Depends(get_db)):
    query = f"""
        SELECT DateEntered
        FROM tblStudy
        WHERE CRGStudyID = ?
    """
    cursor = db.execute(query, (study_id,))
    return cursor.fetchone()[0]

@router.get("/report/pdf_number")
def get_pdf_numbers_by_report_ids(report_ids: List[int] = Query(...), db: sqlite3.Connection = Depends(get_db)):
    query = f"""
        SELECT CRGReportID, ReportNumber
        FROM tblReport
        WHERE CRGReportID IN ({','.join('?' for _ in report_ids)})
    """
    cursor = db.execute(query, tuple(report_ids))
    results = cursor.fetchall()
    
    # Return as a dict {report_id: report_number}
    return {int(row[0]): row[1] for row in results}

@router.get("/report/{report_id}/pdf_number")
def get_pdf_number_by_report_id(report_id: int, db: sqlite3.Connection = Depends(get_db)):
    return get_study_reports_by_ids(report_ids=[report_id], db=db)[report_id]

@router.get("/mapping/report_study")
def get_mapping_report_study(db: sqlite3.Connection = Depends(get_db)):
    query = f"""
        SELECT CRGReportID, CRGStudyID FROM tblStudyReport
    """
    cursor = db.execute(query)
    rows = cursor.fetchall()
    return convert_to_id_based_dict(rows)

@router.get("/mapping/study_report")
def get_mapping_report_study(db: sqlite3.Connection = Depends(get_db)):
    query = f"""
        SELECT CRGStudyID, CRGReportID FROM tblStudyReport
    """
    cursor = db.execute(query)
    rows = cursor.fetchall()
    return convert_to_id_based_dict(rows)

@router.get("/reports/all")
def get_all_reports(db: sqlite3.Connection = Depends(get_db)):
    query = f"""
        SELECT *
        FROM tblReport
        WHERE Title IS NOT NULL OR Abstract IS NOT NULL;
    """
    cursor = db.execute(query)
    rows = cursor.fetchall()
    return convert_to_column_based_dict(cursor.description, rows)

@router.get("/reports/{report_id}")
def get_study_reports_by_id(report_id: int, db: sqlite3.Connection = Depends(get_db)):
    query = f"""
        SELECT * FROM tblReport
        WHERE CRGReportID = ?
    """
    cursor = db.execute(query, (report_id,))
    rows = cursor.fetchall()
    return convert_to_dict_list(cursor.description, rows)

@router.get("/studies")
def get_studies(study_ids: List[int] = Query(...), db: sqlite3.Connection = Depends(get_db)):
    placeholders = ','.join(['?'] * len(study_ids))
    query = f"""
        SELECT * FROM tblStudy
        WHERE CRGStudyID IN ({placeholders})
    """
    cursor = db.execute(query, study_ids)
    rows = cursor.fetchall()
    return convert_to_column_based_dict_ordered(cursor.description, rows, study_ids, 'CRGStudyID')


def normalize_author_names_(authors: List[str]):
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
def normalize_author_names(authors: List[str] = Query(...)):
    
    return normalize_author_names_(authors=authors)

def get_author_frequencies_(authors: List[str]):
    normalized_author_names = normalize_author_names(authors=authors)
    
    result = {}
    for author in normalized_author_names:
        if author in author_frequencies:
            result[author] = author_frequencies[author]

    return result

@router.get("/authors/frequencies")
def get_author_frequencies(authors: List[str] = Query(...)):
    return get_author_frequencies_(authors=authors)

def get_study_persons_(study_ids: List[int], cutoff: str, db: sqlite3.Connection):

    query = """
        SELECT sr.CRGStudyID AS StudyID, Authors
        FROM tblStudyReport sr
        JOIN tblReport r ON sr.CRGReportID = r.CRGReportID
        WHERE r.Dateentered < ?
    """

    params = [cutoff]
    
    if study_ids is not None:
        placeholders = ','.join(['?'] * len(study_ids))
        query += f" AND sr.CRGStudyID IN ({placeholders})"
        params += study_ids
    
    cursor = db.execute(query, params)
    rows = cursor.fetchall()
    result = convert_to_dict_list(cursor.description, rows)

    final_result = {}

    for item in result:
        key = int(item['StudyID'])
        value = item['Authors']
        authors = [author.strip() for author in value.split("//")]
        normalized_authors = normalize_author_names(authors=authors)

        final_result[key] = normalized_authors

    return final_result

@router.get("/study/persons")
def get_study_persons(study_ids: List[int] = Query(None), cutoff: str = Query(None), db: sqlite3.Connection = Depends(get_db)):
    return get_study_persons_(study_ids=study_ids, cutoff=cutoff, db=db)

@router.get("/study_id")
def get_study_id_by_trial_id(trial_id: str = Query(...), cutoff: str = Query(...), db: sqlite3.Connection = Depends(get_db)):
    
    trial_id = trial_id.replace("/", "-")
    alternative_ids = []
    with open(os.path.join(DATABASE_VOLUME, "resources", "trial_id_mapping.json"), "r") as json_file:
        data = json.load(json_file)
        if trial_id in data:
            alternative_ids = data[trial_id]

    alternative_ids += [trial_id]

    alternative_ids = [current_id.replace("/", "-") for current_id in alternative_ids]

    placeholders = ','.join(['?'] * len(alternative_ids))
    
    query = f"""
        SELECT DISTINCT CRGStudyID
        FROM tblStudy
        WHERE (REPLACE(ShortName, '/', '-') IN ({placeholders}) OR REPLACE(TrialRegistrationID, '/', '-') IN ({placeholders}))
        AND DateEntered < ?
    """
    cursor = db.execute(query, tuple(alternative_ids) + tuple(alternative_ids) +(cutoff,))
    rows = cursor.fetchall()

    result = [ row[0] for row in rows]
    #if len(result) > 0:
    #    return list(set(result))
    
    placeholders_authors = " OR ".join(["REPLACE(r.Authors, '/', '-') LIKE '%' || ? || '%'"] * len(alternative_ids))

    query = f"""
        SELECT DISTINCT sr.CRGStudyID
        FROM tblStudyReport sr
        JOIN tblReport r ON sr.CRGReportID = r.CRGReportID
        WHERE ({placeholders_authors} OR REPLACE(r.TrialRegistrationID, '/', '-') IN ({placeholders}))
        AND r.Dateentered < ?
    """
    cursor = db.execute(query, (trial_id, trial_id,cutoff))
    rows = cursor.fetchall()

    for row in rows:
        result.append(row[0])

    return list(set(result))

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
def get_study_participants(study_id: int, db: sqlite3.Connection = Depends(get_db)):
    return get_study_participants_(study_ids=[study_id], db=db)[study_id]

@router.get("/study/participants")
def get_study_participants_(study_ids: List[int] = Query(...), db: sqlite3.Connection = Depends(get_db)):
    placeholders = ','.join(['?'] * len(study_ids))
    query = f"""
        SELECT sp.CRGStudyID AS StudyID, ParticipantDescription
        FROM tblStudyParticipant sp
        JOIN tblParticipant p ON sp.ParticipantsID = p.ParticipantsID
        WHERE sp.CRGStudyID IN ({placeholders});
    """
    cursor = db.execute(query, study_ids)
    rows = cursor.fetchall()
    result = convert_to_dict_list(cursor.description, rows)

    final_result = {}
    for item in result:
        if item['StudyID'] not in final_result.keys():
            final_result[item['StudyID']] = []
        final_result[item.pop('StudyID')].append(item['ParticipantDescription'])

    return final_result

@router.get("/study/{study_id}/design")
def get_study_design(study_id: int, db: sqlite3.Connection = Depends(get_db)):
    return get_study_design_(study_ids=[study_id], db=db)[study_id]

@router.get("/study/design")
def get_study_design_(study_ids: List[int] = Query(...), db: sqlite3.Connection = Depends(get_db)):
    placeholders = ','.join(['?'] * len(study_ids))
    query = f"""
        SELECT sd.CRGStudyID as StudyID, DesignDescription
        FROM tblStudyDesign sd
        JOIN tblDesign d ON sd.DesignID = d.DesignID
        WHERE sd.CRGStudyID IN ({placeholders});
    """
    cursor = db.execute(query, study_ids)
    rows = cursor.fetchall()
    result = convert_to_dict_list(cursor.description, rows)

    final_result = {}
    for item in result:
        if item['StudyID'] not in final_result.keys():
            final_result[item['StudyID']] = []
        final_result[item.pop('StudyID')].append(item['DesignDescription'])

    return final_result

@router.get("/study/{study_id}/tags/interventions")
def get_study_interventions(study_id: int, db: sqlite3.Connection = Depends(get_db)):
    return get_study_interventions_(study_ids=[study_id], db=db)[study_id]

@router.get("/study/tags/interventions")
def get_study_interventions_(study_ids: List[int] = Query(...), db: sqlite3.Connection = Depends(get_db)):
    placeholders = ','.join(['?'] * len(study_ids))
    query = f"""
        SELECT si.CRGStudyID AS StudyID, si.InterventionID AS ID, i.InterventionDescription AS Description
        FROM tblStudyIntervention si
        JOIN tblIntervention i ON si.InterventionID = i.InterventionID 
        WHERE si.CRGStudyID IN ({placeholders});
    """
    cursor = db.execute(query, study_ids)
    rows = cursor.fetchall()
    result = convert_to_dict_list(cursor.description, rows)

    final_result = {}
    for item in result:
        if item['StudyID'] not in final_result.keys():
            final_result[item['StudyID']] = []
        final_result[item.pop('StudyID')].append(item)

    return final_result

@router.get("/tags/interventions/all")
def get_all_interventions(db: sqlite3.Connection = Depends(get_db)):
    query = f"""
        SELECT InterventionID, InterventionDescription FROM tblIntervention
    """
    cursor = db.execute(query)
    rows = cursor.fetchall()
    return convert_to_id_based_dict(rows, multi_values=False)

@router.get("/tags/interventions")
def get_interventions_by_ids(ids: List[int] = Query(...), db: sqlite3.Connection = Depends(get_db)):
    ID_COLUMN = "InterventionID"
    placeholders = ','.join(['?'] * len(ids))
    query = f"""
        SELECT * FROM tblIntervention
        WHERE {ID_COLUMN} IN ({placeholders})
    """
    cursor = db.execute(query, ids)
    rows = cursor.fetchall()
    #return convert_to_column_based_dict_ordered(cursor.description, rows, ids, ID_COLUMN)
    return convert_to_id_based_dict(rows)


@router.get("/study/{study_id}/tags/conditions")
def get_study_conditions(study_id: int, db: sqlite3.Connection = Depends(get_db)):
    return get_study_conditions_(study_ids=[study_id], db=db)[study_id]

@router.get("/study/tags/conditions")
def get_study_conditions_(study_ids: List[int] = Query(...), db: sqlite3.Connection = Depends(get_db)):
    placeholders = ','.join(['?'] * len(study_ids))
    query = f"""
        SELECT sc.CRGStudyID AS StudyID, sc.HealthCareConditionID AS ID, c.HealthCareConditionDescription AS Description
        FROM tblStudyHealthCareCondition sc 
        JOIN tblHealthCareCondition c ON sc.HealthCareConditionID = c.HealthCareConditionID
        WHERE sc.CRGStudyID IN ({placeholders});
    """
    cursor = db.execute(query, study_ids)
    rows = cursor.fetchall()
    result = convert_to_dict_list(cursor.description, rows)

    final_result = {}
    for item in result:
        if item['StudyID'] not in final_result.keys():
            final_result[item['StudyID']] = []
        final_result[item['StudyID']].append({'Description':item['Description'], 'ID':item['ID']})

    return final_result

@router.get("/tags/conditions/all")
def get_all_conditions(db: sqlite3.Connection = Depends(get_db)):
    query = f"""
        SELECT HealthCareConditionID, HealthCareConditionDescription FROM tblHealthCareCondition
    """
    cursor = db.execute(query)
    rows = cursor.fetchall()
    return convert_to_id_based_dict(rows, multi_values=False)

@router.get("/tags/conditions")
def get_conditions_by_ids(ids: List[int] = Query(...), db: sqlite3.Connection = Depends(get_db)):
    ID_COLUMN = "HealthCareConditionID"
    placeholders = ','.join(['?'] * len(ids))
    query = f"""
        SELECT * FROM tblHealthCareCondition
        WHERE {ID_COLUMN} IN ({placeholders})
    """
    cursor = db.execute(query, ids)
    rows = cursor.fetchall()
    #return convert_to_column_based_dict_ordered(cursor.description, rows, ids, ID_COLUMN)
    return convert_to_id_based_dict(rows)

@router.get("/study/{study_id}/tags/outcomes")
def get_study_outcomes(study_id: int, db: sqlite3.Connection = Depends(get_db)):
    return get_study_outcomes_(study_ids=[study_id], db=db)[study_id]

@router.get("/study/tags/outcomes")
def get_study_outcomes_(study_ids: List[int] = Query(...), db: sqlite3.Connection = Depends(get_db)):
    placeholders = ','.join(['?'] * len(study_ids))
    query = f"""
        SELECT so.CRGStudyID AS StudyID, so.OutcomeID AS ID, o.OutcomeDescription AS Description
        FROM tblStudyOutcome so 
        JOIN tblOutcome o ON so.OutcomeID = o.OutcomeID
        WHERE so.CRGStudyID IN ({placeholders});
    """
    cursor = db.execute(query, study_ids)
    rows = cursor.fetchall()
    result = convert_to_dict_list(cursor.description, rows)

    final_result = {}
    for item in result:
        if item['StudyID'] not in final_result.keys():
            final_result[item['StudyID']] = []
        final_result[item['StudyID']].append({'Description':item['Description'], 'ID':item['ID']})

    return final_result

@router.get("/tags/outcomes/all")
def get_all_outcomes(db: sqlite3.Connection = Depends(get_db)):
    query = f"""
        SELECT OutcomeID, OutcomeDescription FROM tblOutcome
    """
    cursor = db.execute(query)
    rows = cursor.fetchall()
    return convert_to_id_based_dict(rows, multi_values=False)

@router.get("/tags/outcomes")
def get_outcomes_by_ids(ids: List[int] = Query(...), db: sqlite3.Connection = Depends(get_db)):
    ID_COLUMN = "OutcomeID"
    placeholders = ','.join(['?'] * len(ids))
    query = f"""
        SELECT * FROM tblOutcome
        WHERE {ID_COLUMN} IN ({placeholders})
    """
    cursor = db.execute(query, ids)
    rows = cursor.fetchall()
    return convert_to_id_based_dict(rows)
    #return convert_to_column_based_dict_ordered(cursor.description, rows, ids, ID_COLUMN)

@router.get("/report/{report_id}/pdf_link")
def get_pdf_by_report_id(report_id: str, db: sqlite3.Connection = Depends(get_db)):
    return get_pdf_links_by_report_ids(report_ids=[report_id], db=db)[report_id]

@router.get("/report/pdf_links")
def get_pdf_links_by_report_ids(report_ids: List[int] = Query(..., description="List of report IDs"),db: sqlite3.Connection = Depends(get_db)):

    pdf_numbers = get_pdf_numbers_by_report_ids(report_ids, db)
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
def get_all_reports_by_study(study_id: int, db : sqlite3.Connection = Depends(get_db)) -> List[ReportData]:
    
    data = get_study_reports_by_id(study_id, db)

    report_ids = [item['CRGReportID'] for item in data]
    
    pdf_links = get_pdf_links_by_report_ids(report_ids,db)

    for i in range(0, len(data)):
        key = str(data[i]['CRGReportID'])
        if key in pdf_links.keys():
            data[i]['PDFLinks'] = pdf_links[key]
        else:
            data[i]['PDFLinks'] = None

    return data

@router.get("/studies/{study_id}/reports/pdf_links", summary="Get all links to all fulltext pdfs belonging to this study")
def get_pdf_links_by_study(study_id: int, db : sqlite3.Connection = Depends(get_db)) -> List[FulltextLink]:
    data = get_study_reports_by_id(study_id, db)
    report_ids = [item['CRGReportID'] for item in data]#data['CRGReportID']

    data = get_pdf_links_by_report_ids(report_ids,db)

    result = [{"report_id": k, "link": v} for k, v in data.items()]
    return result


@router.get("/reports/{report_id}/pdf_link", summary="Get the link to the fulltext pdf for a given report")
def get_pdf_link_by_reports(report_id: int, db : sqlite3.Connection = Depends(get_db)) -> str:

    return get_pdf_links_by_report_ids([report_id],db)[report_id]
    
