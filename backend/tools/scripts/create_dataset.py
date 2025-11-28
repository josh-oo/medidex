
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
import requests
import os
import json

from tqdm import tqdm

load_dotenv()

VECTORSTORE_HOST = os.getenv("VECTORSTORE_SERVICE_HOST")
VECTORSTORE_PORT = os.getenv("VECTORSTORE_SERVICE_PORT")

BACKEND_API = os.getenv("BACKEND_API_URL")
BACKEND_API_KEY = os.getenv("BACKEND_API_KEY")

def create_test_set(path, cutoff, model_id, only_single_report_studies=False):

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

            ground_truth = result[0].payload['belongs_to_study']
            report_id = result[0].payload['source_id']
            title = result[0].payload['title']
            abstract = result[0].payload['abstract']
            authors = result[0].payload['authors']

            response = session.get(BACKEND_API + f"/reports/{report_id}")
            if response.status_code != 200:
                print(f"Cannot refresh vectorstore: Database API (/reports/{report_id}) not reachable")
                return
            report = response.json()[0]

            ground_truth_filtered = []

            for item in ground_truth:
                response = session.get(BACKEND_API + f"/studies/{item}/date_entered")
                if response.status_code != 200:
                    print(f"Cannot refresh vectorstore: Database API (/studies/{item}/date_entered) not reachable")
                    return
                study_date = response.json()

                if study_date < cutoff:
                    ground_truth_filtered.append(item)

            item = {}

            if only_single_report_studies:
                if len(ground_truth_filtered) != 0 or len(ground_truth) != 1:
                    if scroll_offset is None:
                        break
                    continue
                candidate_study_id = ground_truth[0]
                #check if the study only has one report
                response = session.get(BACKEND_API + f"/studies/reports", params={'study_ids': [candidate_study_id], 'fields': ['CRGReportID']})
                if len(response.json()[str(candidate_study_id)]) != 1:
                    if scroll_offset is None:
                        break
                    continue

                item['additional_target_data'] = {}
            
                response = session.get(BACKEND_API + f"/studies", params={'study_ids': [candidate_study_id]})
                related_studies = response.json()

                item['additional_target_data']['countries'] = [country.strip() for country in related_studies['Countries'][0].split("//")] if related_studies['Countries'][0] else None
                item['additional_target_data']['duration'] = [duration.strip() for duration in related_studies['Duration'][0].split("//")] if related_studies['Duration'][0] else None
                item['additional_target_data']['participants_num'] = [p_num.strip() for p_num in related_studies['NumberParticipants'][0].split("//")] if related_studies['NumberParticipants'][0] else None

                response = session.get(BACKEND_API + f"/studies/interventions", params={'study_ids': [candidate_study_id]})
                item['additional_target_data']['assigned_interventions'] = [item['Description'] for item in response.json().get(str(candidate_study_id), [])]
                response = session.get(BACKEND_API + f"/studies/conditions", params={'study_ids': [candidate_study_id]})
                item['additional_target_data']['assigned_conditions'] = [item['Description'] for item in response.json().get(str(candidate_study_id), [])]
                response = session.get(BACKEND_API + f"/studies/outcomes", params={'study_ids': [candidate_study_id]})
                item['additional_target_data']['assigned_outcomes'] = [item['Description'] for item in response.json().get(str(candidate_study_id), [])]
                
                response = session.get(BACKEND_API + f"/studies/participants", params={'study_ids': [candidate_study_id]})
                item['additional_target_data']['participants_desc'] = response.json().get(str(candidate_study_id), [])
                response = session.get(BACKEND_API + f"/studies/design", params={'study_ids': [candidate_study_id]})
                item['additional_target_data']['study_design'] = response.json().get(str(candidate_study_id), [])

            #only consider reports with studies added in the past
            payload = {}
            payload['basic_input'] = {'title': title, 'abstract': abstract, 'authors': authors, 'topK': 50}
            payload['model_id'] = model_id
            payload['embeddings'] = {}
            payload['embeddings']['embedding'] = result[0].vector['default']
            payload['embeddings']['intervention'] = result[0].vector['intervention']
            payload['embeddings']['condition'] = result[0].vector['condition']
            payload['embeddings']['outcome'] = result[0].vector['outcome']

            response = session.post(BACKEND_API + f"/processing/analyze_embedding",json=payload, params=params) 

            item['input'] = {}
            item['input']['title'] = report['Title']
            item['input']['abstract'] = report['Abstract']
            item['input']['authors'] = [author.strip() for author in report['Authors'].split("//")]
            item['raw_output'] = response.json()
            item['label'] = ground_truth_filtered

            with open(os.path.join(path, str(report_id) + ".json"), 'w') as json_file:
                json.dump(item, json_file, indent=4)

            pbar.update(1)
            if scroll_offset is None:
                break

print("Create test set 7th update")
create_test_set("test_set","2025-01-13 00:00:00", "josh-oo_aspect-based-embeddings-v3_6b211a8f4e27b904ab146da7d63a084c2fd94223")#, only_single_report_studies=True) # 7th update

print("Create train set 6th update")
create_test_set("train_set","2024-07-26 00:00:00", "josh-oo_aspect-based-embeddings-v3_6b211a8f4e27b904ab146da7d63a084c2fd94223")#, only_single_report_studies=True) # 6th update