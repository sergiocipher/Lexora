import pytest
import time
from app.buffer import SearchBuffer
from app.config import config

def test_buffer_increment():
    buffer = SearchBuffer()
    
    # Verify starting state
    assert len(buffer.buffer) == 0
    assert buffer.accumulated_updates == 0
    
    # Increment query counts
    trigger1 = buffer.increment("iphone")
    trigger2 = buffer.increment("iphone")
    trigger3 = buffer.increment("ipad")
    
    assert not trigger1
    assert not trigger2
    assert not trigger3
    
    assert buffer.buffer["iphone"] == 2
    assert buffer.buffer["ipad"] == 1
    assert buffer.accumulated_updates == 3

def test_buffer_threshold_trigger():
    buffer = SearchBuffer()
    
    # Set config threshold to 5 for test convenience
    original_max = config.BUFFER_MAX_UPDATES
    config.BUFFER_MAX_UPDATES = 5
    
    try:
        assert not buffer.increment("q")
        assert not buffer.increment("q")
        assert not buffer.increment("q")
        assert not buffer.increment("q")
        
        # 5th increment should trigger immediate flush warning
        trigger = buffer.increment("q")
        assert trigger
        assert buffer.accumulated_updates == 5
    finally:
        # Restore configuration
        config.BUFFER_MAX_UPDATES = original_max

def test_buffer_swap_on_flush():
    buffer = SearchBuffer()
    buffer.increment("iphone")
    buffer.increment("ipad")
    
    # We simulate the thread-safe swap that happens in flush
    with buffer.lock:
        temp_buffer = buffer.buffer
        buffer.buffer = {}
        buffer.accumulated_updates = 0
        
    assert len(buffer.buffer) == 0
    assert buffer.accumulated_updates == 0
    assert temp_buffer["iphone"] == 1
    assert temp_buffer["ipad"] == 1
