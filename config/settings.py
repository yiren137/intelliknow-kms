from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
import os


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Google Gemini
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    # Telegram
    telegram_bot_token: str = ""

    # Slack
    slack_bot_token: str = ""
    slack_app_token: str = ""

    # Backend
    api_base_url: str = "http://localhost:8000"

    # Storage paths
    db_path: str = "data/intelliknow.db"
    faiss_dir: str = "data/faiss_indices"
    uploads_dir: str = "data/uploads"

    # App
    debug: bool = False
    log_level: str = "INFO"

    # Embedding model (local, no API cost)
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_dim: int = 384

    # Chunking
    chunk_size: int = 512
    chunk_overlap: int = 64
    max_retrieval_chunks: int = 5


@lru_cache
def get_settings() -> Settings:
    return Settings()
