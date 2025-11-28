from fastapi import APIRouter, Request
from fastapi import Query, Path, UploadFile, File, HTTPException, Depends, BackgroundTasks
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from qdrant_client import AsyncQdrantClient, models
from qdrant_client.models import Filter, FieldCondition, DatetimeRange
from typing import Dict, List, Optional,  Any
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

import hashlib
import json
import pickle
import asyncio

import enum

from .auth import is_verified_api_call

from .resources import get_study_id_by_trial_id_internal, get_studies_internal, get_study_persons_internal, get_author_frequencies
from .resources import get_study_interventions_internal , get_study_conditions_internal, get_study_outcomes_internal, get_study_participants_internal, get_study_design_internal
from .resources import get_all_interventions_internal, get_all_conditions_internal, get_all_outcomes_internal, get_study_reports_by_ids_internal

from sqlmodel import select, func, delete, update, SQLModel
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from .utils.database_models import TmpReport, TmpReportBatch

load_dotenv()

MODEL_HOST = os.getenv("EMBEDDING_SERVICE_HOST")
MODEL_PORT = os.getenv("EMBEDDING_SERVICE_PORT")
DATABASE_VOLUME = os.getenv("DATABASE_VOLUME")
VECTORSTORE_HOST = os.getenv("VECTORSTORE_SERVICE_HOST")
VECTORSTORE_PORT = os.getenv("VECTORSTORE_SERVICE_PORT")

DEBUG = os.getenv("DEBUG", "FALSE") == "TRUE"

router = APIRouter(tags=["logic"])

cutoff_query = Query(None, description="Cutoff date: for example '2025-01-13 00:00:00' (do not retrieve items entered after that date). Usually only used for testing")
report_index_path = Path(..., description="The target report's index within the batch (starting with 0)")
batch_hash_path = Path(..., description="The batch's hash/id")

k_query = Query(10, description="Maximum number of returned results.")

DATABASE_URL = "sqlite+aiosqlite:///" + os.path.join(DATABASE_VOLUME,"persistent","users.db")

engine = create_async_engine(DATABASE_URL, echo=True)

# Simple in-process pub/sub to allow multiple subscribers per batch
batch_subscribers: Dict[str, List[asyncio.Queue]] = {}
batch_subscribers_lock = asyncio.Lock()

# Track background tasks to prevent resource leaks
background_tasks: set = set()

async def publish_batch_update(batch_hash: str):
    """Publish an update for a specific batch to all subscribers.
    The published value is the batch_hash (keeps compatibility with existing handlers).
    """
    async with batch_subscribers_lock:
        queues = list(batch_subscribers.get(batch_hash, []))

    for q in queues:
        try:
            q.put_nowait(batch_hash)
        except Exception:
            # If put_nowait fails for whatever reason, schedule an async put.
            task = asyncio.create_task(q.put(batch_hash))
            # Track the task to prevent resource leaks and add cleanup callback
            background_tasks.add(task)
            # Use lambda to be explicit and handle potential exceptions in cleanup
            task.add_done_callback(lambda t: background_tasks.discard(t))

async def subscribe_to_batch(batch_hash: str) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue()
    async with batch_subscribers_lock:
        batch_subscribers.setdefault(batch_hash, []).append(q)
    return q

async def unsubscribe_from_batch(batch_hash: str, q: asyncio.Queue):
    async with batch_subscribers_lock:
        lst = batch_subscribers.get(batch_hash)
        if not lst:
            return
        if q in lst:
            lst.remove(q)
        if not lst:
            batch_subscribers.pop(batch_hash, None)

class BatchResponse(BaseModel):
    batch_hash: str
    batch_description: Optional[str]
    number_reports: Optional[int]
    created_at: Optional[datetime]
    embedded: int = 0
    assigned: int = 0

class TagResponse(BaseModel):
    id: str
    keyword: str
    relevance: str

class RawReport(BaseModel):
    title: str
    abstract: Optional[str]
    authors: Optional[List[str]]

class TagCategories(str, enum.Enum):
    interventions = 'interventions'
    conditions = 'conditions'
    outcomes = 'outcomes'
    participants = 'participants'

@router.on_event("startup")
async def startup_event():
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

@lru_cache()
def get_grpc_channel():
    return grpc.aio.insecure_channel(f"{MODEL_HOST}:{MODEL_PORT}")

def get_vectorstore() -> AsyncQdrantClient:
    client = AsyncQdrantClient(host=VECTORSTORE_HOST, grpc_port=VECTORSTORE_PORT, prefer_grpc=True)
    yield client

async def get_session() -> AsyncSession:
    async with AsyncSession(engine) as session:
        yield session

async def process_report(report, batch_hash, index):
    title = report['title']
    abstract = report['abstract']
    authors = report['authors']

    year = report['year']
    report_number = report['report_number']
    journal = report['journal']
    pages = report['pages']
    place = report['place']
    language = report['language']
    issue = report['issue']
    volume = report['volume']
    doi = report['doi']
    
    raw_report = RawReport(title=title, abstract=abstract, authors=authors)
    trial_registration_id = extract_trial_id(raw_report)

    text_to_process = []
    if title:
        text_to_process.append(title)
    if abstract:
        text_to_process.append(abstract)
    text_to_process = "\n".join(text_to_process)
   
    vectors = await _embed_report(text_to_process, get_grpc_channel())
    vectors_blob = pickle.dumps(vectors)

    async with AsyncSession(engine) as session:

        new_report = TmpReport(
            batch_hash=batch_hash,
            batch_inner_id=index,
            title=title,
            abstract=abstract,
            authors=json.dumps(authors) if authors is not None else None,
            year=year,
            report_number=report_number,
            journal=journal,
            pages=pages,
            place=place,
            language=language,
            volume=volume,
            issue=issue,
            doi=doi,
            trial_id=trial_registration_id,
            vectors=vectors_blob
        )

        session.add(new_report)
        await session.commit()

        await publish_batch_update(batch_hash)

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

@router.post("/batches", dependencies=[Depends(is_verified_api_call)], summary="Upload a batch of new reports that need to be assigned to studies (usually in the .ris file format)", description="Uploading a new batch triggers the embedding process. Batches are mainly used to do these compute heavy calculations in the background and only once. All needed data and the calculated embedding vectors are stored temporarily.", status_code=201) 
async def upload_file(background_tasks: BackgroundTasks, file: UploadFile = File(..., description="The .ris file containing all the articles you want to process."), db : AsyncSession = Depends(get_session)):

    entries = await parse_file(file)

    results = []
    fingerprint_string = ""
    for entry in entries:
        title = entry.get('primary_title', None)
        if not title:
            title = entry.get('title', None)

        authors = entry.get('authors',None)
        abstract = entry.get('abstract', None)

        year = entry.get('year', None)
        report_number = entry.get('research_notes', None)
        journal = entry.get('secondary_title', None)
        pages = entry.get('start_page', None)
        place = entry.get('place_published', None)
        language = entry.get('language', None)
        issue = entry.get('note', None)
        volume = entry.get('volume', None)
        doi = entry.get('doi', None)

        fingerprint_string += title if title else "" + abstract if abstract else "" + authors if authors else ""

        results.append({'title':title, 'abstract':abstract, 'authors': authors, 'year': year, 'report_number': report_number, 'journal': journal, 'pages': pages, 'place': place, 'language': language, 'volume': volume, 'issue': issue, 'doi': doi})

    batch_hash = hashlib.sha256(fingerprint_string.encode()).hexdigest()

    # check if batch already exists
    existing = await db.execute(select(TmpReportBatch).where(TmpReportBatch.batch_hash == batch_hash))
    if existing.first():
        raise HTTPException(status_code=400, detail="Data already exists")


    # insert batch
    new_batch = TmpReportBatch(
        batch_hash=batch_hash,
        batch_description=file.filename,
        number_reports=len(results)
    )
    db.add(new_batch)
    await db.commit()

    # schedule background tasks
    for i, result in enumerate(results):
        background_tasks.add_task(process_report, result, batch_hash, i)

    await publish_batch_update(batch_hash)

    return Response(status_code=201)
    
@router.get("/batches", dependencies=[Depends(is_verified_api_call)], summary="Get an overview of current report batches.", description="For each batch the current progress of embedding calculation and the number of already assigned reports is returned")
async def get_available_batches(db: AsyncSession = Depends(get_session)) -> List[BatchResponse]:
    r_subq = (
        select(
            TmpReport.batch_hash,
            func.count().label("embedded"),
            func.count(TmpReport.assigned_studies).label("assigned")
        )
        .group_by(TmpReport.batch_hash)
        .subquery()
    )

    query = (
        select(
            TmpReportBatch,
            func.coalesce(r_subq.c.embedded, 0).label("embedded"),
            func.coalesce(r_subq.c.assigned, 0).label("assigned")
        )
        .outerjoin(r_subq, TmpReportBatch.batch_hash == r_subq.c.batch_hash)
    )
    result = await db.execute(query)
    rows = result.mappings().all()

    flattened = []
    for row in rows:
        batch: TmpReportBatch = row["TmpReportBatch"]
        batch_dict = batch.dict()  # Convert model to dict
        # Merge embedded and assigned into the batch dict
        batch_dict.update({
            "embedded": row["embedded"],
            "assigned": row["assigned"]
        })
        flattened.append(BatchResponse(**batch_dict))

    return flattened

@router.get("/batches/{batch_hash}", dependencies=[Depends(is_verified_api_call)], summary="Get a specific report batch by hash.",description="Returns details and progress information for a single report batch identified by batch_hash.")
async def get_batch_by_hash(batch_hash: str, db: AsyncSession = Depends(get_session)) -> BatchResponse | None:
    r_subq = (
        select(
            TmpReport.batch_hash,
            func.count().label("embedded"),
            func.count(TmpReport.assigned_studies).label("assigned")
        )
        .group_by(TmpReport.batch_hash)
        .subquery()
    )

    query = (
        select(
            TmpReportBatch,
            func.coalesce(r_subq.c.embedded, 0).label("embedded"),
            func.coalesce(r_subq.c.assigned, 0).label("assigned")
        )
        .outerjoin(r_subq, TmpReportBatch.batch_hash == r_subq.c.batch_hash)
        .where(TmpReportBatch.batch_hash == batch_hash)
    )

    result = await db.execute(query)
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Batch not found")

    batch: TmpReportBatch = row["TmpReportBatch"]
    batch_dict = batch.dict()
    batch_dict.update({
        "embedded": row["embedded"],
        "assigned": row["assigned"]
    })

    return BatchResponse(**batch_dict)

@router.delete("/batches/{batch_hash}", dependencies=[Depends(is_verified_api_call)], summary="Delete a report batch and all its associated reports (including calculated embedding vectors) from the temporary storage.", status_code=204)
async def delete_batch(batch_hash: str, db: AsyncSession = Depends(get_session)):
    # delete related reports first (due to FK constraints)
    await db.execute(
        delete(TmpReport).where(TmpReport.batch_hash == batch_hash)
    )
    await db.execute(
        delete(TmpReportBatch).where(TmpReportBatch.batch_hash == batch_hash)
    )
    await db.commit()

    await publish_batch_update(batch_hash)

    return Response(status_code=204)

@router.get("/batches/{batch_hash}/subscribe",dependencies=[Depends(is_verified_api_call)], summary="Stream updated batch information.")
async def stream_batch_updates(batch_hash : str,  request: Request, db: AsyncSession = Depends(get_session)) -> StreamingResponse:
    async def event_stream():
        HEARTBEAT_INTERVAL = 10  # seconds

        # subscribe this client to the batch
        q = await subscribe_to_batch(batch_hash)
        try:
            while True:
                # Check for client disconnect
                if await request.is_disconnected():
                    break

                # Check if batch still exists
                try:
                    batch_exists = await get_batch_by_hash(batch_hash, db)
                except HTTPException as e:
                    if e.status_code == 404:
                        yield f"event: batch_deleted\ndata: Batch deleted\n\n"
                        break
                    else:
                        raise

                try:
                    data = await asyncio.wait_for(q.get(), timeout=HEARTBEAT_INTERVAL)
                    if data == batch_hash:
                        try:
                            result = await get_batch_by_hash(batch_hash, db)
                            yield f"data: {result.json()}\n\n"
                        except HTTPException as e:
                            if e.status_code == 404:
                                yield f"event: batch_deleted\ndata: Batch deleted\n\n"
                                break
                            else:
                                raise
                except asyncio.TimeoutError:
                    # Send heartbeat
                    yield f": heartbeat\n\n"
        finally:
            await unsubscribe_from_batch(batch_hash, q)

    return StreamingResponse(event_stream(), media_type="text/event-stream")

@router.get("/batches/{batch_hash}/{report_index}", dependencies=[Depends(is_verified_api_call)], summary="Get the data and embedding vectors for a specific report in a batch.", description="Retrieve the title, abstract, authors, trial ID, embedding vectors, and assigned studies for a specific report identified by its batch hash and index (starting with 0) within the batch.")
async def get_batched_report(batch_hash: str, report_index: int, db: AsyncSession = Depends(get_session)):
    stmt = (
        select(TmpReport)
        .where(
            TmpReport.batch_hash == batch_hash,
            TmpReport.batch_inner_id == report_index
        )
        .limit(1)
    )

    result = await db.execute(stmt)
    row = result.scalar_one_or_none()  # gets the TmpReport object directly

    if not row:
        return None  # or raise 404

    # Convert SQLAlchemy object to dict dynamically
    report_data = {c.name: getattr(row, c.name) for c in TmpReport.__table__.columns}

    # Decode JSON and Pickle fields
    if report_data.get("authors"):
        report_data["authors"] = json.loads(report_data["authors"])
    if report_data.get("assigned_studies"):
        report_data["assigned_studies"] = json.loads(report_data["assigned_studies"])
    if report_data.get("vectors"):
        report_data["vectors"] = pickle.loads(report_data["vectors"])

    return report_data


@router.put("/batches/{batch_hash}/{report_index}/studies", dependencies=[Depends(is_verified_api_call)], summary="Assign studies to a specific report in a batch.", status_code=204)
async def assign_studies(batch_hash: str = batch_hash_path, report_index: int = report_index_path, study_ids: List[int] = Query(..., description="The study ids (CRGReportIDs) you want to assign to the specified report."), db : AsyncSession = Depends(get_session)):
    stmt = (
        update(TmpReport)
        .where(
            TmpReport.batch_hash == batch_hash,
            TmpReport.batch_inner_id == report_index
        )
        .values(assigned_studies=json.dumps(study_ids))
    )
    await db.execute(stmt)
    await db.commit()

    await publish_batch_update(batch_hash)

    return Response(status_code=204)

@router.delete("/batches/{batch_hash}/{report_index}/studies", dependencies=[Depends(is_verified_api_call)], summary="Remove assigned studies from a specific report in a batch.", status_code=204)
async def delete_assigned_studies(batch_hash: str = batch_hash_path, report_index: int = report_index_path, db : AsyncSession = Depends(get_session)):
    stmt = (
        update(TmpReport)
        .where(
            TmpReport.batch_hash == batch_hash,
            TmpReport.batch_inner_id == report_index
        )
        .values(assigned_studies=None)
    )
    await db.execute(stmt)
    await db.commit()

    await publish_batch_update(batch_hash)

    return Response(status_code=204)

@router.get("/batches/{batch_hash}/{report_index}/similar_tags", dependencies=[Depends(is_verified_api_call)], summary="Get related tags (interventions, outcomes, ...) for a specific report in a batch based on its embedding vectors.")
async def similar_tags(batch_hash: str = batch_hash_path, report_index: int = report_index_path, sources: List[str] = Query(..., description="Which source of tags do you want to search ('mesh', 'meerkat' or both)"), aspect: TagCategories = Query(None, description="The tag category which you are interested in"), k : int = k_query, client=Depends(get_vectorstore), db = Depends(get_session)) -> List[TagResponse]:
    stmt = (
        select(TmpReport.vectors)
        .where(
            TmpReport.batch_hash == batch_hash,
            TmpReport.batch_inner_id == report_index
        )
        .limit(1)
    )

    result = await db.execute(stmt)
    row = result.first()

    if not row:
        raise HTTPException(status_code=404, detail="Report not found")

    vectors = pickle.loads(row[0])

    collection_name = vectors['model_id'] + "_tags"

    vector_names = {'interventions': 'intervention', 'conditions': 'condition', 'outcomes': 'outcome'}

    embedding = vectors[vector_names[aspect]]

    data = await get_similar_tags(embedding, collection_name, sources, aspect, k, client)

    result = [
        {"id": i, "keyword": k, "relevance": r}
        for i, k, r in zip(data["ID"], data["Keyword"], data["Relevance"])
    ]
    return result

@router.get("/batches/{batch_hash}/{report_index}/similar_studies", dependencies=[Depends(is_verified_api_call)], summary="Get related studies for a specific report in a batch based on its embedding vectors.", description="Retrieve studies that are similar to a specific report identified by its batch hash and index (starting with 0) within the batch. Similarity is determined based on the embedding vectors of the report. The similarity search is done at runtime. You can optionally search for similarity based on a specific aspect (e.g., interventions, outcomes) or apply a cutoff date to only consider studies entered before a certain date.")
async def similar_studies(batch_hash: str = batch_hash_path, report_index: int = report_index_path, aspect: TagCategories = Query(None, description="This value is rarely needed. Just if you want to search studies based on a certain aspect."), cutoff: str = cutoff_query, k : int = k_query, client=Depends(get_vectorstore), db = Depends(get_session), return_details=False):
    if not aspect:
        aspect = "default"
    
    stmt = (
        select(
            TmpReport.authors,
            TmpReport.trial_id,
            TmpReport.vectors
        )
        .where(
            TmpReport.batch_hash == batch_hash,
            TmpReport.batch_inner_id == report_index
        )
        .limit(1)
    )

    result = await db.execute(stmt)
    row = result.first()

    if not row:
        raise HTTPException(status_code=404, detail="Report not found")

    authors = row[0]
    trial_id = row[1]
    vectors = pickle.loads(row[2])

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

    search_results = await client.query_points(
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

async def get_similar_studies(embedding, collection_name, aspect: str, trial_id: str, authors: List[str], cutoff: str, k: int, client: AsyncQdrantClient, return_details: bool):
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
        
        response = await get_study_id_by_trial_id_internal(trial_id, cutoff)
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
        search_results = await client.query_points_groups(
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

    all_studies = await get_studies_internal(list(found_study_ids.keys()))
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

    study_persons = await get_study_persons_internal(study_ids, cutoff)
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

@router.get("/{tag_category}/{tag_value}/related_studies", dependencies=[Depends(is_verified_api_call)], summary="Get studies related to a specific tag (intervention, outcome, ...) currently only vector-similarity search is available.", description="Retrieve studies that are related to a specific tag value (e.g., 'Placebo' for interventions) using vector similarity search based on the embedding of the tag value. The similarity search is done at runtime.")
async def get_aspect_related_studies(tag_category: TagCategories = Path(..., description="The tags category (e.g. 'interventions', 'conditions', ...)"), tag_value: str = Path(..., description="The specific tags value (e.g. 'Placebo' for interventions)"), k : int = k_query, client=Depends(get_vectorstore), channel = Depends(get_grpc_channel)):
    embeddings = await _embed_aspect(tag_value, channel)

    collection_name = embeddings['model_id']

    aspect = tag_category
    aspect_mapping = {'interventions': 'intervention', 'conditions': 'condition', 'outcomes': 'outcome'}
    if tag_category in aspect_mapping.keys():
        aspect = aspect_mapping[tag_category]

    return await get_similar_studies(embeddings['embedding'], collection_name, aspect, None, [], None, k, client, return_details=False)


async def single_element_generator(element):
    yield element

async def embed_report(text, channel = Depends(get_grpc_channel)):
    return await _embed_report(text, channel)

async def _embed_report(text : str, channel):
    token = secrets.token_urlsafe(8)

    request = embedding_pb2.EmbedReportRequest(id=token, text=text, authors=[])

    stub = embedding_pb2_grpc.EmbedServiceStub(channel)

    responses = stub.GetReportEmbedding(single_element_generator(request))

    metadata = {k: v for k, v in (await responses.initial_metadata())}

    model_id = metadata['model'].replace("/", "_") + "_" + metadata["revision"]

    response = await responses.read()

    result = {"model_id": model_id, "embedding": list(response.embedding.values), "author_embedding": list(response.embedding.values)}
    for i, aspect in enumerate(metadata['aspects'].split(";")):
        result[aspect] = list(response.aspect_embeddings[i].values)

    return result

async def embed_aspect(text : str, channel = Depends(get_grpc_channel)):
    return await _embed_aspect(text, channel)

async def _embed_aspect(text : str, channel):
    token = secrets.token_urlsafe(8)

    request = embedding_pb2.EmbedAspectsRequest(id=token, aspects=[text])

    stub = embedding_pb2_grpc.EmbedServiceStub(channel)

    responses = stub.GetAspectEmbeddings(single_element_generator(request))

    metadata = {k: v for k, v in (await responses.initial_metadata())}

    model_id = metadata['model'].replace("/", "_") + "_" + metadata["revision"]

    response = await responses.read()

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
    
@router.post("/processing/analyze_embedding", dependencies=[Depends(is_verified_api_call)], include_in_schema=False)
async def analyze_embedding(input: RetrievalInputEmbedding, cutoff: str = Query(None), client=Depends(get_vectorstore)):
    result = await analyze(input.embeddings, input.model_id, input.basic_input.topK, input.basic_input.title, input.basic_input.abstract, input.basic_input.authors, cutoff, client)
    return result

async def analyze(embeddings, model_id, top_k, title, abstract, authors, cutoff, client):
    
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

    related_studies = await get_studies_internal(list(found_study_ids.keys()))
    study_interventions = await get_study_interventions_internal(list(found_study_ids.keys()))
    study_conditions = await get_study_conditions_internal(list(found_study_ids.keys()))
    study_outcomes = await get_study_outcomes_internal(list(found_study_ids.keys()))
    study_participants_desc = await get_study_participants_internal(list(found_study_ids.keys()))
    study_design = await get_study_design_internal(list(found_study_ids.keys()))
    study_reports = await get_study_reports_by_ids_internal(list(found_study_ids.keys()), ['CRGReportID', 'Title', 'Abstract', 'Authors'], cutoff)

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

        tag_results = client.query_points(
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
            result = await get_all_interventions_internal(all_ids)
        elif type_vectorstore == "conditions":
            result = await get_all_conditions_internal(all_ids)
        elif type_vectorstore == "outcomes":
            result = await get_all_outcomes_internal(all_ids)
  
        for item in related_tags:
            item['name'] = result[item['id']][0].strip()
        
        return related_tags

    result['related_interventions'] = await search_related_tags(all_related_interventions, "intervention", "interventions")
    result['related_conditions'] = await search_related_tags(all_related_conditions, "condition", "conditions")
    result['related_outcomes'] = await search_related_tags(all_related_outcomes, "outcome", "outcomes")

    return result


@router.post("/processing/extract_trial_id", dependencies=[Depends(is_verified_api_call)], include_in_schema=False)
def extract_trial_id(raw_report: RawReport):
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

@router.post("/similarity_search/studies", dependencies=[Depends(is_verified_api_call)], summary="DEPRECATED: Use /batches/{batch_hash}/{report_index}/similar_studies instead", deprecated=True)
async def similarity_search_studies(embedding: ReportEmbedding, aspect: str = Query("default"), trial_id: str = Query(None), authors: List[str] = Query(None),  cutoff: str = Query(None), k : int = Query(10), client=Depends(get_vectorstore), return_details=False):
    
    return await get_similar_studies(embedding.main_embedding, embedding.model_id, aspect, trial_id, authors, cutoff, k, client, return_details)

@router.post("/similarity_search/tags", dependencies=[Depends(is_verified_api_call)], summary="DEPRECATED: Use /batches/{batch_hash}/{report_index}/similar_tags instead", deprecated=True)
async def similarity_search_tags(embedding: AspectEmbedding, sources: List[str] = Query(...), type: str = Query(...), k : int = Query(10), client=Depends(get_vectorstore)):
    
    return await get_similar_tags(embedding.embedding, embedding.model_id + "_tags", sources, type, k, client)

@router.get("/readyz", summary="Health check endpoint for readiness probe", tags=["health"])
async def readyz(db: AsyncSession = Depends(get_session), client: AsyncQdrantClient = Depends(get_vectorstore)) -> Dict[str, Any]:
    """
    Check if the service is ready to accept requests.
    
    Returns:
        - status: "ready" or "not_ready"
        - checks: detailed status of each dependency
    """
    checks = {}
    overall_status = "ready"
    
    # Check database connectivity
    try:
        await db.execute(select(1))
        checks["database"] = {"status": "healthy", "message": "Database connection successful"}
    except Exception as e:
        checks["database"] = {"status": "unhealthy", "message": f"Database error: {str(e)}"}
        overall_status = "not_ready"
    
    # Check vector store connectivity
    try:
        collections = await client.get_collections()
        checks["vectorstore"] = {
            "status": "healthy",
            "message": f"Vector store accessible, {len(collections.collections)} collections found"
        }
    except Exception as e:
        checks["vectorstore"] = {"status": "unhealthy", "message": f"Vector store error: {str(e)}"}
        overall_status = "not_ready"
    
    # Check gRPC embedding service connectivity
    try:
        channel = get_grpc_channel()
        # Simple connectivity check - channel state
        state = channel.get_state(try_to_connect=True)
        if state == grpc.ChannelConnectivity.READY:
            checks["embedding_service"] = {"status": "healthy", "message": "gRPC channel ready"}
        else:
            checks["embedding_service"] = {
                "status": "degraded",
                "message": f"gRPC channel state: {state.name}"
            }
            overall_status = "not_ready"
    except Exception as e:
        checks["embedding_service"] = {"status": "unhealthy", "message": f"gRPC error: {str(e)}"}
        overall_status = "not_ready"
    
    # Check background task health
    checks["background_tasks"] = {
        "status": "healthy",
        "active_tasks": len(background_tasks),
        "message": f"{len(background_tasks)} active background tasks"
    }
    
    # Check batch subscribers
    async with batch_subscribers_lock:
        total_subscribers = sum(len(queues) for queues in batch_subscribers.values())
        checks["batch_subscribers"] = {
            "status": "healthy",
            "active_batches": len(batch_subscribers),
            "total_subscribers": total_subscribers,
            "message": f"{len(batch_subscribers)} batches with {total_subscribers} subscribers"
        }
    
    response = {
        "status": overall_status,
        "timestamp": datetime.now().isoformat(),
        "checks": checks
    }
    
    # Return 503 if not ready
    if overall_status != "ready":
        raise HTTPException(status_code=503, detail=response)
    
    return response