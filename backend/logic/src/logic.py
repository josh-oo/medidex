from fastapi import APIRouter
from fastapi import Query, Path, UploadFile, File, HTTPException, Depends, BackgroundTasks
from fastapi.responses import Response
from pydantic import BaseModel
from dotenv import load_dotenv
from qdrant_client import QdrantClient, models
from qdrant_client.models import Filter, FieldCondition, DatetimeRange
from typing import List, Optional
import httpx
import os

from datetime import datetime

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

import asyncio

import sqlite3
import hashlib
import json
import pickle

import enum

from .auth import is_verified, verify_api_key

from .resources import get_study_id_by_trial_id_internal, get_studies_internal, get_study_persons_internal, get_author_frequencies
from .resources import get_study_interventions_internal , get_study_conditions_internal, get_study_outcomes_internal, get_study_participants_internal, get_study_design_internal
from .resources import get_all_interventions_internal, get_all_conditions_internal, get_all_outcomes_internal, get_study_reports_by_ids_internal

class TagCategories(str, enum.Enum):
    interventions = 'interventions'
    conditions = 'conditions'
    outcomes = 'outcomes'
    participants = 'participants'

router = APIRouter(tags=["logic"])

cutoff_query = Query(None, description="Cutoff date: for example '2025-01-13 00:00:00' (do not retrieve items entered after that date). Usually only used for testing")
report_index_path = Path(..., description="The target report's index within the batch (starting with 0)")
batch_hash_path = Path(..., description="The batch's hash/id")

k_query = Query(10, description="Maximum number of returned results.")

@router.on_event("startup")
async def startup_event():
    await startup_event()

load_dotenv()

MODEL_HOST = os.getenv("EMBEDDING_HOST")
MODEL_PORT = os.getenv("EMBEDDING_PORT")
DATABASE_VOLUME = os.getenv("DATABASE_VOLUME")
VECTORSTORE_HOST = os.getenv("VECTORSTORE_HOST")
VECTORSTORE_PORT = os.getenv("VECTORSTORE_PORT")

DEBUG = os.getenv("DEBUG", "FALSE") == "TRUE"

write_queue = asyncio.Queue()

@lru_cache()
def get_grpc_channel():
    return grpc.insecure_channel(f"{MODEL_HOST}:{MODEL_PORT}")

def get_vectorstore():
    client = QdrantClient(host=VECTORSTORE_HOST, grpc_port=VECTORSTORE_PORT, prefer_grpc=True)
    yield client

def get_db():
    conn = sqlite3.connect(os.path.join(DATABASE_VOLUME,"persistent", "users.db"), check_same_thread=False)
    try:
        yield conn
    finally:
        conn.close()

class Batch(BaseModel):
    batch_hash: str
    batch_description: str
    number_reports: int
    created_at: datetime
    embedded: int
    assigned: int

class BatchedReport(BaseModel):
    title: str
    abstract: Optional[str]
    authors: List[str]
    trial_id: Optional[str]
    vectors: dict
    assigned_studies: List[int]

class Tag(BaseModel):
    id: str
    keyword: str
    relevance: str

class RawReport(BaseModel):
    title: str
    abstract: Optional[str]
    authors: Optional[List[str]]

async def startup_event():
    # Start background worker
    asyncio.create_task(write_worker())

async def write_worker():
    """Background task that processes queued writes one at a time"""
    while True:
        query, params, future = await write_queue.get()
        try:
            conn = sqlite3.connect(os.path.join(DATABASE_VOLUME, "persistent", "users.db"))#, check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute(query, params)
            new_rows = cursor.rowcount
            conn.commit()
            conn.close()
            future.set_result(new_rows)
        except Exception as e:
            future.set_exception(e)
        finally:
            write_queue.task_done()

async def process_report(report, batch_hash, index):
    title = report['title']
    abstract = report['abstract']
    authors = report['authors']
    raw_report = RawReport(title=title, abstract=abstract, authors=authors)
    trial_registration_id = await extract_trial_id(raw_report)

    text_to_process = []
    if title:
        text_to_process.append(title)
    if abstract:
        text_to_process.append(abstract)
    text_to_process = "\n".join(text_to_process)
   
    vectors =_embed_report(text_to_process, get_grpc_channel())
    vectors_blob = pickle.dumps(vectors)

    future = asyncio.get_event_loop().create_future()
    query = "INSERT INTO tmp_reports (batch_hash, batch_inner_id, title, abstract, authors, trial_id, vectors) VALUES (?,?,?,?,?, ?, ?)"
    params = (batch_hash,index, title, abstract, json.dumps(authors), trial_registration_id, vectors_blob)
    await write_queue.put((query, params, future))
    await future

async def parse_file(file: UploadFile):
    entries = None
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

    return entries

@router.post("/batches", dependencies=[Depends(is_verified)], summary="Upload a batch of new reports that need to be assigned to studies (usually in the .ris file format)", description="Uploading a new batch triggers the embedding process. Batches are mainly used to do these compute heavy calculations in the background and only once. All needed data and the calculated embedding vectors are stored temporarily.", status_code=201) 
async def upload_file(background_tasks: BackgroundTasks, file: UploadFile = File(..., description="The .ris file containing all the articles you want to process.")):

    entries = await parse_file(file)

    results = []
    fingerprint_string = ""
    for entry in entries:
        title = entry.get('primary_title', None)
        if not title:
            title = entry.get('title', None)

        authors = entry.get('authors',None)
        abstract = entry.get('abstract', None)

        fingerprint_string += title if title else "" + abstract if abstract else "" + authors if authors else ""

        results.append({'title':title, 'abstract':abstract, 'authors': authors})#, 'trial_registration_id':trial_registration_id})

    batch_hash = hashlib.sha256(fingerprint_string.encode()).hexdigest()

    future = asyncio.get_event_loop().create_future()
    query = """
    INSERT OR IGNORE INTO tmp_report_batches (batch_hash, batch_description, number_reports)
    VALUES (?, ?, ?)
    """
    params = (batch_hash, file.filename, len(results))
    await write_queue.put((query, params, future))
    result = await future

    was_inserted = result == 1
    if not was_inserted:
        raise HTTPException(status_code=400, detail="Data already exists")

    for i, result in enumerate(results):
        background_tasks.add_task(process_report, result, batch_hash, i)

    return Response(status_code=201)
    
@router.get("/batches", dependencies=[Depends(is_verified)], summary="Get an overview of current report batches.", description="For each batch the current progress of embedding calculation and the number of already assigned reports is returned")
async def get_available_batches(db = Depends(get_db)) -> List[Batch]:
    query = """
    SELECT b.*, r.embedded, r.assigned
    FROM tmp_report_batches AS b
    LEFT JOIN (
        SELECT 
            batch_hash,
            COUNT(*) AS embedded,
            COUNT(assigned_studies) AS assigned
        FROM tmp_reports
        GROUP BY batch_hash
    ) AS r
    ON b.batch_hash = r.batch_hash;
    """
    cursor = db.execute(query)
    rows = cursor.fetchall()

    column_names = [description[0] for description in cursor.description]
    all_batches = [dict(zip(column_names, row)) for row in rows]

    return all_batches

@router.delete("/batches/{batch_hash}", dependencies=[Depends(is_verified)], summary="Delete a report batch and all its associated reports (including calculated embedding vectors) from the temporary storage.", status_code=204)
async def delete_batch(batch_hash: str = batch_hash_path):
    future = asyncio.get_event_loop().create_future()
    query = """
    DELETE FROM tmp_report_batches WHERE batch_hash = ?;
    """
    params = (batch_hash,)
    await write_queue.put((query, params, future))
    await future

    future = asyncio.get_event_loop().create_future()
    query = """
    DELETE FROM tmp_reports WHERE batch_hash = ?;
    """
    params = (batch_hash,)
    await write_queue.put((query, params, future))
    await future

    return Response(status_code=204)

@router.get("/batches/{batch_hash}/{report_index}", dependencies=[Depends(is_verified)], summary="Get the data and embedding vectors for a specific report in a batch.", description="Retrieve the title, abstract, authors, trial ID, embedding vectors, and assigned studies for a specific report identified by its batch hash and index (starting with 0) within the batch.")
async def get_batched_report(batch_hash: str = batch_hash_path, report_index : int = report_index_path, db = Depends(get_db)) -> BatchedReport:
    query = """
    SELECT title, abstract, authors, trial_id, vectors, assigned_studies
    FROM tmp_reports
    WHERE batch_hash = ?
    AND batch_inner_id = ?
    LIMIT 1;
    """
    cursor = db.execute(query, (batch_hash, report_index))
    rows = cursor.fetchone()

    item = {}
    item['title'] = rows[0]
    item['abstract'] = rows[1]
    item['authors'] = json.loads(rows[2]) if rows[2] else []
    item['trial_id'] = rows[3]
    item['vectors'] = pickle.loads(rows[4])
    item['assigned_studies'] = json.loads(rows[5]) if rows[5] else []
    return item

@router.put("/batches/{batch_hash}/{report_index}/studies", dependencies=[Depends(is_verified)], summary="Assign studies to a specific report in a batch.", status_code=204)
async def assign_studies(batch_hash: str = batch_hash_path, report_index: int = report_index_path, study_ids: List[int] = Query(..., description="The study ids (CRGReportIDs) you want to assign to the specified report.")):
    future = asyncio.get_event_loop().create_future()
    query = """
    UPDATE tmp_reports
    SET assigned_studies = ?
    WHERE batch_hash = ?
    AND batch_inner_id = ?;
    """
    params = (json.dumps(study_ids), batch_hash, report_index)
    await write_queue.put((query, params, future))
    await future
    return Response(status_code=204)

@router.delete("/batches/{batch_hash}/{report_index}/studies", dependencies=[Depends(is_verified)], summary="Remove assigned studies from a specific report in a batch.", status_code=204)
async def delete_assigned_studies(batch_hash: str = batch_hash_path, report_index: int = report_index_path):
    future = asyncio.get_event_loop().create_future()
    query = """
    UPDATE tmp_reports
    SET assigned_studies = ?
    WHERE batch_hash = ?
    AND batch_inner_id = ?;
    """
    params = (None, batch_hash, report_index)
    await write_queue.put((query, params, future))
    await future
    return Response(status_code=204)

@router.get("/batches/{batch_hash}/{report_index}/similar_tags", dependencies=[Depends(is_verified)], summary="Get related tags (interventions, outcomes, ...) for a specific report in a batch based on its embedding vectors.")
async def similar_tags(batch_hash: str = batch_hash_path, report_index: int = report_index_path, sources: List[str] = Query(..., description="Which source of tags do you want to search ('mesh', 'meerkat' or both)"), aspect: TagCategories = Query(None, description="The tag category which you are interested in"), k : int = k_query, client=Depends(get_vectorstore), db = Depends(get_db)) -> List[Tag]:
    query = """
    SELECT vectors
    FROM tmp_reports
    WHERE batch_hash = ?
    AND batch_inner_id = ?
    LIMIT 1;
    """
    cursor = db.execute(query, (batch_hash, report_index))
    rows = cursor.fetchone()

    if not rows:
        raise HTTPException(status_code=404, detail="Report not found")

    vectors = pickle.loads(rows[0])

    collection_name = vectors['model_id'] + "_tags"

    vector_names = {'interventions': 'intervention', 'conditions': 'condition', 'outcomes': 'outcome'}

    embedding = vectors[vector_names[aspect]]

    data = await get_similar_tags(embedding, collection_name, sources, aspect, k, client)

    result = [
        {"id": i, "keyword": k, "relevance": r}
        for i, k, r in zip(data["ID"], data["Keyword"], data["Relevance"])
    ]
    return result

@router.get("/batches/{batch_hash}/{report_index}/similar_studies", dependencies=[Depends(is_verified)], summary="Get related studies for a specific report in a batch based on its embedding vectors.", description="Retrieve studies that are similar to a specific report identified by its batch hash and index (starting with 0) within the batch. Similarity is determined based on the embedding vectors of the report. The similarity search is done at runtime. You can optionally search for similarity based on a specific aspect (e.g., interventions, outcomes) or apply a cutoff date to only consider studies entered before a certain date.")
async def similar_studies(batch_hash: str = batch_hash_path, report_index: int = report_index_path, aspect: TagCategories = Query(None, description="This value is rarely needed. Just if you want to search studies based on a certain aspect."), cutoff: str = cutoff_query, k : int = k_query, client=Depends(get_vectorstore), db = Depends(get_db), return_details=False):
    if not aspect:
        aspect = "default"
    
    query = """
    SELECT  authors, trial_id, vectors
    FROM tmp_reports
    WHERE batch_hash = ?
    AND batch_inner_id = ?
    LIMIT 1;
    """
    cursor = db.execute(query, (batch_hash, report_index))
    rows = cursor.fetchone()

    if not rows:
        raise HTTPException(status_code=404, detail="Report not found")

    authors = rows[0]
    trial_id = rows[1]
    vectors = pickle.loads(rows[2])

    embedding_name = aspect
    if embedding_name == "default":
        embedding_name = "embedding"

    return await get_similar_studies(vectors[embedding_name], vectors['model_id'], aspect, trial_id, authors, cutoff, k, client, return_details)

async def get_similar_tags(embedding, collection_name, sources: List[str], aspect: str, k: int, client=Depends(get_vectorstore)):
    
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
                    match=models.MatchAny(any=[aspect]), #TODO check if it as the same as aspect name
                )
            ]
        ))

    filter = models.Filter(should=filters)

    search_results = client.query_points(
        collection_name=collection_name,
        query=embedding,
        limit=k,
        query_filter=filter,
    )

    results = {'ID': [], 'Keyword':[], 'Relevance': []}

    for result in search_results.points:
        results['ID'].append(result.payload['source_id'])
        results['Keyword'].append(result.payload['display_name'])
        results['Relevance'].append(str(round(result.score * 100)) + "%")

    return results

async def get_similar_studies(embedding, collection_name, aspect: str, trial_id: str, authors: List[str], cutoff: str, k: int, client: QdrantClient, return_details: bool):
    found_study_ids = {}
    debug_map = {}

    return_details= return_details or DEBUG
    
    filters = []
    if cutoff:
        filters.append(Filter(
            must=[
                FieldCondition(key="date_entered",range=DatetimeRange(lt=datetime.fromisoformat(cutoff)))
            ]
        ))        
    
    if trial_id:
        
        response = get_study_id_by_trial_id_internal(trial_id, cutoff)
        if response:
            for result in response:
                found_study_ids[result] = 1.0
                debug_map[result] = [{"source_id":trial_id}]

        filters.append(
                models.Filter(
                    must=[
                        models.FieldCondition(
                            key="belongs_to_trial_id",
                            match=models.MatchValue(value=False)
                        )
                    ],
                    must_not=[
                        models.FieldCondition(
                            key="belongs_to_study",
                            match=models.MatchAny(any=list(found_study_ids.keys()))
                        )
                    ]
                )
            )
    
    filter = models.Filter(must=filters)

    k = k - len(found_study_ids.keys())

    if k > 0:
        search_results = client.query_points_groups(
            collection_name=collection_name,
            query=embedding,
            using=aspect,
            group_by="belongs_to_study",  # Path of the field to group by
            limit=k,  # Max amount of groups
            group_size=1,  # Max amount of points per group
            query_filter=filter,
            with_payload=True,
            #with_vectors=True,
        )

        reranked_results = search_results.groups

        for result in reranked_results:
            for hit in result.hits:
                for item in hit.payload['belongs_to_study']:
                    if item not in found_study_ids:
                        found_study_ids[item] = hit.score
                    debug_map[item] = debug_map.get(item, []) + [hit.payload]

    all_studies = get_studies_internal(list(found_study_ids.keys()))
    #list of dicts to dict of lists:

    #Remove this block for evaluation without authors
    scores_authors = await get_scores_authors(report_authors=authors, study_ids=list(found_study_ids.keys()), cutoff=cutoff)
    for study_id, score in scores_authors.items():
        if found_study_ids[study_id] < 1.0:
            found_study_ids[study_id] = min(0.99, found_study_ids[study_id] + score)

    #result['Relevance'] = list(found_study_ids.values())
    for i in range(0, len(all_studies)):
        item = all_studies[i].dict()
        item['Relevance'] = found_study_ids[item['CRGStudyID']]
        all_studies[i] = item

    result = {}
    for study in all_studies:
        for key, value in study.items(): 
            result.setdefault(key, []).append(value)

    order = ['CRGStudyID', 'Relevance', 'ShortName', 'NumberParticipants', 'Duration', 'Comparison', 'Countries', 'DateEntered', 'DateEdited', 'StatusofStudy']
    reordered = {key: result[key] for key in order}

    if return_details:
        reordered['details'] = [list({d['source_id']: d for d in debug_map[key]}.values()) for key in reordered['CRGStudyID']]

    sorted_indices = sorted(range(len(reordered['Relevance'])), key=lambda i: reordered['Relevance'][i], reverse=True)
    for k in reordered:
        reordered[k] = [reordered[k][i] for i in sorted_indices]

    return reordered

async def get_scores_authors(report_authors: List[str], study_ids: List[int], cutoff: str):

    study_persons = get_study_persons_internal(study_ids, cutoff)
    current_persons = get_author_frequencies(report_authors)

    report_authors = set(current_persons.keys())

    result = {}
    num_report_authors = len(report_authors)
    if num_report_authors == 0:
        print(report_authors)
        return {}
    for study_id, study_authors in study_persons.items():
        total_score = 0
        num_total_authors = len(study_authors) + num_report_authors
        intersection = set(study_authors) & report_authors
        for matching_author in intersection:
            total_score += 1 / current_persons[matching_author]
        total_score = total_score / num_total_authors if num_total_authors > 0 else 0
        result[int(study_id)] = total_score

    return result

@router.get("/{tag_category}/{tag_value}/related_studies", dependencies=[Depends(is_verified)], summary="Get studies related to a specific tag (intervention, outcome, ...) currently only vector-similarity search is available.", description="Retrieve studies that are related to a specific tag value (e.g., 'Placebo' for interventions) using vector similarity search based on the embedding of the tag value. The similarity search is done at runtime.")
async def get_aspect_related_studies(tag_category: TagCategories = Path(..., description="The tags category (e.g. 'interventions', 'conditions', ...)"), tag_value: str = Path(..., description="The specific tags value (e.g. 'Placebo' for interventions)"), k : int = k_query, client=Depends(get_vectorstore), channel = Depends(get_grpc_channel)):
    embeddings = _embed_aspect(tag_value, channel)

    collection_name = embeddings['model_id']

    return await get_similar_studies(embeddings['embedding'], collection_name, tag_category, None, [], None, k, client, return_details=False)


def single_element_generator(element):
    yield element

def embed_report(text, channel = Depends(get_grpc_channel)):
    return _embed_report(text, channel)

def _embed_report(text : str, channel):
    token = secrets.token_urlsafe(8)

    request = embedding_pb2.EmbedReportRequest(id=token, text=text, authors=[])

    stub = embedding_pb2_grpc.EmbedServiceStub(channel)

    responses = stub.GetReportEmbedding(single_element_generator(request))

    metadata = dict(responses.initial_metadata())

    model_id = metadata['model'].replace("/", "_") + "_" + metadata["revision"]

    response = next(responses)

    result = {"model_id": model_id, "embedding": list(response.embedding.values), "author_embedding": list(response.embedding.values)}
    for i, aspect in enumerate(metadata['aspects'].split(";")):
        result[aspect] = list(response.aspect_embeddings[i].values)

    return result

def embed_aspect(text : str, channel = Depends(get_grpc_channel)):
    return _embed_aspect(text, channel)

def _embed_aspect(text : str, channel):
    token = secrets.token_urlsafe(8)

    request = embedding_pb2.EmbedAspectsRequest(id=token, aspects=[text])

    stub = embedding_pb2_grpc.EmbedServiceStub(channel)

    responses = stub.GetAspectEmbeddings(single_element_generator(request))

    metadata = dict(responses.initial_metadata())

    model_id = metadata['model'].replace("/", "_") + "_" + metadata["revision"]

    response = next(responses)

    result = {"model_id": model_id, "embedding": list(response.embedding[0].values)}

    return result










"""
Only used for internal API key protected embedding analysis
"""

class RetrievalInputText(BaseModel):
    title: str
    abstract: Optional[str]
    authors: Optional[List[str]]
    topK: int

class RetrievalInputEmbedding(BaseModel):
    basic_input: RetrievalInputText
    embeddings: dict
    model_id: str
    
@router.post("/processing/analyze_embedding", dependencies=[Depends(verify_api_key)], include_in_schema=False)
async def analyze_embedding(input: RetrievalInputEmbedding, cutoff: str = Query(None), trial_id: str = Query(None), vectorstore=Depends(get_vectorstore)):
    result = await analyze(vectorstore, input.embeddings, input.model_id, input.basic_input.topK, input.basic_input.title, input.basic_input.abstract, input.basic_input.authors, cutoff)
    return result

async def analyze(vectorstore, embeddings, model_id, top_k, title, abstract, authors, cutoff):
    
    trial_id = await extract_trial_id(RawReport(title=title,abstract=abstract, authors=[]))
    pre_result = await get_similar_studies(embeddings['embedding'], model_id, "default", trial_id, authors, cutoff, top_k, client, return_details=True)

    found_study_ids = {}
    for key, score, details in zip(pre_result['CRGStudyID'], pre_result['Relevance'], pre_result['details']):
        found_study_ids[key] = {'score': score, 'report_hit': details[0]['source_id']}

    result = {}
    result['related_studies'] = []

    all_related_interventions = []
    all_related_conditions = []
    all_related_outcomes = []

    scores = [item['score'] for item in found_study_ids.values()]
    report_hits = [item['report_hit'] for item in found_study_ids.values()]

    related_studies = get_studies_internal(list(found_study_ids.keys()))#responses[0].json()
    study_interventions = get_study_interventions_internal(list(found_study_ids.keys()))#responses[1].json()
    study_conditions = get_study_conditions_internal(list(found_study_ids.keys()))#responses[2].json()
    study_outcomes = get_study_outcomes_internal(list(found_study_ids.keys()))# responses[3].json()
    study_participants_desc = get_study_participants_internal(list(found_study_ids.keys()))#responses[4].json()
    study_design = get_study_design_internal(list(found_study_ids.keys()))#responses[5].json()
    study_reports = get_study_reports_by_ids_internal(list(found_study_ids.keys()), ['CRGReportID', 'Title', 'Abstract', 'Authors'], cutoff)#responses[6].json()

    for id, name, num_participants, countries, durations,report_hit, score in zip(related_studies['CRGStudyID'], related_studies['ShortName'], related_studies['NumberParticipants'], related_studies['Countries'], related_studies['Duration'], report_hits, scores):            
        study_item = {}
        study_item['study_id'] =  id
        study_item['study_name'] = name
        study_item['score'] = score
        study_item['report_hit'] = report_hit

        study_item['attributes'] = {}
        study_item['attributes']['countries'] = [country.strip() for country in countries.split("//")] if countries else None
        study_item['attributes']['duration'] = [duration.strip() for duration in durations.split("//")] if durations else None
        study_item['attributes']['participants_num'] = [p_num.strip() for p_num in num_participants.split("//")] if num_participants else None

        study_item['assigned_reports'] = {}

        study_item['attributes']['participants_desc'] = study_participants_desc.get(str(id), [])
        study_item['attributes']['study_design'] = study_design.get(str(id), [])

        related_interventions = study_interventions.get(str(id), [])
        study_item['assigned_interventions'] = [item['Description'] for item in related_interventions]
        all_related_interventions.extend([item['ID'] for item in related_interventions])

        related_conditions = study_conditions.get(str(id), [])
        study_item['assigned_conditions'] = [item['Description'] for item in related_conditions]
        all_related_conditions.extend([item['ID'] for item in related_conditions])

        related_outcomes = study_outcomes.get(str(id), [])
        study_item['assigned_outcomes'] = [item['Description'] for item in related_outcomes]
        all_related_outcomes.extend([item['ID'] for item in related_outcomes])
    
        related_reports = study_reports.get(str(id), [])#responses[2].json()
        for related_report_item in related_reports:
            report_item = {}
            report_item['title'] = related_report_item['Title']
            report_item['abstract'] =related_report_item['Abstract']
            report_item['authors'] = [author.strip() for author in related_report_item['Authors'].split("//")]
            study_item['assigned_reports'][related_report_item['CRGReportID']] = report_item
    
        result['related_studies'].append(study_item)

    async def search_related_tags(allowed_ids, type_embedding, type_vectorstore):

        if len(allowed_ids) == 0:
            return []

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
            item['id'] = point.payload['source_id']
            item['score'] = point.score
            related_tags.append(item)

        all_ids = [item['id'] for item in related_tags]
            
        if type_vectorstore == "interventions":
            result = get_all_interventions_internal(all_ids)
        elif type_vectorstore == "conditions":
            result = get_all_conditions_internal(all_ids)
        elif type_vectorstore == "outcomes":
            result = get_all_outcomes_internal(all_ids)
  
        for item in related_tags:
            item['name'] = result[item['id']][0].strip()
        
        return related_tags

    result['related_interventions'] = await search_related_tags(all_related_interventions, "intervention", "interventions")
    result['related_conditions'] = await search_related_tags(all_related_conditions, "condition", "conditions")
    result['related_outcomes'] = await search_related_tags(all_related_outcomes, "outcome", "outcomes")

    return result


@router.post("/processing/extract_trial_id", dependencies=[Depends(is_verified)], include_in_schema=False)
async def extract_trial_id(raw_report: RawReport):
    ids = extract_trial_registration_ids(raw_report.title)
    if len(ids) == 1:
        return ids[0]

    if raw_report.authors:
        for author in raw_report.authors:
            ids = extract_trial_registration_ids(author)
            if len(ids) == 1:
                return ids[0]
    if raw_report.abstract:
        ids = extract_trial_registration_ids(raw_report.abstract)
        if len(ids) == 1:
            return ids[0]
    
    return None

#TODO deprecated endpoints, remove later

class ReportEmbedding(BaseModel):
    model_id: str
    main_embedding: List[float]
    author_embedding: Optional[List[float]]

class AspectEmbedding(BaseModel):
    model_id: str
    embedding: List[float]

@router.post("/similarity_search/studies", dependencies=[Depends(is_verified)], summary="DEPRECATED: Use /batches/{batch_hash}/{report_index}/similar_studies instead", deprecated=True)
async def similarity_search_studies(embedding: ReportEmbedding, aspect: str = Query("default"), trial_id: str = Query(None), authors: List[str] = Query(None),  cutoff: str = Query(None), k : int = Query(10), client=Depends(get_vectorstore), return_details=False):
    
    return await get_similar_studies(embedding.main_embedding, embedding.model_id, aspect, trial_id, authors, cutoff, k, client, return_details)

@router.post("/similarity_search/tags", dependencies=[Depends(is_verified)], summary="DEPRECATED: Use /batches/{batch_hash}/{report_index}/similar_tags instead", deprecated=True)
async def similarity_search_tags(embedding: AspectEmbedding, sources: List[str] = Query(...), type: str = Query(...), k : int = Query(10), client=Depends(get_vectorstore)):
    
    return await get_similar_tags(embedding.embedding, embedding.model_id + "_tags", sources, type, k, client)