
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, MultiVectorComparator, MultiVectorConfig
from qdrant_client.http.models import PointStruct
from tqdm import tqdm
import requests
import os
import re

import grpc
import embedding_pb2
import embedding_pb2_grpc

import xml.etree.ElementTree as ET

load_dotenv()

MODEL_HOST = os.getenv("EMBEDDING_HOST")
MODEL_PORT = os.getenv("EMBEDDING_PORT")
DATABASE_HOST = os.getenv("DATABASE_HOST")
DATABASE_PORT = os.getenv("DATABASE_PORT")
VECTORSTORE_HOST = os.getenv("VECTORSTORE_HOST")
VECTORSTORE_PORT = os.getenv("VECTORSTORE_PORT")

MESH_DUMP_LOCATION = os.getenv("MESH_DUMP_LOCATION")

def get_missing_ids(client, collection_name, ids):
    response = client.retrieve(collection_name=collection_name, ids=ids)

    existing_ids = {item.id for item in response} 
    missing_ids = [item for item in ids if item not in existing_ids]

    return missing_ids 


def calculate_report_embeddings(data, client=None, batch_size=128):
    #ids = iter(ids)

    def stream_requests(data):
        for id, item in data.items():
            test = embedding_pb2.EmbedRequest(id=id, text=item['texts'])
            yield test
            
    channel = grpc.insecure_channel(f"{MODEL_HOST}:{MODEL_PORT}")
    stub = embedding_pb2_grpc.EmbedServiceStub(channel)

    responses = stub.GetEmbeddingAspects(stream_requests(data))

    all_points = []

    metadata = dict(responses.initial_metadata())

    if len(data) == 0 or client is None:
        return metadata

    collection_name = metadata['model'].replace("/", "_") + "_" + metadata['revision']

    for response in tqdm(responses, total=len(data)):
        if client is None:
            continue

        new_vectors = {"default": response.embedding[0].values,}
        for i, aspect in enumerate(metadata['aspects'].split(";")):
            new_vectors[aspect] = response.aspect_embeddings[0].aspect_embeddings[i].values

        current_id = response.id#next(ids)
        payload = data[current_id]['metadata']

        all_points.append(PointStruct(id=current_id,vector=new_vectors, payload=payload))

        if len(all_points) == batch_size:
            client.upsert(wait=False, collection_name=collection_name, points=all_points)
            all_points = []

    if client and len(all_points) > 0: #upload the remaining vectors
        client.upsert(wait=False, collection_name=collection_name, points=all_points)

    return metadata

def preprocess_reports(reports, report_study_mapping):
    results = {}
    for id, title, abstract in zip(reports['CRGReportID'], reports['Title'],reports['Abstract']):
        title_abstract = []
        if title:
            title_abstract.append(title)
        if abstract:
            title_abstract.append(abstract)
        
        item = {}
        item['metadata'] = {'belongs_to_study': report_study_mapping[str(id)], 'source_id': id}
        item['texts'] = [" ".join(title_abstract)]

        vector_store_id = transform_to_uuid(id, "0000")

        results[vector_store_id ] = item
    
    return results

def load_report_data():
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

    return preprocess_reports(all_reports, report_study_mapping)


def refresh_vector_store(force_recompute_embeddings=False):

    data = load_report_data()
    all_ids = data.keys()

    client = QdrantClient(host=VECTORSTORE_HOST, grpc_port=VECTORSTORE_PORT, prefer_grpc=True)

    model_info = calculate_report_embeddings({}) 
    collection_name = model_info['model'].replace("/", "_") + "_" + model_info['revision']

    collections = client.get_collections().collections
    exists = any(c.name == collection_name for c in collections)

    points_that_need_computation = all_ids

    if not exists:
        vector_config = {"default": VectorParams(size=model_info['dimension'], distance=Distance.COSINE)}
        for aspect in model_info['aspects'].split(";"):
            vector_config[aspect] = VectorParams(size=model_info['dimension'], distance=Distance.COSINE)
        client.create_collection(
            collection_name=collection_name,
            vectors_config=vector_config,
        )
    if not force_recompute_embeddings:
        points_that_need_computation = get_missing_ids(client, collection_name, all_ids)

    relevant_data = {}
    for id in points_that_need_computation:
        relevant_data[id] = data[id]

    calculate_report_embeddings(relevant_data,client=client)

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

REMOVE_CURLY_BRACKETS = re.compile(r'{.*?}')
REMOVE_REGULAR_BRACKETS = re.compile(r'\(.*?\)')
REMOVE_SQUARED_BRACKETS = re.compile(r'\[.*?\]')

EXTRACT_NON_LATIN_BRACKETS = re.compile(r'\[([^\]]*[^\u0000-\u007F][^\]]*)\]')

def normalize_tags(example):
    non_latin = EXTRACT_NON_LATIN_BRACKETS.search(example)
    if non_latin is not None:
        return  non_latin.group(1)
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

    return example

def calculate_tag_embeddings(data, client=None, batch_size=128):

    def stream_requests(data):
        for id, item in data.items():
            test = embedding_pb2.EmbedRequest(id=id, text=item['texts'])
            yield test
            
    channel = grpc.insecure_channel(f"{MODEL_HOST}:{MODEL_PORT}")
    stub = embedding_pb2_grpc.EmbedServiceStub(channel)

    responses = stub.GetEmbedding(stream_requests(data))

    all_points = []

    metadata = dict(responses.initial_metadata())

    if len(data) == 0 or client is None:
        return metadata
    
    collection_name = metadata['model'].replace("/", "_") + "_" + metadata['revision'] + "_tags"

    for response in tqdm(responses, total=len(data)):
        current_id = response.id
        payload = data[current_id]['metadata']
        all_vectors = []
        for item in response.embedding:
            all_vectors.append(item.values)
        all_points.append(PointStruct(id=current_id,vector=all_vectors, payload=payload))

        if len(all_points) == batch_size:
            client.upsert(wait=False, collection_name=collection_name, points=all_points)
            all_points = []

    if client and len(all_points) > 0: #upload the remaining vectors
        client.upsert(wait=False, collection_name=collection_name, points=all_points)

    return metadata

def transform_to_uuid(id, tag):
    id = str(id).lower()
    missing_zeros = 12 - len(id)
    id = "0"*missing_zeros + id
    return f"00000000-{tag}-4000-a000-{id}"

def load_meerkat_tag_data(tag, tag_id="0000"):
    response = requests.get(f"http://{DATABASE_HOST}:{DATABASE_PORT}/tags/{tag}/all/")
    if response.status_code != 200:
        print(f"Cannot refresh tag embeddings: Database API (/tags/{tag}/all/) not reachable")
        return
    all_tags = response.json()

    result = {}
    for key, value in all_tags.items():
        item = {}
        vector_store_id = transform_to_uuid(key, tag_id)
        item['metadata'] = {"tree_ids": [tag], 'source': "meerkat", 'source_id': key, 'display_name': value}
        item['texts'] = [normalize_tags(value)]

        result[vector_store_id] = item
    
    return result

def refresh_all_tag_embeddings(data, force_recompute_embeddings=False):
    all_ids = data.keys()

    client = QdrantClient(host=VECTORSTORE_HOST, grpc_port=VECTORSTORE_PORT, prefer_grpc=True)

    model_info = calculate_tag_embeddings({}) 
    collection_name = model_info['model'].replace("/", "_") + "_" + model_info['revision'] + "_tags"

    collections = client.get_collections().collections
    exists = any(c.name == collection_name for c in collections)

    points_that_need_computation = all_ids
    
    if not exists:
        vector_config = VectorParams(size=model_info['dimension'], 
                                     distance=Distance.COSINE, 
                                     multivector_config=MultiVectorConfig(comparator=MultiVectorComparator.MAX_SIM),
                                     )
        client.create_collection(
            collection_name=collection_name,
            vectors_config=vector_config,
        )
    if not force_recompute_embeddings:
        points_that_need_computation = get_missing_ids(client, collection_name, all_ids)

    relevant_data = {}
    for id in points_that_need_computation:
        relevant_data[id] = data[id]

    calculate_tag_embeddings(relevant_data,client=client)

def refresh_meerkat_tags(tag, tag_id, force_recompute_embeddings=False):
    data = load_meerkat_tag_data(tag, tag_id)
    refresh_all_tag_embeddings(data,force_recompute_embeddings=force_recompute_embeddings)

def parse_large_xml(file_path):
    result = {}
    context = ET.iterparse(file_path, events=("end",))
    
    for event, elem in context:
        if elem.tag == "DescriptorRecord":
            record_id = elem.findtext('DescriptorUI')
            name_elem = elem.find('DescriptorName/String')
            name = name_elem.text if name_elem is not None else None

            tree_numbers = [
                tn.text for tn in elem.findall('TreeNumberList/TreeNumber')
                if tn is not None and tn.text
            ]

            terms = [
                term_elem.findtext('String')
                for term_elem in elem.findall('TermList/Term')
                if term_elem.findtext('String') is not None
            ]

            terms = [
                term.findtext('String')
                for concept in elem.findall('.//ConceptList/Concept')
                for term in concept.findall('TermList/Term')
                if term.find('String') is not None
            ]

            metadata = record = {
                'source': 'mesh',
                'source_id': record_id,
                'display_name': name,
                'tree_ids': tree_numbers,
            }

            record = {
                'metadata': metadata,
                'texts': terms
            }

            uuid = transform_to_uuid(record_id, "1000")
            result[uuid] = record

            elem.clear()  # Free memory

    return result

def refresh_mesh_tags(force_recompute_embeddings=False):
    data= parse_large_xml(MESH_DUMP_LOCATION)
    refresh_all_tag_embeddings(data,force_recompute_embeddings=force_recompute_embeddings)


refresh_vector_store()
refresh_meerkat_tags("interventions", tag_id="0001", force_recompute_embeddings=True)
refresh_meerkat_tags("conditions", tag_id="0002", force_recompute_embeddings=True)
refresh_meerkat_tags("outcomes", tag_id="0003", force_recompute_embeddings=True)
refresh_mesh_tags()