"""Retrieval with a score gate (task A6, guide R3).

Returns the top-k chunks for a question. If even the best chunk is below
min_score, returns nothing, so the caller answers "not found" instead of
guessing from weak matches.
"""

from __future__ import annotations

from app.contracts import Chunk
from app.retrieval.embedder import Embedder
from app.retrieval.store import VectorStore


def retrieve(store: VectorStore, embedder: Embedder, question: str,
             top_k: int, min_score: float) -> list[Chunk]:
    vector = embedder.embed([question])[0]
    chunks = store.query(vector, top_k)
    if not chunks or chunks[0].score < min_score:
        return []
    return [c for c in chunks if c.score >= min_score]
