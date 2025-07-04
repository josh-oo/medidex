from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from typing import List
import sqlite3
import os

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

@app.post("/studies")
def get_studies_by_ids(id_input: IdInput, db: sqlite3.Connection = Depends(get_db)):
    placeholders = ','.join(['?'] * len(id_input.ids))
    query = f"""
        SELECT * FROM tblStudy
        WHERE CRGStudyID IN ({placeholders})
    """
    cursor = db.execute(query, id_input.ids)
    rows = cursor.fetchall()
    return convert_to_column_based_dict_ordered(cursor.description, rows, id_input.ids, 'CRGStudyID')

@app.get("/reports/{report_id}")
def get_study_reports_by_id(report_id: int, db: sqlite3.Connection = Depends(get_db)):
    query = f"""
        SELECT * FROM tblReport
        WHERE CRGReportID = ?
    """
    cursor = db.execute(query, (report_id,))
    rows = cursor.fetchall()
    return convert_to_dict_list(cursor.description, rows)

@app.get("/study/{study_id}/reports")
def get_study_reports_by_id(study_id: int, db: sqlite3.Connection = Depends(get_db)):
    query = f"""
        SELECT r.*
        FROM tblStudyReport sr
        JOIN tblReport r ON sr.CRGReportID = r.CRGReportID
        WHERE sr.CRGStudyID = ?
    """
    cursor = db.execute(query, (study_id,))
    rows = cursor.fetchall()
    return convert_to_column_based_dict(cursor.description, rows)

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

@app.get("/study/{study_id}/reports")
def get_all_reports(study_id: int, db: sqlite3.Connection = Depends(get_db)):
    query = f"""
        SELECT r.*
        FROM tblReport r
        JOIN tblStudyReport sr ON r.CRGReportID = sr.CRGReportID
        WHERE sr.CRGStudyID = ?;
    """
    cursor = db.execute(query, (study_id,))
    rows = cursor.fetchall()
    return convert_to_dict_list(cursor.description,rows)

@app.post("/study/tags/interventions/")
def get_all_interventions(id_input: IdInput, db: sqlite3.Connection = Depends(get_db)):
    placeholders = ','.join(['?'] * len(id_input.ids))
    query = f"""
        SELECT si.InterventionID AS ID, i.InterventionDescription AS Description
        FROM tblStudyIntervention si
        JOIN tblIntervention i ON si.InterventionID = i.InterventionID 
        WHERE si.CRGStudyID IN ({placeholders})
    """
    cursor = db.execute(query, id_input.ids)
    rows = cursor.fetchall()
    return convert_to_dict_list(cursor.description,rows)

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

@app.post("/study/tags/conditions/")
def get_all_interventions(id_input: IdInput, db: sqlite3.Connection = Depends(get_db)):
    placeholders = ','.join(['?'] * len(id_input.ids))
    query = f"""
        SELECT sc.HealthCareConditionID AS ID, c.HealthCareConditionDescription AS Description
        FROM tblStudyHealthCareCondition sc 
        JOIN tblHealthCareCondition c ON sc.HealthCareConditionID = c.HealthCareConditionID
        WHERE sc.CRGStudyID IN ({placeholders})
    """
    cursor = db.execute(query, id_input.ids)
    rows = cursor.fetchall()
    return convert_to_dict_list(cursor.description,rows)

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

@app.post("/study/tags/outcomes/")
def get_all_interventions(id_input: IdInput, db: sqlite3.Connection = Depends(get_db)):
    placeholders = ','.join(['?'] * len(id_input.ids))
    query = f"""
        SELECT so.OutcomeID AS ID, o.OutcomeDescription AS Description
        FROM tblStudyOutcome so 
        JOIN tblOutcome o ON so.OutcomeID = o.OutcomeID
        WHERE so.CRGStudyID IN ({placeholders})
    """
    cursor = db.execute(query, id_input.ids)
    rows = cursor.fetchall()
    return convert_to_dict_list(cursor.description,rows)

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

