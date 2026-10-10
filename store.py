"""Vector store wrapper around ChromaDB, persisted to disk (tasks A4 and A6).

One collection holds every chunk. Each chunk's metadata carries what precedence
and citations need: doc_id, section, page, version, effective dates, authority
level and scope. Chunks are written once and read on every query, so a document
ingested while the system is running is searchable at once (guide R11).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")  # no usage pings from the vector store
import chromadb  # noqa: E402

from app.contracts import Chunk

COLLECTION = "university_chunks"


class VectorStore:
    def __init__(self, path: Path):
        Path(path).mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(path))
        self._col = self._client.get_or_create_collection(
            name=COLLECTION, metadata={"hnsw:space": "cosine"}
        )

    def add(self, ids: list[str], embeddings: list[list[float]], documents: list[str],
            metadatas: list[dict]) -> None:
        if ids:
            self._col.add(ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas)

    def delete_document(self, doc_id: str) -> None:
        self._col.delete(where={"doc_id": doc_id})

    def count_for(self, doc_id: str) -> int:
        return len(self._col.get(where={"doc_id": doc_id})["ids"])

    def query(self, embedding: list[float], top_k: int) -> list[Chunk]:
        n = self._col.count()
        if n == 0:
            return []
        res = self._col.query(query_embeddings=[embedding], n_results=min(top_k, n))
        out: list[Chunk] = []
        for text, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
            out.append(_to_chunk(text, meta, score=1.0 - float(dist)))  # cosine distance -> similarity
        return out


def _to_chunk(text: str, meta: dict, score: float) -> Chunk:
    from datetime import date

    eff_to: Optional[str] = meta.get("effective_to") or None
    return Chunk(
        doc_id=meta["doc_id"],
        section=meta["section"],
        page=meta.get("page"),
        version=meta["version"],
        effective_from=date.fromisoformat(meta["effective_from"]),
        effective_to=date.fromisoformat(eff_to) if eff_to else None,
        authority_level=int(meta["authority_level"]),
        scope_programmes=meta.get("scope_programmes", "ALL"),
        scope_batches=meta.get("scope_batches", "ALL"),
        text=text,
        score=score,
    )
