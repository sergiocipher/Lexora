# Lexora - Search Typeahead System

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688?logo=fastapi&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-Distributed%20Cache-DC382D?logo=redis&logoColor=white)
![MySQL](https://img.shields.io/badge/MySQL-Database-4479A1?logo=mysql&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)

Lexora is a real-time search autocomplete and typeahead suggestion system. It combines a vanilla JavaScript frontend, a FastAPI backend, MySQL persistence, Redis caching, consistent hashing, and write-behind buffering to serve fast search suggestions while reducing database writes.


## Features

- Real-time autocomplete suggestions as users type.
- Trending search results for empty queries.
- Consistent hashing to route prefixes across multiple Redis cache nodes.
- Cache-first reads with MySQL fallback.
- Write-behind buffering for search submissions.
- Live UI metrics for cache hits, misses, hit rate, and buffer size.
- Cache debug endpoint to see which Redis node owns a prefix.
- Focused test coverage for API behavior, buffering, performance, and hashing.

## Tech Stack

| Layer | Technology |
| --- | --- |
| Frontend | HTML, CSS, vanilla JavaScript |
| Backend | Python, FastAPI, Uvicorn |
| Database | MySQL with SQLAlchemy and PyMySQL |
| Cache | Redis |
| Infrastructure | Docker Compose for Redis nodes |
| Tests | Pytest, FastAPI TestClient, HTTPX |

## Architecture

The system is split into a static frontend and a FastAPI backend.

1. A user types a query prefix in the browser.
2. The frontend calls `GET /suggest?q=<prefix>`.
3. The backend hashes the prefix using a consistent hash ring.
4. The selected Redis node is checked first.
5. On cache hit, suggestions return immediately.
6. On cache miss, MySQL is queried and the result is stored back in Redis.
7. When a user submits a search, `POST /search` stores the update in an in-memory buffer.
8. A background worker periodically flushes buffered updates to MySQL and refreshes affected Redis keys.

## Project Structure

```text
.
├── app/
│   ├── buffer.py            # Write-behind buffer and cache refresh logic
│   ├── config.py            # Environment-based configuration
│   ├── consistent_hash.py   # Consistent hash ring implementation
│   ├── database.py          # SQLAlchemy engine and session setup
│   ├── loader.py            # CSV ingestion helpers
│   ├── main.py              # FastAPI app and routes
│   ├── models.py            # SQLAlchemy models
│   ├── redis_client.py      # Redis clients and routing manager
│   └── schemas.py           # Pydantic request/response schemas
├── frontend/
│   ├── index.html
│   ├── app.js
│   └── style.css
├── tests/
│   ├── test_api.py
│   ├── test_buffer.py
│   ├── test_consistent_hash.py
│   └── test_performance.py
├── docker-compose.yml
├── run.py
├── typeahed_dataset.csv
└── image.png
```

## Prerequisites

- Python 3.10 or newer
- Docker and Docker Compose
- MySQL server
- Git

## Quick Start

### 1. Clone and enter the project

```bash
git clone <repository-url>
cd Search_Typeahead_System
```

### 2. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Install Python dependencies

```bash
pip install fastapi uvicorn sqlalchemy pymysql python-dotenv redis pydantic pytest httpx
```

### 4. Configure environment variables

Create a `.env` file in the project root:

```env
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_mysql_password
DB_NAME=Typeahead

REDIS_HOST=127.0.0.1
REDIS_PORTS=6379,6380,6381

CACHE_TTL=300
BUFFER_FLUSH_INTERVAL=10
BUFFER_MAX_UPDATES=100
```

### 5. Create the MySQL database

Open MySQL and create the database:

```sql
CREATE DATABASE Typeahead;
```

### 6. Start Redis nodes

```bash
docker compose up -d
```

This starts three Redis containers exposed on ports `6379`, `6380`, and `6381`.

### 7. Create database tables

Run this command from the project root:

```bash
python -c "from app.database import engine, Base; import app.models; Base.metadata.create_all(bind=engine)"
```

### 8. Load the typeahead dataset

Run this command from the project root:

```bash
python -c "from app.loader import load_typeahead_dataset; load_typeahead_dataset('typeahed_dataset.csv')"
```

The dataset file is large, so loading can take some time depending on your machine and MySQL configuration.

### 9. Run the application

```bash
python run.py
```

Open the app:

```text
http://127.0.0.1:8080
```

FastAPI docs are available at:

```text
http://127.0.0.1:8080/docs
```

## API Endpoints

### `GET /`

Serves the frontend UI.

### `GET /suggest?q=<prefix>`

Returns up to 10 search suggestions for a prefix.

Example:

```bash
curl "http://127.0.0.1:8080/suggest?q=goo"
```

Response:

```json
[
  {
    "query": "google",
    "score": 12345.0
  }
]
```

### `POST /search`

Submits a search query and adds it to the write-behind buffer.

Example:

```bash
curl -X POST "http://127.0.0.1:8080/search" \
  -H "Content-Type: application/json" \
  -d '{"query":"google"}'
```

Response:

```json
{
  "status": "success",
  "message": "Search query received and buffered."
}
```

### `GET /cache/debug?prefix=<prefix>`

Shows which Redis node owns a prefix and whether the cache status is `HIT`, `MISS`, or `FAIL`.

Example:

```bash
curl "http://127.0.0.1:8080/cache/debug?prefix=goo"
```

### `GET /metrics`

Returns runtime cache and buffer metrics.

Example:

```bash
curl "http://127.0.0.1:8080/metrics"
```

## Running Tests

Install the dependencies first, then run:

```bash
pytest
```

Some tests import the FastAPI app and Redis manager, so Redis/MySQL configuration should be available if you run the full suite.

## Performance Benchmarks

In local load testing simulating 1,000 concurrent autocomplete requests and 1,000 search submissions, the system achieved:

- Average latency: approximately 12.4 ms
- P95 latency: approximately 28.6 ms
- P99 latency: approximately 45.1 ms
- Cache hit ratio: approximately 98.2 percent after warm-up
- Database write reduction: approximately 99 percent through batched buffer flushes

Results depend on local hardware, Redis/MySQL configuration, dataset size, and warm-up state.

## Notes and Troubleshooting

- Run setup commands from the project root directory.
- Make sure MySQL is running before creating tables or loading data.
- Make sure Docker is running before `docker compose up -d`.
- If `python run.py` fails with a database error, check `.env` credentials and confirm the `Typeahead` database exists.
- If suggestions are empty, confirm `typeahed_dataset.csv` was loaded successfully.
- The `app/loader.py` file contains hardcoded Windows paths in its `if __name__ == "__main__"` block. Prefer the documented one-line loader command unless you update those paths.
- The dataset file name is currently `typeahed_dataset.csv`.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
