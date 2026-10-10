-- SQLite schema (task T0.2).
-- Tables and columns follow guide Annex C. Column names and types must not be
-- renamed or removed. Extra tables (source_register, audit) come from Annex B
-- and Annex D.
-- Rules written as CHECK constraints are the Annex C "Rules" column.

PRAGMA foreign_keys = ON;

-- Annex B: one row per document. Created first because rule_registry refers to it.
CREATE TABLE IF NOT EXISTS source_register (
    doc_id            TEXT PRIMARY KEY,
    title             TEXT NOT NULL,
    issuer            TEXT NOT NULL,
    authority_level   INTEGER NOT NULL CHECK (authority_level BETWEEN 1 AND 5),
    doc_type          TEXT NOT NULL,
    version           TEXT NOT NULL,
    effective_from    TEXT NOT NULL,            -- YYYY-MM-DD
    effective_to      TEXT,                     -- YYYY-MM-DD or NULL (open-ended)
    supersedes        TEXT,
    scope_programmes  TEXT NOT NULL DEFAULT 'ALL',
    scope_batches     TEXT NOT NULL DEFAULT 'ALL',
    provenance        TEXT NOT NULL DEFAULT '',
    retrieved_on      TEXT,
    synthetic         INTEGER NOT NULL DEFAULT 0 CHECK (synthetic IN (0, 1)),
    CHECK (effective_to IS NULL OR effective_to >= effective_from)
);

-- Annex C: students
CREATE TABLE IF NOT EXISTS students (
    student_id        TEXT PRIMARY KEY
                      CHECK (student_id GLOB 'S[0-9][0-9][0-9][0-9]'),
    full_name         TEXT NOT NULL,
    programme         TEXT NOT NULL,
    batch_year        INTEGER NOT NULL,
    current_semester  INTEGER NOT NULL CHECK (current_semester BETWEEN 1 AND 10),
    cgpa              REAL NOT NULL CHECK (cgpa BETWEEN 0.0 AND 10.0),
    active_backlogs   INTEGER NOT NULL CHECK (active_backlogs >= 0)
);

-- Annex C: courses
CREATE TABLE IF NOT EXISTS courses (
    course_code  TEXT PRIMARY KEY,
    course_name  TEXT NOT NULL,
    programme    TEXT NOT NULL,                 -- must match students.programme values
    semester     INTEGER NOT NULL,
    credits      INTEGER NOT NULL
);

-- Annex C: attendance. Attendance % is computed by tools, never stored.
CREATE TABLE IF NOT EXISTS attendance (
    student_id        TEXT NOT NULL REFERENCES students (student_id),
    course_code       TEXT NOT NULL REFERENCES courses (course_code),
    classes_held      INTEGER NOT NULL CHECK (classes_held > 0),
    classes_attended  INTEGER NOT NULL,
    PRIMARY KEY (student_id, course_code),
    CHECK (classes_attended >= 0 AND classes_attended <= classes_held)
);

-- Annex C: results
CREATE TABLE IF NOT EXISTS results (
    student_id       TEXT NOT NULL REFERENCES students (student_id),
    course_code      TEXT NOT NULL REFERENCES courses (course_code),
    exam_session     TEXT NOT NULL,              -- for example 2026-MAY
    exam_type        TEXT NOT NULL CHECK (exam_type IN ('REGULAR', 'SUPPLEMENTARY')),
    internal_marks   INTEGER NOT NULL,
    external_marks   INTEGER NOT NULL,
    total_marks      INTEGER NOT NULL,
    max_marks        INTEGER NOT NULL CHECK (max_marks > 0),
    result           TEXT NOT NULL CHECK (result IN ('PASS', 'FAIL', 'ABSENT', 'DETAINED')),
    PRIMARY KEY (student_id, course_code, exam_session, exam_type),
    CHECK (internal_marks >= 0 AND external_marks >= 0),
    CHECK (total_marks = internal_marks + external_marks),
    CHECK (total_marks <= max_marks)
);

-- Annex C: rule_registry. Every rule must cite a source document and clause.
CREATE TABLE IF NOT EXISTS rule_registry (
    rule_id          TEXT PRIMARY KEY,           -- for example ATT-MIN-01
    description      TEXT NOT NULL,
    parameter        TEXT NOT NULL,              -- for example min_attendance_pct
    operator         TEXT NOT NULL CHECK (operator IN ('>=', '<=', '>', '<', '=', 'BETWEEN')),
    value            TEXT NOT NULL,              -- threshold value(s), stored as text
    scope_programmes TEXT NOT NULL DEFAULT 'ALL',
    scope_batches    TEXT NOT NULL DEFAULT 'ALL',
    effective_from   TEXT NOT NULL,
    effective_to     TEXT,
    source_doc_id    TEXT NOT NULL REFERENCES source_register (doc_id),
    source_section   TEXT NOT NULL CHECK (length(source_section) > 0),
    CHECK (effective_to IS NULL OR effective_to >= effective_from)
);

-- Annex D: audit record. One row per request, including refused requests.
-- The full record is kept as JSON; the common fields are columns for querying.
CREATE TABLE IF NOT EXISTS audit (
    trace_id           TEXT PRIMARY KEY,
    timestamp          TEXT NOT NULL,            -- ISO 8601, UTC
    student_id         TEXT,
    question_category  TEXT,
    answer_type        TEXT NOT NULL,
    latency_ms         INTEGER NOT NULL DEFAULT 0,
    record_json        TEXT NOT NULL
);
