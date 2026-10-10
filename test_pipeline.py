"""End-to-end tests: ingest a real document, ask questions, check answers and audit (MOCK mode).

Uses the team's own reference data (Source Register and rules) and the extracted
text of the Revised UG Regulations. Student rows are small fixtures written here.
"""

import csv
import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.config import Settings
from app.storage.rules import load_rules_csv
from app.storage.source_register import load_source_register

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "src" / "app" / "storage" / "schema.sql"
REG_TEXT = ROOT / "data" / "documents" / "text" / "1707823221702-Revised_UG_Regulations__24_Jan_2024.txt"
REG_ID = "NITJ-UG-REG-2023"


def _register_metadata(doc_id: str) -> dict:
    with (ROOT / "data" / "documents" / "source_register.csv").open(encoding="utf-8") as h:
        for row in csv.DictReader(h):
            if row["doc_id"] == doc_id:
                return {k: (v or None) for k, v in row.items() if k != "synthetic"} | {"synthetic": False}
    raise KeyError(doc_id)


@pytest.fixture
def client(tmp_path):
    db = tmp_path / "app.sqlite3"
    conn = sqlite3.connect(db)
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    load_source_register(conn, ROOT / "data" / "documents" / "source_register.csv")
    load_rules_csv(conn, ROOT / "data" / "documents" / "rules.csv")
    conn.executescript("""
        INSERT INTO students VALUES ('S1001','Test One','Computer Science and Engineering',2023,7,7.8,0);
        INSERT INTO students VALUES ('S1002','Test Two','Computer Science and Engineering',2023,7,6.9,1);
        INSERT INTO courses VALUES ('CSDC0202','Database Management Systems','Computer Science and Engineering',4,3);
        INSERT INTO attendance VALUES ('S1001','CSDC0202',40,30);
        INSERT INTO attendance VALUES ('S1002','CSDC0202',40,29);
    """)
    conn.commit()
    conn.close()
    settings = Settings(sqlite_path=db, chroma_path=tmp_path / "chroma", mock_llm=True,
                        ollama_base_url="", ollama_model="", embed_model="", top_k=5, min_score=0.25)
    return TestClient(create_app(settings))


def ingest_regulations(client):
    meta = _register_metadata(REG_ID)
    with REG_TEXT.open("rb") as f:
        return client.post("/ingest", files={"file": ("regulations.txt", f, "text/plain")},
                           data={"metadata": json.dumps(meta)})


# ---------- ingestion ----------

def test_ingest_real_regulations_returns_chunks(client):
    r = ingest_regulations(client)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["doc_id"] == REG_ID and body["chunks_indexed"] > 10 and body["status"] == "indexed"


def test_duplicate_doc_id_is_rejected_with_409(client):
    ingest_regulations(client)
    r = ingest_regulations(client)
    assert r.status_code == 409


def test_invalid_metadata_is_rejected_with_422(client):
    meta = _register_metadata(REG_ID) | {"authority_level": 9}
    r = client.post("/ingest", files={"file": ("x.txt", b"some text here for the file", "text/plain")},
                    data={"metadata": json.dumps(meta)})
    assert r.status_code == 422


def test_file_without_text_is_rejected_with_422(client):
    meta = _register_metadata(REG_ID)
    r = client.post("/ingest", files={"file": ("x.txt", b"   ", "text/plain")}, data={"metadata": json.dumps(meta)})
    assert r.status_code == 422


def test_metadata_must_be_json(client):
    r = client.post("/ingest", files={"file": ("x.txt", b"text", "text/plain")}, data={"metadata": "{bad"})
    assert r.status_code == 422


# ---------- policy questions ----------

def test_policy_question_answers_from_ingested_text_with_citation(client):
    ingest_regulations(client)
    r = client.post("/ask", json={"question": "What is the minimum attendance required to appear in the end-semester examination?",
                                  "as_of_date": "2026-10-06"})
    body = r.json()
    assert r.status_code == 200
    assert body["answer_type"] == "retrieved_fact", body
    assert body["citations"] and body["citations"][0]["doc_id"] == REG_ID
    assert body["trace_id"]


def test_question_with_no_matching_source_is_not_found(client):
    ingest_regulations(client)
    r = client.post("/ask", json={"question": "What is the scholarship for studying in Antarctica?"})
    body = r.json()
    assert body["answer_type"] == "not_found"
    assert body["answer"] == "I could not find this information in the authorised university sources."


def test_question_before_any_document_is_not_found(client):
    r = client.post("/ask", json={"question": "What is the minimum attendance required for the exam?"})
    assert r.json()["answer_type"] == "not_found"


def test_live_ingest_is_used_without_restart(client):
    assert client.post("/ask", json={"question": "Mid semester examination instructions for students"}).json()["answer_type"] == "not_found"
    meta = _register_metadata("NITJ-MIDSEM-2026-09")
    with (ROOT / "data" / "documents" / "text" / "Instruction_to_Students_Mid-Semester_Examination_September-2026.txt").open("rb") as f:
        r = client.post("/ingest", files={"file": ("midsem.txt", f, "text/plain")}, data={"metadata": json.dumps(meta)})
    assert r.status_code == 201
    body = client.post("/ask", json={"question": "Mid semester examination instructions for students"}).json()
    assert body["answer_type"] == "retrieved_fact"
    assert body["citations"][0]["doc_id"] == "NITJ-MIDSEM-2026-09"


# ---------- personal questions ----------

def test_eligible_student_gets_calculated_answer_from_tools(client):
    r = client.post("/ask", headers={"X-Student-Id": "S1001"},
                    json={"question": "Am I eligible for the end-semester exam in CSDC0202?"})
    body = r.json()
    assert body["answer_type"] == "calculated"
    assert body["tools_invoked"][0]["tool"] == "get_attendance"
    assert body["applied_rules"][0]["rule_id"] == "ATT-MIN-01"
    assert "eligible" in body["answer"] and "not eligible" not in body["answer"]
    assert "75" in body["applied_rules"][0]["value"]


def test_student_one_class_short_is_not_eligible(client):
    body = client.post("/ask", headers={"X-Student-Id": "S1002"},
                       json={"question": "Am I eligible for the end-semester exam in CSDC0202?"}).json()
    assert body["answer_type"] == "calculated"
    assert "not eligible" in body["answer"]


def test_personal_question_without_identity_is_refused(client):
    body = client.post("/ask", json={"question": "Am I eligible for the end-semester exam in CSDC0202?"}).json()
    assert body["answer_type"] == "refused"


def test_question_naming_another_student_is_refused(client):
    body = client.post("/ask", headers={"X-Student-Id": "S1001"},
                       json={"question": "What is S1002's attendance in CSDC0202?"}).json()
    assert body["answer_type"] == "refused"
    assert "tools_invoked" in body and body["tools_invoked"] == []


def test_personal_question_without_course_asks_which_course(client):
    body = client.post("/ask", headers={"X-Student-Id": "S1001"},
                       json={"question": "What is my attendance?"}).json()
    assert body["answer_type"] == "clarification_needed"


def test_what_if_question_states_its_assumption(client):
    body = client.post("/ask", headers={"X-Student-Id": "S1001"},
                       json={"question": "If I pass CSDC0202 in the supplementary exam, am I eligible?"}).json()
    assert body["answer_type"] == "calculated"
    assert "current record only" in body["explanation"]


def test_ambiguous_question_asks_for_clarification(client):
    body = client.post("/ask", json={"question": "rules?"}).json()
    assert body["answer_type"] == "clarification_needed"


# ---------- audit, sources, health ----------

def test_every_request_has_an_audit_record_including_refusals(client):
    refused = client.post("/ask", json={"question": "Am I eligible for CSDC0202?"}).json()
    audit = client.get(f"/audit/{refused['trace_id']}")
    assert audit.status_code == 200
    record = audit.json()
    assert record["answer_type"] == "refused"
    assert record["question_category"] == "personal_eligibility"
    assert record["model"] == "mock"


def test_unknown_trace_returns_404(client):
    assert client.get("/audit/doesnotexist").status_code == 404


def test_sources_lists_registered_documents(client):
    body = client.get("/sources").json()
    ids = {row["doc_id"] for row in body}
    assert REG_ID in ids and len(ids) == 7  # 6 official + 1 synthetic


def test_health_reports_each_component(client):
    body = client.get("/health").json()
    assert body["api"] == "ok" and body["sqlite"] == "ok" and body["vector_store"] == "ok"
    assert body["llm"] == "mock"


def test_student_with_no_record_gets_not_found_not_an_empty_calculation(client):
    # S1009 is not in the database. The answer must not look like a calculation.
    body = client.post("/ask", headers={"X-Student-Id": "S1009"},
                       json={"question": "Am I eligible for the end-semester exam in CSDC0202?"}).json()
    assert body["answer_type"] == "not_found"
    assert "could not find an attendance record" in body["answer"]
