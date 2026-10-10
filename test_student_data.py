"""Tests for the student data loader and validator (tasks C1' and C2').

These use small fixture folders written into a temp directory. They are test
fixtures, not the team's data.
"""

import sqlite3
from fractions import Fraction
from pathlib import Path

import pytest

from app.storage.students import StudentDataError, load_dataset, read_dataset, validate

SCHEMA = Path(__file__).resolve().parents[2] / "src" / "app" / "storage" / "schema.sql"

STUDENTS = (
    "student_id,full_name,programme,batch_year,current_semester,cgpa,active_backlogs\n"
    "S1001,Test One,B.Tech CSE,2023,5,7.8,0\n"
    "S1002,Test Two,B.Tech CSE,2023,5,6.1,1\n"
)
COURSES = (
    "course_code,course_name,programme,semester,credits\n"
    "CS201,Data Structures,B.Tech CSE,3,4\n"
)
ATTENDANCE = (
    "student_id,course_code,classes_held,classes_attended\n"
    "S1001,CS201,40,30\n"  # exactly 75%
    "S1002,CS201,40,29\n"  # one class below
)
RESULTS = (
    "student_id,course_code,exam_session,exam_type,internal_marks,external_marks,"
    "total_marks,max_marks,result\n"
    "S1001,CS201,2026-MAY,REGULAR,30,45,75,100,PASS\n"
)


def make_folder(tmp_path, students=STUDENTS, courses=COURSES, attendance=ATTENDANCE, results=RESULTS):
    folder = tmp_path / "data"
    folder.mkdir(exist_ok=True)
    (folder / "students.csv").write_text(students, encoding="utf-8")
    (folder / "courses.csv").write_text(courses, encoding="utf-8")
    (folder / "attendance.csv").write_text(attendance, encoding="utf-8")
    (folder / "results.csv").write_text(results, encoding="utf-8")
    return folder


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.executescript(SCHEMA.read_text(encoding="utf-8"))
    yield c
    c.close()


# ---------- C2': validation ----------

def test_valid_folder_has_no_violations(tmp_path):
    errors, _ = validate(read_dataset(make_folder(tmp_path)))
    assert errors == []


def test_attended_above_held_is_reported_with_line(tmp_path):
    bad = ATTENDANCE.replace("S1001,CS201,40,30", "S1001,CS201,40,41")
    errors, _ = validate(read_dataset(make_folder(tmp_path, attendance=bad)))
    assert any("attendance.csv line 2" in e and "between 0 and classes_held" in e for e in errors)


def test_total_must_equal_internal_plus_external(tmp_path):
    bad = RESULTS.replace("30,45,75", "30,45,80")
    errors, _ = validate(read_dataset(make_folder(tmp_path, results=bad)))
    assert any("total_marks (80)" in e for e in errors)


def test_result_pass_below_pass_mark_is_reported_when_pass_mark_known(tmp_path):
    low = RESULTS.replace("30,45,75,100,PASS", "10,20,30,100,PASS")
    errors, _ = validate(read_dataset(make_folder(tmp_path, results=low)), Fraction(40))
    assert any("below the pass mark" in e for e in errors)


def test_result_check_is_reported_as_skipped_without_pass_mark(tmp_path):
    errors, skipped = validate(read_dataset(make_folder(tmp_path)), None)
    assert errors == []
    assert any("result consistency" in s for s in skipped)


def test_judge_student_id_is_rejected(tmp_path):
    bad = STUDENTS + "S9001,Judge,B.Tech CSE,2023,5,7.0,0\n"
    errors, _ = validate(read_dataset(make_folder(tmp_path, students=bad)))
    assert any("reserved for judges" in e and "S9001" in e for e in errors)


def test_judge_course_code_is_rejected(tmp_path):
    bad = COURSES + "JDG101,Judge Course,B.Tech CSE,1,2\n"
    errors, _ = validate(read_dataset(make_folder(tmp_path, courses=bad)))
    assert any("JDG" in e for e in errors)


def test_bad_student_id_format_is_rejected(tmp_path):
    bad = STUDENTS.replace("S1002", "1002")
    errors, _ = validate(read_dataset(make_folder(tmp_path, students=bad)))
    assert any("S followed by 4 digits" in e for e in errors)


def test_duplicate_attendance_is_rejected(tmp_path):
    bad = ATTENDANCE + "S1001,CS201,10,5\n"
    errors, _ = validate(read_dataset(make_folder(tmp_path, attendance=bad)))
    assert any("duplicate attendance" in e for e in errors)


def test_attendance_for_unknown_student_is_rejected(tmp_path):
    bad = ATTENDANCE + "S7777,CS201,10,5\n"
    errors, _ = validate(read_dataset(make_folder(tmp_path, attendance=bad)))
    assert any("S7777" in e and "not in students.csv" in e for e in errors)


def test_cgpa_out_of_range_is_rejected(tmp_path):
    bad = STUDENTS.replace("7.8", "11.2")
    errors, _ = validate(read_dataset(make_folder(tmp_path, students=bad)))
    assert any("cgpa must be 0.00-10.00" in e for e in errors)


# ---------- C1': loading is all-or-nothing ----------

def test_valid_folder_loads_every_table(tmp_path, conn):
    counts = load_dataset(conn, make_folder(tmp_path))
    assert counts == {"students": 2, "courses": 1, "attendance": 2, "results": 1}
    assert conn.execute("SELECT COUNT(*) FROM attendance").fetchone()[0] == 2


def test_invalid_folder_writes_nothing(tmp_path, conn):
    bad = ATTENDANCE.replace("S1001,CS201,40,30", "S1001,CS201,40,41")
    with pytest.raises(StudentDataError) as info:
        load_dataset(conn, make_folder(tmp_path, attendance=bad))
    assert info.value.errors
    assert conn.execute("SELECT COUNT(*) FROM students").fetchone()[0] == 0


def test_database_constraint_failure_rolls_back_everything(tmp_path, conn):
    # Python checks pass, but the schema rejects a duplicate key in students.
    dup = STUDENTS + "S1001,Dup,B.Tech CSE,2023,5,7.0,0\n"
    with pytest.raises(StudentDataError):
        load_dataset(conn, make_folder(tmp_path, students=dup))
    assert conn.execute("SELECT COUNT(*) FROM students").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM courses").fetchone()[0] == 0


def test_missing_file_is_reported(tmp_path, conn):
    folder = make_folder(tmp_path)
    (folder / "results.csv").unlink()
    with pytest.raises(FileNotFoundError):
        load_dataset(conn, folder)
