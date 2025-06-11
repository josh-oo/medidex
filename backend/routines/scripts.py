
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, Batch
from qdrant_client.http.models import PointStruct
from tqdm import tqdm
import requests
import os
import re

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

def calculate_report_embeddings(texts, ids, client=None, report_study_mapping=None, batch_size=128):
    ids = iter(ids)

    def stream_requests(texts):
        for text in texts:
            test = embedding_pb2.EmbedRequest(text=text)
            yield test
            
    channel = grpc.insecure_channel(f"{MODEL_HOST}:{MODEL_PORT}")
    stub = embedding_pb2_grpc.EmbedServiceStub(channel)

    responses = stub.GetEmbeddingAspects(stream_requests(texts))

    all_points = []

    metadata = dict(responses.initial_metadata())
    collection_name = metadata['model'].replace("/", "_") + "_" + metadata['revision']

    for response in tqdm(responses, total=len(texts)):
        if client is None:
            continue

        new_vectors = {"default": response.embedding.values,}
        for i, aspect in enumerate(metadata['aspects'].split(";")):
            new_vectors[aspect] = response.aspect_embeddings[i].values

        current_id = next(ids)
        payload = {"type": "report"}
        payload = {"belongs_to_study": report_study_mapping[str(current_id)]}
        all_points.append(PointStruct(id=current_id,vector=new_vectors, payload=payload))

        if len(all_points) == batch_size:
            client.upsert(wait=False, collection_name=collection_name, points=all_points)
            all_points = []

    if client and len(all_points) > 0: #upload the remaining vectors
        client.upsert(wait=False, collection_name=collection_name, points=all_points)

    return metadata

def get_missing_ids(client, collection_name, ids):
    response = client.retrieve(collection_name=collection_name, ids=ids)

    existing_ids = {item.id for item in response} 
    missing_ids = [item for item in ids if item not in existing_ids]

    return missing_ids 

def preprocess_reports(reports):
    texts = []
    ids = []
    for id, title, abstract in zip(reports['CRGReportID'], reports['Title'],reports['Abstract']):
        ids.append(id)
        title_abstract = []
        if title:
            title_abstract.append(title)
        if abstract:
            title_abstract.append(abstract)
        texts.append(" ".join(title_abstract))
    
    return texts, ids


def refresh_vector_store(force_recompute_embeddings=False):

    response = requests.get(f"http://{DATABASE_HOST}:{DATABASE_PORT}/reports/all/")
    if response.status_code != 200:
        print("Cannot refresh vectorstore: Database API (/reports/all/) not reachable")
        return
    all_reports = response.json()
    
    response = requests.get(f"http://{DATABASE_HOST}:{DATABASE_PORT}/mapping/report_study/")
    if response.status_code != 200:
        print("Cannot refresh study embeddings: Database API (/mapping/report_study/) not reachable")
        return
    report_study_mapping = response.json()

    texts, ids = preprocess_reports(all_reports)

    client = QdrantClient(host=VECTORSTORE_HOST, grpc_port=VECTORSTORE_PORT, prefer_grpc=True)

    model_info = calculate_report_embeddings(['Information Request'], [-1]) 
    collection_name = model_info['model'].replace("/", "_") + "_" + model_info['revision']

    collections = client.get_collections().collections
    exists = any(c.name == collection_name for c in collections)

    points_that_need_computation = ids

    if not exists:
        vector_config = {"default": VectorParams(size=model_info['dimension'], distance=Distance.COSINE)}
        for aspect in model_info['aspects'].split(";"):
            vector_config[aspect] = VectorParams(size=model_info['dimension'], distance=Distance.COSINE)
        client.create_collection(
            collection_name=collection_name,
            vectors_config=vector_config,
        )
    if not force_recompute_embeddings:
        points_that_need_computation = get_missing_ids(client, collection_name, ids)

    relevant_ids = []
    relevant_texts = []
    for id in points_that_need_computation:
        index = ids.index(id)
        relevant_ids.append(id)
        relevant_texts.append(texts[index])

    calculate_report_embeddings(relevant_texts, relevant_ids,client=client,report_study_mapping=report_study_mapping)

"""
def update_type():
    client = QdrantClient(host=VECTORSTORE_HOST, grpc_port=VECTORSTORE_PORT, prefer_grpc=True)

    collection_name="josh-oo_aspect-based-embeddings-v3_6b211a8f4e27b904ab146da7d63a084c2fd94223"

    all_point_ids = []

    # Scroll through the collection to retrieve all point IDs
    scroll_results, next_offset = client.scroll(collection_name=collection_name, limit=100)
    all_point_ids.extend([point.id for point in scroll_results])
    while next_offset:
        scroll_results, next_offset = client.scroll(collection_name=collection_name, limit=100, offset=next_offset)
        all_point_ids.extend([point.id for point in scroll_results])

    client.overwrite_payload(
        collection_name=collection_name,
        payload={
            "type": "report",
        },
        points=all_point_ids,
    )

def refresh_study_embeddings():

    client = QdrantClient(host=VECTORSTORE_HOST, grpc_port=VECTORSTORE_PORT, prefer_grpc=True)
    #client = QdrantClient(url="http://localhost:6333")

    collection_name="josh-oo_aspect-based-embeddings-v3_6b211a8f4e27b904ab146da7d63a084c2fd94223"

    response = requests.get(DATABASE_BACKEND + "/mapping/report_study/")
    if response.status_code != 200:
        print("Cannot refresh study embeddings: Database API (/reports/all/) not reachable")
        return
    
    all_reports = response.json()

    for report, studies in tqdm(all_reports.items()):
        client.overwrite_payload(
            collection_name=collection_name,
            payload={
                "type": "report",
                "belongs_to_study": [int(item) for item in studies],
            },
            points=[int(report)],
    )
    print(all_reports)
"""

def preprocess_tags(tag_set, prefix=""):

    REMOVE_CURLY_BRACKETS = re.compile(r'{.*?}')
    REMOVE_REGULAR_BRACKETS = re.compile(r'\(.*?\)')
    REMOVE_SQUARED_BRACKETS = re.compile(r'\[.*?\]')

    EXTRACT_NON_LATIN_BRACKETS = re.compile(r'\[([^\]]*[^\u0000-\u007F][^\]]*)\]')

    output = {}

    for key, value in tag_set.items():
        example = str(value)
        non_latin = EXTRACT_NON_LATIN_BRACKETS.search(example)
        if non_latin is not None:
            output[prefix + key] = non_latin.group(1)
            continue
        example = REMOVE_CURLY_BRACKETS.sub('', example)
        example = REMOVE_REGULAR_BRACKETS.sub('',example)
        example = REMOVE_SQUARED_BRACKETS.sub('',example)
        example = example.replace("*", "")

        example = example.replace("Aspect -", "")
        example = example.replace("Route -", "")
        example = example.replace("Media -", "")
        example = example.replace("Setting -", "")
        example = example.replace("Focus -", "")
        example = example.replace("Form -", "")
        example = example.replace("Media Method -", "")

        example = example.replace("A -", "")
        example = example.replace("B -", "")
        example = example.replace("C -", "")
        example = example.replace("D -", "")
        example = example.replace("E -", "")

        example = " ".join(example.split()).strip().lower()

        output[prefix+key] = example

    return output

def calculate_tag_embeddings(texts, ids, client=None, type=None, batch_size=128):
    ids = iter(ids)

    def stream_requests(texts):
        for text in texts:
            test = embedding_pb2.EmbedRequest(text=text)
            yield test
            
    channel = grpc.insecure_channel(f"{MODEL_HOST}:{MODEL_PORT}")
    stub = embedding_pb2_grpc.EmbedServiceStub(channel)

    responses = stub.GetEmbedding(stream_requests(texts))

    all_points = []

    metadata = dict(responses.initial_metadata())
    collection_name = metadata['model'].replace("/", "_") + "_" + metadata['revision'] + "_tags"

    for response in tqdm(responses, total=len(texts)):
        if client is None:
            continue

        current_id = next(ids)
        payload = {"type": type}
        all_points.append(PointStruct(id=current_id,vector=response.embedding.values, payload=payload))

        if len(all_points) == batch_size:
            client.upsert(wait=False, collection_name=collection_name, points=all_points)
            all_points = []

    if client and len(all_points) > 0: #upload the remaining vectors
        client.upsert(wait=False, collection_name=collection_name, points=all_points)

    return metadata

def transform_to_uuid(id, tag):
    id = str(id)
    missing_zeros = 12 - len(id)
    id = "0"*missing_zeros + id
    return f"00000000-{tag}-4000-a000-{id}"

def refresh_all_tag_embeddings(tag, tag_id="0000", force_recompute_embeddings=False):
    response = requests.get(f"http://{DATABASE_HOST}:{DATABASE_PORT}/tags/{tag}/all/")
    if response.status_code != 200:
        print(f"Cannot refresh tag embeddings: Database API (/tags/{tag}/all/) not reachable")
        return
    all_tags = response.json()
    all_tags = preprocess_tags(all_tags)

    client = QdrantClient(host=VECTORSTORE_HOST, grpc_port=VECTORSTORE_PORT, prefer_grpc=True)

    model_info = calculate_tag_embeddings(['Information Request'], [-1]) 
    collection_name = model_info['model'].replace("/", "_") + "_" + model_info['revision'] + "_tags"

    collections = client.get_collections().collections
    exists = any(c.name == collection_name for c in collections)

    ids = [transform_to_uuid(id, tag_id) for id in all_tags.keys()]
    texts = list(all_tags.values())

    points_that_need_computation = ids
    
    if not exists:
        vector_config = VectorParams(size=model_info['dimension'], distance=Distance.COSINE)
        client.create_collection(
            collection_name=collection_name,
            vectors_config=vector_config,
        )
    if not force_recompute_embeddings:
        points_that_need_computation = get_missing_ids(client, collection_name, ids)

    relevant_ids = []
    relevant_texts = []
    for id in points_that_need_computation:
        index = ids.index(id)
        relevant_ids.append(id)
        relevant_texts.append(texts[index])

    calculate_tag_embeddings(relevant_texts, relevant_ids,client=client,type=tag)


refresh_vector_store()
refresh_all_tag_embeddings("interventions", tag_id="0001")
refresh_all_tag_embeddings("conditions", tag_id="0002")
refresh_all_tag_embeddings("outcomes", tag_id="0003")
#refresh_study_embeddings()
#refresh_vector_store(force_recomput_embeddings=False)