"""Tests for the Source Register loader (tasks A1 and V1, guide Annex B)."""

import sqlite3
from pathlib import Path

import pytest

from app.storage.source_register import SourceRegisterError, load_source_register, read_source_register

SCHEMA = Path(__file__).resolve().parents[2] / "src" / "app" / "storage" / "schema.sql"
HEADER = (
    "doc_id,title,issuer,authority_level,doc_type,version,effective_from,effective_to,"
    "supersedes,scope_programmes,scope_batches,provenance,retrieved_on,synthetic\n"
)


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.executescript(SCHEMA.read_text(encoding="utf-8"))
    yield c
    c.close()


def write(tmp_path, body):
    path = tmp_path / "register.csv"
    path.write_text(HEADER + body, encoding="utf-8")
    return path


GOOD_ROW = (
    "ACAD-REG-2024,Academic Regulations,Dean,1,regulation,3.1,2024-07-01,,,ALL,2023+,"
    "local copy,2026-10-10,N\n"
)


def test_valid_row_loads_and_synthetic_flag_becomes_bool(tmp_path, conn):
    body = GOOD_ROW + "DEMO-2026,Demo Notice,Office,2,notice,1,2026-01-01,,,ALL,ALL,,,Y\n"
    assert load_source_register(conn, write(tmp_path, body)) == 2
    assert conn.execute("SELECT synthetic FROM source_register WHERE doc_id='DEMO-2026'").fetchone()[0] == 1
    assert conn.execute("SELECT synthetic FROM source_register WHERE doc_id='ACAD-REG-2024'").fetchone()[0] == 0


def test_missing_effective_from_is_rejected_with_line_number(tmp_path):
    body = GOOD_ROW + "UNDATED,Undated Doc,Office,2,notice,1,,,,ALL,ALL,,,N\n"
    with pytest.raises(SourceRegisterError) as info:
        read_source_register(write(tmp_path, body))
    assert info.value.errors[0].startswith("line 3")


def test_authority_level_out_of_range_is_rejected(tmp_path):
    body = "BAD,Bad,Office,6,notice,1,2026-01-01,,,ALL,ALL,,,N\n"
    with pytest.raises(SourceRegisterError):
        read_source_register(write(tmp_path, body))


def test_duplicate_doc_id_is_rejected(tmp_path):
    body = GOOD_ROW + GOOD_ROW
    with pytest.raises(SourceRegisterError, match="duplicate doc_id"):
        read_source_register(write(tmp_path, body))


def test_one_bad_row_writes_nothing(tmp_path, conn):
    body = GOOD_ROW + "BAD,Bad,Office,9,notice,1,2026-01-01,,,ALL,ALL,,,N\n"
    with pytest.raises(SourceRegisterError):
        load_source_register(conn, write(tmp_path, body))
    assert conn.execute("SELECT COUNT(*) FROM source_register").fetchone()[0] == 0


def test_real_register_file_is_valid():
    """The team's own register file must pass the same checks as any other input."""
    path = Path(__file__).resolve().parents[2] / "data" / "documents" / "source_register.csv"
    rows = read_source_register(path)
    assert len(rows) == 7  # 6 official + 1 synthetic test circular
    assert {r.doc_id for r in rows} >= {"NITJ-UG-REG-2023", "NITJ-CAL-2026-ODD"}
