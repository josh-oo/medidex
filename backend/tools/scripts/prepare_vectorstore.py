import os
import asyncio
import httpx
from tqdm.asyncio import tqdm
from dotenv import load_dotenv
from qdrant_client import AsyncQdrantClient, models
from qdrant_client.models import Distance, VectorParams, PointStruct
import xml.etree.ElementTree as ET

from openai import AsyncOpenAI

import re

load_dotenv()

# --- Configuration ---
BACKEND_API = os.getenv("BACKEND_API_URL")
BACKEND_API_KEY = os.getenv("BACKEND_API_KEY")
VECTORSTORE_HOST = "localhost"
VECTORSTORE_PORT = 6334
COLLECTION_NAME = "report_embeddings_medidex"
EMBEDDING_DIM = 768

MESH_DUMP_LOCATION = os.getenv("MESH_DUMP_LOCATION")

# --- Throttling Controls ---
BACKEND_SEMAPHORE = asyncio.Semaphore(4)
EMBEDDING_SEMAPHORE = asyncio.Semaphore(8)

#IMPORTANT: do not use langchain since it applies tokenization before sending it to TEI
#https://github.com/huggingface/text-embeddings-inference/issues/273
embeddings_model = AsyncOpenAI(
        base_url="https://kueq8w7uodo0c2bd.us-east-1.aws.endpoints.huggingface.cloud/v1",
        #base_url="http://localhost:8080/v1",
        api_key="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", 
)

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

def transform_to_uuid(id, tag="0000"):
    return f"00000000-{tag}-4000-a000-{str(id).lower().zfill(12)}"

#################### Tag Embeddings
async def load_meerkat_tag_data(tag, tag_id="0000"):
    headers = {"X-API-Key": BACKEND_API_KEY, "Content-Type": "application/json"}
    
    async with httpx.AsyncClient(headers=headers, timeout=60.0) as client:
        response = await client.get(f"{BACKEND_API}/{tag}")
        if response.status_code != 200:
            raise Exception("Auth or Connection Failed for initial fetch.")
        all_tags = response.json()

        result = {}
        for tag_item in all_tags:
            key = tag_item['id']
            value = tag_item['keyword']
            item = {}
            vector_store_id = transform_to_uuid(key, tag_id)
            item['metadata'] = {"tree_ids": [tag], 'source': "meerkat", 'source_id': key, 'display_name': value, "is_report": False}
            item['texts'] = [normalize_tags(value)]

            result[vector_store_id] = item
        
        return result

def load_mesh_tag_data(file_path):
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
                "is_report": False
            }

            record = {
                'metadata': metadata,
                'texts': terms
            }

            uuid = transform_to_uuid(record_id, "1000")
            result[uuid] = record

            elem.clear()  # Free memory

    return result

#################### Report Embeddings

async def fetch_report_mapping(client, report_item, all_trial_studies):
    """Parallel worker for fetching study mappings from backend."""
    resp = await client.get(f"{BACKEND_API}/reports/{report_item['CRGReportID']}/studies")
    study_data = resp.json() if resp.status_code == 200 else []
    study_ids = [s['studyId'] for s in study_data]
    
    clean_authors = [a.strip() for a in report_item['Authors'].split("//") if a.strip()]
    belongs_to_trial_id = all(s in all_trial_studies for s in study_ids) if study_ids else False
    
    return transform_to_uuid(report_item['CRGReportID']), {
        "text": f"{report_item['Title'] or ''} \n {report_item['Abstract'] or ''}".strip(),
        "metadata": {
            "is_report": True,
            "belongs_to_study": study_ids,
            "report_id": report_item['CRGReportID'],
            "date_entered": report_item['Dateentered'],
            "authors": clean_authors,
            "title": report_item['Title'],
            "abstract": report_item['Abstract'],
            "belongs_to_trial_id": belongs_to_trial_id
        }
    }


async def load_report_data_async(vectorstore, report_ids=None):
    """Fetches all reports and studies, then parallels the mapping lookups."""
    
    headers = {"X-API-Key": BACKEND_API_KEY, "Content-Type": "application/json"}
    
    async with httpx.AsyncClient(headers=headers, timeout=60.0) as client:
        print("Fetching initial report list...")
        report_params = {}
        if report_ids:
            report_params['report_ids'] = report_ids
        resp_reports = await client.get(f"{BACKEND_API}/reports", params=report_params)
        resp_studies = await client.get(f"{BACKEND_API}/trial/studies")
        
        if resp_reports.status_code != 200 or resp_studies.status_code != 200:
            raise Exception("Auth or Connection Failed for initial fetch.")
        
        
        reports = resp_reports.json()
        all_studies = resp_studies.json()

        # 4. Process Batches (Parallel Embedding Calls)
        async def report_processing(batch_reports):
            tasks = [
                fetch_report_mapping(client, r, all_studies)
                for r in batch_reports
            ]

            async with BACKEND_SEMAPHORE:
                results = await asyncio.gather(*tasks, return_exceptions=True)
            data = {k: v for item in results if isinstance(item, tuple) and item for k, v in [item]}
            await process_batch(vectorstore, data)

        batch_size = 32 
        tasks = []
        for i in range(0, len(reports), batch_size):
            batch_reports = reports[i:i + batch_size]
            tasks.append(report_processing(batch_reports))

        print(f"Embedding {len(reports)} points...")
        await tqdm.gather(*tasks, desc="Embedding & Upserting")


async def process_batch(client, data):
    """Parallel worker for embedding generation and Qdrant upsert."""
    async with EMBEDDING_SEMAPHORE:
        batch_texts = [value["text"] for _, value in data.items()]
        batch_ids = [key for key, _ in data.items()]
        if not batch_texts:
            return
        #print(batch_texts)

        # Generate embeddings
        response = await embeddings_model.embeddings.create(
            input=batch_texts,
            model=None
        )
        vectors = [data.embedding for data in response.data]

        points = [
            PointStruct(id=bid, vector=vec, payload=data[bid]["metadata"])
            for bid, vec in zip(batch_ids, vectors)
        ]

        await client.upsert(collection_name=COLLECTION_NAME, points=points)

# --- Tag Embedding Batch Upsert ---
async def process_tag_batch(client, batch_ids, tag_data):
    """Batch embedding and upsert for tag data."""
    async with EMBEDDING_SEMAPHORE:
        batch_texts = [tag_data[bid]["texts"][0] for bid in batch_ids if tag_data[bid]["texts"]]
        if not batch_texts:
            return
        response = await embeddings_model.embeddings.create(
            input=batch_texts,
            model=None
        )
        vectors = [data.embedding for data in response.data]
        points = [
            PointStruct(id=bid, vector=vec, payload=tag_data[bid]["metadata"])
            for bid, vec in zip(batch_ids, vectors)
        ]
        await client.upsert(collection_name=COLLECTION_NAME, points=points)

async def process_and_upsert():
    client = AsyncQdrantClient(host=VECTORSTORE_HOST, grpc_port=VECTORSTORE_PORT, prefer_grpc=True)

    # 1. Prepare Collection
    collections = await client.get_collections()
    if not any(c.name == COLLECTION_NAME for c in collections.collections):
        await client.create_collection(
            collection_name=COLLECTION_NAME,
            on_disk_payload=True,
            vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE)
        )

        await client.create_payload_index(
            collection_name=COLLECTION_NAME,
            field_name="is_report",
            field_schema=models.PayloadSchemaType.BOOL,
        )

        await client.create_payload_index(
            collection_name=COLLECTION_NAME,
            field_name="source",
            field_schema=models.PayloadSchemaType.KEYWORD,
        )

        await client.create_payload_index(
            collection_name=COLLECTION_NAME,
            field_name="tree_ids",
            field_schema=models.PayloadSchemaType.KEYWORD,
        )

        await client.create_payload_index(
            collection_name=COLLECTION_NAME,
            field_name="source_id",
            field_schema=models.PayloadSchemaType.UUID,
        )

        await client.create_payload_index(
            collection_name=COLLECTION_NAME,
            field_name="belongs_to_trial_id",
            field_schema=models.PayloadSchemaType.BOOL,
        )

        await client.create_payload_index(
            collection_name=COLLECTION_NAME,
            field_name="belongs_to_study",
            field_schema=models.PayloadSchemaType.KEYWORD,
        )

        await client.create_payload_index(
            collection_name=COLLECTION_NAME,
            field_name="date_entered",
            field_schema=models.PayloadSchemaType.DATETIME,
        )

        await client.create_payload_index(
            collection_name=COLLECTION_NAME,
            field_name="date_entered",
            field_schema=models.PayloadSchemaType.DATETIME,
        )

    # 2. Load Report Data (Parallel Backend Calls)
    await load_report_data_async(vectorstore=client)

    # --- Tag Embedding Upsert ---
    # Example: interventions
    for tag, tag_uuid in [("interventions", "0001"), ("conditions", "0002"), ("outcomes", "0003")]:
        tag_data = await load_meerkat_tag_data(tag, tag_id=tag_uuid)
        tag_ids = list(tag_data.keys())
        tag_batch_size = 32
        tag_tasks = []
        for i in range(0, len(tag_ids), tag_batch_size):
            batch_ids = tag_ids[i:i + tag_batch_size]
            tag_tasks.append(process_tag_batch(client, batch_ids, tag_data))
        print(f"Embedding & upserting {len(tag_ids)} {tag} tags...")
        await tqdm.gather(*tag_tasks, desc="Tag Embedding & Upserting")

    # Tag embedding mesh
    tag_data_mesh = load_mesh_tag_data(MESH_DUMP_LOCATION)
    tag_ids = list(tag_data_mesh.keys())
    tag_batch_size = 32
    tag_tasks = []
    for i in range(0, len(tag_ids), tag_batch_size):
        batch_ids = tag_ids[i:i + tag_batch_size]
        tag_tasks.append(process_tag_batch(client, batch_ids, tag_data_mesh))
    print(f"Embedding & upserting {len(tag_ids)} mesh tags...")
    await tqdm.gather(*tag_tasks, desc="Tag Embedding & Upserting")

if __name__ == "__main__":
    try:
        asyncio.run(process_and_upsert())
    except RuntimeWarning as e:
        print(f"RuntimeWarning: {e}")
    except Exception as e:
        print(f"Exception: {e}")
    finally:
        # Attempt to cancel all running tasks to avoid shutdown errors
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                tasks = [t for t in asyncio.all_tasks(loop) if not t.done()]
                for task in tasks:
                    task.cancel()
                loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
        except Exception:
            pass