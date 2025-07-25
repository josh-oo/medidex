
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
import requests
import os
import json

from tqdm import tqdm

load_dotenv()

DATABASE_HOST = os.getenv("DATABASE_HOST")
DATABASE_PORT = os.getenv("DATABASE_PORT")
VECTORSTORE_HOST = os.getenv("VECTORSTORE_HOST")
VECTORSTORE_PORT = os.getenv("VECTORSTORE_PORT")

BACKEND_API = os.getenv("BACKEND_API")
BACKEND_API_KEY = os.getenv("BACKEND_API_KEY")

def create_test_set(path, cutoff, model_id):

    if not os.path.exists(path):
        os.makedirs(path)

    params = {"cutoff":cutoff}

    session = requests.Session()
    session.headers.update({'X-API-Key': BACKEND_API_KEY})

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
    scroll_offset = None

    #response = session.get(f"http://{DATABASE_HOST}:{DATABASE_PORT}/study/tags/interventions", params={'study_ids': [35469, 36597]})
    #print("Test: ", response.text)
    with tqdm() as pbar:
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

            #print(result[0].vector)

            ground_truth = result[0].payload['belongs_to_study']
            report_id = result[0].payload['source_id']

            response = session.get(f"http://{DATABASE_HOST}:{DATABASE_PORT}/reports/{report_id}")
            if response.status_code != 200:
                print(f"Cannot refresh vectorstore: Database API (/reports/{report_id}) not reachable")
                return
            report = response.json()[0]

            ground_truth_filtered = []

            for item in ground_truth:
                response = session.get(f"http://{DATABASE_HOST}:{DATABASE_PORT}/study/{item}/date_entered")
                if response.status_code != 200:
                    print(f"Cannot refresh vectorstore: Database API (/study/{item}/date_entered) not reachable")
                    return
                study_date = response.json()

                if study_date < cutoff:
                    ground_truth_filtered.append(item)

            #only consider reports with studies added in the past
            payload = {}
            payload['topK'] = 50
            payload['model_id'] = model_id
            payload['embeddings'] = {}
            payload['embeddings']['embedding'] = result[0].vector['default']
            payload['embeddings']['intervention'] = result[0].vector['intervention']
            payload['embeddings']['condition'] = result[0].vector['condition']
            payload['embeddings']['outcome'] = result[0].vector['outcome']

            response = session.post(BACKEND_API + f"/api/v1/analyze_embedding",json=payload, params=params) 

            item = {}
            item['input'] = {}
            item['input']['title'] = report['Title']
            item['input']['abstract'] = report['Abstract']
            item['input']['authors'] = [author.strip() for author in report['Authors'].split("//")]
            item['raw_output'] = response.json()
            item['label'] = ground_truth_filtered

            with open(os.path.join(path, str(report_id) + ".json"), 'w') as json_file:
                json.dump(item, json_file, indent=4)

            if scroll_offset is None:
                break
            pbar.update(1)

print("Create test set 7th update")
create_test_set("test_set","2025-01-13 00:00:00", "josh-oo_aspect-based-embeddings-v3_6b211a8f4e27b904ab146da7d63a084c2fd94223") # 7th update

print("Create train set 6th update")
create_test_set("train_set","2024-07-26 00:00:00", "josh-oo_aspect-based-embeddings-v3_6b211a8f4e27b904ab146da7d63a084c2fd94223") # 6th update