"""Tests for the SQLite schema against guide Annex C (task T0.2)."""

import sqlite3
from pathlib import Path

import pytest

SCHEMA = Path(__file__).resolve().parents[2] / "src" / "app" / "storage" / "schema.sql"


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    conn.execute(
        "INSERT INTO source_register (doc_id, title, issuer, authority_level, doc_type, "
        "version, effective_from) VALUES ('ACAD-REG-2024', 'Academic Regulations', "
        "'Dean', 1, 'regulation', '3.1', '2024-07-01')"
    )
    conn.execute(
        "INSERT INTO students (student_id, full_name, programme, batch_year, "
        "current_semester, cgpa, active_backlogs) VALUES "
        "('S1001', 'Test Student', 'B.Tech CSE', 2023, 5, 7.8, 0)"
    )
    conn.execute(
        "INSERT INTO courses (course_code, course_name, programme, semester, credits) "
        "VALUES ('CS201', 'Data Structures', 'B.Tech CSE', 3, 4)"
    )
    conn.commit()
    yield conn
    conn.close()


def expect_rejected(db, sql, params=()):
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(sql, params)


def test_schema_creates_all_annex_c_tables(db):
    names = {
        row[0]
        for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"students", "courses", "attendance", "results", "rule_registry"} <= names
    assert {"source_register", "audit"} <= names


def test_valid_attendance_row_is_accepted(db):
    db.execute(
        "INSERT INTO attendance VALUES ('S1001', 'CS201', 40, 31)"
    )
    row = db.execute("SELECT classes_held, classes_attended FROM attendance").fetchone()
    assert row == (40, 31)


def test_attended_cannot_exceed_held(db):
    expect_rejected(db, "INSERT INTO attendance VALUES ('S1001', 'CS201', 40, 41)")


def test_held_must_be_positive(db):
    expect_rejected(db, "INSERT INTO attendance VALUES ('S1001', 'CS201', 0, 0)")


def test_student_id_must_match_s_plus_four_digits(db):
    expect_rejected(
        db,
        "INSERT INTO students VALUES ('1001', 'Bad ID', 'B.Tech CSE', 2023, 5, 7.0, 0)",
    )


@pytest.mark.parametrize("cgpa", [-0.1, 10.01])
def test_cgpa_range(db, cgpa):
    expect_rejected(
        db,
        "INSERT INTO students VALUES ('S1002', 'Bad CGPA', 'B.Tech CSE', 2023, 5, ?, 0)",
        (cgpa,),
    )


def test_semester_range(db):
    expect_rejected(
        db,
        "INSERT INTO students VALUES ('S1003', 'Bad Sem', 'B.Tech CSE', 2023, 11, 7.0, 0)",
    )


def test_negative_backlogs_rejected(db):
    expect_rejected(
        db,
        "INSERT INTO students VALUES ('S1004', 'Bad Backlog', 'B.Tech CSE', 2023, 5, 7.0, -1)",
    )


def test_result_must_be_annex_c_value(db):
    expect_rejected(
        db,
        "INSERT INTO results VALUES ('S1001', 'CS201', '2026-MAY', 'REGULAR', "
        "30, 50, 80, 100, 'MAYBE')",
    )


def test_total_must_equal_internal_plus_external(db):
    expect_rejected(
        db,
        "INSERT INTO results VALUES ('S1001', 'CS201', '2026-MAY', 'REGULAR', "
        "30, 50, 85, 100, 'PASS')",
    )


def test_valid_result_row_is_accepted(db):
    db.execute(
        "INSERT INTO results VALUES ('S1001', 'CS201', '2026-MAY', 'REGULAR', "
        "30, 45, 75, 100, 'PASS')"
    )
    assert db.execute("SELECT COUNT(*) FROM results").fetchone()[0] == 1


def test_exam_type_limited_to_regular_or_supplementary(db):
    expect_rejected(
        db,
        "INSERT INTO results VALUES ('S1001', 'CS201', '2026-MAY', 'OTHER', "
        "30, 45, 75, 100, 'PASS')",
    )


def test_rule_must_cite_existing_source_document(db):
    expect_rejected(
        db,
        "INSERT INTO rule_registry (rule_id, description, parameter, operator, value, "
        "effective_from, source_doc_id, source_section) VALUES ('ATT-MIN-01', 'Min att', "
        "'min_attendance_pct', '>=', '75', '2024-07-01', 'UNKNOWN-DOC', '7.2')",
    )


def test_rule_with_source_is_accepted(db):
    db.execute(
        "INSERT INTO rule_registry (rule_id, description, parameter, operator, value, "
        "effective_from, source_doc_id, source_section) VALUES ('ATT-MIN-01', 'Min att', "
        "'min_attendance_pct', '>=', '75', '2024-07-01', 'ACAD-REG-2024', '7.2')"
    )
    assert db.execute("SELECT COUNT(*) FROM rule_registry").fetchone()[0] == 1


def test_rule_source_section_cannot_be_empty(db):
    expect_rejected(
        db,
        "INSERT INTO rule_registry (rule_id, description, parameter, operator, value, "
        "effective_from, source_doc_id, source_section) VALUES ('ATT-MIN-02', 'x', "
        "'p', '>=', '1', '2024-07-01', 'ACAD-REG-2024', '')",
    )


def test_course_code_must_exist_for_attendance(db):
    expect_rejected(db, "INSERT INTO attendance VALUES ('S1001', 'NOPE', 10, 5)")
