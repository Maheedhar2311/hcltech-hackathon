"""FastAPI app: the fixed contract from guide Section 6 (task E1 and E2).

Endpoints:
  POST /ask                 question (+ optional as_of_date); identity from header X-Student-Id
  POST /ingest              file + metadata JSON (Annex B fields)
  GET  /health              API, SQLite, vector store and LLM status
  GET  /audit/{trace_id}    Annex D audit record
  GET  /sources             Source Register

Services are built once at startup from settings (see app/config.py).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from app.config import Settings, load_settings
from app.contracts import AskRequest, AskResponse, IngestResult
from app.ingestion.service import IngestError, ingest_document
from app.llm.gateway import LLMGateway
from app.orchestrator.graph import Services, ask
from app.retrieval.embedder import HashEmbedder, SentenceTransformerEmbedder
from app.retrieval.store import VectorStore
from app.storage.audit import read_audit

SCHEMA = Path(__file__).resolve().parents[1] / "storage" / "schema.sql"


def build_services(settings: Settings) -> Services:
    settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.sqlite_path, check_same_thread=False)
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    embedder = HashEmbedder() if settings.mock_llm else SentenceTransformerEmbedder(settings.embed_model)
    gateway = LLMGateway(mock=settings.mock_llm, base_url=settings.ollama_base_url, model=settings.ollama_model)
    model_name = "mock" if settings.mock_llm else settings.ollama_model
    return Services(
        conn=conn,
        store=VectorStore(settings.chroma_path),
        embedder=embedder,
        gateway=gateway,
        top_k=settings.top_k,
        min_score=settings.min_score,
        model_name=model_name,
    )


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    settings = settings or load_settings()
    app = FastAPI(title="University Student Services Assistant", version="0.1.0")
    svc = build_services(settings)
    app.state.svc = svc

    @app.post("/ask", response_model=AskResponse)
    def post_ask(body: AskRequest, x_student_id: Optional[str] = Header(default=None, alias="X-Student-Id")):
        return ask(svc, body.question, body.as_of_date, x_student_id)

    @app.post("/ingest", response_model=IngestResult, status_code=201)
    async def post_ingest(file: UploadFile = File(...), metadata: str = Form(...)):
        try:
            meta = json.loads(metadata)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=422, detail=f"metadata is not valid JSON: {exc}")
        if not isinstance(meta, dict):
            raise HTTPException(status_code=422, detail="metadata must be a JSON object")
        data = await file.read()
        try:
            return ingest_document(svc.conn, svc.store, svc.embedder, data, file.filename or "", meta)
        except IngestError as exc:
            raise HTTPException(status_code=exc.status, detail=exc.message)

    @app.get("/health")
    def health():
        status = {"api": "ok"}
        try:
            svc.conn.execute("SELECT 1").fetchone()
            status["sqlite"] = "ok"
        except sqlite3.Error as exc:
            status["sqlite"] = f"error: {exc}"
        try:
            svc.store._col.count()
            status["vector_store"] = "ok"
        except Exception as exc:
            status["vector_store"] = f"error: {exc}"
        status["llm"] = svc.gateway.health()
        healthy = status["sqlite"] == "ok" and status["vector_store"] == "ok" and status["llm"] in {"ok", "mock"}
        return JSONResponse(status_code=200 if healthy else 503, content=status)

    @app.get("/audit/{trace_id}")
    def get_audit(trace_id: str):
        record = read_audit(svc.conn, trace_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"no audit record for {trace_id}")
        return record

    @app.get("/sources")
    def get_sources():
        cols = ["doc_id", "title", "issuer", "authority_level", "doc_type", "version", "effective_from",
                "effective_to", "supersedes", "scope_programmes", "scope_batches", "provenance",
                "retrieved_on", "synthetic"]
        rows = svc.conn.execute(f"SELECT {', '.join(cols)} FROM source_register ORDER BY doc_id").fetchall()
        return [dict(zip(cols, r)) for r in rows]

    return app


app = None


def get_app() -> FastAPI:
    """Entry point for `uvicorn app.api.main:get_app --factory`."""
    global app
    if app is None:
        app = create_app()
    return app
