"""Streamlit UI (task E4). Calls the API only; no business logic lives here.

Run locally:
    streamlit run src/app/ui/app.py
Environment:
    API_URL   base address of the API (default http://localhost:8000)
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # so `app.ui.client` imports when run directly

from app.ui import client  # noqa: E402

API_URL = os.environ.get("API_URL", "http://localhost:8000").rstrip("/")

BADGE = {
    "retrieved_fact": ("Fact from a document", "green"),
    "calculated": ("Calculated from your record", "blue"),
    "not_found": ("Not found in sources", "gray"),
    "clarification_needed": ("Clarification needed", "orange"),
    "refused": ("Refused", "red"),
    "conflict_flagged": ("Conflict: please contact the office", "red"),
}

METADATA_TEMPLATE = {
    "doc_id": "EXAMPLE-DOC-2026",
    "title": "Title of the document",
    "issuer": "Issuing office",
    "authority_level": 2,
    "doc_type": "notice",
    "version": "1.0",
    "effective_from": date.today().isoformat(),
    "effective_to": None,
    "supersedes": None,
    "scope_programmes": "ALL",
    "scope_batches": "ALL",
    "provenance": "Where the file came from",
    "retrieved_on": date.today().isoformat(),
    "synthetic": False,
}


def show_health() -> None:
    status = client.health(API_URL)
    overall = all(status.get(k) in ("ok", "mock") for k in ("api", "sqlite", "vector_store", "llm"))
    if overall:
        st.caption(f"Service ready: LLM {status.get('llm')}")
    else:
        st.error("Service not ready: " + json.dumps(status))


def ask_tab() -> None:
    st.subheader("Ask a question")
    question = st.text_area("Your question", placeholder="What is the minimum attendance for the end-semester exam?")
    use_date = st.checkbox("Use a specific as-of date", value=False)
    as_of = st.date_input("As-of date", value=date.today()) if use_date else None
    if st.button("Ask", type="primary", disabled=not question.strip()):
        try:
            st.session_state["last"] = client.ask(API_URL, question.strip(), as_of,
                                                  st.session_state.get("student_id") or None)
        except client.ApiError as exc:
            st.error(f"The service returned an error ({exc.status}): {exc.message}")
        except Exception as exc:
            st.error(f"Could not reach the service at {API_URL}: {exc}")

    result = st.session_state.get("last")
    if not result:
        return
    label, color = BADGE.get(result["answer_type"], (result["answer_type"], "gray"))
    st.markdown(f":{color}[**{label}**]")
    st.write(result["answer"])
    if result.get("explanation") and result["explanation"] != result["answer"]:
        st.caption(result["explanation"])
    if result.get("citations"):
        st.markdown("**Sources**")
        st.table([{k: c.get(k) for k in ("doc_id", "title", "section", "page", "version", "effective_from")}
                  for c in result["citations"]])
    if result.get("applied_rules"):
        st.markdown("**Rules applied**")
        st.table(result["applied_rules"])
    if result.get("conflicts_detected"):
        st.markdown("**Notes on versions and conflicts**")
        for note in result["conflicts_detected"]:
            st.write(f"- {note}")
    if result.get("tools_invoked"):
        with st.expander("Tool calls"):
            st.json(result["tools_invoked"])
    st.caption(f"Trace ID: {result['trace_id']} · as of {result['as_of_date']}")
    if st.checkbox("Show audit record", key=f"audit-{result['trace_id']}"):
        try:
            st.json(client.audit(API_URL, result["trace_id"]))
        except client.ApiError as exc:
            st.error(str(exc))


def ingest_tab() -> None:
    st.subheader("Add a document")
    st.caption("The document is indexed immediately. It does not change any rule until a rule is registered.")
    upload = st.file_uploader("PDF or text file", type=["pdf", "txt", "md"])
    metadata_text = st.text_area("Source Register metadata (JSON)", value=json.dumps(METADATA_TEMPLATE, indent=2), height=320)
    if st.button("Add document", type="primary", disabled=upload is None):
        try:
            metadata = json.loads(metadata_text)
        except json.JSONDecodeError as exc:
            st.error(f"Metadata is not valid JSON: {exc}")
            return
        try:
            out = client.ingest(API_URL, upload.name, upload.getvalue(), metadata)
            st.success(f"Indexed {out['doc_id']}: {out['chunks_indexed']} passages.")
        except client.ApiError as exc:
            st.error(f"Not added ({exc.status}): {exc.message}")
        except Exception as exc:
            st.error(f"Could not reach the service at {API_URL}: {exc}")


def sources_tab() -> None:
    st.subheader("Registered sources")
    try:
        rows = client.sources(API_URL)
    except Exception as exc:
        st.error(f"Could not load sources: {exc}")
        return
    st.dataframe(rows, use_container_width=True)


def main() -> None:
    st.set_page_config(page_title="University Student Services Assistant", page_icon="🎓", layout="wide")
    st.title("University Student Services Assistant")
    with st.sidebar:
        st.text_input("Student ID (sent as X-Student-Id)", key="student_id", placeholder="S1001",
                      help="Needed for questions about your own record. Leave empty for general questions.")
        st.caption(f"API: {API_URL}")
        show_health()
    tab_ask, tab_ingest, tab_sources = st.tabs(["Ask", "Add document", "Sources"])
    with tab_ask:
        ask_tab()
    with tab_ingest:
        ingest_tab()
    with tab_sources:
        sources_tab()


main()  # Streamlit runs this file top to bottom on each interaction
