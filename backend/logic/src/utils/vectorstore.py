from qdrant_client import models
from qdrant_client.http.models import PointStruct
from .embedding import _embed_report

from datetime import datetime, timezone

def transform_to_uuid(id, tag="0000"):
    id = str(id).lower()
    missing_zeros = 12 - len(id)
    id = "0"*missing_zeros + id
    return f"00000000-{tag}-4000-a000-{id}"

async def get_vectors_by_crg_report_id(crg_report_id, client, collection_name):
    point_id = transform_to_uuid(crg_report_id)
    result = await client.retrieve(
        collection_name=collection_name,
        ids=[point_id],
        with_vectors=True,
        with_payload=False,
    )
    return result[0].vector

async def crg_report_exists(crg_report_id, client, collection_name):
    point_id = transform_to_uuid(crg_report_id)
    result = await client.retrieve(
        collection_name=collection_name,
        ids=[point_id],
        with_vectors=False,
        with_payload=False,
    )
    if result:
        return True
    return False

async def delete_vectors_by_crg_report_ids(crg_report_ids, client, collection_name):
    ids = [transform_to_uuid(crg_report_id) for crg_report_id in crg_report_ids]
    await client.delete(
        collection_name=collection_name,
        points_selector=models.PointIdsList(
            points=ids,
        )
)

async def add_report_to_vectorstore(report, embedding_channel, client, collection_name):
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

    new_id = transform_to_uuid(report.CRGReportID)
    payload = {
        'title': title,
        'abstract': abstract,
        'source_id': report.CRGReportID,
        'authors': authors,
        'date_entered': datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        'belongs_to_study': [],
        'belongs_to_trial_id': False,
    }
    new_vectors = {"default": vectors.pop("embedding"), "authors": vectors.pop("author_embedding")}
    for key, value in vectors.items():
        new_vectors[key] = value

    new_vectors.pop("model_id")

    points = [PointStruct(id=new_id,vector=new_vectors, payload=payload)]
    await client.upsert(wait=True, collection_name=collection_name, points=points)