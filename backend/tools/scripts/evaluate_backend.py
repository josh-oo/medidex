from dotenv import load_dotenv
from tqdm import tqdm
import asyncio
import httpx
import os
import sys
import time

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue

load_dotenv()

VECTORSTORE_HOST = os.getenv("VECTORSTORE_HOST")
VECTORSTORE_PORT = os.getenv("VECTORSTORE_PORT")
BACKEND_API = os.getenv("BACKEND_API")
BACKEND_API_KEY = os.getenv("BACKEND_API_KEY")

async def wait_for_services(timeout=120):
    """Wait for backend service to be ready"""
    print("Waiting for backend service to be ready...")
    
    start_time = time.time()
    
    async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
        while time.time() - start_time < timeout:
            try:
                response = await client.get(f"{BACKEND_API}/readyz")
                if response.status_code == 200:
                    print("✅ Backend API is ready")
                    return True
            except Exception:
                pass
            
            await asyncio.sleep(5)
    
    # Timeout reached
    print(f"❌ Backend API not ready at {BACKEND_API}/readyz")
    raise TimeoutError(f"Backend service not ready after {timeout} seconds")

def evaluate_with_cutoff(cutoff, model_id):
    return asyncio.run(evaluate_with_cutoff_async(cutoff, model_id))

async def calculate_rank(result, model_id, cutoff, client):
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
        response = await client.get(BACKEND_API + f"/studies/{item}/date_entered")
        if response.status_code != 200:
            print(f"Cannot refresh vectorstore: Database API (/studies/{item}/date_entered) not reachable")
            return
        
        corresponding_study_entered = response.json()
    
        if corresponding_study_entered < cutoff:
            ground_truth_filtered.append(item)
    
    if len(ground_truth_filtered) == 1:
        
        title = result[0].payload['title']
        abstract = result[0].payload['abstract']
        
        trial_id = None
        data = {'title': title, 'abstract': abstract, 'authors': []}
        
        response = await client.post(BACKEND_API + "/processing/extract_trial_id", json=data)
        if response.status_code == 200 and response.json():
            trial_id = response.json()
        text = title + (" " + abstract) if abstract else ""

        ground_truth = ground_truth_filtered[0]
        payload = {"text": text, "main_embedding": result[0].vector['default'],"participants_embedding": result[0].vector['participants'], "author_embedding": result[0].vector['authors'], "model_id": model_id}
        params = {"cutoff":cutoff, "trial_id":trial_id, 'authors': authors}
        response = await client.post(BACKEND_API + "/similarity_search/studies", json=payload,params=params)
        predicted_studies = response.json()['CRGStudyID']

        rank = 11
        if ground_truth in predicted_studies:
            rank = predicted_studies.index(ground_truth) + 1

        return rank


async def evaluate_with_cutoff_async(cutoff, model_id):
    
    async with httpx.AsyncClient(headers={'X-API-Key': BACKEND_API_KEY}, timeout=httpx.Timeout(30.0)) as client:

        vectorstore = AsyncQdrantClient(host=VECTORSTORE_HOST, grpc_port=VECTORSTORE_PORT, prefer_grpc=True)

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

        pbar = tqdm()

        recall_at_1 = []
        recall_at_3 = []
        recall_at_10 = []

        tasks = set()

        while True:
            if tasks:
                done, pending = await asyncio.wait(tasks, timeout=0)
                for d in done:
                    rank = d.result()
                    if rank:
                        recall_at_1.append(int(rank == 1))
                        recall_at_3.append(int(rank <= 3))
                        recall_at_10.append(int(rank <= 10))
                    pbar.update(1)
                tasks = pending
            
            result, scroll_offset = await vectorstore.scroll(
                collection_name=model_id,
                scroll_filter=filter_condition,
                limit=1,
                offset=scroll_offset,
                with_vectors=True,
                with_payload=True 
            )

            tasks.add(asyncio.create_task(calculate_rank(result, model_id, cutoff, client)))
            
            if scroll_offset is None:
                break

        if tasks:
            for d in asyncio.as_completed(tasks):
                rank = await d
                if rank:
                    recall_at_1.append(int(rank == 1))
                    recall_at_3.append(int(rank <= 3))
                    recall_at_10.append(int(rank <= 10))
                pbar.update(1)

    metrics = {
        'recall_at_1_count': sum(recall_at_1),
        'recall_at_3_count': sum(recall_at_3),
        'recall_at_10_count': sum(recall_at_10),
        'total_count': len(recall_at_1)
    }

    print()
    print(f"Recall@1  {metrics['recall_at_1_count'] / metrics['total_count']} ({metrics['recall_at_1_count']}/{metrics['total_count']})")
    print(f"Recall@3  {metrics['recall_at_3_count'] / metrics['total_count']} ({metrics['recall_at_3_count']}/{metrics['total_count']})")
    print(f"Recall@10 {metrics['recall_at_10_count'] / metrics['total_count']} ({metrics['recall_at_10_count']}/{metrics['total_count']})")
    
    return metrics


def run_integration_tests():
    """Run all integration tests and verify exact metric matches using integer counts"""
    
    # Wait for services first
    try:
        asyncio.run(wait_for_services(timeout=120))
    except TimeoutError as e:
        print(f"❌ Service health check failed: {e}")
        return False
    
    # Define expected exact results (using integer counts)
    EXPECTED_RESULTS = {
        "5th update": {
            'recall_at_1_count': 157,
            'recall_at_3_count': 176,
            'recall_at_10_count': 181,
            'total_count': 191
        },
        "6th update": {
            'recall_at_1_count': 186,
            'recall_at_3_count': 206,
            'recall_at_10_count': 210,
            'total_count': 222
        },
        "7th update": {
            'recall_at_1_count': 120,
            'recall_at_3_count': 129,
            'recall_at_10_count': 135,
            'total_count': 149
        }
    }
    
    tests = [
        ("5th update", "2024-01-24 00:00:00", "josh-oo_aspect-based-embeddings-v3_6b211a8f4e27b904ab146da7d63a084c2fd94223"),
        ("6th update", "2024-07-26 00:00:00", "josh-oo_aspect-based-embeddings-v3_6b211a8f4e27b904ab146da7d63a084c2fd94223"),
        ("7th update", "2025-01-13 00:00:00", "josh-oo_aspect-based-embeddings-v3_6b211a8f4e27b904ab146da7d63a084c2fd94223"),
    ]
    
    all_passed = True
    results_summary = []
    
    for name, cutoff, model_id in tests:
        print(f"\n{'='*60}")
        print(f"Evaluate {name}")
        print('='*60)
        
        try:
            actual = evaluate_with_cutoff(cutoff, model_id)
            expected = EXPECTED_RESULTS[name]
            
            # Compare integer counts instead of floats
            matches = (
                actual['recall_at_1_count'] == expected['recall_at_1_count'] and
                actual['recall_at_3_count'] == expected['recall_at_3_count'] and
                actual['recall_at_10_count'] == expected['recall_at_10_count'] and
                actual['total_count'] == expected['total_count']
            )
            
            if matches:
                print(f"✅ {name} PASSED - Metrics match exactly")
                results_summary.append(f"✅ {name}: PASSED")
            else:
                print(f"❌ {name} FAILED - Metrics do not match")
                print(f"   Expected: R@1={expected['recall_at_1_count']}/{expected['total_count']}, R@3={expected['recall_at_3_count']}/{expected['total_count']}, R@10={expected['recall_at_10_count']}/{expected['total_count']}")
                print(f"   Actual:   R@1={actual['recall_at_1_count']}/{actual['total_count']}, R@3={actual['recall_at_3_count']}/{actual['total_count']}, R@10={actual['recall_at_10_count']}/{actual['total_count']}")
                all_passed = False
                results_summary.append(f"❌ {name}: FAILED")
                
        except Exception as e:
            print(f"❌ {name} FAILED with error: {e}")
            import traceback
            traceback.print_exc()
            all_passed = False
            results_summary.append(f"❌ {name}: ERROR - {str(e)}")
    
    # Print summary
    print(f"\n{'='*60}")
    print("INTEGRATION TEST SUMMARY")
    print('='*60)
    for result in results_summary:
        print(result)
    print(f"\nOverall: {'✅ ALL TESTS PASSED' if all_passed else '❌ SOME TESTS FAILED'}")
    
    return all_passed


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--ci":
        success = run_integration_tests()
        sys.exit(0 if success else 1)
    else:
        # Original behavior for manual testing
        print("Evaluate 5th update")
        evaluate_with_cutoff("2024-01-24 00:00:00", "josh-oo_aspect-based-embeddings-v3_6b211a8f4e27b904ab146da7d63a084c2fd94223") # 5th update
        #expected
        """
        Recall@1  0.8219895287958116 (157/191)
        Recall@3  0.9214659685863874 (176/191)
        Recall@10 0.9476439790575916 (181/191)
        """

        print("Evaluate 6th update")
        evaluate_with_cutoff("2024-07-26 00:00:00", "josh-oo_aspect-based-embeddings-v3_6b211a8f4e27b904ab146da7d63a084c2fd94223") # 6th update
        #expected
        """
        Recall@1  0.8378378378378378 (186/222)
        Recall@3  0.9279279279279279 (206/222)
        Recall@10 0.9459459459459459 (210/222)
        """

        print("Evaluate 7th update")
        evaluate_with_cutoff("2025-01-13 00:00:00", "josh-oo_aspect-based-embeddings-v3_6b211a8f4e27b904ab146da7d63a084c2fd94223") # 7th update
        #expected
        """
        Recall@1  0.8053691275167785 (120/149)
        Recall@3  0.8657718120805369 (129/149)
        Recall@10 0.9060402684563759 (135/149)
        """