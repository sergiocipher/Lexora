import time  # BUG-1 FIX: moved to top-level, not inside retry loops
import redis
import json
import logging
from typing import List, Dict, Any, Optional, Tuple
from app.config import config
from app.consistent_hash import ConsistentHashRing

from redis.retry import Retry
from redis.backoff import ExponentialBackoff

logger = logging.getLogger("redis_client")
# BUG-12 FIX: removed duplicate basicConfig call — logging is configured centrally in main.py

class RedisClusterManager:
    """
    Manages connection pools to multiple Redis instances and routes read/write
    operations to the appropriate instance using consistent hashing.
    """
    def __init__(self) -> None:
        self.node_ports = config.REDIS_PORTS
        self.host = config.REDIS_HOST
        
        self.pools: Dict[str, redis.ConnectionPool] = {}
        self.clients: Dict[str, redis.Redis] = {}
        self.node_names: List[str] = []
        
        self.port_to_name: Dict[int, str] = {}
        self.name_to_port: Dict[str, int] = {}
        
        for idx, port in enumerate(sorted(self.node_ports)):
            name = f"redis-{idx+1}"
            self.port_to_name[port] = name
            self.name_to_port[name] = port
            self.node_names.append(name)
            
            pool = redis.ConnectionPool(
                host=self.host,
                port=port,
                decode_responses=True,
                socket_timeout=2.0,
                socket_connect_timeout=2.0,
                max_connections=100
            )
            self.pools[name] = pool
            
            retry = Retry(ExponentialBackoff(), 3)
            self.clients[name] = redis.Redis(
                connection_pool=pool,
                retry=retry,
                retry_on_error=[redis.exceptions.ConnectionError, redis.exceptions.TimeoutError],
                health_check_interval=30
            )
            logger.info(f"Initialized connection pool for Redis node {name} on port {port} with retry backoff")
            
        self.ring = ConsistentHashRing(nodes=self.node_names, replicas=100)

    def get_client_for_key(self, key: str) -> Tuple[str, redis.Redis]:
        """Resolves the routed Redis client and its node name for a given key using the ring."""
        node_name = self.ring.get_node(key)
        if not node_name:
            raise ValueError("No Redis nodes available on the ring.")
        return node_name, self.clients[node_name]

    def get_suggestions(self, prefix: str) -> Tuple[Optional[List[Dict[str, Any]]], str, str]:
        """
        Retrieves cached suggestions for a query prefix.
        Returns:
            Tuple[suggestions_list, selected_node_name, cache_status]
            cache_status can be 'HIT', 'MISS', or 'FAIL' (if node is down).
        """
        node_name, client = self.get_client_for_key(prefix)
        cache_key = f"suggest:{prefix}"
        
        for attempt in range(3):
            try:
                val = client.get(cache_key)
                if val:
                    return json.loads(val), node_name, "HIT"
                return None, node_name, "MISS"
            except redis.RedisError as e:
                logger.warning(f"Attempt {attempt+1} failed on primary Redis node {node_name}: {e}. Retrying...")
                time.sleep(0.01 * (attempt + 1))  # BUG-1 FIX: using top-level import
                
        logger.error(f"Primary Redis node {node_name} is down after retries. Attempting failover...")
        
        for fallback_node in self.node_names:
            if fallback_node == node_name:
                continue
            for attempt in range(2):
                try:
                    fallback_client = self.clients[fallback_node]
                    val = fallback_client.get(cache_key)
                    if val:
                        logger.info(f"Failover successful: retrieved cache from fallback node {fallback_node}")
                        return json.loads(val), fallback_node, "HIT"
                    return None, fallback_node, "MISS"
                except redis.RedisError as e:
                    logger.warning(f"Failover attempt {attempt+1} failed on node {fallback_node}: {e}")
                    time.sleep(0.01)
                    
        return None, node_name, "FAIL"

    def set_suggestions(self, prefix: str, suggestions: List[Dict[str, Any]], ttl: Optional[int] = None) -> bool:
        """Saves prefix suggestions to Redis."""
        node_name, client = self.get_client_for_key(prefix)
        cache_key = f"suggest:{prefix}"
        if ttl is None:
            ttl = config.CACHE_TTL
            
        for attempt in range(3):
            try:
                client.set(cache_key, json.dumps(suggestions), ex=ttl)
                return True
            except redis.RedisError as e:
                logger.warning(f"Attempt {attempt+1} failed to set key on primary node {node_name}: {e}. Retrying...")
                time.sleep(0.01 * (attempt + 1))
                
        logger.error(f"Failed to set key on primary Redis node {node_name} after retries. Attempting failover...")
        
        for fallback_node in self.node_names:
            if fallback_node == node_name:
                continue
            for attempt in range(2):
                try:
                    fallback_client = self.clients[fallback_node]
                    fallback_client.set(cache_key, json.dumps(suggestions), ex=ttl)
                    logger.info(f"Failover successful: saved cache to fallback node {fallback_node}")
                    return True
                except redis.RedisError as e:
                    logger.warning(f"Failover attempt {attempt+1} failed to set key on node {fallback_node}: {e}")
                    time.sleep(0.01)
        return False

    def exists(self, prefix: str) -> bool:
        """Checks if a prefix is currently cached in Redis."""
        node_name, client = self.get_client_for_key(prefix)
        cache_key = f"suggest:{prefix}"
        
        for attempt in range(3):
            try:
                return bool(client.exists(cache_key))
            except redis.RedisError as e:
                logger.warning(f"Attempt {attempt+1} failed to check existence on primary node {node_name}: {e}. Retrying...")
                time.sleep(0.01 * (attempt + 1))
                
        logger.error(f"Failed to check key existence on primary node {node_name} after retries. Attempting failover...")
        
        for fallback_node in self.node_names:
            if fallback_node == node_name:
                continue
            for attempt in range(2):
                try:
                    fallback_client = self.clients[fallback_node]
                    return bool(fallback_client.exists(cache_key))
                except redis.RedisError:
                    time.sleep(0.01)
        return False

    def delete_suggestions(self, prefix: str) -> bool:
        """Deletes prefix suggestions from Redis (used for invalidating cache)."""
        node_name, client = self.get_client_for_key(prefix)
        cache_key = f"suggest:{prefix}"
        
        for attempt in range(3):
            try:
                client.delete(cache_key)
                return True
            except redis.RedisError as e:
                logger.warning(f"Attempt {attempt+1} failed to delete key on primary node {node_name}: {e}. Retrying...")
                time.sleep(0.01 * (attempt + 1))
                
        logger.error(f"Failed to delete key on primary Redis node {node_name} after retries. Evicting from fallbacks...")
        
        success = False
        for fallback_node in self.node_names:
            if fallback_node == node_name:
                continue
            for attempt in range(2):
                try:
                    self.clients[fallback_node].delete(cache_key)
                    success = True
                    break
                except redis.RedisError:
                    time.sleep(0.01)
        return success

# Global singleton client manager
redis_cluster = RedisClusterManager()
