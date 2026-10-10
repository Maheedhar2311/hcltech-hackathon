"""Atomic ingest (task A5): a failure part-way through leaves nothing behind."""

import sqlite3
from pathlib import Path

import pytest

from app.ingestion.service import IngestError, ingest_document
from app.retrieval.embedder import HashEmbedder
from app.retrieval.store import VectorStore

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "src" / "app" / "storage" / "schema.sql"
TEXT = b"Clause R1 The minimum attendance for the examination is 75 percent for every student in the course."
META = {"doc_id": "ATOMIC-TEST-1", "title": "Atomic test", "issuer": "Test", "authority_level": 2,
        "doc_type": "notice", "version": "1", "effective_from": "2026-01-01", "synthetic": True}


@pytest.fixture
def env(tmp_path):
    conn = sqlite3.connect(tmp_path / "db.sqlite3")
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    store = VectorStore(tmp_path / "chroma")
    yield conn, store
    conn.close()


def _register_count(conn):
    return conn.execute("SELECT COUNT(*) FROM source_register WHERE doc_id = 'ATOMIC-TEST-1'").fetchone()[0]


def test_vector_store_failure_writes_nothing(env, monkeypatch):
    conn, store = env

    def boom(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(store, "add", boom)
    with pytest.raises(IngestError) as info:
        ingest_document(conn, store, HashEmbedder(), TEXT, "a.txt", META)
    assert info.value.status == 500
    assert _register_count(conn) == 0
    assert store.count_for("ATOMIC-TEST-1") == 0


def test_register_failure_removes_the_chunks_already_written(env):
    conn, store = env
    # Force the register write to fail after the chunks are already in the vector store.
    conn.executescript("""
        CREATE TRIGGER block_register BEFORE INSERT ON source_register
        BEGIN SELECT RAISE(ABORT, 'register write refused'); END;
    """)
    with pytest.raises(IngestError) as info:
        ingest_document(conn, store, HashEmbedder(), TEXT, "a.txt", META)
    assert info.value.status == 500
    assert _register_count(conn) == 0
    assert store.count_for("ATOMIC-TEST-1") == 0  # the chunks were undone


def test_successful_ingest_writes_both(env):
    conn, store = env
    result = ingest_document(conn, store, HashEmbedder(), TEXT, "a.txt", META)
    assert result.chunks_indexed >= 1
    assert _register_count(conn) == 1
    assert store.count_for("ATOMIC-TEST-1") == result.chunks_indexed
