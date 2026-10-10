"""Deterministic student tools (tasks C3', C4', C5').

Every tool is plain Python over SQLite. None uses an LLM. The student ID is a
parameter supplied by the orchestrator from the X-Student-Id header. Tools never
read it from model output or from the question text.

Thresholds come from rule_registry (guide R5, Annex C), never from code.
Comparisons use exact fractions, not rounded percentages, so a value of
74.996% is not treated as 75%. The displayed percentage is rounded to 2 places.
"""

from __future__ import annotations

import operator
import sqlite3
import time
from fractions import Fraction
from typing import Callable

from app.contracts import EligibilityResult, ToolResult, ToolStatus
from app.storage.rules import get_rule

_OPERATORS: dict[str, Callable[[Fraction, Fraction], bool]] = {
    ">=": operator.ge,
    ">": operator.gt,
    "<=": operator.le,
    "<": operator.lt,
    "=": operator.eq,
}


def _timed(tool: str, inputs: dict, fn: Callable[[], ToolResult]) -> ToolResult:
    start = time.perf_counter()
    result = fn()
    result.tool = tool
    result.input = inputs
    result.ms = int((time.perf_counter() - start) * 1000)
    return result


def _error(message: str, rule_id: str | None = None) -> ToolResult:
    return ToolResult(status=ToolStatus.ERROR, error=message, rule_id=rule_id, tool="")


def _attendance_row(conn: sqlite3.Connection, student_id: str, course_code: str):
    return conn.execute(
        "SELECT classes_held, classes_attended FROM attendance "
        "WHERE student_id = ? AND course_code = ?",
        (student_id, course_code),
    ).fetchone()


def get_attendance(conn: sqlite3.Connection, student_id: str, course_code: str) -> ToolResult:
    """C3': classes held, attended and the percentage, computed here."""

    def run() -> ToolResult:
        row = _attendance_row(conn, student_id, course_code)
        if row is None:
            return _error(f"no attendance record for {student_id} in {course_code}")
        held, attended = row
        pct = round(float(Fraction(attended, held) * 100), 2)
        return ToolResult(
            output={"classes_held": held, "classes_attended": attended, "attendance_pct": pct}
        )

    return _timed("get_attendance", {"student_id": student_id, "course_code": course_code}, run)


def check_exam_eligibility(
    conn: sqlite3.Connection, student_id: str, course_code: str, rule_id: str
) -> ToolResult:
    """C4': compare attendance with the threshold in rule_registry.

    Returns ELIGIBLE, NOT_ELIGIBLE, or UNCLEAR when the data needed is missing.
    The rule's cited source is returned with the result.
    """

    def run() -> ToolResult:
        rule = get_rule(conn, rule_id)
        if rule is None:
            return _error(f"rule {rule_id} is not in rule_registry", rule_id)
        if rule.parameter != "min_attendance_pct":
            return _error(f"rule {rule_id} has unsupported parameter {rule.parameter!r}", rule_id)
        if rule.operator not in _OPERATORS:
            return _error(f"rule {rule_id} has unsupported operator {rule.operator!r}", rule_id)

        threshold = Fraction(rule.value)
        row = _attendance_row(conn, student_id, course_code)
        if row is None:
            return ToolResult(
                rule_id=rule_id,
                output={
                    "result": EligibilityResult.UNCLEAR.value,
                    "reason": f"no attendance record for {course_code}",
                    "threshold": rule.value,
                    "source_doc_id": rule.source_doc_id,
                    "source_section": rule.source_section,
                },
            )
        held, attended = row
        actual = Fraction(attended, held) * 100
        passed = _OPERATORS[rule.operator](actual, threshold)
        return ToolResult(
            rule_id=rule_id,
            output={
                "result": (EligibilityResult.ELIGIBLE if passed else EligibilityResult.NOT_ELIGIBLE).value,
                "attendance_pct": round(float(actual), 2),
                "threshold": f"{rule.operator} {rule.value}",
                "source_doc_id": rule.source_doc_id,
                "source_section": rule.source_section,
            },
        )

    return _timed(
        "check_exam_eligibility",
        {"student_id": student_id, "course_code": course_code, "rule_id": rule_id},
        run,
    )


def get_results(conn: sqlite3.Connection, student_id: str, course_code: str) -> ToolResult:
    """C5': every result row for one student and course (regular and supplementary)."""

    def run() -> ToolResult:
        rows = conn.execute(
            "SELECT exam_session, exam_type, internal_marks, external_marks, total_marks, "
            "max_marks, result FROM results WHERE student_id = ? AND course_code = ? "
            "ORDER BY exam_session, exam_type",
            (student_id, course_code),
        ).fetchall()
        if not rows:
            return _error(f"no results for {student_id} in {course_code}")
        return ToolResult(
            output={
                "results": [
                    {
                        "exam_session": r[0],
                        "exam_type": r[1],
                        "internal_marks": r[2],
                        "external_marks": r[3],
                        "total_marks": r[4],
                        "max_marks": r[5],
                        "result": r[6],
                    }
                    for r in rows
                ]
            }
        )

    return _timed("get_results", {"student_id": student_id, "course_code": course_code}, run)
