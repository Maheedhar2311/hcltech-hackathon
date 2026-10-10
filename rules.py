"""Rule registry storage (tasks B1 and B2).

Thresholds used by tools and precedence live in the `rule_registry` table,
never in code (guide Annex C). Each rule must cite a source document that
exists in the Source Register and a non-empty clause.

Loading a CSV is all-or-nothing: if any row is invalid, nothing is written.
"""

from __future__ import annotations

import csv
import sqlite3
from datetime import date
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

Operator = Literal[">=", "<=", ">", "<", "=", "BETWEEN"]


class RuleRow(BaseModel):
    """One row of rule_registry (guide Annex C)."""

    rule_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    parameter: str = Field(min_length=1)
    operator: Operator
    value: str = Field(min_length=1)
    scope_programmes: str = "ALL"
    scope_batches: str = "ALL"
    effective_from: date
    effective_to: Optional[date] = None
    source_doc_id: str = Field(min_length=1)
    source_section: str = Field(min_length=1)

    @field_validator("effective_to")
    @classmethod
    def _to_after_from(cls, value, info):
        start = info.data.get("effective_from")
        if value is not None and start is not None and value < start:
            raise ValueError("effective_to must not be before effective_from")
        return value


class RuleLoadError(ValueError):
    """Raised when a rules CSV has invalid rows. Carries one message per bad row."""

    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


_INSERT = (
    "INSERT INTO rule_registry (rule_id, description, parameter, operator, value, "
    "scope_programmes, scope_batches, effective_from, effective_to, source_doc_id, "
    "source_section) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)


def _source_exists(conn: sqlite3.Connection, doc_id: str) -> bool:
    row = conn.execute("SELECT 1 FROM source_register WHERE doc_id = ?", (doc_id,)).fetchone()
    return row is not None


def _params(rule: RuleRow) -> tuple:
    return (
        rule.rule_id,
        rule.description,
        rule.parameter,
        rule.operator,
        rule.value,
        rule.scope_programmes,
        rule.scope_batches,
        rule.effective_from.isoformat(),
        rule.effective_to.isoformat() if rule.effective_to else None,
        rule.source_doc_id,
        rule.source_section,
    )


def insert_rule(conn: sqlite3.Connection, rule: RuleRow) -> None:
    """Insert one rule. Raises ValueError if its source document is not registered."""
    if not _source_exists(conn, rule.source_doc_id):
        raise ValueError(f"rule {rule.rule_id}: unknown source_doc_id {rule.source_doc_id!r}")
    with conn:
        conn.execute(_INSERT, _params(rule))


def get_rule(conn: sqlite3.Connection, rule_id: str) -> Optional[RuleRow]:
    """Return one rule by id, or None if it is not registered."""
    row = conn.execute(
        "SELECT rule_id, description, parameter, operator, value, scope_programmes, "
        "scope_batches, effective_from, effective_to, source_doc_id, source_section "
        "FROM rule_registry WHERE rule_id = ?",
        (rule_id,),
    ).fetchone()
    if row is None:
        return None
    return RuleRow(
        rule_id=row[0],
        description=row[1],
        parameter=row[2],
        operator=row[3],
        value=row[4],
        scope_programmes=row[5],
        scope_batches=row[6],
        effective_from=row[7],
        effective_to=row[8],
        source_doc_id=row[9],
        source_section=row[10],
    )


def load_rules_csv(conn: sqlite3.Connection, path: Path) -> int:
    """Load rules from a CSV file with the rule_registry columns.

    All-or-nothing: every row is validated first. If any row fails, no rows
    are written and RuleLoadError lists every problem with its line number.
    Returns the number of rules inserted.
    """
    rules: list[RuleRow] = []
    errors: list[str] = []
    with Path(path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for line_no, raw in enumerate(reader, start=2):  # line 1 is the header
            data = {
                k: v.strip()
                for k, v in raw.items()
                if k in RuleRow.model_fields and isinstance(v, str)
            }
            data["effective_to"] = data.get("effective_to") or None
            data["scope_programmes"] = data.get("scope_programmes") or "ALL"
            data["scope_batches"] = data.get("scope_batches") or "ALL"
            try:
                rule = RuleRow(**data)
            except ValueError as exc:  # pydantic's ValidationError is a ValueError
                errors.append(f"line {line_no}: {exc}")
                continue
            if not _source_exists(conn, rule.source_doc_id):
                errors.append(f"line {line_no}: unknown source_doc_id {rule.source_doc_id!r}")
                continue
            rules.append(rule)

    if errors:
        raise RuleLoadError(errors)

    try:
        with conn:  # one transaction for the whole file
            conn.executemany(_INSERT, [_params(r) for r in rules])
    except sqlite3.IntegrityError as exc:
        # e.g. a rule_id that is already registered. Nothing from this file is kept.
        raise RuleLoadError([f"database rejected the rules file: {exc}"]) from exc
    return len(rules)
