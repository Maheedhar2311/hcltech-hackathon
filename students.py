"""Student data loader and validator (tasks C1' and C2').

Reads four CSV files from one folder, checks them against guide Annex C and the
logical rules in the guide, and loads them into SQLite. Loading is
all-or-nothing: if any check fails, nothing is written.

Files expected in the folder:
  students.csv, courses.csv, attendance.csv, results.csv

Checks that need a pass mark (result consistent with marks) use the rule
`pass_mark_pct` from rule_registry, if one is loaded. Without it that check is
reported as skipped, not passed. The pass mark must come from our documents.
"""

from __future__ import annotations

import csv
import re
import sqlite3
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Callable, Optional

from app.storage.rules import get_rule

STUDENT_ID = re.compile(r"^S\d{4}$")
JUDGE_ID = re.compile(r"^S9\d{3}$")  # guide: S9000-S9999 reserved for judges
JUDGE_COURSE = re.compile(r"^JDG")  # guide: JDG course codes reserved for judges
RESULT_VALUES = {"PASS", "FAIL", "ABSENT", "DETAINED"}
EXAM_TYPES = {"REGULAR", "SUPPLEMENTARY"}
PASS_MARK_RULE = "pass_mark_pct"


class StudentDataError(ValueError):
    """Raised when student data fails validation. Carries every problem found."""

    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


@dataclass
class Dataset:
    students: list[dict]
    courses: list[dict]
    attendance: list[dict]
    results: list[dict]


# ---------- reading ----------

def read_csv(path: Path) -> list[tuple[int, dict]]:
    """Return (line_number, row) pairs. Line 1 is the header."""
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return [
            (line_no, {k: (v or "").strip() for k, v in row.items() if k})
            for line_no, row in enumerate(reader, start=2)
        ]


def read_dataset(folder: Path) -> Dataset:
    """Read the four CSVs. Missing files raise FileNotFoundError."""
    folder = Path(folder)
    return Dataset(
        students=read_csv(folder / "students.csv"),
        courses=read_csv(folder / "courses.csv"),
        attendance=read_csv(folder / "attendance.csv"),
        results=read_csv(folder / "results.csv"),
    )


# ---------- validation (task C2') ----------

def _int(row: dict, field: str, errors: list[str], where: str) -> Optional[int]:
    try:
        return int(row[field])
    except (KeyError, ValueError):
        errors.append(f"{where}: {field} must be a whole number, got {row.get(field)!r}")
        return None


def _real(row: dict, field: str, errors: list[str], where: str) -> Optional[float]:
    try:
        return float(row[field])
    except (KeyError, ValueError):
        errors.append(f"{where}: {field} must be a number, got {row.get(field)!r}")
        return None


def validate(data: Dataset, pass_mark_pct: Optional[Fraction] = None,
             ese: Optional[tuple[Fraction, int]] = None) -> tuple[list[str], list[str]]:
    """ese = (minimum end-semester percent, end-semester maximum marks), e.g. (30, 70).
    The end-semester maximum is not stated in the documents; callers must say what they assumed."""
    """Return (violations, skipped_checks). An empty violations list means valid."""
    errors: list[str] = []
    skipped: list[str] = []

    # students
    student_ids: dict[str, str] = {}  # id -> programme
    for line, row in data.students:
        where = f"students.csv line {line}"
        sid = row.get("student_id", "")
        if not STUDENT_ID.match(sid):
            errors.append(f"{where}: student_id must be S followed by 4 digits, got {sid!r}")
        elif JUDGE_ID.match(sid):
            errors.append(f"{where}: {sid} is reserved for judges (S9000-S9999)")
        elif sid in student_ids:
            errors.append(f"{where}: duplicate student_id {sid}")
        if not row.get("full_name"):
            errors.append(f"{where}: full_name is required")
        if not row.get("programme"):
            errors.append(f"{where}: programme is required")
        _int(row, "batch_year", errors, where)
        sem = _int(row, "current_semester", errors, where)
        if sem is not None and not 1 <= sem <= 10:
            errors.append(f"{where}: current_semester must be 1-10, got {sem}")
        cgpa = _real(row, "cgpa", errors, where)
        if cgpa is not None and not 0.0 <= cgpa <= 10.0:
            errors.append(f"{where}: cgpa must be 0.00-10.00, got {cgpa}")
        backlogs = _int(row, "active_backlogs", errors, where)
        if backlogs is not None and backlogs < 0:
            errors.append(f"{where}: active_backlogs must be >= 0, got {backlogs}")
        if sid and row.get("programme"):
            student_ids.setdefault(sid, row["programme"])

    # courses
    course_programmes: dict[str, str] = {}
    for line, row in data.courses:
        where = f"courses.csv line {line}"
        code = row.get("course_code", "")
        if not code:
            errors.append(f"{where}: course_code is required")
            continue
        if JUDGE_COURSE.match(code):
            errors.append(f"{where}: {code} is reserved for judges (JDG prefix)")
        if code in course_programmes:
            errors.append(f"{where}: duplicate course_code {code}")
        course_programmes[code] = row.get("programme", "")
        if row.get("programme") and row["programme"] not in set(student_ids.values()):
            errors.append(f"{where}: programme {row['programme']!r} matches no student programme")
        _int(row, "semester", errors, where)
        _int(row, "credits", errors, where)

    # attendance
    seen_att: set[tuple[str, str]] = set()
    for line, row in data.attendance:
        where = f"attendance.csv line {line}"
        sid, code = row.get("student_id", ""), row.get("course_code", "")
        if sid not in student_ids:
            errors.append(f"{where}: student_id {sid!r} is not in students.csv")
        if code not in course_programmes:
            errors.append(f"{where}: course_code {code!r} is not in courses.csv")
        if (sid, code) in seen_att:
            errors.append(f"{where}: duplicate attendance for {sid} in {code}")
        seen_att.add((sid, code))
        held = _int(row, "classes_held", errors, where)
        attended = _int(row, "classes_attended", errors, where)
        if held is not None and held <= 0:
            errors.append(f"{where}: classes_held must be > 0, got {held}")
        if held is not None and attended is not None and not 0 <= attended <= held:
            errors.append(
                f"{where}: classes_attended must be between 0 and classes_held ({held}), got {attended}"
            )

    # results
    seen_res: set[tuple[str, str, str, str]] = set()
    for line, row in data.results:
        where = f"results.csv line {line}"
        sid, code = row.get("student_id", ""), row.get("course_code", "")
        exam_type = row.get("exam_type", "")
        session = row.get("exam_session", "")
        if sid not in student_ids:
            errors.append(f"{where}: student_id {sid!r} is not in students.csv")
        if code not in course_programmes:
            errors.append(f"{where}: course_code {code!r} is not in courses.csv")
        if exam_type not in EXAM_TYPES:
            errors.append(f"{where}: exam_type must be REGULAR or SUPPLEMENTARY, got {exam_type!r}")
        key = (sid, code, session, exam_type)
        if key in seen_res:
            errors.append(f"{where}: duplicate result for {sid} {code} {session} {exam_type}")
        seen_res.add(key)
        internal = _int(row, "internal_marks", errors, where)
        external = _int(row, "external_marks", errors, where)
        total = _int(row, "total_marks", errors, where)
        max_marks = _int(row, "max_marks", errors, where)
        result = row.get("result", "")
        if result not in RESULT_VALUES:
            errors.append(f"{where}: result must be one of PASS, FAIL, ABSENT, DETAINED, got {result!r}")
        if None not in (internal, external, total):
            if internal < 0 or external < 0:
                errors.append(f"{where}: marks must not be negative")
            if total != internal + external:
                errors.append(
                    f"{where}: total_marks ({total}) must equal internal + external ({internal + external})"
                )
        if max_marks is not None and max_marks <= 0:
            errors.append(f"{where}: max_marks must be > 0, got {max_marks}")
        if None not in (total, max_marks) and total > max_marks:
            errors.append(f"{where}: total_marks ({total}) exceeds max_marks ({max_marks})")
        if pass_mark_pct is None:
            if "result consistency" not in skipped:
                skipped.append("result consistency (no pass_mark_pct rule loaded)")
        if ese is None and "end-semester 30% rule" not in skipped:
            skipped.append("end-semester 30% rule (end-semester maximum not given)")
        if pass_mark_pct is not None and None not in (total, max_marks) and max_marks > 0 and result in {"PASS", "FAIL"}:
            passed = Fraction(total, max_marks) * 100 >= pass_mark_pct
            if ese is not None and external is not None:
                ese_min_pct, ese_max = ese
                passed_ese = Fraction(external, ese_max) * 100 >= ese_min_pct  # R13.3
                passed = passed and passed_ese
            if result == "PASS" and not passed:
                errors.append(f"{where}: result PASS but marks are below the pass mark or the end-semester minimum")
            if result == "FAIL" and passed:
                errors.append(f"{where}: result FAIL but marks meet the pass mark and the end-semester minimum")

    return errors, skipped


EXTERNAL_MAX_ASSUMED = 70  # end-semester maximum marks; assumed, not stated in the documents


def ese_from_registry(conn: sqlite3.Connection) -> Optional[tuple[Fraction, int]]:
    """(minimum end-semester percent, end-semester maximum) from rule esem_min_pct, or None."""
    rule = get_rule(conn, "ESE-MIN-01")
    return (Fraction(rule.value), EXTERNAL_MAX_ASSUMED) if rule else None


def pass_mark_from_registry(conn: sqlite3.Connection) -> Optional[Fraction]:
    """Read the pass mark percentage from rule_registry, or None if not loaded."""
    rule = get_rule(conn, PASS_MARK_RULE)
    if rule is None:
        return None
    return Fraction(rule.value)


# ---------- loading (task C1') ----------

_INSERTS: dict[str, tuple[str, Callable[[dict], tuple]]] = {
    "students": (
        "INSERT INTO students (student_id, full_name, programme, batch_year, "
        "current_semester, cgpa, active_backlogs) VALUES (?, ?, ?, ?, ?, ?, ?)",
        lambda r: (
            r["student_id"], r["full_name"], r["programme"], int(r["batch_year"]),
            int(r["current_semester"]), float(r["cgpa"]), int(r["active_backlogs"]),
        ),
    ),
    "courses": (
        "INSERT INTO courses (course_code, course_name, programme, semester, credits) "
        "VALUES (?, ?, ?, ?, ?)",
        lambda r: (
            r["course_code"], r["course_name"], r["programme"],
            int(r["semester"]), int(r["credits"]),
        ),
    ),
    "attendance": (
        "INSERT INTO attendance (student_id, course_code, classes_held, classes_attended) "
        "VALUES (?, ?, ?, ?)",
        lambda r: (
            r["student_id"], r["course_code"],
            int(r["classes_held"]), int(r["classes_attended"]),
        ),
    ),
    "results": (
        "INSERT INTO results (student_id, course_code, exam_session, exam_type, "
        "internal_marks, external_marks, total_marks, max_marks, result) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        lambda r: (
            r["student_id"], r["course_code"], r["exam_session"], r["exam_type"],
            int(r["internal_marks"]), int(r["external_marks"]), int(r["total_marks"]),
            int(r["max_marks"]), r["result"],
        ),
    ),
}


def load_dataset(conn: sqlite3.Connection, folder: Path) -> dict[str, int]:
    """Validate the folder and load it. All-or-nothing.

    Returns the number of rows inserted per table. Raises StudentDataError
    with every violation found; nothing is written in that case.
    """
    data = read_dataset(folder)
    errors, _skipped = validate(data, pass_mark_from_registry(conn), ese_from_registry(conn))
    if errors:
        raise StudentDataError(errors)

    tables = {
        "students": data.students,
        "courses": data.courses,
        "attendance": data.attendance,
        "results": data.results,
    }
    counts: dict[str, int] = {}
    try:
        with conn:  # one transaction for all four tables
            for table, rows in tables.items():
                sql, to_params = _INSERTS[table]
                conn.executemany(sql, [to_params(row) for _, row in rows])
                counts[table] = len(rows)
    except sqlite3.IntegrityError as exc:
        # Constraints in schema.sql caught something the Python checks missed.
        raise StudentDataError([f"database rejected the data: {exc}"]) from exc
    return counts
