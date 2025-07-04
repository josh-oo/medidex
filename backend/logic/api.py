from fastapi import FastAPI, Depends

from src.auth import is_admin, is_verified
from src.auth import get_users, update_user
from src.auth import signup, login, logout
from src.auth import get_api_keys, create_api_key, delete_api_key, verify_api_key

from src.logic import upload_file,get_all_reports_by_study
from src.logic import similarity_search_tags, similarity_search_studies
from src.logic import embedding_aspects, embedding
from src.logic import analyze_text, analyze_embedding

# Initialize FastAPI
app = FastAPI()

@app.get("/readyz")
def check():
    return "Ready"

@app.post("/upload", dependencies=[Depends(is_verified)])
async def logic_upload_file(result = Depends(upload_file)):
    return result

@app.get("/study/{study_id}/reports", dependencies=[Depends(is_verified)])
def logic_get_reports(result = Depends(get_all_reports_by_study)):
    return result

@app.post("/similarity_search/tags", dependencies=[Depends(is_verified)])
async def similarity_search_tags(result = Depends(similarity_search_tags)):
    return result

@app.post("/similarity_search/studies", dependencies=[Depends(is_verified)])
async def similarity_search_studies(result = Depends(similarity_search_studies)):
    return result

@app.post("/embedding/aspects", dependencies=[Depends(is_verified)])
async def embedding_aspects(result = Depends(embedding_aspects)):
    return result

@app.post("/embedding", dependencies=[Depends(is_verified)])
async def embedding(result = Depends(embedding)):
    return result

@app.post("/api_key/{owner}",  dependencies=[Depends(is_verified)])
def auth_create_api_key(result = Depends(create_api_key)):
   return result

@app.delete("/api_key/{key_id}",  dependencies=[Depends(is_verified)])
def auth_delete_api_key(result = Depends(delete_api_key)):
    return result

@app.get("/api_keys/{owner}", dependencies=[Depends(is_verified)])
def auth_get_api_keys(result = Depends(get_api_keys)):
    return result

@app.get("/users", dependencies=[Depends(is_admin)])
def auth_get_users(users = Depends(get_users)):
    return users

@app.put("/user/{user_id}", dependencies=[Depends(is_admin)])
def auth_update_user(result = Depends(update_user)):
    return result
    
@app.post("/signup")
def auth_ignup(token = Depends(signup)):
    return {"access_token": token, "token_type": "bearer"}

@app.post("/login")
def auth_login(token = Depends(login)):
    return {"access_token": token, "token_type": "bearer"}

@app.post("/logout")
def auth_logout(result = Depends(logout)):
    return result


@app.post("/api/v1/analyze_text", dependencies=[Depends(verify_api_key)])
async def logic_analyze_text(result = Depends(analyze_text)):
    return result

@app.post("/api/v1/analyze_embedding", dependencies=[Depends(verify_api_key)])
async def logic_analyze_embedding(result = Depends(analyze_embedding)):
    return result