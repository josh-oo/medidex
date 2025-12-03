from dotenv import load_dotenv
from datetime import datetime, timedelta
from tqdm import tqdm
import asyncio
import httpx
import os
import sys
import time

load_dotenv()

BACKEND_API = os.getenv("BACKEND_API_URL")
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

async def calculate_rank_score(crg_report_id, cutoff, client, fixed_k=None):

    ks = [1, 10,100,1_000,10_000]
    if fixed_k:
        ks = [fixed_k]
    
    dt = datetime.strptime(cutoff, "%Y-%m-%d %H:%M:%S")
    exclusive_cutoff = dt - timedelta(days=1)

    response = await client.get(BACKEND_API + f"/reports/{crg_report_id}/studies", params={"date_to": exclusive_cutoff})
    ground_truth = [item['CRGStudyID'] for item in response.json()]

    rank = 10_000
    score = -1
    
    if len(ground_truth) == 1:
        ground_truth = ground_truth[0]
        for k in ks:
            params = {"cutoff":cutoff, 'k': k}
            response = await client.get(BACKEND_API + f"/reports/{crg_report_id}/similar_studies",params=params)
            predicted_studies = response.json()['CRGStudyID']

            if ground_truth in predicted_studies:
                index = predicted_studies.index(ground_truth)
                score = response.json()['Relevance'][index]
                rank = index + 1
                break
        return (rank, score)
    
async def calculate_rank_score_negative_hints(crg_report_id, cutoff, client, fixed_k=None):

    ks = [1, 10,100,1_000,10_000]
    if fixed_k:
        ks = [fixed_k]
    
    dt = datetime.strptime(cutoff, "%Y-%m-%d %H:%M:%S")
    exclusive_cutoff = dt - timedelta(days=1)

    response = await client.get(BACKEND_API + f"/reports/{crg_report_id}/studies", params={"date_to": exclusive_cutoff})
    ground_truth = [item['CRGStudyID'] for item in response.json()]

    rank = 10_000
    score = -1

    negative_samples = []
    
    if len(ground_truth) == 1:
        ground_truth = ground_truth[0]
        for k in ks:
            params = {"cutoff":cutoff, 'k': k, 'negative_samples': negative_samples}
            try:
                response = await client.get(
                    BACKEND_API + f"/reports/{crg_report_id}/similar_studies",
                    params=params,
                    timeout=120.0  # Override timeout for this specific call
                )
            except httpx.ReadTimeout:
                print(f"Timeout for report {crg_report_id}, skipping SAMPLES ",negative_samples)
                break
            predicted_studies = response.json()['CRGStudyID']

            if ground_truth in predicted_studies:
                index = predicted_studies.index(ground_truth)
                score = response.json()['Relevance'][index]
                rank = index + 1
                break
            negative_reports = await client.get(BACKEND_API + f"/studies/{predicted_studies[0]}/reports")
            new_negative_samples = [item['CRGReportID'] for item in negative_reports.json()]
            negative_samples.extend(new_negative_samples[:1])
        return (rank, score)

async def calculate_rank_score_negative_hints_(crg_report_id, cutoff, client):    
    dt = datetime.strptime(cutoff, "%Y-%m-%d %H:%M:%S")
    exclusive_cutoff = dt - timedelta(days=1)

    response = await client.get(BACKEND_API + f"/reports/{crg_report_id}/studies", params={"date_to": exclusive_cutoff})
    ground_truth = [item['CRGStudyID'] for item in response.json()]

    rank = 10_000
    score = -1

    negative_samples = []
    
    if len(ground_truth) == 1:
        ground_truth = ground_truth[0]
        while True:
            params = {"cutoff":cutoff, 'k': 10, 'negative_samples': negative_samples}
            print(crg_report_id, len(negative_samples))
            response = await client.get(BACKEND_API + f"/reports/{crg_report_id}/similar_studies",params=params)
            predicted_studies = response.json()['CRGStudyID']

            if ground_truth in predicted_studies:
                index = predicted_studies.index(ground_truth)
                score = response.json()['Relevance'][index]
                rank = len(negative_samples) + index + 1
                break
            else:
                negative_samples.extend(predicted_studies)

        return (rank, score)

async def evaluate_with_cutoff_async(cutoff):

    timeout = httpx.Timeout(
        read=20.0,
        connect=10.0,
        write=30.0,
        pool=30.0
    )

    limits = httpx.Limits(
        max_keepalive_connections=20,
        max_connections=50,
        keepalive_expiry=30.0
    )
    
    async with httpx.AsyncClient(headers={'X-API-Key': BACKEND_API_KEY}, timeout=timeout, limits=limits) as client:

        response =  await client.get(f"{BACKEND_API}/reports", params={"date_from": cutoff, "date_to": cutoff})
        current_crg_report_ids = [item['CRGReportID'] for item in response.json()]

        pbar = tqdm(total=len(current_crg_report_ids))

        recall_at_1 = []
        recall_at_3 = []
        recall_at_10 = []

        tasks = set()

        for crg_report_id in current_crg_report_ids:
            if tasks:
                done, pending = await asyncio.wait(tasks, timeout=0)
                for d in done:
                    result = d.result()
                    if result:
                        rank = result[0]
                        recall_at_1.append(int(rank == 1))
                        recall_at_3.append(int(rank <= 3))
                        recall_at_10.append(int(rank <= 10))
                    pbar.update(1)
                tasks = pending

            tasks.add(asyncio.create_task(calculate_rank_score(crg_report_id, cutoff, client, fixed_k=10)))

        if tasks:
            for d in asyncio.as_completed(tasks):
                result = await d
                if result:
                    rank = result[0]
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

def evaluate_with_cutoff(cutoff):
    return asyncio.run(evaluate_with_cutoff_async(cutoff))

async def evaluate_with_cutoff_async_(cutoff):

    timeout = httpx.Timeout(
        read=20.0,
        connect=10.0,
        write=30.0,
        pool=30.0
    )

    limits = httpx.Limits(
        max_keepalive_connections=20,
        max_connections=50,
        keepalive_expiry=30.0
    )
    
    async with httpx.AsyncClient(headers={'X-API-Key': BACKEND_API_KEY}, timeout=timeout, limits=limits) as client:

        response =  await client.get(f"{BACKEND_API}/reports", params={"date_from": cutoff, "date_to": cutoff})
        current_crg_report_ids = [item['CRGReportID'] for item in response.json()]

        pbar = tqdm(total=len(current_crg_report_ids))

        tasks = set()

        ranks = []
        scores = []

        for crg_report_id in current_crg_report_ids:
            if tasks:
                done, pending = await asyncio.wait(tasks, timeout=0)
                for d in done:
                    result = d.result()
                    if result:
                        ranks.append(result[0])
                        scores.append(result[1])
                    pbar.update(1)
                tasks = pending

            tasks.add(asyncio.create_task(calculate_rank_score_negative_hints(crg_report_id, cutoff, client)))

        if tasks:
            for d in asyncio.as_completed(tasks):
                result = await d
                if result:
                    ranks.append(result[0])
                    scores.append(result[1])
                pbar.update(1)

    print()
    print(f"Total studies visited {sum(ranks)}")
    print(f"Lowest rank for positive study {max(ranks)}")
    print(f"Lowest score for positive study {min(scores)}")

def evaluate_with_cutoff_(cutoff):
    return asyncio.run(evaluate_with_cutoff_async_(cutoff))

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
            'recall_at_1_count': 158,
            'recall_at_3_count': 176,
            'recall_at_10_count': 181,
            'total_count': 191
        },
        "6th update": {
            'recall_at_1_count': 188,#TODO check why did it increase from 186 to 187
            'recall_at_3_count': 206,
            'recall_at_10_count': 210,
            'total_count': 222
        },
        "7th update": {
            'recall_at_1_count': 120,#TODO check why did it decrease from 120 to 119
            'recall_at_3_count': 129,
            'recall_at_10_count': 135,
            'total_count': 149
        }
    }
    
    tests = [
        ("5th update", "2024-01-24 00:00:00"),
        ("6th update", "2024-07-26 00:00:00"),
        ("7th update", "2025-01-13 00:00:00"),
    ]
    
    all_passed = True
    results_summary = []
    
    for name, cutoff in tests:
        print(f"\n{'='*60}")
        print(f"Evaluate {name}")
        print('='*60)
        
        try:
            actual = evaluate_with_cutoff(cutoff)
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
        #evaluate_with_cutoff_("2024-01-24 00:00:00")
        # Original behavior for manual testing
        print("Evaluate 5th update")
        evaluate_with_cutoff("2024-01-24 00:00:00") # 5th update

        print("Evaluate 6th update")
        evaluate_with_cutoff("2024-07-26 00:00:00") # 6th update

        print("Evaluate 7th update")
        evaluate_with_cutoff("2025-01-13 00:00:00") # 7th update