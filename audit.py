"""Audit store (task C13, guide R10 and Annex D). One row per request, including refusals."""

from __future__ import annotations

import sqlite3
from typing import Optional

from app.contracts import AuditRecord


def write_audit(conn: sqlite3.Connection, record: AuditRecord) -> None:
    with conn:
        conn.execute(
            "INSERT INTO audit (trace_id, timestamp, student_id, question_category, answer_type, "
            "latency_ms, record_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                record.trace_id,
                record.timestamp.isoformat(),
                record.student_id,
                record.question_category.value if record.question_category else None,
                record.answer_type.value,
                record.latency_ms,
                record.model_dump_json(),
            ),
        )


def read_audit(conn: sqlite3.Connection, trace_id: str) -> Optional[AuditRecord]:
    row = conn.execute("SELECT record_json FROM audit WHERE trace_id = ?", (trace_id,)).fetchone()
    return AuditRecord.model_validate_json(row[0]) if row else None
