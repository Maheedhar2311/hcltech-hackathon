"""Evaluation harness (tasks V2-V3, guide Section 7).

Runs every question in tests/eval/eval_set.json against a fresh copy of the
database and a fresh vector store, then writes measured results.

Method (stated in the report):
- Answer correctness: exact, case-insensitive substring checks from the eval set
  (must_contain / must_not_contain). No LLM judge.
- Citation accuracy: the expected document appears in the answer's citations.
- Abstention accuracy: unanswerable items must return not_found; answerable items must not.
- Retrieval hit rate: the expected document appears among the retrieved passages (audit record).
- Latency: wall-clock time per question; p50 and p95 reported.
- LLM calls and tokens: from the audit record.

Usage:
    MOCK_LLM=true  .venv/bin/python scripts/evaluate.py          # deterministic run
    MOCK_LLM=false .venv/bin/python scripts/evaluate.py          # live Ollama + MiniLM
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sqlite3
import statistics
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app.api.main import build_services  # noqa: E402
from app.config import load_settings  # noqa: E402
from app.ingestion.service import ingest_document  # noqa: E402
from app.orchestrator.graph import ask  # noqa: E402

TEXTS = {
    "NITJ-UG-REG-2023": "1707823221702-Revised_UG_Regulations__24_Jan_2024.txt",
    "NITJ-FYC-2023": "1706074410458-First_Year_Curriculum_(2023_onwards).txt",
    "NITJ-NEP-STRUCT-2023": "1724067883973-New_UG_structure-Modified_N.txt",
    "NITJ-CAL-2026-ODD": "1766573734772-Academic_Activities_Calendar_July_-Dec_2026.txt",
    "NITJ-MIDSEM-2026-09": "Instruction_to_Students_Mid-Semester_Examination_September-2026.txt",
    "NITJ-SOP-ACAD-2022": "Standard_operating_procedure_for_the_Academic_Section_17937.txt",
    "SYN-CIRC-ATT-2026": None,  # synthetic, lives in data/documents/synthetic
}
TEXT_DIR = ROOT / "data" / "documents" / "text"
SYN_DIR = ROOT / "data" / "documents" / "synthetic"
GROUPS = ["policy", "version", "unanswerable", "personal", "cross_student", "multi_step", "ambiguous"]


def _text_path(doc_id: str) -> Path:
    if doc_id.startswith("SYN-"):
        return SYN_DIR / "SYN-CIRC-ATT-2026.txt"
    return TEXT_DIR / TEXTS[doc_id]


def _meta_rows() -> list[dict]:
    with (ROOT / "data" / "documents" / "source_register.csv").open(encoding="utf-8") as h:
        rows = list(csv.DictReader(h))
    out = []
    for r in rows:
        if r["doc_id"] not in TEXTS:
            continue
        meta = {k: (v or None) for k, v in r.items()}
        meta["authority_level"] = int(meta["authority_level"])
        meta["synthetic"] = (meta.get("synthetic") or "N") == "Y"
        for key in ("effective_to", "supersedes", "retrieved_on", "provenance", "scope_programmes", "scope_batches"):
            if meta.get(key) is None:
                meta.pop(key, None)
        out.append(meta)
    return out


def _check(item: dict, answer: str, explanation: str, citations: list[dict], answer_type: str) -> dict:
    text = (answer + " " + explanation).lower()
    type_ok = answer_type == item["expect_type"]
    must_ok = all(s.lower() in text for s in item["must_contain"])
    forbid_ok = all(s.lower() not in text for s in item["must_not_contain"])
    cite_ok = None
    if item["expect_doc"]:
        cite_ok = item["expect_doc"] in {c["doc_id"] for c in citations}
    return {"type_ok": type_ok, "content_ok": must_ok and forbid_ok, "cite_ok": cite_ok}


def run(eval_items: list[dict], db_path: Path, mock: bool) -> tuple[list[dict], dict]:
    workdir = Path(tempfile.mkdtemp(prefix="eval-"))
    db_copy = workdir / "app.sqlite3"
    shutil.copy(db_path, db_copy)
    settings = load_settings()
    settings = type(settings)(**{**settings.__dict__, "sqlite_path": db_copy,
                                 "chroma_path": workdir / "chroma", "mock_llm": mock,
                                 "min_score": 0.25 if mock else 0.5})
    svc = build_services(settings)

    ingested = []
    for meta in _meta_rows():
        data = _text_path(meta["doc_id"]).read_bytes()
        result = ingest_document(svc.conn, svc.store, svc.embedder, data, _text_path(meta["doc_id"]).name, meta)
        ingested.append((meta["doc_id"], result.chunks_indexed))

    results = []
    for item in eval_items:
        start = time.perf_counter()
        resp = ask(svc, item["question"], date.fromisoformat(item["as_of"]), item["student_id"])
        elapsed = time.perf_counter() - start
        audit = json.loads(svc.conn.execute("SELECT record_json FROM audit WHERE trace_id = ?",
                                            (resp.trace_id,)).fetchone()[0])
        citations = [c.model_dump(mode="json") for c in resp.citations]
        checks = _check(item, resp.answer, resp.explanation, citations, resp.answer_type.value)
        retrieved_docs = {s["doc_id"] for s in audit["sources_retrieved"]}
        results.append({
            "id": item["id"], "group": item["group"], "question": item["question"],
            "answer_type": resp.answer_type.value, "expect_type": item["expect_type"],
            "answer": resp.answer, "citations": [f"{c['doc_id']} {c['section']}" for c in citations],
            "latency_s": round(elapsed, 3), "llm_calls": audit["llm_calls"], "tokens": audit["tokens"],
            "retrieval_hit": (item["expect_doc"] in retrieved_docs) if item["expect_doc"] else None,
            "fallbacks": audit["fallbacks"],
            **checks,
        })
    return results, {"ingested": ingested, "workdir": str(workdir)}


def summarise(results: list[dict]) -> dict:
    def rate(values):
        values = [v for v in values if v is not None]
        return round(sum(values) / len(values), 3) if values else None

    answerable = [r for r in results if r["expect_type"] != "not_found"]
    unanswerable = [r for r in results if r["expect_type"] == "not_found"]
    latencies = sorted(r["latency_s"] for r in results)
    p95 = latencies[min(len(latencies) - 1, int(round(0.95 * (len(latencies) - 1))))]
    by_group = {}
    for g in GROUPS:
        rows = [r for r in results if r["group"] == g]
        if rows:
            by_group[g] = {"n": len(rows), "type_accuracy": rate([r["type_ok"] for r in rows]),
                           "content_accuracy": rate([r["content_ok"] for r in rows])}
    return {
        "n_questions": len(results),
        "answer_type_accuracy": rate([r["type_ok"] for r in results]),
        "answer_content_accuracy": rate([r["content_ok"] for r in results]),
        "citation_accuracy": rate([r["cite_ok"] for r in results]),
        "abstention_accuracy_unanswerable": rate([r["answer_type"] == "not_found" for r in unanswerable]),
        "false_abstention_answerable": rate([r["answer_type"] == "not_found" for r in answerable]),
        "retrieval_hit_rate": rate([r["retrieval_hit"] for r in results]),
        "latency_p50_s": round(statistics.median(latencies), 3),
        "latency_p95_s": round(p95, 3),
        "llm_calls_per_question": round(statistics.mean(r["llm_calls"] for r in results), 2),
        "tokens_per_question": round(statistics.mean(r["tokens"] for r in results), 1),
        "by_group": by_group,
    }


def write_report(summary: dict, results: list[dict], meta: dict, mode: str, out: Path) -> None:
    lines = [
        "# Evaluation report",
        "",
        f"Run: {date.today().isoformat()} · mode: **{mode}** · questions: {summary['n_questions']}",
        "",
        "## Method",
        "- Answer correctness: case-insensitive substring checks listed in `tests/eval/eval_set.json`. No LLM judge.",
        "- Citation accuracy: expected document is among the answer's citations.",
        "- Abstention: unanswerable items must return `not_found`; answerable items must not.",
        "- Retrieval hit rate: expected document is among the retrieved passages (audit record).",
        "- Latency: wall-clock per question, in this process, on this machine.",
        "- Documents ingested in this run: " + ", ".join(f"{d} ({n} passages)" for d, n in meta["ingested"]),
        "",
        "## Results",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Answer type accuracy | {summary['answer_type_accuracy']} |",
        f"| Answer content accuracy | {summary['answer_content_accuracy']} |",
        f"| Citation accuracy | {summary['citation_accuracy']} |",
        f"| Abstention on unanswerable questions | {summary['abstention_accuracy_unanswerable']} |",
        f"| False abstention on answerable questions | {summary['false_abstention_answerable']} |",
        f"| Retrieval hit rate | {summary['retrieval_hit_rate']} |",
        f"| Latency p50 / p95 (s) | {summary['latency_p50_s']} / {summary['latency_p95_s']} |",
        f"| LLM calls per question | {summary['llm_calls_per_question']} |",
        f"| Tokens per question | {summary['tokens_per_question']} |",
        "",
        "## By group",
        "",
        "| Group | n | Answer type | Content |",
        "|---|---|---|---|",
    ]
    for g, v in summary["by_group"].items():
        lines.append(f"| {g} | {v['n']} | {v['type_accuracy']} | {v['content_accuracy']} |")
    lines += ["", "## Per question", "", "| ID | Expected | Got | Content ok | Cited | Citations | Latency s |", "|---|---|---|---|---|---|---|"]
    for r in results:
        lines.append(f"| {r['id']} | {r['expect_type']} | {r['answer_type']} | {r['content_ok']} | {r['cite_ok']} | "
                     f"{'; '.join(r['citations']) or '-'} | {r['latency_s']} |")
    fails = [r for r in results if not (r["type_ok"] and r["content_ok"])]
    lines += ["", "## Failures", ""]
    lines += [f"- **{r['id']}** ({r['question']}): got `{r['answer_type']}`, answer: {r['answer'][:200]}" for r in fails] or ["None."]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=ROOT / "data" / "app.sqlite3")
    parser.add_argument("--report", type=Path, default=ROOT / "docs" / "evaluation_report.md")
    parser.add_argument("--json", type=Path, default=ROOT / "tests" / "eval" / "results.json")
    args = parser.parse_args()

    eval_set = json.loads((ROOT / "tests" / "eval" / "eval_set.json").read_text(encoding="utf-8"))["questions"]
    mock = load_settings().mock_llm
    results, meta = run(eval_set, args.db, mock)
    summary = summarise(results)
    mode = "MOCK (deterministic embedder, no LLM)" if mock else "LIVE (MiniLM embedder, qwen2.5:7b)"
    write_report(summary, results, meta, mode, args.report)
    args.json.write_text(json.dumps({"summary": summary, "results": results}, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
