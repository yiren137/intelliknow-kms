"""FAISS IndexFlatIP per intent space with deletion support via metadata.pkl."""
from __future__ import annotations
import os
import pickle
from typing import Dict, List, Tuple
import numpy as np
import faiss
from config.settings import get_settings

settings = get_settings()


class VectorStore:
    """One FAISS index per intent space.

    Stores raw vectors alongside metadata so we can rebuild the index when
    documents are deleted (FAISS IndexFlatIP has no native remove()).
    """

    def __init__(self, intent_space: str):
        self.intent_space = intent_space
        self.dir = os.path.join(settings.faiss_dir, intent_space)
        os.makedirs(self.dir, exist_ok=True)

        self.index_path = os.path.join(self.dir, "index.faiss")
        self.meta_path = os.path.join(self.dir, "metadata.pkl")

        self.index: faiss.IndexFlatIP = faiss.IndexFlatIP(settings.embedding_dim)
        # metadata entries: list of dicts, index == faiss_id
        self.metadata: List[Dict] = []

        self._load()

    # ------------------------------------------------------------------ #
    # Persistence                                                           #
    # ------------------------------------------------------------------ #

    def _load(self):
        if os.path.exists(self.index_path) and os.path.exists(self.meta_path):
            self.index = faiss.read_index(self.index_path)
            with open(self.meta_path, "rb") as f:
                self.metadata = pickle.load(f)

    def _save(self):
        faiss.write_index(self.index, self.index_path)
        with open(self.meta_path, "wb") as f:
            pickle.dump(self.metadata, f)

    # ------------------------------------------------------------------ #
    # Write                                                                 #
    # ------------------------------------------------------------------ #

    def add_chunks(
        self,
        vectors: np.ndarray,
        chunk_texts: List[str],
        document_id: int,
        chunk_ids: List[int],
    ) -> List[int]:
        """Add embeddings and return the list of faiss_ids assigned."""
        start_id = len(self.metadata)
        self.index.add(vectors)
        faiss_ids = list(range(start_id, start_id + len(vectors)))

        for i, (fid, text, cid) in enumerate(zip(faiss_ids, chunk_texts, chunk_ids)):
            self.metadata.append(
                {
                    "faiss_id": fid,
                    "document_id": document_id,
                    "chunk_id": cid,
                    "chunk_text": text,
                    "vector": vectors[i],
                    "deleted": False,
                }
            )

        self._save()
        return faiss_ids

    # ------------------------------------------------------------------ #
    # Delete                                                                #
    # ------------------------------------------------------------------ #

    def remove_document_chunks(self, document_id: int):
        """Mark entries as deleted and rebuild the index without them."""
        for entry in self.metadata:
            if entry["document_id"] == document_id:
                entry["deleted"] = True

        active = [m for m in self.metadata if not m["deleted"]]
        if active:
            vectors = np.stack([m["vector"] for m in active]).astype(np.float32)
            new_index = faiss.IndexFlatIP(settings.embedding_dim)
            new_index.add(vectors)
            # Remap faiss_ids
            for new_id, entry in enumerate(active):
                entry["faiss_id"] = new_id
            self.index = new_index
            self.metadata = active
        else:
            self.index = faiss.IndexFlatIP(settings.embedding_dim)
            self.metadata = []

        self._save()

    # ------------------------------------------------------------------ #
    # Search                                                                #
    # ------------------------------------------------------------------ #

    def search(
        self, query_vector: np.ndarray, top_k: int = 5
    ) -> List[Tuple[float, Dict]]:
        """Return list of (score, metadata_dict) sorted by descending score."""
        if self.index.ntotal == 0:
            return []

        k = min(top_k, self.index.ntotal)
        scores, ids = self.index.search(query_vector, k)

        results = []
        for score, idx in zip(scores[0], ids[0]):
            if idx < 0 or idx >= len(self.metadata):
                continue
            meta = self.metadata[idx]
            if meta.get("deleted"):
                continue
            results.append((float(score), meta))

        return results

    # ------------------------------------------------------------------ #
    # Stats                                                                 #
    # ------------------------------------------------------------------ #

    @property
    def total_chunks(self) -> int:
        return sum(1 for m in self.metadata if not m.get("deleted"))


# Global store registry — one instance per intent space
_stores: Dict[str, VectorStore] = {}


def get_vector_store(intent_space: str) -> VectorStore:
    if intent_space not in _stores:
        _stores[intent_space] = VectorStore(intent_space)
    return _stores[intent_space]
