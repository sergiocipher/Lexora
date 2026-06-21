import os
import csv
import sys
import time
from datetime import datetime, timedelta
import pymysql
from app.config import config
from app.database import engine

def get_raw_connection():
    return pymysql.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        database=config.DB_NAME,
        autocommit=False
    )

def clear_tables():
    print("Clearing existing tables...")
    conn = get_raw_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
            cursor.execute("TRUNCATE TABLE query_logs;")
            cursor.execute("TRUNCATE TABLE search_queries;")
            cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
        conn.commit()
        print("Tables cleared successfully.")
    except Exception as e:
        conn.rollback()
        print(f"Error clearing tables: {e}")
        sys.exit(1)
    finally:
        conn.close()

def drop_indexes():
    print("Dropping query_logs indexes for fast ingestion...")
    conn = get_raw_connection()
    try:
        with conn.cursor() as cursor:
            # Safely attempt to drop indexes in case they already exist
            for idx_name in ["ix_query_logs_query_text", "ix_query_logs_query_time", "idx_log_query_time"]:
                try:
                    cursor.execute(f"ALTER TABLE query_logs DROP INDEX {idx_name};")
                except Exception:
                    pass
        conn.commit()
    except Exception as e:
        print(f"Warning: error dropping indexes: {e}")
    finally:
        conn.close()

def create_indexes():
    print("Recreating query_logs indexes...")
    start = time.time()
    conn = get_raw_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("ALTER TABLE query_logs ADD INDEX ix_query_logs_query_text (query_text);")
            cursor.execute("ALTER TABLE query_logs ADD INDEX ix_query_logs_query_time (query_time);")
            cursor.execute("ALTER TABLE query_logs ADD INDEX idx_log_query_time (query_text, query_time);")
        conn.commit()
        print(f"Indexes recreated in {time.time() - start:.2f} seconds.")
    except Exception as e:
        conn.rollback()
        print(f"Error recreating indexes: {e}")
        sys.exit(1)
    finally:
        conn.close()

def load_typeahead_dataset(file_path: str):
    print(f"Loading typeahead dataset from {file_path}...")
    start_time = time.time()
    conn = get_raw_connection()
    
    insert_sql = """
        INSERT IGNORE INTO search_queries (query_text, global_count, weekly_count, daily_count, trending_score)
        VALUES (%s, %s, %s, %s, %s)
    """
    
    batch_size = 50000
    batch = []
    total_loaded = 0
    
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            reader = csv.reader(f)
            next(reader)
            
            for row in reader:
                if not row or len(row) < 5:
                    continue
                
                query = row[0].strip()[:255]
                if not query:
                    continue
                
                try:
                    global_cnt = int(row[1])
                    weekly_cnt = int(row[2])
                    daily_cnt = int(row[3])
                    trending_sc = float(row[4])
                except ValueError:
                    continue
                
                batch.append((query, global_cnt, weekly_cnt, daily_cnt, trending_sc))
                
                if len(batch) >= batch_size:
                    with conn.cursor() as cursor:
                        cursor.executemany(insert_sql, batch)
                    conn.commit()
                    total_loaded += len(batch)
                    print(f"Loaded {total_loaded} rows into search_queries...")
                    batch = []
            
            if batch:
                with conn.cursor() as cursor:
                    cursor.executemany(insert_sql, batch)
                conn.commit()
                total_loaded += len(batch)
                
        duration = time.time() - start_time
        print(f"Completed loading {total_loaded} rows into search_queries in {duration:.2f} seconds.")
    except Exception as e:
        conn.rollback()
        print(f"Error loading typeahead dataset: {e}")
        sys.exit(1)
    finally:
        conn.close()

def load_raw_queries(file_path: str):
    print(f"Loading raw query logs from {file_path}...")
    start_time = time.time()
    
    max_dataset_time = datetime(2006, 5, 31, 23, 59, 51)
    now = datetime.now()
    delta = now - max_dataset_time
    print(f"Calculated date shift delta: {delta.days} days, {delta.seconds // 3600} hours")
    
    conn = get_raw_connection()
    insert_sql = "INSERT INTO query_logs (query_text, query_time) VALUES (%s, %s)"
    
    batch_size = 50000
    batch = []
    total_loaded = 0
    
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            reader = csv.reader(f)
            next(reader)
            
            for row in reader:
                if not row or len(row) < 2:
                    continue
                
                query = row[0].strip()[:255]
                time_str = row[1].strip()
                if not query or not time_str:
                    continue
                
                try:
                    dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
                    shifted_dt = dt + delta
                except ValueError:
                    continue
                
                batch.append((query, shifted_dt))
                
                if len(batch) >= batch_size:
                    with conn.cursor() as cursor:
                        cursor.executemany(insert_sql, batch)
                    conn.commit()
                    total_loaded += len(batch)
                    print(f"Loaded {total_loaded} rows into query_logs...")
                    batch = []
            
            if batch:
                with conn.cursor() as cursor:
                    cursor.executemany(insert_sql, batch)
                conn.commit()
                total_loaded += len(batch)
                
        duration = time.time() - start_time
        print(f"Completed loading {total_loaded} rows into query_logs in {duration:.2f} seconds.")
    except Exception as e:
        conn.rollback()
        print(f"Error loading raw query logs: {e}")
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    ta_csv = r"a:\PROJECTS\HLD Projects\Search_Typeahead_System\typeahed_dataset.csv"
    raw_csv = r"a:\PROJECTS\HLD Projects\Search_Typeahead_System\raw_queries.csv"
    
    print("Starting optimized data ingestion process...")
    clear_tables()
    load_typeahead_dataset(ta_csv)
    
    # Fast Ingestion Workflow for query_logs:
    drop_indexes()
    load_raw_queries(raw_csv)
    create_indexes()
    
    print("Data Ingestion completed successfully!")
