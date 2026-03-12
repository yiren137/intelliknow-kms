"""Singleton wrapper around sentence-transformers all-MiniLM-L6-v2."""
from __future__ import annotations
from typing import List
import numpy as np
from sentence_transformers import SentenceTransformer
from config.settings import get_settings

settings = get_settings()

_model: SentenceTransformer | None = None


def get_embedder() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(settings.embedding_model)
    return _model


def embed_texts(texts: List[str]) -> np.ndarray:
    """Return L2-normalised float32 embeddings of shape (N, dim)."""
    model = get_embedder()
    vecs = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return vecs.astype(np.float32)


def embed_query(text: str) -> np.ndarray:
    """Return a single normalised query vector of shape (1, dim)."""
    return embed_texts([text])
