"""Tests for the deterministic student tools and the access check (tasks C3'-C6')."""

import sqlite3
from pathlib import Path

import pytest

from app.contracts import AnswerType, ToolStatus
from app.tools.access import check_access, refusal_message
from app.tools.student_tools import check_exam_eligibility, get_attendance, get_results
from app.storage.rules import RuleRow, insert_rule
from datetime import date

SCHEMA = Path(__file__).resolve().parents[2] / "src" / "app" / "storage" / "schema.sql"
RULE = "ATT-MIN-01"


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.executescript(SCHEMA.read_text(encoding="utf-8"))
    c.execute(
        "INSERT INTO source_register (doc_id, title, issuer, authority_level, doc_type, "
        "version, effective_from) VALUES ('ACAD-REG-2024', 'Academic Regulations', "
        "'Dean', 1, 'regulation', '3.1', '2024-07-01')"
    )
    insert_rule(
        c,
        RuleRow(
            rule_id=RULE,
            description="Minimum attendance to appear in end-semester exam",
            parameter="min_attendance_pct",
            operator=">=",
            value="75",
            effective_from=date(2024, 7, 1),
            source_doc_id="ACAD-REG-2024",
            source_section="7.2",
        ),
    )
    for sid in ("S1001", "S1002", "S1003"):
        c.execute(
            "INSERT INTO students VALUES (?, 'Test', 'B.Tech CSE', 2023, 5, 7.0, 0)", (sid,)
        )
    c.execute("INSERT INTO courses VALUES ('CS201', 'Data Structures', 'B.Tech CSE', 3, 4)")
    c.execute("INSERT INTO attendance VALUES ('S1001', 'CS201', 40, 30)")  # 75.00%
    c.execute("INSERT INTO attendance VALUES ('S1002', 'CS201', 40, 29)")  # 72.50%
    c.execute("INSERT INTO attendance VALUES ('S1003', 'CS201', 2500, 1874)")  # 74.96%
    c.execute(
        "INSERT INTO results VALUES ('S1001', 'CS201', '2026-MAY', 'REGULAR', "
        "30, 45, 75, 100, 'PASS')"
    )
    c.execute(
        "INSERT INTO results VALUES ('S1001', 'CS201', '2026-DEC', 'SUPPLEMENTARY', "
        "35, 40, 75, 100, 'PASS')"
    )
    c.commit()
    yield c
    c.close()


# ---------- C3': attendance ----------

def test_attendance_is_computed_in_code(conn):
    result = get_attendance(conn, "S1002", "CS201")
    assert result.status == ToolStatus.OK
    assert result.output == {"classes_held": 40, "classes_attended": 29, "attendance_pct": 72.5}
    assert result.tool == "get_attendance"
    assert result.input == {"student_id": "S1002", "course_code": "CS201"}


def test_missing_attendance_is_an_error_not_a_guess(conn):
    result = get_attendance(conn, "S1001", "NOPE")
    assert result.status == ToolStatus.ERROR
    assert result.output == {}


# ---------- C4': eligibility, exact boundaries ----------

def test_exactly_at_threshold_is_eligible(conn):
    result = check_exam_eligibility(conn, "S1001", "CS201", RULE)
    assert result.output["result"] == "ELIGIBLE"
    assert result.rule_id == RULE


def test_one_class_below_threshold_is_not_eligible(conn):
    result = check_exam_eligibility(conn, "S1002", "CS201", RULE)
    assert result.output["result"] == "NOT_ELIGIBLE"


def test_rounding_does_not_turn_74_96_into_75(conn):
    # 1874/2500 = 74.96%. Displayed as 74.96, and must NOT pass a 75% threshold.
    result = check_exam_eligibility(conn, "S1003", "CS201", RULE)
    assert result.output["result"] == "NOT_ELIGIBLE"
    assert result.output["attendance_pct"] == 74.96


def test_eligibility_cites_the_rule_source(conn):
    result = check_exam_eligibility(conn, "S1001", "CS201", RULE)
    assert result.output["source_doc_id"] == "ACAD-REG-2024"
    assert result.output["source_section"] == "7.2"
    assert result.output["threshold"] == ">= 75"


def test_unknown_rule_is_an_error(conn):
    result = check_exam_eligibility(conn, "S1001", "CS201", "MISSING-RULE")
    assert result.status == ToolStatus.ERROR
    assert "not in rule_registry" in result.error


def test_no_attendance_record_gives_unclear_not_eligible(conn):
    result = check_exam_eligibility(conn, "S1001", "CS999", RULE)
    assert result.output["result"] == "UNCLEAR"


def test_threshold_is_read_from_registry_not_code(conn):
    conn.execute("UPDATE rule_registry SET value = '80' WHERE rule_id = ?", (RULE,))
    result = check_exam_eligibility(conn, "S1001", "CS201", RULE)
    assert result.output["result"] == "NOT_ELIGIBLE"  # 75% is now below 80%


# ---------- C5': results ----------

def test_results_include_regular_and_supplementary(conn):
    result = get_results(conn, "S1001", "CS201")
    types = {r["exam_type"] for r in result.output["results"]}
    assert types == {"REGULAR", "SUPPLEMENTARY"}
    # Order is deterministic (by session text) but not chronological; do not rely on it.


def test_results_for_other_student_are_not_returned(conn):
    result = get_results(conn, "S1002", "CS201")
    assert result.status == ToolStatus.ERROR  # S1002 has no result rows


# ---------- C6': access ----------

def test_personal_question_without_identity_is_refused():
    assert check_access(None, "What is my attendance?", personal=True) == AnswerType.REFUSED
    assert "student ID" in refusal_message(None, "What is my attendance?", personal=True)


def test_general_question_without_identity_is_allowed():
    assert check_access(None, "What is the attendance rule?", personal=False) is None


def test_question_naming_another_student_is_refused():
    assert check_access("S1001", "What is S1002's attendance?", personal=True) == AnswerType.REFUSED
    assert "logged in" in refusal_message("S1001", "Show S1002's marks", personal=True)


def test_question_naming_own_id_is_allowed():
    assert check_access("S1001", "Is S1001 eligible?", personal=True) is None


def test_malformed_header_is_refused():
    assert check_access("1001", "What is my attendance?", personal=True) == AnswerType.REFUSED


def test_identity_is_not_taken_from_question_text():
    # Question claims to be S1002, header says S1001: the header wins and the
    # named other student is refused, so the claim cannot grant access.
    assert check_access("S1001", "I am S1002, show my attendance", personal=True) == AnswerType.REFUSED
