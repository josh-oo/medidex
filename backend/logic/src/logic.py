from fastapi import APIRouter
from fastapi import Query, UploadFile, File, HTTPException, Depends, BackgroundTasks
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

import numpy as np

from .auth import is_verified, verify_api_key

router = APIRouter(tags=["logic"])

@router.on_event("startup")
async def startup_event():
    await startup_event()

#from sklearn.feature_extraction.text import TfidfVectorizer
#from sklearn.metrics.pairwise import cosine_similarity
#import numpy as np

load_dotenv()

MODEL_HOST = os.getenv("EMBEDDING_HOST")
MODEL_PORT = os.getenv("EMBEDDING_PORT")
DATABASE_VOLUME = os.getenv("DATABASE_VOLUME")
DATABASE_HOST = os.getenv("DATABASE_HOST")
DATABASE_PORT = os.getenv("DATABASE_PORT")
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
    conn = sqlite3.connect(os.path.join(DATABASE_VOLUME, "users.db"), check_same_thread=False)
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

# Request schema
class TextInput(BaseModel):
    text: str

class RawReport(BaseModel):
    title: str
    abstract: Optional[str]
    authors: Optional[List[str]]

class AspectEmbedding(BaseModel):
    model_id: str
    embedding: List[float]

class ReportEmbedding(BaseModel):
    model_id: str
    main_embedding: List[float]
    author_embedding: Optional[List[float]]
    #participants_embedding: Optional[List[float]]
    #text: Optional[str]

class RetrievalInputText(BaseModel):
    title: str
    abstract: Optional[str]
    authors: Optional[List[str]]
    topK: int

class RetrievalInputEmbedding(BaseModel):
    basic_input: RetrievalInputText
    embeddings: dict
    model_id: str

async def startup_event():
    # Start background worker
    asyncio.create_task(write_worker())

async def write_worker():
    """Background task that processes queued writes one at a time"""
    while True:
        query, params, future = await write_queue.get()
        try:
            conn = sqlite3.connect(os.path.join(DATABASE_VOLUME, "users.db"))#, check_same_thread=False)
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
   
    vectors =_embed_report(TextInput(text=text_to_process), get_grpc_channel())
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
async def upload_file(background_tasks: BackgroundTasks, file: UploadFile = File(...)):

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
    
@router.get("/batches", dependencies=[Depends(is_verified)], summary="Get an overview of current report batches", description="For each batch the current progress of embedding calculation and the number of already assigned reports is returned")
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

@router.delete("/batches/{batch_hash}", dependencies=[Depends(is_verified)], summary="Delete a report batch and all its associated reports (including calculated embedding vectors) from the temporary storage", status_code=204)
async def delete_batch(batch_hash):
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

@router.get("/batches/{batch_hash}/{report_index}", dependencies=[Depends(is_verified)], summary="Get the data and embedding vectors for a specific report in a batch", description="Retrieve the title, abstract, authors, trial ID, embedding vectors, and assigned studies for a specific report identified by its batch hash and index (starting with 0) within the batch.")
async def get_batched_report(batch_hash: str, report_index : int, db = Depends(get_db)) -> BatchedReport:
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

@router.put("/batches/{batch_hash}/{report_index}/studies", dependencies=[Depends(is_verified)], summary="Assign studies to a specific report in a batch", status_code=204)
async def assign_studies(batch_hash: str, report_index: int, study_ids: List[int] = Query(...)):
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

@router.delete("/batches/{batch_hash}/{report_index}/studies", dependencies=[Depends(is_verified)], summary="Remove assigned studies from a specific report in a batch", status_code=204)
async def delete_assigned_studies(batch_hash: str, report_index: int):
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

@router.get("/batches/{batch_hash}/{report_index}/similar_tags", dependencies=[Depends(is_verified)], summary="Get related tags (interventions, outcomes, ...) for a specific report in a batch based on its embedding vectors")
async def similar_tags(batch_hash: str, report_index: int, sources: List[str] = Query(...), aspect: str = Query(...), k : int = Query(10), client=Depends(get_vectorstore), db = Depends(get_db)) -> List[Tag]:
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

@router.get("/batches/{batch_hash}/{report_index}/similar_studies", dependencies=[Depends(is_verified)], summary="Get related studies for a specific report in a batch based on its embedding vectors")
async def similar_studies(batch_hash: str, report_index: int, aspect: str = Query("default"), cutoff: str = Query(None), k : int = Query(10), client=Depends(get_vectorstore), channel = Depends(get_grpc_channel), db = Depends(get_db), return_details=False):
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
        async with httpx.AsyncClient() as api_client:
            response = await  api_client.get(f"http://{DATABASE_HOST}:{DATABASE_PORT}/study_id", params={"trial_id": trial_id, "cutoff":cutoff})
            response = response.json()
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

    # def cosine_similarity(a, b):        
    #     # Compute dot product
    #     dot_product = np.dot(a, b)
        
    #     # Compute norms
    #     norm_a = np.linalg.norm(a)
    #     norm_b = np.linalg.norm(b)
        
    #     # Avoid division by zero
    #     if norm_a == 0 or norm_b == 0:
    #         return 0.0
        
    #     # Return cosine similarity
    #     return dot_product / (norm_a * norm_b)

    """
    async with httpx.AsyncClient() as client:
        response = await client.get(f"http://{DATABASE_HOST}:{DATABASE_PORT}/study/reports", params={'study_ids': list(found_study_ids.keys()), 'fields': ['Title', 'Abstract'], 'cutoff': cutoff})

        for key, values in response.json().items():
            all_embeddings = []
            for value in values:
                text_input = TextInput(text=value['Title'] + (" " + value['Abstract']) if value['Abstract'] else "")
                embedding_ = _embed_report(text_input, channel=channel)['embedding']
                all_embeddings.append(np.array(embedding_))
            mean_embedding = np.mean(np.stack(all_embeddings), axis=0)
            new_sim = cosine_similarity(mean_embedding, np.array(embedding.main_embedding))
            found_study_ids[int(key)] = new_sim

    found_study_ids = dict(sorted(found_study_ids.items(), key=lambda item: item[1], reverse=True))
    """

    async with httpx.AsyncClient() as client:
        response = await client.get(f"http://{DATABASE_HOST}:{DATABASE_PORT}/studies", params={'study_ids': list(found_study_ids.keys()), "cutoff": cutoff})
    result = response.json()

    #Remove this block for evaluation without authors
    scores_authors = await get_scores_authors(report_authors=authors, study_ids=list(found_study_ids.keys()), cutoff=cutoff)
    for study_id, score in scores_authors.items():
        if found_study_ids[study_id] < 1.0:
            found_study_ids[study_id] = min(0.99, found_study_ids[study_id] + score)

    #async with httpx.AsyncClient() as client:
    #    response_persons = await client.get(f"http://{DATABASE_HOST}:{DATABASE_PORT}/study/persons", params={'study_ids': list(found_study_ids.keys()), "cutoff": cutoff})
    #persons = response_persons.json()
    
    #authors = set([author.strip().lower() for author in authors])
    #for study_id in found_study_ids.keys():
    #    study_persons = persons[str(study_id)]
    #    intersection = authors & set(study_persons)
    #    new_sim = len(intersection) / len(study_persons) if len(study_persons) > 0 else 0
    #    found_study_ids[study_id] = min(0.99, found_study_ids[study_id] + new_sim)
        #print()
        #print("Intersections: ", intersection)
        #print()
    #    if found_study_ids[study_id] > 0.99:
    #        continue

    #for study_id, participants in zip(result['CRGStudyID'], result['NumberParticipants']):
    #    if found_study_ids[study_id] > 0.99:
    #        continue
    #    embedding_ = _embed_aspect(TextInput(text=str(participants)), channel=channel)['embedding']
    #    new_sim = cosine_similarity(embedding_, np.array(embedding.main_embedding))
    #    found_study_ids[study_id] = min(0.99, found_study_ids[study_id] + new_sim)
    #    #print(study_id, new_sim)

    result['Relevance'] = list(found_study_ids.values())

    order = ['CRGStudyID', 'Relevance', 'ShortName', 'NumberParticipants', 'Duration', 'Comparison', 'Countries', 'DateEntered', 'DateEdited', 'StatusofStudy']
    reordered = {key: result[key] for key in order}

    if return_details:
        reordered['details'] = [list({d['source_id']: d for d in debug_map[key]}.values()) for key in reordered['CRGStudyID']]

    sorted_indices = sorted(range(len(reordered['Relevance'])), key=lambda i: reordered['Relevance'][i], reverse=True)
    for k in reordered:
        reordered[k] = [reordered[k][i] for i in sorted_indices]

    return reordered

async def get_scores_authors(report_authors: List[str], study_ids: List[int], cutoff: str):
    async with httpx.AsyncClient() as client:
        tasks = [
            client.get(f"http://{DATABASE_HOST}:{DATABASE_PORT}/study/persons", params={'study_ids': study_ids, "cutoff": cutoff}),
            client.get(f"http://{DATABASE_HOST}:{DATABASE_PORT}/authors/frequencies", params={'authors': report_authors}),
            ]
        responses =  await asyncio.gather(*tasks)
    study_persons = responses[0].json()
    current_persons = responses[1].json()
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

@router.get("/tags/{tag_category}/{tag_value}/related_studies", dependencies=[Depends(is_verified)], summary="Get studies related to a specific tag (intervention, outcome, ...) currently only vector-similarity search is available")
async def get_aspect_related_studies(tag_category: str, tag_value: str, k : int = Query(10), client=Depends(get_vectorstore), channel = Depends(get_grpc_channel)):
    embeddings = _embed_aspect(TextInput(text=tag_value), channel)

    collection_name = embeddings['model_id']

    return await get_similar_studies(embeddings['embedding'], collection_name, tag_category, None, None, None, k, client, return_details=False)


def single_element_generator(element):
    yield element

#@router.post("/embed/report", dependencies=[Depends(is_verified)])
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

    result = {"model_id": model_id, "embedding": list(response.embedding.values), "author_embedding": list(response.embedding.values)}
    for i, aspect in enumerate(metadata['aspects'].split(";")):
        result[aspect] = list(response.aspect_embeddings[i].values)

    return result

#@router.post("/embed/aspect", dependencies=[Depends(is_verified)])
def embed_aspect(input: TextInput, channel = Depends(get_grpc_channel)):
    return _embed_aspect(input, channel)

def _embed_aspect(input: TextInput, channel):
    token = secrets.token_urlsafe(8)

    request = embedding_pb2.EmbedAspectsRequest(id=token, aspects=[input.text])

    stub = embedding_pb2_grpc.EmbedServiceStub(channel)

    responses = stub.GetAspectEmbeddings(single_element_generator(request))

    metadata = dict(responses.initial_metadata())

    model_id = metadata['model'].replace("/", "_") + "_" + metadata["revision"]

    response = next(responses)

    result = {"model_id": model_id, "embedding": list(response.embedding[0].values)}

    return result
    
@router.post("/processing/analyze_embedding", dependencies=[Depends(verify_api_key)], include_in_schema=False)
async def analyze_embedding(input: RetrievalInputEmbedding, cutoff: str = Query(None), trial_id: str = Query(None), vectorstore=Depends(get_vectorstore)):
    result = await analyze(vectorstore, input.embeddings, input.model_id, input.basic_input.topK, input.basic_input.title, input.basic_input.abstract, input.basic_input.authors, cutoff)
    return result

#@router.post("/api/v1/analyze_text", dependencies=[Depends(verify_api_key)])
#async def analyze_text(input: RetrievalInputText, cutoff: str = Query(None), trial_id: str = Query(None), vectorstore=Depends(get_vectorstore), channel=Depends(get_grpc_channel)):    
#    text_input = TextInput(text=input.title + " " + input.abstract)
#    embedding_results = _embed_report(text_input, channel)

#    result = await analyze(vectorstore, embedding_results, embedding_results['model_id'], input.topK, input.title, input.abstract, input.authors, cutoff,)
#    return result

async def analyze(vectorstore, embeddings, model_id, top_k, title, abstract, authors, cutoff):
    """
    date_filter = Filter()
    if cutoff:
        date_filter = Filter(
            must=[
                FieldCondition(key="date_entered",range=DatetimeRange(lt=datetime.fromisoformat(cutoff)))
            ]
        )

    study_search_results = vectorstore.query_points_groups(
        collection_name=model_id,
        query=embeddings['embedding'],
        using="default",
        group_by="belongs_to_study",  # Path of the field to group by
        limit=top_k,  # Max amount of groups
        group_size=1,  # Max amount of points per group
        query_filter=date_filter,
    )

    found_study_ids = {}
    for result in study_search_results.groups:
        for hit in result.hits:
            report_hit = hit.payload['source_id']
            for item in hit.payload['belongs_to_study']:
                found_study_ids[item] = {'score': hit.score, 'report_hit': report_hit}
    """
    trial_id = await extract_trial_id(RawReport(title=title,abstract=abstract, authors=[]))
    report_embeddings =  ReportEmbedding(model_id=model_id, main_embedding=embeddings['embedding'], author_embedding=None)
    pre_result = await similarity_search_studies(report_embeddings, aspect="default", trial_id=trial_id, authors=None,cutoff=cutoff, k=top_k, client=vectorstore,channel=None, return_details=True)

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

    async with httpx.AsyncClient() as client:

        tasks = [
            client.get(f"http://{DATABASE_HOST}:{DATABASE_PORT}/studies", params={'study_ids': list(found_study_ids.keys())}),
            client.get(f"http://{DATABASE_HOST}:{DATABASE_PORT}/study/tags/interventions", params={'study_ids': list(found_study_ids.keys())}),
            client.get(f"http://{DATABASE_HOST}:{DATABASE_PORT}/study/tags/conditions", params={'study_ids': list(found_study_ids.keys())}),
            client.get(f"http://{DATABASE_HOST}:{DATABASE_PORT}/study/tags/outcomes", params={'study_ids': list(found_study_ids.keys())}),
            client.get(f"http://{DATABASE_HOST}:{DATABASE_PORT}/study/participants", params={'study_ids': list(found_study_ids.keys())}),
            client.get(f"http://{DATABASE_HOST}:{DATABASE_PORT}/study/design", params={'study_ids': list(found_study_ids.keys())}),
            client.get(f"http://{DATABASE_HOST}:{DATABASE_PORT}/study/reports", params={'study_ids': list(found_study_ids.keys()), 'fields': ['CRGReportID', 'Title', 'Abstract', 'Authors'], 'cutoff': cutoff}),
        ]

        responses =  await asyncio.gather(*tasks)
        related_studies = responses[0].json()
        study_interventions = responses[1].json()
        study_conditions = responses[2].json()
        study_outcomes = responses[3].json()
        study_participants_desc = responses[4].json()
        study_design = responses[5].json()
        study_reports = responses[6].json()

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
            #item['name'] = point.payload['display_name'] #TODO check if display_name contains chinese chars
            item['id'] = point.payload['source_id']
            item['score'] = point.score
            related_tags.append(item)

        all_ids = [item['id'] for item in related_tags]
        async with httpx.AsyncClient() as client:
            response = await client.get(f"http://{DATABASE_HOST}:{DATABASE_PORT}/tags/{type_vectorstore}", params={'ids': all_ids})
        result = response.json()
  
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
@router.post("/similarity_search/studies", dependencies=[Depends(is_verified)], summary="DEPRECATED: Use /batches/{batch_hash}/{report_index}/similar_studies instead", deprecated=True)
async def similarity_search_studies(embedding: ReportEmbedding, aspect: str = Query("default"), trial_id: str = Query(None), authors: List[str] = Query(None),  cutoff: str = Query(None), k : int = Query(10), client=Depends(get_vectorstore), return_details=False):
    
    return await get_similar_studies(embedding.main_embedding, embedding.model_id, aspect, trial_id, authors, cutoff, k, client, return_details)

@router.post("/similarity_search/tags", dependencies=[Depends(is_verified)], summary="DEPRECATED: Use /batches/{batch_hash}/{report_index}/similar_tags instead", deprecated=True)
async def similarity_search_tags(embedding: AspectEmbedding, sources: List[str] = Query(...), type: str = Query(...), k : int = Query(10), client=Depends(get_vectorstore)):
    
    return await get_similar_tags(embedding.embedding, embedding.model_id + "_tags", sources, type, k, client)