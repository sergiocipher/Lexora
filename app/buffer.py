import logging
import asyncio
from datetime import datetime, timedelta
import threading
from typing import Dict, Set
import pymysql
from app.config import config
from app.database import engine
from app.redis_client import redis_cluster

logger = logging.getLogger("buffer")
logging.basicConfig(level=logging.INFO)

class SearchBuffer:
    """
    In-memory counts buffer that aggregates search query submissions.
    Reduces database writes by batch flushing to MySQL and updating Redis.
    """
    def __init__(self) -> None:
        self.buffer: Dict[str, int] = {}
        self.lock = threading.Lock()
        self.accumulated_updates = 0
        
    def increment(self, query: str) -> bool:
        """
        Increments the search count for a query in-memory.
        Returns:
            bool: True if the buffer limit (BUFFER_MAX_UPDATES) has been reached and needs a flush.
        """
        query = query.strip()
        if not query:
            return False
            
        with self.lock:
            self.buffer[query] = self.buffer.get(query, 0) + 1
            self.accumulated_updates += 1
            trigger_flush = self.accumulated_updates >= config.BUFFER_MAX_UPDATES
            
        return trigger_flush

    def flush_sync(self) -> None:
        """
        Synchronously flushes the buffered updates to MySQL.
        Recalculates counts/scores and updates affected Redis caches.
        """
        with self.lock:
            if not self.buffer:
                return
            temp_buffer = self.buffer
            self.buffer = {}
            self.accumulated_updates = 0
            
        logger.info(f"Flushing buffer with {len(temp_buffer)} unique queries...")
        
        now = datetime.now()
        
        # 1. Update MySQL
        # Connect using the raw PyMySQL connection from config
        conn = pymysql.connect(
            host=config.DB_HOST,
            port=config.DB_PORT,
            user=config.DB_USER,
            password=config.DB_PASSWORD,
            database=config.DB_NAME,
            autocommit=False
        )
        
        try:
            with conn.cursor() as cursor:
                # Batch log query requests
                log_entries = []
                for q, count in temp_buffer.items():
                    for _ in range(count):
                        log_entries.append((q[:255], now))
                        
                cursor.executemany("INSERT INTO query_logs (query_text, query_time) VALUES (%s, %s)", log_entries)
                
                # Recalculate and update search_queries
                for q, count in temp_buffer.items():
                    q_truncated = q[:255]
                    
                    # Insert new query or update global count
                    cursor.execute("""
                        INSERT INTO search_queries (query_text, global_count, weekly_count, daily_count, trending_score)
                        VALUES (%s, %s, 0, 0, 0.0)
                        ON DUPLICATE KEY UPDATE global_count = global_count + %s
                    """, (q_truncated, count, count))
                    
                    # Fetch total global count
                    cursor.execute("SELECT global_count FROM search_queries WHERE query_text = %s", (q_truncated,))
                    global_cnt = cursor.fetchone()[0]
                    
                    # Calculate rolling daily and weekly counts
                    one_day_ago = now - timedelta(days=1)
                    one_week_ago = now - timedelta(days=7)
                    
                    cursor.execute("SELECT COUNT(*) FROM query_logs WHERE query_text = %s AND query_time >= %s", (q_truncated, one_day_ago))
                    daily_cnt = cursor.fetchone()[0]
                    
                    cursor.execute("SELECT COUNT(*) FROM query_logs WHERE query_text = %s AND query_time >= %s", (q_truncated, one_week_ago))
                    weekly_cnt = cursor.fetchone()[0]
                    
                    # Compute trending score
                    # Trending Score = 0.6 * Global Count + 0.3 * Weekly Count + 0.1 * Daily Count
                    trending_sc = 0.6 * global_cnt + 0.3 * weekly_cnt + 0.1 * daily_cnt
                    
                    cursor.execute("""
                        UPDATE search_queries
                        SET daily_count = %s, weekly_count = %s, trending_score = %s
                        WHERE query_text = %s
                    """, (daily_cnt, weekly_cnt, trending_sc, q_truncated))
                    
            conn.commit()
            logger.info("MySQL batch count updates committed successfully.")
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to flush buffer to MySQL: {e}")
            # Restore the unsaved counts back to the buffer
            with self.lock:
                for q, count in temp_buffer.items():
                    self.buffer[q] = self.buffer.get(q, 0) + count
                    self.accumulated_updates += count
            return
        finally:
            conn.close()
            
        # 2. Refresh Redis cache entries for all affected prefixes
        # Build set of unique prefixes
        affected_prefixes: Set[str] = set()
        for q in temp_buffer.keys():
            # Standard prefixes from length 1 to 10
            for i in range(1, min(len(q) + 1, 11)):
                affected_prefixes.add(q[:i].lower())
                
        logger.info(f"Re-evaluating cache status for {len(affected_prefixes)} affected prefixes...")
        
        # Connect to DB to select current suggestions
        db_conn = pymysql.connect(
            host=config.DB_HOST,
            port=config.DB_PORT,
            user=config.DB_USER,
            password=config.DB_PASSWORD,
            database=config.DB_NAME,
            cursorclass=pymysql.cursors.DictCursor
        )
        
        try:
            with db_conn.cursor() as db_cursor:
                for prefix in affected_prefixes:
                    # Only refresh if the prefix is already cached (avoiding populating unpopular keys)
                    if not redis_cluster.exists(prefix):
                        continue
                    
                    # Query top 10 suggestions for prefix
                    # We look up case-insensitively using prefix match
                    db_cursor.execute("""
                        SELECT query_text as query, trending_score as score
                        FROM search_queries
                        WHERE query_text LIKE %s
                        ORDER BY trending_score DESC
                        LIMIT 10
                    """, (f"{prefix}%",))
                    
                    suggestions = db_cursor.fetchall()
                    
                    # Update cache key
                    redis_cluster.set_suggestions(prefix, suggestions)
            logger.info("Affected Redis cache entries refreshed successfully.")
        except Exception as e:
            logger.error(f"Error refreshing Redis cache entries during flush: {e}")
        finally:
            db_conn.close()

    async def flush_async(self) -> None:
        """Asynchronously executes the database flush using thread execution pool."""
        await asyncio.to_thread(self.flush_sync)

# Global singleton count buffer instance
search_buffer = SearchBuffer()
