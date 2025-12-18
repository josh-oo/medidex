from fastapi import APIRouter, Request
from fastapi import Query, Path, UploadFile, File, HTTPException, Depends, BackgroundTasks
from fastapi.responses import Response, StreamingResponse, JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from qdrant_client import models
from qdrant_client.models import Filter, FieldCondition, DatetimeRange
from typing import Dict, List, Optional,  Any
import math
import os

from datetime import datetime, timezone

import grpc

from functools import lru_cache

from datetime import datetime

from .utils.trial_registration_id import extract_trial_id
from .utils.vectorstore import transform_to_uuid, transform_to_crg_report_id
from .utils.vectorstore import get_vectors_by_crg_report_id, delete_vectors_by_crg_report_ids, add_report_to_vectorstore, crg_reports_exist, link_report_to_study_ids, search_report, search_tags, get_collections, calculate_score_pairs
from .utils.embedding import _embed_aspect
from .utils.ris_parser import parse_file

import hashlib
import asyncio

import enum

from .auth import is_verified_api_call, get_user_id

from .resources import get_study_id_by_trial_ids_internal, get_studies_internal, get_study_persons_internal, get_author_frequencies
from .resources import get_study_interventions_internal , get_study_conditions_internal, get_study_outcomes_internal, get_study_participants_internal, get_study_design_internal
from .resources import get_all_interventions_internal, get_all_conditions_internal, get_all_outcomes_internal, get_study_reports_by_ids_internal
from .resources import add_new_report_batch, get_report_studies_by_id_internal, get_report_by_id_internal
from .resources import add_report_studies_by_id_internal, delete_report_studies_by_id_internal
from .resources import get_report_trial_ids_internal, get_similar_report_studies_internal
from .resources import get_session
from .resources import post_report_event, Event

from sqlmodel import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from .utils.database_models import Report, Batch, ReportAdded, BatchInnerScore

load_dotenv()

MODEL_HOST = os.getenv("EMBEDDING_SERVICE_HOST")
MODEL_PORT = os.getenv("EMBEDDING_SERVICE_PORT")
COLLECTION_NAME = os.getenv("VECTORSTORE_COLLECTION_NAME")

POSTGRES_USER = os.getenv("POSTGRES_USER")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
POSTGRES_DB_USERS = os.getenv("POSTGRES_DB_USERS")
POSTGRES_HOST = os.getenv("POSTGRES_HOST")
POSTGRES_PORT = os.getenv("POSTGRES_PORT")

DEBUG = os.getenv("DEBUG", "FALSE") == "TRUE"

router = APIRouter(tags=["logic"])

cutoff_query = Query(None, description="Cutoff date: for example '2025-01-13 00:00:00' (do not retrieve items entered after that date). Usually only used for testing")
report_index_path = Path(..., description="The target report's index within the batch (starting with 0)")
batch_hash_path = Path(..., description="The batch's hash/id")

k_query = Query(10, description="Maximum number of returned results.")

# Simple in-process pub/sub to allow multiple subscribers per batch
batch_subscribers: Dict[str, List[asyncio.Queue]] = {}
batch_subscribers_lock = asyncio.Lock()

# Track background tasks to prevent resource leaks
background_tasks: set = set()

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
    default = 'default'
    interventions = 'interventions'
    conditions = 'conditions'
    outcomes = 'outcomes'
    participants = 'participants'

@lru_cache()
def get_grpc_channel():
    channel = grpc.aio.insecure_channel(f"{MODEL_HOST}:{MODEL_PORT}")
    channel.get_state(try_to_connect=True)
    return channel

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

async def finalize_batch_upload(batch_hash:str, session: AsyncSession):
    """
    Finalize a batch upload by checking if all reports have been processed.
    Updates batch status and notifies subscribers when complete.
    """
    # Get all reports in the batch
    result = await session.execute(
        select(ReportAdded.CRGReportID).where(ReportAdded.BatchHash == batch_hash)
    )
    crg_report_ids = result.scalars().all()
    
    if not crg_report_ids:
        return
    
    # Check if all reports have embeddings
    num_existing = await crg_reports_exist(crg_report_ids)
    
    all_processed = num_existing == len(crg_report_ids)
    
    if all_processed:
        # Update batch status in database (you'll need to add a status field to Batch model)
        batch = await session.execute(select(Batch).where(Batch.BatchHash == batch_hash))
        batch_obj = batch.scalar_one_or_none()
        if batch_obj:
            #TODO
            # batch_obj.Status = "completed"  # Add Status field to Batch model
            # batch_obj.CompletedAt = datetime.now()  # Add CompletedAt field
            await session.commit()
        
        # Notify all subscribers that batch is complete
        score_pairs = await calculate_score_pairs(crg_report_ids)
        all_scores = []
        for pair in score_pairs:
            all_scores.append(BatchInnerScore(CRGReportID=transform_to_crg_report_id(pair.a), OtherID=transform_to_crg_report_id(pair.b), Score=pair.score))

        print(all_scores[:10])
        session.add_all(all_scores)
        await session.commit()

        print("Batch finalized")
        await publish_batch_update(batch_hash)

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

async def process_report(report, batch_hash, session):
    
    await add_report_to_vectorstore(report, get_grpc_channel())

    await publish_batch_update(batch_hash)

    await finalize_batch_upload(batch_hash, session)

@router.get("/readyz", summary="Health check endpoint for readiness probe", tags=["health"])
async def readyz(db: AsyncSession = Depends(get_session)) -> Dict[str, Any]:
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
        collections = await get_collections()
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

@router.post("/batches", dependencies=[Depends(is_verified_api_call)], summary="Upload a batch of new reports that need to be assigned to studies (usually in the .ris file format)", description="Uploading a new batch triggers the embedding process. Batches are mainly used to do these compute heavy calculations in the background and only once. All needed data and the calculated embedding vectors are stored temporarily.", status_code=201) 
async def upload_file(background_tasks: BackgroundTasks, file: UploadFile = File(..., description="The .ris file containing all the articles you want to process."), session : AsyncSession = Depends(get_session)):

    entries = await parse_file(file)

    reports = []
    fingerprint_string = ""
    for entry in entries:
        title = entry.get('primary_title', None)
        if not title:
            title = entry.get('title', None)

        authors = entry.get('authors',None)
        abstract = entry.get('abstract', None)
        report_number = int(entry.get('research_notes', 0))

        trial_ids = extract_trial_id(title=title, abstract=abstract, authors=authors)
        if len(trial_ids) == 1:
            trial_ids = trial_ids[0]
        else:
            trial_ids = None

        report = Report(
            Title=title,
            Abstract=abstract,
            Authors="//".join(authors),
            ReportNumber=report_number,
            Journal=entry.get('secondary_title', None),
            Year=int(entry.get('year', None)),
            Volume= entry.get('volume', None),
            Issue=entry.get('note', None),
            Pages=entry.get('start_page', None),
            Language=entry.get('language', None),
            Publisher=entry.get('publisher', None),
            City=entry.get('place_published', None),
            DOI=entry.get('doi', None),
            TrialRegistrationID=trial_ids,
            CopyStatus= "Copy Obtained" if report_number != 0 else "Seeking Source",
            TypeofReportID=0, #TODO ask alessandro
            PublicationTypeID=1, #TODO ask alessandro
            #TODO Dupstring missing
            #OriginalTitle: Optional[str] TODO
        )

        fingerprint_string += title if title else "" + abstract if abstract else "" + authors if authors else ""

        reports.append(report)

    batch_hash = hashlib.sha256(fingerprint_string.encode()).hexdigest()

    reports = await add_new_report_batch(batch_hash,file.filename,reports, user="unknown", session=session)

    # schedule background tasks
    for report in reports:
        background_tasks.add_task(process_report, report, batch_hash, session)

    await publish_batch_update(batch_hash)

    #TODO disabled for legacy reasons
    #reports_dict = [report.dict() for report in reports]
    #JSONResponse(content={"batch_hash": batch_hash, "batch_description": file.filename, "reports": reports_dict}, status_code=201)

    return Response(status_code=201)

async def get_batch_by_hash(batch_hash: str, db: AsyncSession = Depends(get_session)):
    batch = await db.execute(select(Batch).where(Batch.BatchHash == batch_hash))
    result = batch.scalar_one_or_none()
    if not result:
        raise HTTPException(status_code=404, detail="Batch not found")
    return result

async def get_batch_associated_reports(batch: Batch = Depends(get_batch_by_hash), db: AsyncSession = Depends(get_session)):
    result = await db.execute(
        select(ReportAdded.CRGReportID).where(ReportAdded.BatchHash == batch.BatchHash)
    )
    return result.scalars().all()

async def get_batch_stats(batch: Batch = Depends(get_batch_by_hash), crg_report_ids : List[int] = Depends(get_batch_associated_reports), user_id : Optional[str] = Depends(get_user_id)) -> BatchResponse:
    # Fetch all report studies in parallel
    study_tasks = [get_report_studies_by_id_internal(report_id, user=user_id) for report_id in crg_report_ids]
    all_studies = await asyncio.gather(*study_tasks)
    generated_embeddings = await crg_reports_exist(crg_report_ids)

    # Count reports with assigned studies
    assigned_count = sum(1 for studies in all_studies if len(studies) > 0)

    return BatchResponse(
        batch_hash=batch.BatchHash,
        batch_description=batch.BatchDescription,
        created_at=batch.DateCreated,
        number_reports=len(crg_report_ids),
        embedded=generated_embeddings,
        assigned=assigned_count,
    )

@router.get("/batches", dependencies=[Depends(is_verified_api_call)], summary="Get an overview of current report batches.", description="For each batch the current progress of embedding calculation and the number of already assigned reports is returned")
async def get_available_batches(db: AsyncSession = Depends(get_session), user_id : Optional[str] = Depends(get_user_id)) -> List[BatchResponse]:
    # Get all batches
    result = await db.execute(select(Batch))
    batches = result.scalars().all()

    # Process all batches in parallel
    tasks = []
    for batch in batches:
        crg_report_ids = await get_batch_associated_reports(batch, db)
        tasks.append(get_batch_stats(batch, crg_report_ids, user_id))
    batch_responses = await asyncio.gather(*tasks)

    return batch_responses

@router.get("/batches/{batch_hash}", dependencies=[Depends(is_verified_api_call)], summary="Get a specific report batch by hash.",description="Returns details and progress information for a single report batch identified by batch_hash.")
async def get_batch_stats_by_hash(batch_stats : BatchResponse = Depends(get_batch_stats)) -> BatchResponse:
    return batch_stats

@router.delete("/batches/{batch_hash}", dependencies=[Depends(is_verified_api_call)], summary="Delete a report batch and all its associated reports (including calculated embedding vectors) from the temporary storage.", status_code=204)
async def delete_batch(batch: Batch = Depends(get_batch_by_hash), crg_report_ids : List[int] = Depends(get_batch_associated_reports), db: AsyncSession = Depends(get_session)):
    
    #Deletes the batch and through cascade and triggers everythig related to it
    await db.execute(delete(Batch).where(Batch.BatchHash == batch.BatchHash))
    await db.commit()

    await delete_vectors_by_crg_report_ids(crg_report_ids)

    await publish_batch_update(batch.BatchHash)
    
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

async def batch_hash_id_to_crg_report_id(batch_hash: str = batch_hash_path, report_index: int = report_index_path, db : AsyncSession = Depends(get_session)):
    stmt = (
        select(ReportAdded.CRGReportID)
        .where(
            ReportAdded.BatchHash == batch_hash,
        )
        .order_by(ReportAdded.CRGReportID)
        .offset(report_index)
        .limit(1)
    )

    result = await db.execute(stmt)
    crg_report_id = result.scalar_one_or_none()
    if not crg_report_id:
        raise HTTPException(status_code=404, detail="Report not found")
    return crg_report_id

@router.get("/batches/{batch_hash}/{report_index}", dependencies=[Depends(is_verified_api_call)], summary="Get the data and embedding vectors for a specific report in a batch.", description="Retrieve the title, abstract, authors, trial ID, embedding vectors, and assigned studies for a specific report identified by its batch hash and index (starting with 0) within the batch.")
async def get_batched_report(crg_report_id= Depends(batch_hash_id_to_crg_report_id), user_id : Optional[str] = Depends(get_user_id)):

    # Run DB/vectorstore calls in parallel
    vectors_task = get_vectors_by_crg_report_id(crg_report_id)
    report_task = get_report_by_id_internal(crg_report_id)
    assigned_studies_task = get_report_studies_by_id_internal(crg_report_id, user=user_id)

    report_obj, vectors, assigned_studies = await asyncio.gather(
        report_task, vectors_task, assigned_studies_task
    )

    # Convert Report model to dict
    report = report_obj.dict()

    # Normalize keys to lowercase
    report = {key.lower(): value for key, value in report.items()}


    # Normalize vectors key for legacy
    vectors['embedding'] = vectors.pop("default")

    # Normalize authors
    report["authors"] = report["authors"].split("//") if report.get("authors") else []

    # Assigned studies from DB (not JSON field)
    report["assigned_studies"] = [s.CRGStudyID for s in assigned_studies]

    report["vectors"] = vectors

    return report

@router.put("/batches/{batch_hash}/{report_index}/studies", dependencies=[Depends(is_verified_api_call)], summary="Assign studies to a specific report in a batch.", status_code=200)
async def assign_studies(batch_hash: str = batch_hash_path, study_ids: List[int] = Query(..., description="The study ids (CRGReportIDs) you want to assign to the specified report."), crg_report_id= Depends(batch_hash_id_to_crg_report_id), user_id: Optional[str] = Depends(get_user_id)):
    await asyncio.gather(
        add_report_studies_by_id_internal(crg_report_id, study_ids, user_id),
        link_report_to_study_ids(crg_report_id, study_ids, user_id)
    )

    await publish_batch_update(batch_hash)
    await post_report_event(crg_report_id, Event(event_type=f"study::links::changed", timestamp=datetime.now(timezone.utc).isoformat()), user_id)

    return await get_batched_report(crg_report_id, user_id)

@router.delete("/batches/{batch_hash}/{report_index}/studies", dependencies=[Depends(is_verified_api_call)], summary="Remove assigned studies from a specific report in a batch.", status_code=200)
async def delete_assigned_studies(batch_hash: str = batch_hash_path, crg_report_id= Depends(batch_hash_id_to_crg_report_id), user_id: Optional[str] = Depends(get_user_id)):
    await asyncio.gather(
        delete_report_studies_by_id_internal(crg_report_id, user_id),
        link_report_to_study_ids(crg_report_id, [], user_id)
    )

    await publish_batch_update(batch_hash)
    await post_report_event(crg_report_id, Event(event_type=f"study::links::changed", timestamp=datetime.now(timezone.utc).isoformat()), user_id)

    return await get_batched_report(crg_report_id, user_id)

@router.get("/batches/{batch_hash}/{report_index}/similar_tags", dependencies=[Depends(is_verified_api_call)], summary="Get related tags (interventions, outcomes, ...) for a specific report in a batch based on its embedding vectors.")
async def similar_tags(sources: List[str] = Query(..., description="Which source of tags do you want to search ('mesh', 'meerkat' or both)"), aspect: TagCategories = Query(TagCategories.interventions, description="The tag category which you are interested in"), k : int = k_query, crg_report_id= Depends(batch_hash_id_to_crg_report_id)) -> List[TagResponse]:

    if aspect == TagCategories.default:
        raise HTTPException(status_code=400, detail="No tags for 'default' embedding.")
    
    vectors = await get_vectors_by_crg_report_id(crg_report_id)

    vector_names = {'interventions': 'intervention', 'conditions': 'condition', 'outcomes': 'outcome'}

    embedding = vectors[vector_names[aspect]]

    data = await get_similar_tags(embedding, sources, aspect, k)

    result = [
        {"id": i, "keyword": k, "relevance": r}
        for i, k, r in zip(data["ID"], data["Keyword"], data["Relevance"])
    ]
    return result

@router.get("/batches/{batch_hash}/{report_index}/similar_studies", dependencies=[Depends(is_verified_api_call)], summary="Get related studies for a specific report in a batch based on its embedding vectors.", description="Retrieve studies that are similar to a specific report identified by its batch hash and index (starting with 0) within the batch. Similarity is determined based on the embedding vectors of the report. The similarity search is done at runtime. You can optionally search for similarity based on a specific aspect (e.g., interventions, outcomes) or apply a cutoff date to only consider studies entered before a certain date.")
async def similar_studies(aspect: TagCategories = Query(TagCategories.default, description="This value is rarely needed. Just if you want to search studies based on a certain aspect."), cutoff: str = cutoff_query, k : int = k_query, crg_report_id= Depends(batch_hash_id_to_crg_report_id), user_id = Depends(get_user_id), return_details : bool = False):

    return await get_similar_studies_by_id(crg_report_id, aspect, cutoff, k, None, None, user_id, return_details)

async def get_similar_tags(embedding, sources: List[str], aspect: str, k: int):
    
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

    search_results = await search_tags(embedding, k, filter)

    results = {'ID': [], 'Keyword':[], 'Relevance': []}

    for result in search_results.points:
        results['ID'].append(result.payload['source_id'])
        results['Keyword'].append(result.payload['display_name'])
        results['Relevance'].append(str(round(result.score * 100)) + "%")

    return results

async def get_similar_studies_by_embedding(embedding, aspect: str, trial_id: List[str], authors: List[str], cutoff: str, k: int, user_id: str, return_details: bool):
    return await get_similar_study_by_query(embedding,aspect,cutoff,k, [], [trial_id], authors, user_id, return_details=return_details)

import random
import numpy as np

def get_random_sigma(user_id: str, report_id: int) -> float:
    data = f"{user_id}|{report_id}".encode("utf-8")
    seed = int(hashlib.sha256(data).hexdigest(), 16)
    rng = random.Random(seed)
    if rng.random() < 0.5:
      return 0.0
    rng = random.Random(seed+1)
    return rng.random() 


async def get_similar_studies_by_id(crg_report_id : int, aspect: TagCategories, cutoff: str, k: int, negative_studies: List[int], negative_reports: List[int], user_id : Optional[str], return_details: bool):

    report = await get_report_by_id_internal(crg_report_id)

    authors = [item.strip() for item in report.Authors.split("//")]
    trial_ids = await get_report_trial_ids_internal(report, include_fulltext=True)

    if not negative_studies:
        negative_studies = []

    if not negative_reports:
        negative_reports = []
    
    positive_ids = [transform_to_uuid(crg_report_id)]
    negative_ids = [transform_to_uuid(negative_id) for negative_id in negative_reports]
    #TODO remove negative samples from trial id retrieval

    query=models.RecommendQuery(
                recommend=models.RecommendInput(
                    positive=positive_ids,
                    negative=negative_ids,
                    strategy=models.RecommendStrategy.AVERAGE_VECTOR,
                )
            )
    
    #if len(trial_ids) > 0:
    #    return None
    
    """
    #TODO REMOVE TESTS#######################
    vectors = await get_vectors_by_crg_report_id(crg_report_id)
    query = np.array(vectors['default'])

    alpha = get_random_sigma("A", crg_report_id)

    np.random.seed(crg_report_id)

    direction = np.random.normal(0.0, 1.0, size=len(query))
    direction = direction / np.linalg.norm(direction)

    #pre_noise = np.random.normal(0.0, np.std(query) * alpha, size=len(query))

    #query = query * (1-alpha) + direction * alpha
    #print(query.shape)
    ########################################
    """
    
    result = await get_similar_study_by_query(query,aspect,cutoff,k,negative_studies, trial_ids, authors, user_id, return_details=return_details)

    # Check if there are any similar items in the same batch which are more similar than already retrieved existing studies
    if result.get('Relevance'):
        min_score = min(result['Relevance'])
        batch_studies = await get_similar_report_studies_internal(crg_report_id, min_score, user_id)
        
        # Create a map of existing study IDs to their positions and scores
        existing_study_map = {}
        for idx, study_id in enumerate(result.get('CRGStudyID', [])):
            existing_study_map[study_id] = {
                'index': idx,
                'score': result['Relevance'][idx]
            }
        
        for study, score in batch_studies:
            study_dict = study.dict()
            study_id = study_dict.get('CRGStudyID')
            
            # If study already exists, update with higher score
            if study_id in existing_study_map:
                existing_info = existing_study_map[study_id]
                if score > existing_info['score']:
                    # Update the existing entry with the higher score
                    result['Relevance'][existing_info['index']] = score
            else:
                # Add new study
                result['Relevance'].append(score)
                for key in result.keys():
                    if key == "Relevance":
                        continue
                    result[key].append(study_dict.get(key))
                
                # Track the new study in our map
                existing_study_map[study_id] = {
                    'index': len(result['Relevance']) - 1,
                    'score': score
                }
        
        # Reorder all results by relevance score (descending)
        if result['Relevance']:
            sorted_indices = sorted(
                range(len(result['Relevance'])), 
                key=lambda i: result['Relevance'][i], 
                reverse=True
            )
            for key in result.keys():
                result[key] = [result[key][i] for i in sorted_indices]

            # Truncate to k results if we have more
            if len(result['Relevance']) > k:
                for key in result.keys():
                    result[key] = result[key][:k]

    #print(studies)


    """
    #TODO REMOVE TESTS#######################
    np.random.seed(crg_report_id)
    alpha = get_random_sigma("A", crg_report_id)
    post_noise = np.random.uniform(0.0, alpha*2, size=len(result['Relevance'])) - alpha
    #print(alpha, post_noise)
    for i in range(0, len(result['Relevance'])):
        result['Relevance'][i] = post_noise[i] + result['Relevance'][i]

    sorted_indices = sorted(range(len(result['Relevance'])), key=lambda i: result['Relevance'][i], reverse=True)
    for key in result.keys():
        result[key] = [result[key][i] for i in sorted_indices]

    ########################################
    """

    await post_report_event(crg_report_id, Event(event_type=f"similar::studies::k::{k}", timestamp=datetime.now(timezone.utc).isoformat()), user_id)

    return result

async def get_similar_study_by_query(query, aspect: TagCategories, cutoff: str, k: int, negative_studies: List[int], trial_ids: List[str], authors:List[str], user_id: Optional[str], return_details: bool):
    
    found_study_ids = {}
    #found_study_titles = {}
    debug_map = {}

    return_details= return_details or DEBUG
    
    filters = []
    if cutoff:
        filters.append(Filter(
            must=[
                FieldCondition(key="date_entered",range=DatetimeRange(lt=datetime.fromisoformat(cutoff)))
            ]
        ))    
    
    if len(trial_ids) > 0:
        response = await get_study_id_by_trial_ids_internal(trial_ids, cutoff)
        penalty = 0.00
        if response:
            for trial_id in trial_ids:
                study_ids = response[trial_id]
                for study_id in study_ids:
                    if study_id in negative_studies:
                        continue
                    found_study_ids[study_id] = 1.00 - penalty
                    debug_map[study_id] = [{"source_id":trial_id}]
                    penalty += 0.01

    blacklist = list(found_study_ids.keys()) + negative_studies
    if len(blacklist) > 0:
            
        if len(found_study_ids.keys()) > 0:
            filters.append(
                Filter(
                    must=[
                        models.FieldCondition(
                            key="belongs_to_trial_id",
                            match=models.MatchValue(value=False)
                        )
                    ],
                )
            )
        filters.append(
                Filter(
                    must_not=[
                        models.FieldCondition(
                            key="belongs_to_study",
                            match=models.MatchAny(any=blacklist)
                        )
                    ]
                )
            )
    
    filter = models.Filter(must=filters)

    k = k - len(found_study_ids.keys())

    if k > 0:
        search_results = await search_report(query,aspect,k,filter, user=user_id)

        reranked_results = search_results.groups

        for result in reranked_results:
            for hit in result.hits:
                candidates = hit.payload['belongs_to_study']
                for item in candidates:
                    if item not in found_study_ids:
                        found_study_ids[item] = hit.score
                    info = dict(hit.payload)
                    info['score'] = hit.score
                    debug_map[item] = debug_map.get(item, []) + [info]

    if len(found_study_ids.keys()) == 0:
        return {'CRGStudyID': [] }
    all_studies = await get_studies_internal(list(found_study_ids.keys()))
    #list of dicts to dict of lists:

    #Remove this block for evaluation without authors
    scores_authors = await get_scores_authors(report_authors=authors, study_ids=list(found_study_ids.keys()), cutoff=cutoff)
    for study_id, score in scores_authors.items():
        debug_map[study_id].append({'source_id': 'author_reranking', 'score': 0.65 * score})
        found_study_ids[study_id] = min(1.00, found_study_ids[study_id] + 0.65 * score)

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

    study_persons = await get_study_persons_internal(study_ids, cutoff, normalize_names=True)
    current_persons = get_author_frequencies(report_authors)

    report_authors = set(current_persons.keys())

    result = {}
    num_report_authors = len(report_authors)
    if num_report_authors == 0:
        return {}
    for study_id, study_authors in study_persons.items():
        total_score = 0
        num_total_authors = len(study_authors) + num_report_authors
        intersection = set(study_authors) & report_authors
        for matching_author in intersection:
            if matching_author in current_persons:
                total_score += 1 / math.log(current_persons[matching_author] + 2)
        total_score = total_score / num_total_authors if num_total_authors > 0 else 0
        result[int(study_id)] = total_score

    return result

#['Asarnow RF', 'Marder SR', 'Mintz J', 'Van Putten T', 'Zimmerman KE']
#1743, 2959, 3730

@router.get("/features/authors", dependencies=[Depends(is_verified_api_call)], include_in_schema=False)
async def get_author_features(authors : List[str] = Query(...), study_ids : List[int] = Query(...), cutoff : str = Query(None)):
    data = {}
    study_persons = await get_study_persons_internal(study_ids, cutoff, normalize_names=True)
    current_person_freq = get_author_frequencies(authors)
    for study_id, study_authors in study_persons.items():
        features = build_features( study_authors, current_person_freq)
        data[study_id] = features
    return data

def build_features(study_authors, current_person_freq):
    ra = set(current_person_freq.keys()) # report_authors
    sa = set(study_authors)

    overlap = ra & sa
    num_overlap = len(overlap)

    inv_freq_sum = sum(1 / current_person_freq[a] for a in overlap) if overlap else 0
    inv_freq_sum_log = sum(1 / math.log(current_person_freq[a] + 2) for a in overlap) if overlap else 0

    num_report = len(ra)
    num_study = len(sa)
    jaccard = num_overlap / len(ra | sa) if (ra | sa) else 0

    return {
        "num_overlap": num_overlap,
        "inv_freq_sum": inv_freq_sum,
        "inv_freq_sum_log": inv_freq_sum_log,
        "num_report": num_report,
        "num_study": num_study,
        "jaccard": jaccard,
    }


@router.get("/{tag_category}/{tag_value}/related_studies", dependencies=[Depends(is_verified_api_call)], summary="Get studies related to a specific tag (intervention, outcome, ...) currently only vector-similarity search is available.", description="Retrieve studies that are related to a specific tag value (e.g., 'Placebo' for interventions) using vector similarity search based on the embedding of the tag value. The similarity search is done at runtime.")
async def get_aspect_related_studies(tag_category: TagCategories = Path(..., description="The tags category (e.g. 'interventions', 'conditions', ...)"), tag_value: str = Path(..., description="The specific tags value (e.g. 'Placebo' for interventions)"), k : int = k_query, channel = Depends(get_grpc_channel) , user_id = Depends(get_user_id)):
    embeddings = await _embed_aspect(tag_value, channel)

    aspect = tag_category
    aspect_mapping = {'interventions': 'intervention', 'conditions': 'condition', 'outcomes': 'outcome'}
    if tag_category in aspect_mapping.keys():
        aspect = aspect_mapping[tag_category]

    return await get_similar_studies_by_embedding(embeddings['embedding'], aspect, [], [], None, k, user_id, return_details=False)



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
async def analyze_embedding(input: RetrievalInputEmbedding, cutoff: str = Query(None)):
    result = await analyze(input.embeddings, input.model_id, input.basic_input.topK, input.basic_input.title, input.basic_input.abstract, input.basic_input.authors, cutoff)
    return result

async def analyze(embeddings, top_k, title, abstract, authors, cutoff):
    
    trial_id = extract_trial_id(RawReport(title=title,abstract=abstract, authors=[]))
    trial_id = [trial_id[0]] if len(trial_id) == 1 else None
    pre_result = await get_similar_studies_by_embedding(embeddings['embedding'], "default", trial_id, authors, cutoff, top_k, return_details=True)

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

    (related_studies, study_interventions, study_conditions, study_outcomes, study_participants_desc, study_design, study_reports) = await asyncio.gather(
        get_studies_internal(list(found_study_ids.keys())),
        get_study_interventions_internal(list(found_study_ids.keys())),
        get_study_conditions_internal(list(found_study_ids.keys())),
        get_study_outcomes_internal(list(found_study_ids.keys())),
        get_study_participants_internal(list(found_study_ids.keys())),
        get_study_design_internal(list(found_study_ids.keys())),
        get_study_reports_by_ids_internal(list(found_study_ids.keys()), ['CRGReportID', 'Title', 'Abstract', 'Authors'], cutoff)
    )

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

        tag_results = search_tags(embeddings[type_embedding], len(allowed_ids), tag_filter)

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

class ReportEmbedding(BaseModel):
    model_id: str
    main_embedding: List[float]
    author_embedding: Optional[List[float]]

class AspectEmbedding(BaseModel):
    model_id: str
    embedding: List[float]

@router.get("/reports/{report_id}/similar_studies", dependencies=[Depends(is_verified_api_call)], summary="")
async def similarity_search_studies_by_id(report_id: int, aspect: TagCategories = Query(TagCategories.default, description="This value is rarely needed. Just if you want to search studies based on a certain aspect."),  cutoff: str = Query(None), k : int = Query(10), negative_studies : List[int]=Query(None),negative_reports : List[int]=Query(None), return_details=False, user_id : str = Depends(get_user_id)):
    return await get_similar_studies_by_id(report_id, aspect, cutoff, k, negative_studies, negative_reports, user_id, return_details)