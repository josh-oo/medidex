from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from typing import List, Optional
import sqlite3
import os

from datetime import date

load_dotenv()

DATABASE_VOLUME = os.getenv("DATABASE_VOLUME")

# Initialize FastAPI
app = FastAPI()

def get_db():
    conn = sqlite3.connect("file:" + os.path.join(DATABASE_VOLUME,"meerkat.db") + "?mode=ro",uri=True, check_same_thread=False)
    #conn.execute("PRAGMA journal_mode=DELETE;")  # avoid WAL writes
    try:
        yield conn
    finally:
        conn.close()

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

@app.get("/readyz")
def check(db: sqlite3.Connection = Depends(get_db)):
    try:
        db.cursor()
    except Exception as ex:
        raise HTTPException(status_code=503, detail="Service not ready")
    return JSONResponse(status_code=200, content={"status": "ok"})

@app.get("/studies")
def get_studies(study_ids: List[int] = Query(...), db: sqlite3.Connection = Depends(get_db)):
    placeholders = ','.join(['?'] * len(study_ids))
    query = f"""
        SELECT * FROM tblStudy
        WHERE CRGStudyID IN ({placeholders})
    """
    cursor = db.execute(query, study_ids)
    rows = cursor.fetchall()
    return convert_to_column_based_dict_ordered(cursor.description, rows, study_ids, 'CRGStudyID')

@app.get("/study/{study_id}/reports")
def get_study_reports_by_id(study_id: int, db: sqlite3.Connection = Depends(get_db)):
    return get_study_reports_by_ids(study_ids=[study_id], fields=None, cutoff=None, db=db)[study_id]

@app.get("/study/reports")
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

@app.get("/study/{study_id}/date_entered")
def get_study_date_by_id(study_id: int, db: sqlite3.Connection = Depends(get_db)):
    query = f"""
        SELECT DateEntered
        FROM tblStudy
        WHERE CRGStudyID = ?
    """
    cursor = db.execute(query, (study_id,))
    return cursor.fetchone()[0]

@app.get("/mapping/report_study")
def get_mapping_report_study(db: sqlite3.Connection = Depends(get_db)):
    query = f"""
        SELECT CRGReportID, CRGStudyID FROM tblStudyReport
    """
    cursor = db.execute(query)
    rows = cursor.fetchall()
    return convert_to_id_based_dict(rows)

@app.get("/mapping/study_report")
def get_mapping_report_study(db: sqlite3.Connection = Depends(get_db)):
    query = f"""
        SELECT CRGStudyID, CRGReportID FROM tblStudyReport
    """
    cursor = db.execute(query)
    rows = cursor.fetchall()
    return convert_to_id_based_dict(rows)

@app.get("/reports/all")
def get_all_reports(db: sqlite3.Connection = Depends(get_db)):
    query = f"""
        SELECT *
        FROM tblReport
        WHERE Title IS NOT NULL OR Abstract IS NOT NULL;
    """
    cursor = db.execute(query)
    rows = cursor.fetchall()
    return convert_to_column_based_dict(cursor.description, rows)

@app.get("/reports/{report_id}")
def get_study_reports_by_id(report_id: int, db: sqlite3.Connection = Depends(get_db)):
    query = f"""
        SELECT * FROM tblReport
        WHERE CRGReportID = ?
    """
    cursor = db.execute(query, (report_id,))
    rows = cursor.fetchall()
    return convert_to_dict_list(cursor.description, rows)

@app.get("/study_id")
def get_study_id_by_trial_id(trial_id: str = Query(...), cutoff: str = Query(...), db: sqlite3.Connection = Depends(get_db)):
    query = f"""
        SELECT CRGStudyID
        FROM tblStudy
        WHERE ShortName = ? OR TrialRegistrationID = ? 
        AND DateEntered < ?
    """
    cursor = db.execute(query, (trial_id, trial_id,cutoff))
    rows = cursor.fetchone()

    if rows:
        return rows

    query = f"""
        SELECT sr.CRGStudyID
        FROM tblStudyReport sr
        JOIN tblReport r ON sr.CRGReportID = r.CRGReportID
        WHERE r.Authors LIKE '%' || ? || '%' OR r.TrialRegistrationID = ?
        AND r.Dateentered < ?
    """
    cursor = db.execute(query, (trial_id, trial_id,cutoff))
    rows = cursor.fetchone()

    return rows

@app.get("/study/{study_id}/participants")
def get_study_participants(study_id: int, db: sqlite3.Connection = Depends(get_db)):
    return get_study_participants_(study_ids=[study_id], db=db)[study_id]

@app.get("/study/participants")
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

@app.get("/study/{study_id}/design")
def get_study_design(study_id: int, db: sqlite3.Connection = Depends(get_db)):
    return get_study_design_(study_ids=[study_id], db=db)[study_id]

@app.get("/study/design")
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

@app.get("/study/{study_id}/tags/interventions")
def get_study_interventions(study_id: int, db: sqlite3.Connection = Depends(get_db)):
    return get_study_interventions_(study_ids=[study_id], db=db)[study_id]

@app.get("/study/tags/interventions")
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

@app.get("/tags/interventions/all")
def get_all_interventions(db: sqlite3.Connection = Depends(get_db)):
    query = f"""
        SELECT InterventionID, InterventionDescription FROM tblIntervention
    """
    cursor = db.execute(query)
    rows = cursor.fetchall()
    return convert_to_id_based_dict(rows, multi_values=False)

@app.post("/tags/interventions")
def get_interventions_by_ids(id_input: IdInput, db: sqlite3.Connection = Depends(get_db)):
    ID_COLUMN = "InterventionID"
    placeholders = ','.join(['?'] * len(id_input.ids))
    query = f"""
        SELECT * FROM tblIntervention
        WHERE {ID_COLUMN} IN ({placeholders})
    """
    cursor = db.execute(query, id_input.ids)
    rows = cursor.fetchall()
    return convert_to_column_based_dict_ordered(cursor.description, rows, id_input.ids, ID_COLUMN)


@app.get("/study/{study_id}/tags/conditions")
def get_study_conditions(study_id: int, db: sqlite3.Connection = Depends(get_db)):
    return get_study_conditions_(study_ids=[study_id], db=db)[study_id]

@app.get("/study/tags/conditions")
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

@app.get("/tags/conditions/all")
def get_all_conditions(db: sqlite3.Connection = Depends(get_db)):
    query = f"""
        SELECT HealthCareConditionID, HealthCareConditionDescription FROM tblHealthCareCondition
    """
    cursor = db.execute(query)
    rows = cursor.fetchall()
    return convert_to_id_based_dict(rows, multi_values=False)

@app.post("/tags/conditions")
def get_conditions_by_ids(id_input: IdInput, db: sqlite3.Connection = Depends(get_db)):
    ID_COLUMN = "HealthCareConditionID"
    placeholders = ','.join(['?'] * len(id_input.ids))
    query = f"""
        SELECT * FROM tblHealthCareCondition
        WHERE {ID_COLUMN} IN ({placeholders})
    """
    cursor = db.execute(query, id_input.ids)
    rows = cursor.fetchall()
    return convert_to_column_based_dict_ordered(cursor.description, rows, id_input.ids, ID_COLUMN)

@app.get("/study/{study_id}/tags/outcomes")
def get_study_outcomes(study_id: int, db: sqlite3.Connection = Depends(get_db)):
    return get_study_conditions_(study_ids=[study_id], db=db)[study_id]

@app.get("/study/tags/outcomes")
def get_study_conditions_(study_ids: List[int] = Query(...), db: sqlite3.Connection = Depends(get_db)):
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

@app.get("/tags/outcomes/all")
def get_all_outcomes(db: sqlite3.Connection = Depends(get_db)):
    query = f"""
        SELECT OutcomeID, OutcomeDescription FROM tblOutcome
    """
    cursor = db.execute(query)
    rows = cursor.fetchall()
    return convert_to_id_based_dict(rows, multi_values=False)

@app.post("/tags/outcomes")
def get_outcomes_by_ids(id_input: IdInput, db: sqlite3.Connection = Depends(get_db)):
    ID_COLUMN = "OutcomeID"
    placeholders = ','.join(['?'] * len(id_input.ids))
    query = f"""
        SELECT * FROM tblOutcome
        WHERE {ID_COLUMN} IN ({placeholders})
    """
    cursor = db.execute(query, id_input.ids)
    rows = cursor.fetchall()
    return convert_to_column_based_dict_ordered(cursor.description, rows, id_input.ids, ID_COLUMN)