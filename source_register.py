"""Source Register loader (tasks A1 and V1, guide Annex B).

Reads a CSV with the Annex B columns, validates every row with the SourceMetadata
model, and writes the rows to the `source_register` table. Loading is
all-or-nothing: if any row is invalid, nothing is written.

The same validation is used later by POST /ingest for a single document.
"""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from pydantic import ValidationError

from app.contracts import SourceMetadata


class SourceRegisterError(ValueError):
    """Raised when the Source Register file has invalid rows. Lists every problem."""

    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


_INSERT = (
    "INSERT INTO source_register (doc_id, title, issuer, authority_level, doc_type, version, "
    "effective_from, effective_to, supersedes, scope_programmes, scope_batches, provenance, "
    "retrieved_on, synthetic) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)


def _clean(raw: dict) -> dict:
    """Blank cells become None. Annex B's `synthetic` column is Y/N; it becomes a bool."""
    data = {k: (v.strip() if isinstance(v, str) else v) for k, v in raw.items() if k}
    for key in ("effective_to", "supersedes", "retrieved_on"):
        data[key] = data.get(key) or None
    data["provenance"] = data.get("provenance") or ""
    data["scope_programmes"] = data.get("scope_programmes") or "ALL"
    data["scope_batches"] = data.get("scope_batches") or "ALL"
    data["synthetic"] = (data.get("synthetic") or "N").upper() == "Y"
    return data


def read_source_register(path: Path) -> list[SourceMetadata]:
    """Validate every row. Raises SourceRegisterError listing all bad rows."""
    rows: list[SourceMetadata] = []
    errors: list[str] = []
    seen: set[str] = set()
    with Path(path).open(newline="", encoding="utf-8") as handle:
        for line_no, raw in enumerate(csv.DictReader(handle), start=2):
            try:
                meta = SourceMetadata(**_clean(raw))
            except (ValidationError, TypeError) as exc:
                errors.append(f"line {line_no}: {exc}")
                continue
            if meta.doc_id in seen:
                errors.append(f"line {line_no}: duplicate doc_id {meta.doc_id}")
            seen.add(meta.doc_id)
            rows.append(meta)
    if errors:
        raise SourceRegisterError(errors)
    return rows


def load_source_register(conn: sqlite3.Connection, path: Path) -> int:
    """Validate and insert all rows in one transaction. Returns the row count."""
    rows = read_source_register(path)
    try:
        with conn:
            conn.executemany(
                _INSERT,
                [
                    (
                        m.doc_id, m.title, m.issuer, m.authority_level, m.doc_type, m.version,
                        m.effective_from.isoformat(),
                        m.effective_to.isoformat() if m.effective_to else None,
                        m.supersedes, m.scope_programmes, m.scope_batches, m.provenance,
                        m.retrieved_on.isoformat() if m.retrieved_on else None,
                        1 if m.synthetic else 0,
                    )
                    for m in rows
                ],
            )
    except sqlite3.IntegrityError as exc:
        raise SourceRegisterError([f"database rejected the register: {exc}"]) from exc
    return len(rows)
