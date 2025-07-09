from fastapi import Query, UploadFile, File, HTTPException, Depends
from pydantic import BaseModel
from dotenv import load_dotenv
from qdrant_client import QdrantClient, models
from qdrant_client.models import Filter, FieldCondition, DatetimeRange
from typing import List, Optional
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

from datetime import datetime

from .utils.trial_registration_id import extract_trial_registration_ids

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

class RetrievalInputText(BaseModel):
    text: str
    topK: int

class RetrievalInputEmbedding(BaseModel):
    embeddings: dict
    model_id: str
    topK: int

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
            text_stream = io.StringIO(content.decode('utf-8-sig'))  # RIS is plain text
            entries = rispy.load(text_stream)  # returns a list of dicts
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to parse .ris: {str(e)}")
        
    elif file.filename.endswith(".cgi"):
        try:
            content = await file.read()
            text_stream = io.StringIO(add_end_tag(content.decode('utf-8-sig')))  # RIS is plain text
            entries = rispy.load(text_stream, implementation=CgiParser, skip_unknown_tags=True)  # returns a list of dicts
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to parse .cgi: {str(e)}")
        
    elif file.filename.endswith(".nbib"):
        try:
            content = await file.read()
            decoded = content.decode("utf-8-sig")
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

        authors = entry.get('authors',None)
        abstract = entry.get('abstract', None)
        trial_registration_id = None

        ids = extract_trial_registration_ids(title)
        if len(ids) == 1:
            trial_registration_id = ids[0]

        if authors and not trial_registration_id:
            for author in authors:
                ids = extract_trial_registration_ids(author)
                if len(ids) == 1:
                    trial_registration_id = ids[0]
        if abstract and not trial_registration_id:
            ids = extract_trial_registration_ids(abstract)
            if len(ids) == 1:
                trial_registration_id = ids[0]

        #TODO study acronym
        results.append({'title':title, 'abstract':abstract, 'authors': authors, 'trial_registration_id':trial_registration_id})

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

async def similarity_search_studies(embedding: EmbeddingInput, aspect: str = Query("default"), trial_id: str = Query(None),  cutoff: str = Query(None), client=Depends(get_db)):
    date_filter = Filter()
    if cutoff:
        date_filter = Filter(
            must=[
                FieldCondition(key="date_entered",range=DatetimeRange(lt=datetime.fromisoformat(cutoff)))
            ]
        )

    search_results = client.query_points_groups(
        collection_name=embedding.model_id,
        # Same as in the regular query_points() API
        query=embedding.embedding,
        using=aspect,
        # Grouping parameters
        group_by="belongs_to_study",  # Path of the field to group by
        limit=10,  # Max amount of groups
        group_size=1,  # Max amount of points per group
        query_filter=date_filter,
    )

    found_study_ids = {}
    if trial_id:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"http://{DATABASE_HOST}:{DATABASE_PORT}/study_id", params={"trial_id": trial_id, "cutoff":cutoff})
            response = response.json()
            if response:
                for result in response:
                    found_study_ids[result] = "100% (Trial ID)"

    for result in search_results.groups:
        for hit in result.hits:
            for item in hit.payload['belongs_to_study']:
                if item not in found_study_ids:
                    found_study_ids[item] = str(round(hit.score * 100)) + "%"

    async with httpx.AsyncClient() as client:
        response = await client.post(f"http://{DATABASE_HOST}:{DATABASE_PORT}/studies", json={'ids': list(found_study_ids.keys())})

    result = response.json()
    result['Relevance'] = list(found_study_ids.values())

    #move relevance to the front
    #order = ['CRGStudyID', 'Relevance', 'Short_name', 'Participants', 'Duration', 'Comparison', 'Countries', 'Date_entered', 'Date_edited', 'Status_of_study']
    order = ['CRGStudyID', 'Relevance', 'ShortName', 'NumberParticipants', 'Duration', 'Comparison', 'Countries', 'DateEntered', 'DateEdited', 'StatusofStudy']
    reordered = {key: result[key] for key in order}

    return reordered

def single_element_generator(element):
    yield element

def embed_report(input: TextInput, channel = Depends(get_grpc_channel)):
    return _embed_report(input, channel)

def _embed_report(input: TextInput, channel):
    token = secrets.token_urlsafe(8)

    request = embedding_pb2.EmbedReportRequest(id=token, text=input.text, authors=[])

    stub = embedding_pb2_grpc.EmbedServiceStub(channel)

    responses = stub.GetReportEmbedding(single_element_generator(request))

    metadata = dict(responses.initial_metadata())

    model_id = metadata['model'].replace("/", "_") + "_" + metadata["revision"]

    response = next(responses)

    result = {"model_id": model_id, "embedding": list(response.embedding.values)}
    for i, aspect in enumerate(metadata['aspects'].split(";")):
        result[aspect] = list(response.aspect_embeddings[i].values)

    return result

def embed_aspect(input: TextInput, channel = Depends(get_grpc_channel)):
    return _embed_aspect(input, channel)

def _embed_aspect(input: TextInput, channel):
    token = secrets.token_urlsafe(8)

    request = embedding_pb2.EmbedRequestAspect(id=token, aspects=[input.text])

    stub = embedding_pb2_grpc.EmbedServiceStub(channel)

    responses = stub.GetAspectEmbeddings(single_element_generator(request))

    metadata = dict(responses.initial_metadata())

    model_id = metadata['model'].replace("/", "_") + "_" + metadata["revision"]

    response = next(responses)

    result = {"model_id": model_id, "embedding": list(response.embedding[0].values)}

    return result

def get_all_reports_by_study(study_id: int):
    url = f"http://{DATABASE_HOST}:{DATABASE_PORT}/study/{study_id}/reports"
    with httpx.Client() as client:
        response = client.get(url)
        response.raise_for_status()  # Optional: raises on 4xx/5xx
        return response.json()
    
async def analyze_embedding(input: RetrievalInputEmbedding, cutoff: str = Query(None), vectorstore=Depends(get_db)):
    result = await analyze(vectorstore, input.embeddings, input.model_id, input.topK, cutoff)
    return result

async def analyze_text(input: RetrievalInputText, cutoff: str = Query(None), vectorstore=Depends(get_db), channel=Depends(get_grpc_channel)):    
    text_input = TextInput(text=input.text)
    embedding_results = _embedding_aspects(text_input, channel)

    result = await analyze(vectorstore, embedding_results, embedding_results['model_id'], input.topK, cutoff)
    return result

async def analyze(vectorstore, embeddings, model_id, top_k, cutoff):
    date_filter = Filter()
    if cutoff:
        date_filter = Filter(
            must=[
                FieldCondition(key="date_entered",range=DatetimeRange(lt=datetime.fromisoformat(cutoff)))
            ]
        )

    study_search_results = vectorstore.query_points_groups(
        collection_name=model_id,
        # Same as in the regular query_points() API
        query=embeddings['embedding'],
        using="default",
        # Grouping parameters
        group_by="belongs_to_study",  # Path of the field to group by
        limit=top_k,  # Max amount of groups
        group_size=1,  # Max amount of points per group
        query_filter=date_filter,
    )

    found_study_ids = {}
    #scores = []
    #report_hits = []
    for result in study_search_results.groups:
        for hit in result.hits:
            report_hit = hit.payload['source_id']
            for item in hit.payload['belongs_to_study']:
                found_study_ids[item] = {'score': hit.score, 'report_hit': report_hit}
                #scores.append(hit.score)
                #report_hits.append(report_hit)

    result = {}
    result['related_studies'] = []

    all_related_interventions = []
    all_related_conditions = []
    all_related_outcomes = []

    scores = [item['score'] for item in found_study_ids.values()]
    report_hits = [item['report_hit'] for item in found_study_ids.values()]

    async with httpx.AsyncClient() as client:
        related_studies = (await client.post(f"http://{DATABASE_HOST}:{DATABASE_PORT}/studies", json={'ids': list(found_study_ids.keys())})).json()
        #TODO error handling

        for id, name, report_hit, score in zip(related_studies['CRGStudyID'], related_studies['ShortName'], report_hits, scores):
            item = {}
            item['study_id'] =  id
            item['study_name'] = name
            item['score'] = score
            item['report_hit'] = report_hit

            item['assigned_reports'] = {}

            related_interventions = (await client.post(f"http://{DATABASE_HOST}:{DATABASE_PORT}/study/tags/interventions/", json={'ids': [id]})).json()
            item['assigned_interventions'] = [item['Description'] for item in related_interventions]
            all_related_interventions.extend([item['ID'] for item in related_interventions])

            related_conditions = (await client.post(f"http://{DATABASE_HOST}:{DATABASE_PORT}/study/tags/conditions/", json={'ids': [id]})).json()
            item['assigned_conditions'] = [item['Description'] for item in related_conditions]
            all_related_conditions.extend([item['ID'] for item in related_conditions])

            related_outcomes = (await client.post(f"http://{DATABASE_HOST}:{DATABASE_PORT}/study/tags/outcomes/", json={'ids': [id]})).json()
            item['assigned_outcomes'] = [item['Description'] for item in related_outcomes]
            all_related_outcomes.extend([item['ID'] for item in related_outcomes])
        
            related_reports = (await client.get(f"http://{DATABASE_HOST}:{DATABASE_PORT}/study/{id}/reports")).json()
            for report_id, report_title, report_abstract, report_authors in zip(related_reports['CRGReportID'], related_reports['Title'], related_reports['Abstract'], related_reports['Authors']):
                report_item = {}
                report_item['title'] = report_title
                report_item['abstract'] = report_abstract
                report_item['authors'] = [author.strip() for author in report_authors.split("//")]
                item['assigned_reports'][report_id] = report_item

        
            result['related_studies'].append(item)

    def search_related_tags(allowed_ids, type_embedding, type_vectorstore):

        tag_filter = models.Filter(
            must=[
                models.FieldCondition(key="source", match=models.MatchValue(value="meerkat")),
                models.FieldCondition(key="tree_ids",match=models.MatchAny(any=[type_vectorstore])),
                models.FieldCondition(key="source_id",match=models.MatchAny(any=[str(item) for item in allowed_ids]))
            ]
        )

        tag_results = vectorstore.query_points(
            collection_name=model_id + "_tags",
            query=embeddings[type_embedding],
            limit=len(allowed_ids),
            query_filter=tag_filter,
        )

        related_tags = []
        for point in tag_results.points:
            item = {}
            item['name'] = point.payload['display_name']
            item['id'] = point.payload['source_id']
            item['score'] = point.score
            related_tags.append(item)
        
        return related_tags

    result['related_interventions'] = search_related_tags(all_related_interventions, "intervention", "interventions")
    result['related_conditions'] = search_related_tags(all_related_conditions, "condition", "conditions")
    result['related_outcomes'] = search_related_tags(all_related_outcomes, "outcome", "outcomes")

    return result