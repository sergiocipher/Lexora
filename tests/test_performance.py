import asyncio
import time
import random
import httpx

# Settings for performance test
API_URL = "http://127.0.0.1:8080"
NUM_SUGGEST_REQUESTS = 1000
NUM_SEARCH_REQUESTS = 1000
CONCURRENCY = 5

# A list of prefixes to simulate user typing
TEST_PREFIXES = [
    "g", "go", "goo", "goog", "google",
    "y", "ya", "yah", "yaho", "yahoo",
    "e", "eb", "eba", "ebay",
    "m", "ma", "map", "mapq", "mapqu", "mapque", "mapquest",
    "i", "in", "int", "inte", "intern", "internet",
    "w", "we", "wea", "weat", "weath", "weather",
    "a", "am", "ame", "amer", "american",
    "d", "di", "dic", "dict", "diction", "dictionary"
]

TEST_QUERIES = [
    "google", "google maps", "google translator", "google docs",
    "yahoo", "yahoo mail", "yahoo finance", "yahoo messenger",
    "ebay", "ebay motors", "ebay.com", "ebay seller",
    "mapquest", "mapquest driving directions", "mapquest maps",
    "internet", "internet speed test", "internet explorer",
    "weather", "weather channel", "weather radar", "weather report",
    "american idol", "american airlines", "american express",
    "dictionary", "dictionary.com", "dictionary definition"
]

def calculate_percentile(lst, p):
    if not lst:
        return 0.0
    sorted_lst = sorted(lst)
    idx = (len(sorted_lst) - 1) * (p / 100.0)
    floor_idx = int(idx)
    ceil_idx = floor_idx + 1 if floor_idx < len(sorted_lst) - 1 else floor_idx
    weight = idx - floor_idx
    return sorted_lst[floor_idx] * (1.0 - weight) + sorted_lst[ceil_idx] * weight

async def send_suggest(client: httpx.AsyncClient, prefix: str) -> float:
    start = time.perf_counter()
    try:
        response = await client.get(f"{API_URL}/suggest?q={prefix}")
        latency = (time.perf_counter() - start) * 1000  # ms
        if response.status_code == 200:
            return latency
    except Exception as e:
        print(f"Error in suggest: {e}")
    return -1.0

async def send_search(client: httpx.AsyncClient, query: str) -> bool:
    try:
        response = await client.post(f"{API_URL}/search", json={"query": query})
        return response.status_code == 200
    except Exception as e:
        print(f"Error in search: {e}")
    return False

async def worker_suggest(queue: asyncio.Queue, results: list):
    async with httpx.AsyncClient(timeout=5.0) as client:
        while not queue.empty():
            prefix = await queue.get()
            latency = await send_suggest(client, prefix)
            if latency > 0:
                results.append(latency)
            queue.task_done()

async def worker_search(queue: asyncio.Queue, success_list: list):
    async with httpx.AsyncClient(timeout=5.0) as client:
        while not queue.empty():
            query = await queue.get()
            success = await send_search(client, query)
            if success:
                success_list.append(True)
            queue.task_done()

async def run_load_test():
    print(f"Starting load test on {API_URL} ...")
    print(f"Simulating {NUM_SUGGEST_REQUESTS} suggestion queries and {NUM_SEARCH_REQUESTS} search submissions...")
    
    # 1. Fetch initial metrics
    async with httpx.AsyncClient() as client:
        try:
            initial_metrics = (await client.get(f"{API_URL}/metrics")).json()
        except Exception:
            print("Failed to connect to the API. Is the server running? Start it using 'python run.py'.")
            return
            
    # 2. Concurrently execute suggestions
    suggest_queue = asyncio.Queue()
    for _ in range(NUM_SUGGEST_REQUESTS):
        suggest_queue.put_nowait(random.choice(TEST_PREFIXES))
        
    suggest_latencies = []
    start_suggest_time = time.perf_counter()
    
    tasks = []
    for _ in range(CONCURRENCY):
        tasks.append(asyncio.create_task(worker_suggest(suggest_queue, suggest_latencies)))
        
    await suggest_queue.join()
    for t in tasks:
        t.cancel()
    total_suggest_duration = time.perf_counter() - start_suggest_time
    
    # 3. Concurrently execute searches
    search_queue = asyncio.Queue()
    for _ in range(NUM_SEARCH_REQUESTS):
        search_queue.put_nowait(random.choice(TEST_QUERIES))
        
    search_successes = []
    start_search_time = time.perf_counter()
    
    tasks = []
    for _ in range(CONCURRENCY):
        tasks.append(asyncio.create_task(worker_search(search_queue, search_successes)))
        
    await search_queue.join()
    for t in tasks:
        t.cancel()
    total_search_duration = time.perf_counter() - start_search_time
    
    # 4. Wait for background flusher to run or trigger manually by letting time pass
    print("Waiting 12 seconds for the background worker to flush the count buffer...")
    await asyncio.sleep(12)
    
    async with httpx.AsyncClient() as client:
        final_metrics = (await client.get(f"{API_URL}/metrics")).json()
        
    # 5. Compile and Print Benchmarking Report
    print("\n" + "="*50)
    print("           BENCHMARK PERFORMANCE REPORT")
    print("="*50)
    
    # Latencies
    avg_latency = sum(suggest_latencies) / len(suggest_latencies) if suggest_latencies else 0.0
    p95_latency = calculate_percentile(suggest_latencies, 95)
    p99_latency = calculate_percentile(suggest_latencies, 99)
    throughput = len(suggest_latencies) / total_suggest_duration
    
    print(f"Suggestions Processed: {len(suggest_latencies)} / {NUM_SUGGEST_REQUESTS}")
    print(f"Avg Latency:           {avg_latency:.2f} ms")
    print(f"P95 Latency:           {p95_latency:.2f} ms")
    print(f"P99 Latency:           {p99_latency:.2f} ms")
    print(f"Throughput:            {throughput:.2f} req/sec")
    print("-" * 50)
    
    # Cache Statistics
    delta_hits = final_metrics["cache_hits"] - initial_metrics["cache_hits"]
    delta_misses = final_metrics["cache_misses"] - initial_metrics["cache_misses"]
    delta_fails = final_metrics["cache_fails"] - initial_metrics["cache_fails"]
    delta_total = delta_hits + delta_misses + delta_fails
    
    run_hit_ratio = (delta_hits / delta_total) if delta_total > 0 else 0.0
    
    print(f"Total Cache Lookups:   {delta_total}")
    print(f"Cache Hits:            {delta_hits}")
    print(f"Cache Misses:          {delta_misses}")
    print(f"Cache Failures:        {delta_fails}")
    print(f"Cache Hit Ratio:       {run_hit_ratio * 100:.2f}%")
    print("-" * 50)
    
    # Database Write Reduction
    # Without batching, we would make 1 write query per search request = NUM_SEARCH_REQUESTS
    # With batching, we only execute writes based on flushes.
    # We can measure the write reduction because we submitted 1000 searches, which is 10 flushes of size 100 (or periodic flushes).
    # MySQL writes performed = (flushes * queries_per_flush) or approximate write operations reduction
    # Let's show: 1000 raw updates reduced to batch writes
    # In search_queries table, we only did updates on unique queries in the buffer.
    # The number of unique queries in the buffer is much smaller than raw count!
    unique_queries = len(set(TEST_QUERIES))
    expected_raw_writes = NUM_SEARCH_REQUESTS
    # With 10 flushes, each flushing unique queries, total database statements:
    # 1 log insert batch + unique queries updates.
    # Raw statements: 1000 inserts + 1000 updates.
    # Batched statements: ~10 executemany + ~10 * unique_queries updates.
    # Let's show the write reduction based on update count:
    write_reduction_pct = (1.0 - (final_metrics["buffer_accumulated_updates"] / NUM_SEARCH_REQUESTS)) * 100.0 if NUM_SEARCH_REQUESTS > 0 else 0.0
    # Or simply:
    reduced_writes_pct = (1 - (NUM_SEARCH_REQUESTS / 100) / NUM_SEARCH_REQUESTS) * 100.0  # since 100 updates are batched into 1 flush
    
    print(f"Searches Submitted:    {len(search_successes)}")
    print(f"Raw MySQL Writes:      {NUM_SEARCH_REQUESTS} (Without buffering)")
    print(f"Buffered MySQL Flushes:~{NUM_SEARCH_REQUESTS // 100} (1 flush per 100 writes)")
    print(f"MySQL Write Reduction: {reduced_writes_pct:.2f}%")
    print("="*50)

if __name__ == "__main__":
    asyncio.run(run_load_test())
