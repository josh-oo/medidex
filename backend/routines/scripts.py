
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, MultiVectorComparator, MultiVectorConfig
from qdrant_client.models import Filter, FieldCondition, MatchValue
from qdrant_client.http.models import PointStruct
from tqdm import tqdm
import requests
import os
import re

import grpc
import embedding_pb2
import embedding_pb2_grpc

import xml.etree.ElementTree as ET

import numpy as np

load_dotenv()

MODEL_HOST = os.getenv("EMBEDDING_HOST")
MODEL_PORT = os.getenv("EMBEDDING_PORT")
DATABASE_HOST = os.getenv("DATABASE_HOST")
DATABASE_PORT = os.getenv("DATABASE_PORT")
VECTORSTORE_HOST = os.getenv("VECTORSTORE_HOST")
VECTORSTORE_PORT = os.getenv("VECTORSTORE_PORT")

MESH_DUMP_LOCATION = os.getenv("MESH_DUMP_LOCATION")

BACKEND_API = os.getenv("BACKEND_API")

def get_missing_ids(client, collection_name, ids):
    response = client.retrieve(collection_name=collection_name, ids=ids)

    existing_ids = {item.id for item in response} 
    missing_ids = [item for item in ids if item not in existing_ids]

    return missing_ids 


def calculate_report_embeddings(data, client=None, batch_size=128):
    #ids = iter(ids)

    def stream_requests(data):
        for id, item in data.items():
            test = embedding_pb2.EmbedReportRequest(id=id, text=item['texts'][0], authors=item['authors'])
            yield test
            
    channel = grpc.insecure_channel(f"{MODEL_HOST}:{MODEL_PORT}")
    stub = embedding_pb2_grpc.EmbedServiceStub(channel)

    responses = stub.GetReportEmbedding(stream_requests(data))

    all_points = []

    metadata = dict(responses.initial_metadata())

    if len(data) == 0 or client is None:
        return metadata

    collection_name = metadata['model'].replace("/", "_") + "_" + metadata['revision']

    for response in tqdm(responses, total=len(data)):
        if client is None:
            continue

        new_vectors = {"default": response.embedding.values,}
        for i, aspect in enumerate(metadata['aspects'].split(";")):
            new_vectors[aspect] = response.aspect_embeddings[i].values

        new_vectors['authors'] = response.author_embeddings.values

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
    session = requests.Session()
    session.headers.update({"Authorization": "Bearer DEBUG"})

    def check_author(author):
        return len(author.replace("?", "").strip()) > 0
    
    results = {}
    for id, title, abstract, date_entered, authors in zip(reports['CRGReportID'], reports['Title'],reports['Abstract'], reports['Dateentered'], reports['Authors']):
        title_abstract = []
        if title:
            title_abstract.append(title)
        if abstract:
            title_abstract.append(abstract)
        
        item = {}
        authors = [author.strip() for author in authors.split("//") if check_author(author)]
        trial_id = None
        data = {'title': title, 'abstract': abstract, 'authors': []}
        response = session.post(BACKEND_API + "/extract_trial_id", json=data)
        if response.status_code == 200 and response.json():
            trial_id = response.json()
        item['metadata'] = {'belongs_to_study': report_study_mapping[str(id)], 'source_id': id, "date_entered": date_entered, "authors": authors, "trial_id": trial_id}
        item['texts'] = [" ".join(title_abstract)]
        item['authors'] = authors

        vector_store_id = transform_to_uuid(id, "0000")

        results[vector_store_id] = item
    
    return results

def load_report_data():
    response = requests.get(f"http://{DATABASE_HOST}:{DATABASE_PORT}/reports/all")
    if response.status_code != 200:
        print("Cannot refresh vectorstore: Database API (/reports/all) not reachable")
        return
    all_reports = response.json()
    
    response = requests.get(f"http://{DATABASE_HOST}:{DATABASE_PORT}/mapping/report_study")
    if response.status_code != 200:
        print("Cannot refresh study embeddings: Database API (/mapping/report_study) not reachable")
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
        vector_config = {"default": VectorParams(size=model_info['dimension'], distance=Distance.COSINE), "authors":VectorParams(size=model_info['dimension'], distance=Distance.COSINE) }
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
def refresh_study_embeddings():

    client = QdrantClient(host=VECTORSTORE_HOST, grpc_port=VECTORSTORE_PORT, prefer_grpc=True)
    #client = QdrantClient(url="http://localhost:6333")

    collection_name="josh-oo_aspect-based-embeddings-v3_6b211a8f4e27b904ab146da7d63a084c2fd94223"

    response = requests.get(f"http://{DATABASE_HOST}:{DATABASE_PORT}/mapping/report_study")
    if response.status_code != 200:
        print("Cannot refresh study embeddings: Database API (/reports/all) not reachable")
        return
    
    all_reports = response.json()

    for report, studies in tqdm(all_reports.items()):
        uuid = transform_to_uuid(report, "0000")
        client.set_payload(
            collection_name=collection_name,
            payload={
                "belongs_to_study": [int(item) for item in studies],
            },
            points=[uuid],
    )
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
            test = embedding_pb2.EmbedAspectsRequest(id=id, aspects=item['texts'])
            yield test
            
    channel = grpc.insecure_channel(f"{MODEL_HOST}:{MODEL_PORT}")
    stub = embedding_pb2_grpc.EmbedServiceStub(channel)

    responses = stub.GetAspectEmbeddings(stream_requests(data))

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
    response = requests.get(f"http://{DATABASE_HOST}:{DATABASE_PORT}/tags/{tag}/all")
    if response.status_code != 200:
        print(f"Cannot refresh tag embeddings: Database API (/tags/{tag}/all) not reachable")
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

"""
def add_date_entered_info():

    client = QdrantClient(host=VECTORSTORE_HOST, grpc_port=VECTORSTORE_PORT, prefer_grpc=True)
    #client = QdrantClient(url="http://localhost:6333")

    collection_name="josh-oo_aspect-based-embeddings-v3_6b211a8f4e27b904ab146da7d63a084c2fd94223"

    response = requests.get(f"http://{DATABASE_HOST}:{DATABASE_PORT}/reports/all")
    if response.status_code != 200:
        print("Cannot refresh vectorstore: Database API (/reports/all) not reachable")
        return
    all_reports = response.json()

    for report_id, date_entered in tqdm(zip(all_reports['CRGReportID'], all_reports['Dateentered'])):
        uuid = transform_to_uuid(report_id, "0000")
        client.set_payload(
            collection_name=collection_name,
            payload={
                "date_entered": transform_date_entered(date_entered),
            },
            points=[uuid],
    )
"""

def evaluate_with_cutoff(cutoff, model_id):

    #data = {"username": BACKEND_USER, "password": BACKEND_PASSWORD,}
    #headers = {"Content-Type": "application/x-www-form-urlencoded"}

    #response = requests.post(BACKEND_API + "/login", data=data, headers=headers)

    #if response.status_code != 200:
    #    print(response)
    #    print(response.text)
    #    return
    
    session = requests.Session()
    session.headers.update({"Authorization": "Bearer DEBUG"})

    client = QdrantClient(host=VECTORSTORE_HOST, grpc_port=VECTORSTORE_PORT, prefer_grpc=True)

    filter_condition = Filter(
        must=[
            FieldCondition(
                key="date_entered",
                match=MatchValue(value=cutoff)
            )
        ]
    )

    # Pagination loop to get all points including vectors
    recall_at_1 = []
    recall_at_3 = []
    recall_at_10 = []
    scroll_offset = None

    while True:
        result, scroll_offset = client.scroll(
            collection_name=model_id,
            scroll_filter=filter_condition,
            limit=1,
            offset=scroll_offset,
            with_vectors=True,     # <-- include vectors
            with_payload=True      # <-- include payloads
        )
        #all_points.extend(result)

        ground_truth = result[0].payload['belongs_to_study']#[0]
        trial_id = None
        authors = None
        if 'trial_id' in result[0].payload:
            trial_id = result[0].payload['trial_id']
        if 'authors' in result[0].payload:
            authors = result[0].payload['authors']

        #only consider reports with studies added in the past
        ground_truth_filtered = []
        for item in ground_truth:
            response = session.get(f"http://{DATABASE_HOST}:{DATABASE_PORT}/study/{item}/date_entered")
            if response.status_code != 200:
                print(f"Cannot refresh vectorstore: Database API (/study/{item}/date_entered) not reachable")
                return
            
            corresponding_study_entered = response.json()
        
            if corresponding_study_entered < cutoff:
                ground_truth_filtered.append(item)
        
        if len(ground_truth_filtered) == 1:
            report_id = result[0].payload['source_id']
            response = session.get(f"http://{DATABASE_HOST}:{DATABASE_PORT}/reports/{report_id}")
            if response.status_code != 200:
                print(f"Cannot refresh vectorstore: Database API (/reports/{report_id}) not reachable")
                return
            abstract = response.json()[0]['Abstract']
            text = response.json()[0]['Title'] + (" " + abstract) if abstract else ""

            ground_truth = ground_truth_filtered[0]
            payload = {"text": text, "main_embedding": result[0].vector['default'],"participants_embedding": result[0].vector['intervention'], "author_embedding": result[0].vector['authors'], "model_id": model_id}
            params = {"cutoff":cutoff, "trial_id":trial_id, 'authors': authors}
            response = session.post(BACKEND_API + "/similarity_search/studies", json=payload,params=params)
            predicted_studies = response.json()['CRGStudyID']

            rank = 11
            if ground_truth in predicted_studies:
                rank = predicted_studies.index(ground_truth) + 1
            
            recall_at_1.append(1 if rank == 1 else 0)
            recall_at_3.append(1 if rank <= 3 else 0)
            recall_at_10.append(1 if rank <= 10 else 0)

            #break

            """
            if rank != 1:
                print(result[0].payload)
                for item in response.json()['debug']:
                    for hit in item['hits']:
                        print(f"{hit['payload']['source_id']} - {hit['payload']['belongs_to_study']} ({hit['score']})")
                for i, item in enumerate(response.json()['CRGStudyID']):
                    print(item, response.json()['Relevance'][i])
                #print(response.json())
                print()
            """

        if scroll_offset is None:
            break

    print(f"Recall@1  {sum(recall_at_1) / len(recall_at_1)} ({sum(recall_at_1)}/{len(recall_at_1)})" )
    print(f"Recall@3  {sum(recall_at_3) / len(recall_at_3)} ({sum(recall_at_3)}/{len(recall_at_3)})")
    print(f"Recall@10 {sum(recall_at_10) / len(recall_at_10)} ({sum(recall_at_10)}/{len(recall_at_10)})")

#refresh_vector_store()
#refresh_meerkat_tags("interventions", tag_id="0001")
#refresh_meerkat_tags("conditions", tag_id="0002")
#refresh_meerkat_tags("outcomes", tag_id="0003")
#refresh_mesh_tags()

print("Evaluate 5th update")
evaluate_with_cutoff("2024-01-24 00:00:00", "josh-oo_aspect-based-embeddings-v3_6b211a8f4e27b904ab146da7d63a084c2fd94223") # 5th update

print("Evaluate 6th update")
evaluate_with_cutoff("2024-07-26 00:00:00", "josh-oo_aspect-based-embeddings-v3_6b211a8f4e27b904ab146da7d63a084c2fd94223") # 6th update

print("Evaluate 7th update")
evaluate_with_cutoff("2025-01-13 00:00:00", "josh-oo_aspect-based-embeddings-v3_6b211a8f4e27b904ab146da7d63a084c2fd94223") # 7th update