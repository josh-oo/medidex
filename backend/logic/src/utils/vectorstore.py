from qdrant_client import models
from qdrant_client.http.models import PointStruct
from qdrant_client import AsyncQdrantClient
from dotenv import load_dotenv
from .embedding import _embed_report
import os
import numpy as np

from datetime import datetime, timezone

load_dotenv()

VECTORSTORE_HOST = os.getenv("VECTORSTORE_SERVICE_HOST")
VECTORSTORE_PORT = os.getenv("VECTORSTORE_SERVICE_PORT")
COLLECTION_NAME = os.getenv("VECTORSTORE_COLLECTION_NAME")

CLIENT = AsyncQdrantClient(
    host=VECTORSTORE_HOST, 
    grpc_port=VECTORSTORE_PORT, 
    prefer_grpc=True
)

def transform_to_uuid(id, tag="0000"):
    id = str(id).lower()
    missing_zeros = 12 - len(id)
    id = "0"*missing_zeros + id
    return f"00000000-{tag}-4000-a000-{id}"

def transform_to_crg_report_id(uuid):
    return int(uuid.split("-")[-1])

async def get_collections():
    return await CLIENT.get_collections()

async def get_all_saved_crg_report_ids():
    """
    Remove orphan nodes from vectorstore - delete points whose source_id 
    doesn't exist in the Meerkat database anymore.
    """
    # Get all points with their source_id from vectorstore
    scroll_result = await CLIENT.scroll(
        collection_name=COLLECTION_NAME ,
        limit=10000,  # Adjust based on your collection size
        with_payload=['source_id'],
        with_vectors=False,
    )
    
    all_points = scroll_result[0]
    offset = scroll_result[1]
    
    # Continue scrolling if there are more points
    while offset is not None:
        scroll_result = await CLIENT.scroll(
            collection_name=COLLECTION_NAME ,
            limit=10000,
            offset=offset,
            with_payload=['source_id'],
            with_vectors=False,
        )
        all_points.extend(scroll_result[0])
        offset = scroll_result[1]
    
    # Extract source_ids from vectorstore
    vectorstore_source_ids = set()
    for point in all_points:
        if point.payload and 'source_id' in point.payload:
            vectorstore_source_ids.add(point.payload['source_id'])
    
    return vectorstore_source_ids

async def link_report_to_study_ids(crg_report_id, study_ids, user):
    field = "belongs_to_study"
    if user:
        field = "temporary"
        study_ids = {user: {'belongs_to_study': study_ids}}
    await CLIENT.set_payload(
        collection_name=COLLECTION_NAME,
        payload={field: study_ids},
        points=[transform_to_uuid(crg_report_id)],
    )

async def get_vectors_by_crg_report_id(crg_report_id):
    point_id = transform_to_uuid(crg_report_id)
    result = await CLIENT.retrieve(
        collection_name=COLLECTION_NAME ,
        ids=[point_id],
        with_vectors=True,
        with_payload=False,
    )
    return result[0].vector

async def crg_reports_exist(crg_report_ids):
    point_ids = [transform_to_uuid(crg_report_id) for crg_report_id in crg_report_ids]
    result = await CLIENT.retrieve(
        collection_name=COLLECTION_NAME,
        ids=point_ids,
        with_vectors=False,
        with_payload=False,
    )
    if not result:
        return 0
    return len(result)

async def calculate_score_pairs(crg_report_ids):
    # Fetch all vectors
    point_ids = [transform_to_uuid(crg_report_id) for crg_report_id in crg_report_ids]
    results = await CLIENT.retrieve(
        collection_name=COLLECTION_NAME,
        ids=point_ids,
        with_vectors=True,
        with_payload=False,
    )
    vectors = np.array([point.vector['default'] for point in results])
    # Compute cosine similarity matrix
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    normalized = vectors / norms
    similarity_matrix = np.dot(normalized, normalized.T)
    # Return as list of (i, j, score) tuples
    pairs = []
    n = len(crg_report_ids)
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            pairs.append((crg_report_ids[i], crg_report_ids[j], float(similarity_matrix[i, j])))
    return pairs


async def delete_vectors_by_crg_report_ids(crg_report_ids):
    ids = [transform_to_uuid(crg_report_id) for crg_report_id in crg_report_ids]
    await CLIENT.delete(
        collection_name=COLLECTION_NAME ,
        points_selector=models.PointIdsList(
            points=ids,
        )
)

async def add_report_to_vectorstore(report, embedding_channel):
    title = report.Title
    abstract = report.Abstract
    authors = [item.strip() for item in report.Authors.split("//")]

    text_to_process = []
    if title:
        text_to_process.append(title)
    if abstract:
        text_to_process.append(abstract)
    text_to_process = "\n".join(text_to_process)
   
    vectors = await _embed_report(text_to_process, embedding_channel)
    #TODO maybe the batch is already deleted, then this vector should not be added

    new_id = transform_to_uuid(report.CRGReportID)
    payload = {
        'title': title,
        'abstract': abstract,
        'source_id': report.CRGReportID,
        'authors': authors,
        'date_entered': datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        'belongs_to_study': [],
        'belongs_to_trial_id': False,
        'temporary': {},
    }
    new_vectors = {"default": vectors.pop("embedding"), "authors": vectors.pop("author_embedding")}
    for key, value in vectors.items():
        new_vectors[key] = value

    new_vectors.pop("model_id")

    points = [PointStruct(id=new_id,vector=new_vectors, payload=payload)]
    await CLIENT.upsert(wait=True, collection_name=COLLECTION_NAME, points=points)

async def search_report(query,aspect,k,filter, user):
    return await CLIENT.query_points_groups(
            collection_name=COLLECTION_NAME,
            query=query,
            using=aspect,
            group_by="belongs_to_study",  # Path of the field to group by
            limit=k,  # Max amount of groups
            group_size=1,  # Max amount of points per group
            query_filter=filter,
            with_payload=["belongs_to_study", f"temporary.{user}.belongs_to_study", "title", "authors", "source_id"],
        )

async def search_tags(query, k, filter):
    return await CLIENT.query_points(
        collection_name=COLLECTION_NAME + "_tags",
        query=query,
        limit=k,
        query_filter=filter,
    )