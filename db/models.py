from dataclasses import dataclass, field
from typing import Optional


@dataclass
class IntentSpace:
    id: int
    name: str
    display_name: str
    description: str
    keywords: str
    confidence_threshold: float
    is_active: bool
    created_at: str


@dataclass
class Document:
    id: int
    filename: str
    original_name: str
    intent_space_id: int
    file_type: str
    file_size_bytes: int
    chunk_count: int
    status: str
    uploaded_at: str
    indexed_at: Optional[str] = None


@dataclass
class Chunk:
    id: int
    document_id: int
    faiss_id: int
    intent_space_id: int
    chunk_text: str
    chunk_index: int
    page_number: Optional[int]
    created_at: str


@dataclass
class QueryLog:
    id: int
    query_text: str
    source: str
    user_id: Optional[str]
    intent_space_id: Optional[int]
    intent_space_name: Optional[str]
    confidence_score: Optional[float]
    response_status: str
    response_text: Optional[str]
    latency_ms: Optional[int]
    documents_accessed: str
    created_at: str


@dataclass
class BotIntegration:
    id: int
    platform: str
    is_active: bool
    config_json: str
    last_seen_at: Optional[str]
    created_at: str
