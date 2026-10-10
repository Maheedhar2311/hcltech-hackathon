"""The UI's HTTP client against a real API server, and the Streamlit page in Streamlit's test runner.

The API runs in a background thread on a free local port (MOCK mode, temporary data).
"""

import json
import socket
import sqlite3
import threading
import time
from pathlib import Path

import pytest
import uvicorn

from app.config import Settings
from app.api.main import create_app
from app.storage.rules import load_rules_csv
from app.storage.source_register import load_source_register
from app.ui import client

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "src" / "app" / "storage" / "schema.sql"
REG_TEXT = ROOT / "data" / "documents" / "text" / "1707823221702-Revised_UG_Regulations__24_Jan_2024.txt"
UI_FILE = ROOT / "src" / "app" / "ui" / "app.py"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("ui")
    db = tmp / "app.sqlite3"
    conn = sqlite3.connect(db)
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    load_source_register(conn, ROOT / "data" / "documents" / "source_register.csv")
    load_rules_csv(conn, ROOT / "data" / "documents" / "rules.csv")
    conn.executescript("""
        INSERT INTO students VALUES ('S1001','Test One','Computer Science and Engineering',2023,7,7.8,0);
        INSERT INTO courses VALUES ('CSDC0202','Database Management Systems','Computer Science and Engineering',4,3);
        INSERT INTO attendance VALUES ('S1001','CSDC0202',40,30);
    """)
    conn.commit()
    conn.close()
    settings = Settings(sqlite_path=db, chroma_path=tmp / "chroma", mock_llm=True, ollama_base_url="",
                        ollama_model="", embed_model="", top_k=5, min_score=0.25)
    port = _free_port()
    srv = uvicorn.Server(uvicorn.Config(create_app(settings), host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    srv.should_exit = True
    thread.join(timeout=10)


def test_health_is_reported_through_the_client(server):
    body = client.health(server)
    assert body["api"] == "ok" and body["llm"] == "mock"


def test_ask_through_the_client_returns_the_contract_fields(server):
    out = client.ask(server, "Am I eligible for the end-semester exam in CSDC0202?", None, "S1001")
    assert out["answer_type"] == "calculated"
    assert {"trace_id", "answer", "citations", "tools_invoked", "as_of_date"} <= set(out)


def test_api_error_carries_the_server_message(server):
    with pytest.raises(client.ApiError) as info:
        client.audit(server, "does-not-exist")
    assert info.value.status == 404
    assert "no audit record" in info.value.message


def test_ingest_through_the_client_then_duplicate_is_rejected(server):
    meta = {"doc_id": "NITJ-UG-REG-2023", "title": "Regulations", "issuer": "NIT Jalandhar",
            "authority_level": 1, "doc_type": "regulation", "version": "2023", "effective_from": "2024-01-24",
            "scope_programmes": "ALL", "scope_batches": "2023+", "synthetic": False}
    out = client.ingest(server, "regulations.txt", REG_TEXT.read_bytes(), meta)
    assert out["doc_id"] == "NITJ-UG-REG-2023" and out["chunks_indexed"] > 10
    with pytest.raises(client.ApiError) as info:
        client.ingest(server, "regulations.txt", REG_TEXT.read_bytes(), meta)
    assert info.value.status == 409


def test_sources_and_audit_through_the_client(server):
    ids = {row["doc_id"] for row in client.sources(server)}
    assert "NITJ-UG-REG-2023" in ids
    trace = client.ask(server, "What is the minimum attendance to appear in the exam?", None, None)["trace_id"]
    assert client.audit(server, trace)["trace_id"] == trace


def test_streamlit_page_runs_without_exceptions(server, monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("API_URL", server)
    at = AppTest.from_file(str(UI_FILE), default_timeout=60).run()
    assert not at.exception, [e.value for e in at.exception]
    assert any("University Student Services Assistant" in t.value for t in at.title)
