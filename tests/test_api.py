import pytest
from fastapi.testclient import TestClient
from app.main import app, metrics
from app.buffer import search_buffer
from app.redis_client import redis_cluster

client = TestClient(app)

@pytest.fixture(autouse=True)
def reset_metrics_and_buffer():
    # Reset in-memory tracking metrics and clear buffer before each test
    metrics["cache_hits"] = 0
    metrics["cache_misses"] = 0
    metrics["cache_fails"] = 0
    metrics["total_suggest_requests"] = 0
    with search_buffer.lock:
        search_buffer.buffer.clear()
        search_buffer.accumulated_updates = 0

def test_suggest_endpoint_empty_query():
    # An empty query should return overall trending searches (which we seeded with typeahed_dataset.csv)
    response = client.get("/suggest?q=")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) <= 10
    if len(data) > 0:
        # Check that it's sorted by score descending
        scores = [item["score"] for item in data]
        assert scores == sorted(scores, reverse=True)

def test_suggest_endpoint_prefix():
    # We query with a standard prefix
    prefix = "goog"
    response = client.get(f"/suggest?q={prefix}")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    
    for item in data:
        assert item["query"].lower().startswith(prefix)
        assert "score" in item

def test_search_submission_buffering():
    # Submitting a search query should succeed and increment the buffer count
    response = client.post("/search", json={"query": "pytest testing"})
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    
    # Check that it has been buffered
    with search_buffer.lock:
        assert "pytest testing" in search_buffer.buffer
        assert search_buffer.buffer["pytest testing"] == 1
        assert search_buffer.accumulated_updates == 1

def test_cache_debug_endpoint():
    prefix = "ebay"
    response = client.get(f"/cache/debug?prefix={prefix}")
    assert response.status_code == 200
    data = response.json()
    assert data["prefix"] == prefix
    assert "selected_node" in data
    assert data["cache_status"] in ["HIT", "MISS", "FAIL"]

def test_metrics_endpoint():
    # First submit search and query suggestions to alter metrics
    client.post("/search", json={"query": "test query"})
    client.get("/suggest?q=test")
    
    response = client.get("/metrics")
    assert response.status_code == 200
    data = response.json()
    
    assert "cache_hits" in data
    assert "cache_misses" in data
    assert "cache_hit_rate" in data
    assert data["total_suggest_requests"] == 1
    assert data["buffer_accumulated_updates"] == 1
