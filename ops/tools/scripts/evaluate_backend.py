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

print("Bakcned test: ", BACKEND_API)

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

async def calculate_rank_score(report_id, cutoff, client, semaphore, fixed_k=None):

    async with semaphore:

        ks = [1, 10,100,1_000,10_000]
        if fixed_k:
            ks = [fixed_k]
        
        dt = datetime.strptime(cutoff, "%Y-%m-%d %H:%M:%S")
        exclusive_cutoff = dt - timedelta(days=1)

        response = await client.get(BACKEND_API + f"/reports/{report_id}/studies", params={"date_to": exclusive_cutoff})
        response.raise_for_status()
        ground_truth = [item['studyId'] for item in response.json()]

        rank = 10_000
        score = -1
        
        if len(ground_truth) == 1:
            ground_truth = ground_truth[0]
            for k in ks:
                params = {"cutoff":cutoff, 'k': k}
                response = await client.get(BACKEND_API + f"/reports/{report_id}/similar-studies",params=params)
                response.raise_for_status()
                result = response.json()
                predicted_studies = [item['study']['studyId'] for item in result]

                if ground_truth in predicted_studies:
                    index = predicted_studies.index(ground_truth)
                    score = result[index]['relevance']
                    rank = index + 1
                    break
            return (rank, score, report_id)
    
async def calculate_rank_score_negative_hints(report_id, cutoff, client, fixed_k=None):

    ks = [1, 10,100,1_000,10_000]
    if fixed_k:
        ks = [fixed_k]
            
    dt = datetime.strptime(cutoff, "%Y-%m-%d %H:%M:%S")
    exclusive_cutoff = dt - timedelta(days=1)

    response = await client.get(BACKEND_API + f"/reports/{report_id}/studies", params={"date_to": exclusive_cutoff})
    ground_truth = [item['studyId'] for item in response.json()]

    rank = 10_000
    score = -1

    negative_studies = []
    negative_reports = []
    
    if len(ground_truth) == 1:
        ground_truth = ground_truth[0]
        for k in ks:
            #params = {"cutoff":cutoff, 'k': k, 'negative_studies': negative_studies, 'negative_reports': negative_reports}
            params = {"cutoff":cutoff, 'k': k, 'negative_reports': negative_reports}
            response = await client.get(BACKEND_API + f"/reports/{report_id}/similar-studies",params=params)
            response.raise_for_status()
            result = response.json()
            predicted_studies = [item['study']['studyId'] for item in result]

            if ground_truth in predicted_studies:
                index = predicted_studies.index(ground_truth)
                score = result[index]['relevance']
                rank = index + 1
                break

            negative_studies.extend(predicted_studies)
            for item in result['details']:
                if isinstance(item[0]['source_id'],int):
                    negative_reports.append(item[0]['source_id'])

            
        return (rank, score, report_id)
    else:
        pass

# ...existing code...

async def evaluate_with_cutoff_async(cutoff):
    SEMAPHORE = asyncio.Semaphore(128)

    timeout = httpx.Timeout(
        read=120.0,
        connect=10.0,
        write=30.0,
        pool=30.0
    )
    limits = httpx.Limits(
        max_keepalive_connections=20,
        max_connections=50,
        keepalive_expiry=30.0
    )
    headers = {'X-API-Key': BACKEND_API_KEY}

    async with httpx.AsyncClient(headers=headers, timeout=timeout, limits=limits) as client:
        response =  await client.get(f"{BACKEND_API}/reports", params={"date_from": cutoff, "date_to": cutoff})
        response.raise_for_status()
        current_report_ids = [item['id'] for item in response.json()]

        pbar = tqdm(total=len(current_report_ids))

        recall_at_1 = []
        recall_at_3 = []
        recall_at_10 = []

        tasks = [
            asyncio.create_task(calculate_rank_score(report_id, cutoff, client, SEMAPHORE, fixed_k=10))
            for report_id in current_report_ids
        ]

        for task in asyncio.as_completed(tasks):
            result = await task
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
    
    headers = {'X-API-Key': BACKEND_API_KEY}

    async with httpx.AsyncClient(headers=headers, timeout=timeout, limits=limits) as client:

        response =  await client.get(f"{BACKEND_API}/reports", params={"date_from": cutoff, "date_to": cutoff})
        current_report_ids = [item['id'] for item in response.json()]

        ranks = []
        scores = []
        report_ids = []


        pbar = tqdm(total=len(current_report_ids))

        for item in [44161, 44779]:
            if item in current_report_ids:
                current_report_ids.remove(item)

        tasks = [
            asyncio.create_task(calculate_rank_score_negative_hints(report_id, cutoff, client))
            for report_id in current_report_ids
        ]

        for task in asyncio.as_completed(tasks):
            result = await task
            if result:
                ranks.append(result[0])
                scores.append(result[1])
                report_ids.append(result[2])
            pbar.update(1)

    print()
    index_of_most_difficult = ranks.index(max(ranks))
    print(f"Most difficult to process: {report_ids[index_of_most_difficult]}")
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
            'recall_at_1_count': 174,
            'recall_at_3_count': 185,
            'recall_at_10_count': 189,
            'total_count': 191
        },
        "6th update": {
            'recall_at_1_count': 203,
            'recall_at_3_count': 216,
            'recall_at_10_count': 217,
            'total_count': 222
        },
        "7th update": {
            'recall_at_1_count': 136,
            'recall_at_3_count': 142,
            'recall_at_10_count': 145,
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

async def test():
    async with httpx.AsyncClient(headers={'X-API-Key': BACKEND_API_KEY}) as client:
        await calculate_rank_score_negative_hints(43030, "2024-01-24 00:00:00", client)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--ci":
        success = run_integration_tests()
        sys.exit(0 if success else 1)
    else:
        
        # Original behavior for manual testing
        print("Evaluate 5th update")
        evaluate_with_cutoff("2024-01-24 00:00:00") # 5th update

        print("Evaluate 6th update")
        evaluate_with_cutoff("2024-07-26 00:00:00") # 6th update

        print("Evaluate 7th update")
        evaluate_with_cutoff("2025-01-13 00:00:00") # 7th update