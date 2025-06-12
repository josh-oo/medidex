from fastapi import FastAPI, Query, UploadFile, File, HTTPException, Depends
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from pydantic import BaseModel
from dotenv import load_dotenv
from qdrant_client import QdrantClient, models
from typing import List, Annotated
import httpx
import os

import grpc
import embedding_pb2
import embedding_pb2_grpc

from rispy.parser import RisParser
import rispy
import nbib
import io

import sqlite3
from passlib.context import CryptContext
from jose import jwt
from datetime import datetime, timedelta, timezone

load_dotenv()

MODEL_HOST = os.getenv("EMBEDDING_HOST")
MODEL_PORT = os.getenv("EMBEDDING_PORT")
DATABASE_HOST = os.getenv("DATABASE_HOST")
DATABASE_PORT = os.getenv("DATABASE_PORT")
VECTORSTORE_HOST = os.getenv("VECTORSTORE_HOST")
VECTORSTORE_PORT = os.getenv("VECTORSTORE_PORT")

DATABASE_VOLUME = os.getenv("DATABASE_VOLUME")
JWT_SECRET = os.getenv("JWT_SECRET")

# Initialize FastAPI
app = FastAPI()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_db():
    conn = sqlite3.connect(os.path.join(DATABASE_VOLUME,"users.db"))
    try:
        yield conn
    finally:
        conn.close()

# Request schema
class TextInput(BaseModel):
    text: str

class EmbeddingInput(BaseModel):
    embedding: List[float]
    model_id: str

@app.get("/readyz")
def check():
    return "Ready"

@app.post("/upload")
async def upload_file(file: UploadFile = File(...), token: str = Depends(oauth2_scheme)):
    class CgiParser(RisParser):
        START_TAG = "DB"

    def add_end_tag(text: str) -> str:
        return '\n'.join(
            line if line.strip() else "ER  -  \n\n"
            for line in text.splitlines()
        )
    
    if file.filename.endswith(".ris"):
        try:
            content = await file.read()
            text_stream = io.StringIO(content.decode('utf-8'))  # RIS is plain text
            entries = rispy.load(text_stream)  # returns a list of dicts
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to parse .ris: {str(e)}")
        
    elif file.filename.endswith(".cgi"):
        try:
            content = await file.read()
            text_stream = io.StringIO(add_end_tag(content.decode('utf-8')))  # RIS is plain text
            entries = rispy.load(text_stream, implementation=CgiParser, skip_unknown_tags=True)  # returns a list of dicts
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to parse .cgi: {str(e)}")
        
    elif file.filename.endswith(".nbib"):
        try:
            content = await file.read()
            decoded = content.decode("utf-8")
            entries = nbib.read(decoded)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to parse .nbib: {str(e)}")

    else:
        raise HTTPException(status_code=400, detail="Only .ris and .nbib files are accepted")

    results = []
    for entry in entries:
        title = entry.get('primary_title', None)
        if not title:
            title = entry.get('title', None)
        results.append({'title':title, 'abstract':entry.get('abstract', None)})

    return results

@app.post("/similarity_search/tags/{type}")
async def similarity_search_tags(type: str, embedding: EmbeddingInput, token: str = Depends(oauth2_scheme)):

    client = QdrantClient(host=VECTORSTORE_HOST, grpc_port=VECTORSTORE_PORT, prefer_grpc=True)

    search_results = client.query_points(
        collection_name=embedding.model_id + "_tags",
        query=embedding.embedding,
        limit=10,
        query_filter=models.Filter(must=[models.FieldCondition(key="type", match=models.MatchValue(value=type))]),
    )

    found_tag_ids = []
    scores = []

    for result in search_results.points:
        current_id = int(result.id.split("-")[-1])
        found_tag_ids.append(current_id)
        scores.append(str(round(result.score * 100)) + "%")

    async with httpx.AsyncClient() as client:
        response = await client.post(f"http://{DATABASE_HOST}:{DATABASE_PORT}/tags/{type}", json={'ids': found_tag_ids})

    result = response.json()
    result['Relevance'] = scores
    return result

@app.post("/similarity_search/studies")
async def similarity_search_studies(embedding: EmbeddingInput, aspect: str = Query("default"), token: str = Depends(oauth2_scheme)):

    client = QdrantClient(host=VECTORSTORE_HOST, grpc_port=VECTORSTORE_PORT, prefer_grpc=True)

    search_results = client.query_points_groups(
        collection_name=embedding.model_id,
        # Same as in the regular query_points() API
        query=embedding.embedding,
        using=aspect,
        # Grouping parameters
        group_by="belongs_to_study",  # Path of the field to group by
        limit=10,  # Max amount of groups
        group_size=1,  # Max amount of points per group
    )

    found_study_ids = []
    scores = []
    for result in search_results.groups:
        for hit in result.hits:
            for item in hit.payload['belongs_to_study']:
                found_study_ids.append(item)
                scores.append(str(round(hit.score * 100)) + "%")

    async with httpx.AsyncClient() as client:
        response = await client.post(f"http://{DATABASE_HOST}:{DATABASE_PORT}/studies", json={'ids': found_study_ids})

    result = response.json()
    result['Relevance'] = scores
    return result

@app.post("/embedding/aspects")
async def embedding_aspects(input: TextInput, token: str = Depends(oauth2_scheme)):

    def single_element_generator(element):
        yield element

    request = embedding_pb2.EmbedRequest(text=input.text)

    channel = grpc.insecure_channel(f"{MODEL_HOST}:{MODEL_PORT}")
    stub = embedding_pb2_grpc.EmbedServiceStub(channel)

    responses = stub.GetEmbeddingAspects(single_element_generator(request))

    metadata = dict(responses.initial_metadata())

    model_id = metadata['model'].replace("/", "_") + "_" + metadata["revision"]

    response = next(responses)

    result = {"model_id": model_id, "embedding": list(response.embedding.values)}
    for i, aspect in enumerate(metadata['aspects'].split(";")):
        result[aspect] = list(response.aspect_embeddings[i].values)

    return result

@app.post("/embedding", )
async def embedding_aspects(input: TextInput, token: str = Depends(oauth2_scheme)):

    def single_element_generator(element):
        yield element

    request = embedding_pb2.EmbedRequest(text=input.text)

    channel = grpc.insecure_channel(f"{MODEL_HOST}:{MODEL_PORT}")
    stub = embedding_pb2_grpc.EmbedServiceStub(channel)

    responses = stub.GetEmbedding(single_element_generator(request))

    metadata = dict(responses.initial_metadata())

    model_id = metadata['model'].replace("/", "_") + "_" + metadata["revision"]

    response = next(responses)

    result = {"model_id": model_id, "embedding": list(response.embedding.values)}

    return result

class UserOut(BaseModel):
    id: int
    email: str

class UserCreate(BaseModel):
    email: str
    password: str

def generate_token():
    pass

@app.post("/signup", response_model=UserOut)
def signup(user: UserCreate, db: sqlite3.Connection = Depends(get_db)):
    db.row_factory = sqlite3.Row
    cursor = db.cursor()

    # Check if user already exists
    cursor.execute("SELECT * FROM users WHERE email = ?", (user.email,))
    existing_user = cursor.fetchone()
    if existing_user:
        db.close()
        raise HTTPException(status_code=400, detail="Email already registered")

    # Insert new user
    hashed_pw = pwd_context.hash(user.password)
    cursor.execute(
        "INSERT INTO users (email, password) VALUES (?, ?)",
        (user.email, hashed_pw)
    )
    db.commit()

    # Fetch the new user (with ID)
    new_user_id = cursor.lastrowid
    cursor.execute("SELECT id, email FROM users WHERE id = ?", (new_user_id,))
    new_user = cursor.fetchone()
    db.close()

    return {"id": new_user["id"], "email": new_user["email"]}

@app.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: sqlite3.Connection = Depends(get_db)):
    db.row_factory = sqlite3.Row
    cursor = db.cursor()

    print("Form data: ", form_data)

    # Find user by email
    cursor.execute("SELECT * FROM users WHERE email = ?", (form_data.username,))
    user = cursor.fetchone()

    # Validate credentials
    if not user or not pwd_context.verify(form_data.password, user["password"]):
        db.close()
        raise HTTPException(status_code=400, detail="Invalid credentials")

    # Create JWT token
    expire = datetime.now(tz=timezone.utc) + timedelta(minutes=15)
    token = jwt.encode({'user': user['email'], 'exp': expire}, 'secret', algorithm='HS256')
    db.close()
    return {"access_token": token, "token_type": "bearer", "name": user['email']}

@app.get("/items")
async def read_items(token: Annotated[str, Depends(oauth2_scheme)]):
    return {"token": token}


