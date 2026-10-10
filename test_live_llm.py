"""Live tests against the local Ollama model (qwen2.5:7b). Skipped if Ollama is not running.

Run with:  .venv/bin/python -m pytest tests/integration/test_live_llm.py -s

These check the parts that only the real model exercises:
- the classifier returns one allowed category for each question,
- the explanation uses the facts it is given,
- the number check replaces an explanation that invents a number,
- one full question (eligibility) works end to end with the live model.

The embedder is the deterministic hash embedder, so the test does not need the
MiniLM download. Retrieval quality is not tested here.
"""

import json
import sqlite3
import urllib.request
from datetime import date
from pathlib import Path

import pytest

from app.contracts import AnswerType, Category
from app.ingestion.service import ingest_document
from app.llm.gateway import LLMGateway, numbers_in
from app.orchestrator.graph import Services, ask
from app.retrieval.embedder import HashEmbedder
from app.retrieval.store import VectorStore
from app.storage.rules import load_rules_csv
from app.storage.source_register import load_source_register

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "src" / "app" / "storage" / "schema.sql"
BASE = "http://localhost:11434"
MODEL = "qwen2.5:7b"
REG_TEXT = ROOT / "data" / "documents" / "text" / "1707823221702-Revised_UG_Regulations__24_Jan_2024.txt"


def _ollama_ready() -> bool:
    try:
        with urllib.request.urlopen(f"{BASE}/api/tags", timeout=5) as resp:
            names = [m["name"] for m in json.loads(resp.read())["models"]]
        return MODEL in names
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _ollama_ready(), reason=f"Ollama with {MODEL} is not running")


@pytest.fixture
def gateway():
    return LLMGateway(mock=False, base_url=BASE, model=MODEL, timeout=300)


@pytest.fixture
def services(tmp_path):
    db = tmp_path / "app.sqlite3"
    conn = sqlite3.connect(db, check_same_thread=False)
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    load_source_register(conn, ROOT / "data" / "documents" / "source_register.csv")
    load_rules_csv(conn, ROOT / "data" / "documents" / "rules.csv")
    conn.executescript("""
        INSERT INTO students VALUES ('S1001','Test One','Computer Science and Engineering',2023,7,7.8,0);
        INSERT INTO courses VALUES ('CSDC0202','Database Management Systems','Computer Science and Engineering',4,3);
        INSERT INTO attendance VALUES ('S1001','CSDC0202',40,30);
    """)
    conn.commit()
    svc = Services(conn=conn, store=VectorStore(tmp_path / "chroma"), embedder=HashEmbedder(),
                   gateway=LLMGateway(mock=False, base_url=BASE, model=MODEL, timeout=300),
                   top_k=5, min_score=0.25, model_name=MODEL)
    yield svc
    conn.close()


CASES = [
    ("What is the minimum attendance required to appear in the end-semester examination?", Category.POLICY),
    ("How do I apply for the supplementary examination?", Category.PROCEDURE),
    ("What is my attendance in CSDC0202?", Category.PERSONAL_DATA),
    ("Am I eligible for the end-semester exam in CSDC0202?", Category.PERSONAL_ELIGIBILITY),
    ("If I fail CSDC0202 and pass the supplementary, will I be eligible for placement?", Category.MULTI_STEP),
]


@pytest.mark.parametrize("question,expected", CASES)
def test_live_classifier_returns_the_expected_category(gateway, question, expected):
    got = gateway.classify(question)
    print(f"\n  classifier: {got.value:22s} expected {expected.value:22s} | {question}")
    # Strict on purpose: a wrong label fails the test.
    assert got == expected, f"wrong label for: {question}"


def test_live_explanation_uses_the_facts_it_is_given(gateway):
    facts = ["Your attendance in CSDC0202 is 75.0%.", "Required attendance is >= 75. Result: eligible."]
    text = gateway.explain("Am I eligible for the end-semester exam in CSDC0202?", facts, template="TEMPLATE")
    print(f"\n  explanation: {text}")
    assert text != "TEMPLATE" or "number not in facts" in " ".join(gateway.stats.fallbacks) or \
        "model unavailable" in " ".join(gateway.stats.fallbacks)
    assert numbers_in(text) <= numbers_in(" ".join(facts)) or text == "TEMPLATE"


def test_number_check_rejects_an_invented_number(gateway):
    """If the model adds a figure the tools did not produce, the template is used instead."""
    class Invents(LLMGateway):
        def _chat(self, messages, schema):
            return {"message": {"content": "Your attendance is 91.7%, so you are eligible."}, "eval_count": 1}

    g = Invents(mock=False)
    out = g.explain("q", ["Your attendance is 75.0%."], template="SAFE")
    assert out == "SAFE"
    assert any("number not in facts" in f for f in g.stats.fallbacks)


def test_live_eligibility_question_end_to_end(services):
    meta = {
        "doc_id": "NITJ-UG-REG-2023", "title": "Ordinances and Regulations for Undergraduate Programme 2023",
        "issuer": "Dr B R Ambedkar NIT Jalandhar", "authority_level": 1, "doc_type": "regulation",
        "version": "2023 (rev. 24 Jan 2024)", "effective_from": "2024-01-24", "scope_programmes": "ALL",
        "scope_batches": "2023+", "synthetic": False,
    }
    # The regulation is already in the register from load_source_register; ingest only adds its text.
    ingest_document(services.conn, services.store, services.embedder, REG_TEXT.read_bytes(),
                    "regulations.txt", meta)
    resp = ask(services, "Am I eligible for the end-semester exam in CSDC0202?", date(2026, 10, 6), "S1001")
    print(f"\n  answer_type: {resp.answer_type.value}\n  answer: {resp.answer}\n  explanation: {resp.explanation}")
    assert resp.answer_type == AnswerType.CALCULATED
    assert "eligible" in resp.answer and "not eligible" not in resp.answer
    audit = services.conn.execute("SELECT record_json FROM audit WHERE trace_id = ?", (resp.trace_id,)).fetchone()
    record = json.loads(audit[0])
    print(f"  llm_calls: {record['llm_calls']}  tokens: {record['tokens']}  fallbacks: {record['fallbacks']}")
    assert record["llm_calls"] >= 1
