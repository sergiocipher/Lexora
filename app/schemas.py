from pydantic import BaseModel, Field
from typing import List, Dict, Any

class SearchRequest(BaseModel):
    query: str = Field(..., description="The query string submitted by the user", min_length=1, max_length=255)

class SuggestionResponse(BaseModel):
    query: str
    score: float

class CacheDebugResponse(BaseModel):
    prefix: str
    selected_node: str
    cache_status: str

class MetricsResponse(BaseModel):
    cache_hits: int
    cache_misses: int
    cache_fails: int
    cache_hit_rate: float
    total_suggest_requests: int
    buffer_accumulated_updates: int
