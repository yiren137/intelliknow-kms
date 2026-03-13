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
    # NOTE: changing this requires rebuilding all FAISS indices (delete data/faiss_indices/)
    embedding_model: str = "BAAI/bge-base-en-v1.5"
    embedding_dim: int = 768

    # Chunking
    chunk_size: int = 512
    chunk_overlap: int = 64
    max_retrieval_chunks: int = 5

    # Retrieval quality
    min_retrieval_score: float = 0.2       # chunks below this score are ignored
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # Query result cache TTL in seconds (0 = disabled)
    query_cache_ttl: int = 300

    # Conversation history turns kept per user per bot
    max_conversation_history: int = 5


@lru_cache
def get_settings() -> Settings:
    return Settings()
