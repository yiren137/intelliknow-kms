"""FAISS IndexFlatIP + BM25 hybrid search per intent space."""
from __future__ import annotations
import os
import pickle
from typing import Dict, List, Tuple
import numpy as np
import faiss
from rank_bm25 import BM25Okapi
from config.settings import get_settings

settings = get_settings()


def _tokenize(text: str) -> list[str]:
    return text.lower().split()


class VectorStore:
    """One FAISS index + BM25 index per intent space.

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
        self.metadata: List[Dict] = []
        self._bm25: BM25Okapi | None = None

        self._load()
        self._rebuild_bm25()

    # ------------------------------------------------------------------ #
    # Persistence                                                           #
    # ------------------------------------------------------------------ #

    def _load(self):
        if os.path.exists(self.index_path) and os.path.exists(self.meta_path):
            self.index = faiss.read_index(self.index_path)
            with open(self.meta_path, "rb") as f:
                self.metadata = pickle.load(f)
            self._reconcile()

    def _reconcile(self):
        """Remove FAISS entries whose chunk_id no longer exists in the DB.

        Guards against DB/index drift that happens when the app is restarted
        after a crash, a manual DB reset, or a failed delete operation.
        """
        from db.database import get_db_connection
        import logging
        log = logging.getLogger("intelliknow.vector_store")

        if not self.metadata:
            return

        chunk_ids = [m["chunk_id"] for m in self.metadata if not m.get("deleted")]
        if not chunk_ids:
            return

        with get_db_connection() as conn:
            placeholders = ",".join("?" * len(chunk_ids))
            rows = conn.execute(
                f"SELECT id FROM chunks WHERE id IN ({placeholders})", chunk_ids
            ).fetchall()
        valid_ids = {r["id"] for r in rows}

        stale = [m["chunk_id"] for m in self.metadata if not m.get("deleted") and m["chunk_id"] not in valid_ids]
        if not stale:
            return

        log.warning(
            "Reconciling vector store '%s': removing %d stale chunk(s) %s",
            self.intent_space, len(stale), stale,
        )
        stale_set = set(stale)
        for entry in self.metadata:
            if entry["chunk_id"] in stale_set:
                entry["deleted"] = True

        active = [m for m in self.metadata if not m["deleted"]]
        if active:
            vectors = np.stack([m["vector"] for m in active]).astype(np.float32)
            new_index = faiss.IndexFlatIP(settings.embedding_dim)
            new_index.add(vectors)
            for new_id, entry in enumerate(active):
                entry["faiss_id"] = new_id
            self.index = new_index
            self.metadata = active
        else:
            self.index = faiss.IndexFlatIP(settings.embedding_dim)
            self.metadata = []

        self._save()

    def _save(self):
        faiss.write_index(self.index, self.index_path)
        with open(self.meta_path, "wb") as f:
            pickle.dump(self.metadata, f)

    def _rebuild_bm25(self):
        active_texts = [
            _tokenize(m["chunk_text"])
            for m in self.metadata
            if not m.get("deleted")
        ]
        self._bm25 = BM25Okapi(active_texts) if active_texts else None
        # Map active metadata to BM25 index positions
        self._bm25_meta = [m for m in self.metadata if not m.get("deleted")]

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
        self._rebuild_bm25()
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
            for new_id, entry in enumerate(active):
                entry["faiss_id"] = new_id
            self.index = new_index
            self.metadata = active
        else:
            self.index = faiss.IndexFlatIP(settings.embedding_dim)
            self.metadata = []

        self._save()
        self._rebuild_bm25()

    # ------------------------------------------------------------------ #
    # Search                                                                #
    # ------------------------------------------------------------------ #

    def search(
        self, query_vector: np.ndarray, top_k: int = 5
    ) -> List[Tuple[float, Dict]]:
        """Pure vector search — returns (score, metadata) sorted by descending score."""
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

    def hybrid_search(
        self, query_text: str, query_vector: np.ndarray, top_k: int = 5
    ) -> List[Tuple[float, Dict]]:
        """Hybrid BM25 + vector search merged with Reciprocal Rank Fusion."""
        if self.index.ntotal == 0:
            return []

        candidate_k = min(top_k * 3, self.index.ntotal)

        # --- Vector search ---
        vec_results = self.search(query_vector, top_k=candidate_k)
        vec_rank = {meta["chunk_id"]: rank for rank, (_, meta) in enumerate(vec_results)}

        # --- BM25 search ---
        bm25_rank: dict[int, int] = {}
        if self._bm25 and self._bm25_meta:
            tokens = _tokenize(query_text)
            bm25_scores = self._bm25.get_scores(tokens)
            top_bm25_idx = np.argsort(bm25_scores)[::-1][:candidate_k]
            for rank, idx in enumerate(top_bm25_idx):
                if idx < len(self._bm25_meta):
                    cid = self._bm25_meta[idx]["chunk_id"]
                    bm25_rank[cid] = rank

        # --- Reciprocal Rank Fusion (k=60) ---
        k_rrf = 60
        all_chunk_ids = set(vec_rank) | set(bm25_rank)
        rrf_scores: dict[int, float] = {}
        for cid in all_chunk_ids:
            score = 0.0
            if cid in vec_rank:
                score += 1.0 / (k_rrf + vec_rank[cid])
            if cid in bm25_rank:
                score += 1.0 / (k_rrf + bm25_rank[cid])
            rrf_scores[cid] = score

        # Build result list from vector search metadata (it has the full meta)
        meta_by_cid = {meta["chunk_id"]: (score, meta) for score, meta in vec_results}
        # Also include BM25-only results
        for idx, meta in enumerate(self._bm25_meta or []):
            cid = meta["chunk_id"]
            if cid not in meta_by_cid:
                meta_by_cid[cid] = (0.0, meta)

        ranked = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
        results = []
        for cid, rrf_score in ranked[:top_k]:
            if cid in meta_by_cid:
                orig_score, meta = meta_by_cid[cid]
                results.append((orig_score, meta))

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
