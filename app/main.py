import os
import logging
import asyncio
from pathlib import Path
from contextlib import asynccontextmanager
from typing import List, Dict, Any

from fastapi import FastAPI, Depends, Query, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.config import config
from app.database import get_db
from app.models import SearchQuery
from app.schemas import SearchRequest, SuggestionResponse, CacheDebugResponse, MetricsResponse
from app.redis_client import redis_cluster
from app.buffer import search_buffer

logger = logging.getLogger("main")
logging.basicConfig(level=logging.INFO)

# Metrics tracking counters
metrics = {
    "cache_hits": 0,
    "cache_misses": 0,
    "cache_fails": 0,
    "total_suggest_requests": 0
}

async def periodic_flush_worker():
    """Background worker that flushes the buffer to database every 10 seconds."""
    while True:
        try:
            await asyncio.sleep(config.BUFFER_FLUSH_INTERVAL)
            await search_buffer.flush_async()
        except asyncio.CancelledError:
            logger.info("Background periodic flush worker cancelled.")
            break
        except Exception as e:
            logger.error(f"Error in background periodic flush: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Start the background flusher task
    worker_task = asyncio.create_task(periodic_flush_worker())
    logger.info("FastAPI application started. Background buffer flush worker initialized.")
    yield
    # Shutdown: Cancel the worker task and perform a final flush
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass
    logger.info("FastAPI application shutting down. Performing final buffer flush...")
    search_buffer.flush_sync()
    logger.info("Final buffer flush completed.")

app = FastAPI(
    title="Search Typeahead System API",
    description="Sleek, scalable autocomplete suggestion API using consistent hashing and write-reduction buffering.",
    version="1.0.0",
    lifespan=lifespan
)

# Root Endpoint: Serve the main frontend page
@app.get("/", response_class=FileResponse)
def read_root():
    frontend_index = Path("frontend/index.html")
    if not frontend_index.exists():
        raise HTTPException(status_code=404, detail="Frontend index.html not found.")
    return FileResponse(frontend_index)

# Suggestion API
@app.get("/suggest", response_model=List[SuggestionResponse])
def suggest(
    q: str = Query("", description="Prefix to get autocomplete suggestions for"),
    db: Session = Depends(get_db)
):
    """
    Returns up to 10 autocomplete suggestions matching the query prefix.
    Utilizes consistent hashing and a cache-first approach.
    """
    metrics["total_suggest_requests"] += 1
    
    prefix = q.strip().lower()
    if not prefix:
        # Check cache first for overall trending
        cached_suggestions, node_name, cache_status = redis_cluster.get_suggestions("__empty__")
        if cache_status == "HIT":
            metrics["cache_hits"] += 1
            return cached_suggestions
        if cache_status == "MISS":
            metrics["cache_misses"] += 1
        else:
            metrics["cache_fails"] += 1
            
        try:
            db_suggestions = db.query(SearchQuery.query_text, SearchQuery.trending_score)\
                .order_by(SearchQuery.trending_score.desc())\
                .limit(10)\
                .all()
            results = [{"query": s.query_text, "score": s.trending_score} for s in db_suggestions]
            if cache_status == "MISS":
                redis_cluster.set_suggestions("__empty__", results)
            return results
        except Exception as e:
            logger.error(f"Database query failed for empty prefix: {e}")
            return []
        
    # Check Redis cache first
    cached_suggestions, node_name, cache_status = redis_cluster.get_suggestions(prefix)
    
    if cache_status == "HIT":
        metrics["cache_hits"] += 1
        return cached_suggestions
        
    # Cache MISS or FAIL
    if cache_status == "MISS":
        metrics["cache_misses"] += 1
    else:
        metrics["cache_fails"] += 1
        
    # Query MySQL database
    try:
        db_suggestions = db.query(SearchQuery.query_text, SearchQuery.trending_score)\
            .filter(SearchQuery.query_text.like(f"{prefix}%"))\
            .order_by(SearchQuery.trending_score.desc())\
            .limit(10)\
            .all()
            
        results = [{"query": s.query_text, "score": s.trending_score} for s in db_suggestions]
        
        # Write back to Redis for subsequent hits (only if not a complete Redis node failure)
        if cache_status == "MISS":
            redis_cluster.set_suggestions(prefix, results)
            
        return results
    except Exception as e:
        logger.error(f"Database query failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal database failure while retrieving suggestions."
        )

# Search Submission API
@app.post("/search")
async def search(request: SearchRequest):
    """
    Submits a search query. Increments its count in-memory.
    Returns success instantly and flushes to MySQL asynchronously.
    """
    query = request.query.strip()
    if not query:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Search query cannot be empty."
        )
        
    # Increment in-memory buffer count
    trigger_flush = search_buffer.increment(query)
    
    # If the buffer reached threshold capacity, trigger flush immediately
    if trigger_flush:
        logger.info("Buffer capacity reached threshold. Triggering immediate asynchronous flush...")
        asyncio.create_task(search_buffer.flush_async())
        
    return {"status": "success", "message": "Search query received and buffered."}

# Cache Debug API
@app.get("/cache/debug", response_model=CacheDebugResponse)
def cache_debug(prefix: str = Query(..., description="Query prefix to debug mapping and cache state")):
    """
    Debugging endpoint showing which Redis node a prefix is routed to,
    and whether it is currently a cache HIT, MISS, or FAIL.
    """
    prefix = prefix.strip().lower()
    if not prefix:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Prefix cannot be empty."
        )
        
    try:
        node_name, _ = redis_cluster.get_client_for_key(prefix)
        # Attempt to retrieve from cache to see status
        _, _, status_val = redis_cluster.get_suggestions(prefix)
        
        return {
            "prefix": prefix,
            "selected_node": node_name,
            "cache_status": status_val
        }
    except Exception as e:
        logger.error(f"Error debugging cache prefix '{prefix}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve cache debugging details."
        )

# System Metrics API
@app.get("/metrics", response_model=MetricsResponse)
def get_metrics():
    """Returns real-time performance and cache metrics of the system."""
    hits = metrics["cache_hits"]
    misses = metrics["cache_misses"]
    fails = metrics["cache_fails"]
    total = hits + misses + fails
    
    hit_rate = (hits / total) if total > 0 else 0.0
    
    with search_buffer.lock:
        buffer_size = search_buffer.accumulated_updates
        
    return {
        "cache_hits": hits,
        "cache_misses": misses,
        "cache_fails": fails,
        "cache_hit_rate": round(hit_rate, 4),
        "total_suggest_requests": metrics["total_suggest_requests"],
        "buffer_accumulated_updates": buffer_size
    }

# Mount static files (HTML, CSS, JS)
frontend_dir = Path("frontend")
if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")
