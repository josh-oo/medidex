from fastapi import FastAPI, Depends

from src import auth
from src.auth import is_admin, is_verified, verify_api_key

from src.logic import upload_file, get_available_batches, get_batched_report, delete_batch, get_all_reports_by_study, get_pdf_links_by_reports, extract_trial_id
from src.logic import similarity_search_tags, similarity_search_studies
from src.logic import embed_report, embed_aspect
from src.logic import analyze_text, analyze_embedding

from src.logic import startup_event as logic_startup_event

from src.logic import assign_studies, delete_assigned_studies

# Initialize FastAPI
app = FastAPI(root_path="/api")
app.include_router(auth.router)

@app.on_event("startup")
async def startup_event():
    await logic_startup_event()

@app.get("/readyz", tags=["health"], summary="Readiness probe")
def check():
    return "Ready"

@app.post("/upload", dependencies=[Depends(is_verified)])
async def logic_upload_file(result = Depends(upload_file)):
    return result

@app.get("/batches", dependencies=[Depends(is_verified)])
async def logic_get_available_batches(result = Depends(get_available_batches)):
    return result

@app.get("/batches/{batch_hash}/{report_index}", dependencies=[Depends(is_verified)])
async def logic_get_batched_report(result = Depends(get_batched_report)):
    return result

@app.delete("/batches/{batch_hash}", dependencies=[Depends(is_verified)])
async def logic_delete_batch(result = Depends(delete_batch)):
    return result

@app.put("/batches/{batch_hash}/{report_index}/studies", dependencies=[Depends(is_verified)])
async def logic_assign_studies(result = Depends(assign_studies)):
    return result

@app.delete("/batches/{batch_hash}/{report_index}/studies", dependencies=[Depends(is_verified)])
async def logic_delete_assigned_studies(result = Depends(delete_assigned_studies)):
    return result

@app.post("/extract_trial_id", dependencies=[Depends(is_verified)])
async def logic_extracdt_trial_id(result = Depends(extract_trial_id)):
    return result

@app.get("/study/{study_id}/reports", dependencies=[Depends(is_verified)])
def logic_get_reports(result = Depends(get_all_reports_by_study)):
    return result

@app.get("/report/pdf_links", dependencies=[Depends(is_verified)])
def logic_get_pdf_links_by_reports(result = Depends(get_pdf_links_by_reports)):
    return result

@app.post("/similarity_search/tags", dependencies=[Depends(is_verified)])
async def similarity_search_tags(result = Depends(similarity_search_tags)):
    return result

@app.post("/similarity_search/studies", dependencies=[Depends(is_verified)])
async def similarity_search_studies(result = Depends(similarity_search_studies)):
    return result

@app.post("/embed/report", dependencies=[Depends(is_verified)])
async def embed_report(result = Depends(embed_report)):
    return result

@app.post("/embed/aspect", dependencies=[Depends(is_verified)])
async def embed_aspect(result = Depends(embed_aspect)):
    return result

@app.post("/api/v1/analyze_text", dependencies=[Depends(verify_api_key)])
async def logic_analyze_text(result = Depends(analyze_text)):
    return result

@app.post("/api/v1/analyze_embedding", dependencies=[Depends(verify_api_key)])
async def logic_analyze_embedding(result = Depends(analyze_embedding)):
    return result