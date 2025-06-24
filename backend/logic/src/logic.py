from fastapi import Query, UploadFile, File, HTTPException, Depends
from pydantic import BaseModel
from dotenv import load_dotenv
from qdrant_client import QdrantClient, models
from typing import List
import httpx
import os

import grpc
import embedding_pb2
import embedding_pb2_grpc

from functools import lru_cache

from rispy.parser import RisParser
import rispy
import nbib
import io

import secrets

load_dotenv()

MODEL_HOST = os.getenv("EMBEDDING_HOST")
MODEL_PORT = os.getenv("EMBEDDING_PORT")
DATABASE_HOST = os.getenv("DATABASE_HOST")
DATABASE_PORT = os.getenv("DATABASE_PORT")
VECTORSTORE_HOST = os.getenv("VECTORSTORE_HOST")
VECTORSTORE_PORT = os.getenv("VECTORSTORE_PORT")

@lru_cache()
def get_grpc_channel():
    return grpc.insecure_channel(f"{MODEL_HOST}:{MODEL_PORT}")

def get_db():
    client = QdrantClient(host=VECTORSTORE_HOST, grpc_port=VECTORSTORE_PORT, prefer_grpc=True)
    yield client

# Request schema
class TextInput(BaseModel):
    text: str

class EmbeddingInput(BaseModel):
    embedding: List[float]
    model_id: str

async def upload_file(file: UploadFile = File(...)):

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

async def similarity_search_tags(embedding: EmbeddingInput, sources: List[str] = Query(...), type: str = Query(...), client=Depends(get_db)):
    
    #TODO implement more sophisticated tree based search here

    filters = []
    if "mesh" in sources:
        filters.append(models.FieldCondition(key="source", match=models.MatchValue(value="mesh")))

    if "meerkat" in sources:
        filters.append(models.Filter(
            must=[
                models.FieldCondition(key="source", match=models.MatchValue(value="meerkat")),
                models.FieldCondition(
                    key="tree_ids",
                    match=models.MatchAny(any=[type]),
                )
            ]
        ))

    filter = models.Filter(should=filters)

    search_results = client.query_points(
        collection_name=embedding.model_id + "_tags",
        query=embedding.embedding,
        limit=10,
        query_filter=filter,
    )

    results = {'ID': [], 'Keyword':[], 'Relevance': []}

    for result in search_results.points:
        results['ID'].append(result.payload['source_id'])
        results['Keyword'].append(result.payload['display_name'])
        results['Relevance'].append(str(round(result.score * 100)) + "%")

    return results

async def similarity_search_studies(embedding: EmbeddingInput, aspect: str = Query("default"), client=Depends(get_db)):

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

async def embedding_aspects(input: TextInput, channel = Depends(get_grpc_channel)):

    def single_element_generator(element):
        yield element

    token = secrets.token_urlsafe(8)

    request = embedding_pb2.EmbedRequest(id=token, text=[input.text])

    stub = embedding_pb2_grpc.EmbedServiceStub(channel)

    responses = stub.GetEmbeddingAspects(single_element_generator(request))

    metadata = dict(responses.initial_metadata())

    model_id = metadata['model'].replace("/", "_") + "_" + metadata["revision"]

    response = next(responses)

    result = {"model_id": model_id, "embedding": list(response.embedding[0].values)}
    for i, aspect in enumerate(metadata['aspects'].split(";")):
        result[aspect] = list(response.aspect_embeddings[0].aspect_embeddings[i].values)

    return result

async def embedding(input: TextInput, channel = Depends(get_grpc_channel)):

    def single_element_generator(element):
        yield element

    token = secrets.token_urlsafe(8)

    request = embedding_pb2.EmbedRequest(id=token, text=input.text)

    stub = embedding_pb2_grpc.EmbedServiceStub(channel)

    responses = stub.GetEmbedding(single_element_generator(request))

    metadata = dict(responses.initial_metadata())

    model_id = metadata['model'].replace("/", "_") + "_" + metadata["revision"]

    response = next(responses)

    result = {"model_id": model_id, "embedding": list(response.embedding[0].values)}

    return result

async def analyze_text(input: TextInput):
    embedding_results = embedding_aspects(input)
    return embedding_results