from fastapi import FastAPI, Query
from pydantic import BaseModel
from dotenv import load_dotenv
from qdrant_client import QdrantClient, models
from typing import List
import httpx
import os

import grpc
import embedding_pb2
import embedding_pb2_grpc

load_dotenv()

MODEL_HOST = os.getenv("EMBEDDING_HOST")
MODEL_PORT = os.getenv("EMBEDDING_PORT")
DATABASE_HOST = os.getenv("DATABASE_HOST")
DATABASE_PORT = os.getenv("DATABASE_PORT")
VECTORSTORE_HOST = os.getenv("VECTORSTORE_HOST")
VECTORSTORE_PORT = os.getenv("VECTORSTORE_PORT")

# Initialize FastAPI
app = FastAPI()

# Request schema
class TextInput(BaseModel):
    text: str

class EmbeddingInput(BaseModel):
    embedding: List[float]
    model_id: str

@app.get("/readyz")
def check():
    return "Ready"

@app.post("/similarity_search/tags/{type}")
async def similarity_search_tags(type: str, embedding: EmbeddingInput):

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
async def similarity_search_studies(embedding: EmbeddingInput, aspect: str = Query("default")):

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
async def embedding_aspects(input: TextInput):

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

@app.post("/embedding")
async def embedding_aspects(input: TextInput):

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

    

