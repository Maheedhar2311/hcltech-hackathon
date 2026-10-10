"""Tests for the rule registry (tasks B1 and B2)."""

import sqlite3
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.storage.rules import RuleLoadError, RuleRow, get_rule, insert_rule, load_rules_csv

SCHEMA = Path(__file__).resolve().parents[2] / "src" / "app" / "storage" / "schema.sql"

CSV_HEADER = (
    "rule_id,description,parameter,operator,value,scope_programmes,scope_batches,"
    "effective_from,effective_to,source_doc_id,source_section\n"
)


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    conn.execute(
        "INSERT INTO source_register (doc_id, title, issuer, authority_level, doc_type, "
        "version, effective_from) VALUES ('ACAD-REG-2024', 'Academic Regulations', "
        "'Dean', 1, 'regulation', '3.1', '2024-07-01')"
    )
    conn.commit()
    yield conn
    conn.close()


def rule(**overrides):
    data = dict(
        rule_id="ATT-MIN-01",
        description="Minimum attendance to appear in end-semester exam",
        parameter="min_attendance_pct",
        operator=">=",
        value="75",
        effective_from=date(2024, 7, 1),
        source_doc_id="ACAD-REG-2024",
        source_section="7.2",
    )
    data.update(overrides)
    return RuleRow(**data)


# ---------- B1 ----------

def test_insert_and_read_back_a_rule(db):
    insert_rule(db, rule())
    stored = get_rule(db, "ATT-MIN-01")
    assert stored.value == "75"
    assert stored.source_doc_id == "ACAD-REG-2024"
    assert stored.source_section == "7.2"


def test_rule_without_source_section_is_rejected_by_model():
    with pytest.raises(ValidationError):
        rule(source_section="")


def test_rule_citing_unknown_document_is_rejected(db):
    with pytest.raises(ValueError, match="unknown source_doc_id"):
        insert_rule(db, rule(source_doc_id="NOT-REGISTERED"))
    assert get_rule(db, "ATT-MIN-01") is None


def test_unknown_rule_returns_none(db):
    assert get_rule(db, "NOPE") is None


def test_effective_to_before_effective_from_is_rejected():
    with pytest.raises(ValidationError):
        rule(effective_to=date(2023, 1, 1))


def test_operator_must_be_allowed():
    with pytest.raises(ValidationError):
        rule(operator="~=")


# ---------- B2 ----------

def write_csv(tmp_path, body):
    path = tmp_path / "rules.csv"
    path.write_text(CSV_HEADER + body, encoding="utf-8")
    return path


def test_csv_loads_all_valid_rows(db, tmp_path):
    path = write_csv(
        tmp_path,
        "ATT-MIN-01,Min attendance,min_attendance_pct,>=,75,ALL,ALL,2024-07-01,,ACAD-REG-2024,7.2\n"
        "ATT-MIN-02,Min attendance for supplementary,min_attendance_pct,>=,80,ALL,ALL,2024-07-01,,ACAD-REG-2024,7.3\n",
    )
    assert load_rules_csv(db, path) == 2
    assert get_rule(db, "ATT-MIN-02").value == "80"


def test_csv_with_one_bad_row_writes_nothing(db, tmp_path):
    path = write_csv(
        tmp_path,
        "ATT-MIN-01,Good,min_attendance_pct,>=,75,ALL,ALL,2024-07-01,,ACAD-REG-2024,7.2\n"
        "ATT-MIN-02,Bad source,min_attendance_pct,>=,80,ALL,ALL,2024-07-01,,UNKNOWN-DOC,7.3\n",
    )
    with pytest.raises(RuleLoadError) as info:
        load_rules_csv(db, path)
    assert any("line 3" in e and "UNKNOWN-DOC" in e for e in info.value.errors)
    assert get_rule(db, "ATT-MIN-01") is None  # the good row was not written either


def test_csv_reports_every_bad_row_with_line_number(db, tmp_path):
    path = write_csv(
        tmp_path,
        "ATT-MIN-01,x,p,~=,75,ALL,ALL,2024-07-01,,ACAD-REG-2024,7.2\n"
        "ATT-MIN-02,x,p,>=,80,ALL,ALL,2024-07-01,,ACAD-REG-2024,\n",
    )
    with pytest.raises(RuleLoadError) as info:
        load_rules_csv(db, path)
    assert len(info.value.errors) == 2
    assert info.value.errors[0].startswith("line 2")
    assert info.value.errors[1].startswith("line 3")


def test_csv_with_already_registered_rule_is_rejected_and_nothing_written(db, tmp_path):
    path = write_csv(
        tmp_path,
        "ATT-MIN-01,Min attendance,min_attendance_pct,>=,75,ALL,ALL,2024-07-01,,ACAD-REG-2024,7.2\n",
    )
    load_rules_csv(db, path)
    with pytest.raises(RuleLoadError, match="database rejected"):
        load_rules_csv(db, path)  # same rule_id again
    assert db.execute("SELECT COUNT(*) FROM rule_registry").fetchone()[0] == 1


def test_csv_blank_optional_columns_use_defaults(db, tmp_path):
    path = write_csv(
        tmp_path,
        "ATT-MIN-01,Min attendance,min_attendance_pct,>=,75,,,2024-07-01,,ACAD-REG-2024,7.2\n",
    )
    load_rules_csv(db, path)
    stored = get_rule(db, "ATT-MIN-01")
    assert stored.scope_programmes == "ALL"
    assert stored.scope_batches == "ALL"
    assert stored.effective_to is None
