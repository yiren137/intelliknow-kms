"""Pydantic request/response models for the FastAPI layer."""
from __future__ import annotations
from typing import Any, List, Optional
from pydantic import BaseModel, Field


# ------------------------------------------------------------------ #
# Query                                                                #
# ------------------------------------------------------------------ #

class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    source: str = Field(default="api")
    user_id: Optional[str] = None
    conversation_history: Optional[List[List[str]]] = None  # [[user_q, assistant_a], ...]


class SourceDoc(BaseModel):
    document_name: str
    document_id: int
    page_number: Optional[int]
    score: float


class QueryResponse(BaseModel):
    query: str
    query_log_id: int
    intent_space: str
    intent_space_name: str
    confidence: float
    reasoning: str
    answer: str
    sources: List[SourceDoc]
    latency_ms: int
    status: str


# ------------------------------------------------------------------ #
# Documents                                                            #
# ------------------------------------------------------------------ #

class DocumentOut(BaseModel):
    id: int
    filename: str
    original_name: str
    intent_space_id: int
    intent_space_name: Optional[str] = None
    file_type: str
    file_size_bytes: int = 0
    chunk_count: int
    status: str
    uploaded_at: str
    indexed_at: Optional[str]


class DocumentUploadResponse(BaseModel):
    id: int
    original_name: str
    intent_space: str
    chunk_count: int
    status: str


class ChunkOut(BaseModel):
    id: int
    chunk_index: int
    page_number: Optional[int]
    chunk_text: str


# ------------------------------------------------------------------ #
# Intent Spaces                                                        #
# ------------------------------------------------------------------ #

class IntentSpaceCreate(BaseModel):
    name: str = Field(..., pattern=r"^[a-z0-9_]+$", max_length=50)
    display_name: str = Field(..., max_length=100)
    description: str = Field(default="", max_length=500)
    keywords: str = Field(default="", max_length=500)
    confidence_threshold: float = Field(default=0.7, ge=0.0, le=1.0)


class IntentSpaceUpdate(BaseModel):
    display_name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    keywords: Optional[str] = Field(None, max_length=500)
    confidence_threshold: Optional[float] = Field(None, ge=0.0, le=1.0)
    is_active: Optional[bool] = None


class IntentSpaceOut(BaseModel):
    id: int
    name: str
    display_name: str
    description: str
    keywords: str = ""
    confidence_threshold: float = 0.7
    is_active: bool
    created_at: str
    document_count: Optional[int] = 0
    accuracy_rate: Optional[float] = None


# ------------------------------------------------------------------ #
# Analytics                                                            #
# ------------------------------------------------------------------ #

class AnalyticsSummary(BaseModel):
    total_queries: int
    successful_queries: int
    success_rate: float
    total_documents: int
    total_chunks: int
    avg_latency_ms: float
    top_intent_spaces: List[dict]


class QueryLogEntry(BaseModel):
    id: int
    query_text: str
    source: str
    user_id: Optional[str]
    intent_space_name: Optional[str]
    confidence_score: Optional[float]
    response_status: str
    latency_ms: Optional[int]
    cache_hit: bool = False
    feedback: Optional[int]
    created_at: str


class FeedbackRequest(BaseModel):
    feedback: int = Field(..., description="1 for thumbs up, -1 for thumbs down")


class DocumentAccessStat(BaseModel):
    document_id: int
    original_name: str
    access_count: int
    intent_space_name: Optional[str]


class DailyVolume(BaseModel):
    date: str
    query_count: int


# ------------------------------------------------------------------ #
# Bots                                                                 #
# ------------------------------------------------------------------ #

class BotStatus(BaseModel):
    id: int
    platform: str
    is_active: bool
    last_seen_at: Optional[str]
    created_at: str


class BotUpdate(BaseModel):
    is_active: Optional[bool] = None


# ------------------------------------------------------------------ #
# Generic                                                              #
# ------------------------------------------------------------------ #

class MessageResponse(BaseModel):
    message: str
    detail: Optional[Any] = None
