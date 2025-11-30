from qdrant_client import models

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

async def delete_vectors_by_crg_report_ids(crg_report_ids, client, collection_name):
    ids = [transform_to_uuid(crg_report_id) for crg_report_id in crg_report_ids]
    await client.delete(
        collection_name=collection_name,
        points_selector=models.PointIdsList(
            points=ids,
        )
)
