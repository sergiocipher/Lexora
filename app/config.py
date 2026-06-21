import os
from pathlib import Path
from dotenv import load_dotenv

from urllib.parse import quote_plus

# Find the root of the project
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env
load_dotenv(BASE_DIR / ".env")

class Config:
    # Database configurations
    DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
    DB_PORT = int(os.getenv("DB_PORT", 3306))
    DB_USER = os.getenv("DB_USER", "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "").strip().strip('"')
    DB_NAME = os.getenv("DB_NAME", "Typeahead")

    @property
    def DATABASE_URL(self) -> str:
        encoded_password = quote_plus(self.DB_PASSWORD)
        return f"mysql+pymysql://{self.DB_USER}:{encoded_password}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    # Redis configurations
    REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
    REDIS_PORTS = [int(p.strip()) for p in os.getenv("REDIS_PORTS", "6379,6380,6381").split(",")]

    # Search Autocomplete configurations
    CACHE_TTL = int(os.getenv("CACHE_TTL", 300))  # 5 minutes default
    BUFFER_FLUSH_INTERVAL = int(os.getenv("BUFFER_FLUSH_INTERVAL", 10))  # seconds
    BUFFER_MAX_UPDATES = int(os.getenv("BUFFER_MAX_UPDATES", 100))  # updates count

config = Config()
