"""Generate synthetic student CSVs with a local LLM (task S1-S3, guide Section 4.2).

Division of work (see docs/data_card in data/students/DATA_CARD.md):
- The LLM (Ollama, qwen2.5:7b) proposes fictional names, CGPA, and raw attendance
  and internal/external marks. It is constrained by a JSON schema.
- Code sets the edge-case values exactly (guide Section 4.2 list), and derives
  every result (PASS, FAIL, DETAINED, ABSENT) and every backlog count from the
  rules. The LLM never decides a result.
- Every record is checked by the team's validator (src/app/storage/students.py)
  before any file is written. Nothing is written if a check fails.

Usage:
    python3 scripts/generate_students/generate.py --out data/students
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from app.storage.students import Dataset, validate  # noqa: E402

HERE = Path(__file__).resolve().parent
PROMPT_FILE = HERE / "prompts" / "student_profile_prompt.txt"
OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen2.5:7b"
MAX_ATTEMPTS = 5

# Rule values. They match rule_registry (data/documents/rules.csv). Kept here so the
# generator is self-contained; the team's tools read them from the registry.
ATTENDANCE_MIN_PCT = 75
ESE_MAX = 70  # end-semester marks out of 70 (assumption, not stated in the documents)
INTERNAL_MAX = 30  # internal marks out of 30 (assumption, not stated in the documents)
PASS_TOTAL = 40  # grade E (total >= 40), R13.1 table
ESE_MIN_PCT = 30  # R13.3

REGULAR_SESSION = "2026-EVEN"
PROG_CSE = "Computer Science and Engineering"
PROG_IT = "Information Technology"

COURSES = [
    # code, title, programme, semester, credits. Titles and credits from the curricula.
    ("CSDC0202", "Database Management Systems", PROG_CSE, 4, 3),
    ("CSDC0204", "Design and Analysis of Algorithms", PROG_CSE, 4, 3),
    ("CSDC0206", "Computer Networks", PROG_CSE, 4, 3),
    ("CSDC0208", "Formal Language and Automata Theory", PROG_CSE, 4, 4),
    ("ITMI0201", "Database Management Systems", PROG_IT, 3, 3),  # semester inferred from document order
    ("ITMI0202", "Algorithms and Complexity", PROG_IT, 4, 3),
]
COURSE_CODES_BY_PROGRAMME = {
    PROG_CSE: ["CSDC0202", "CSDC0204", "CSDC0206", "CSDC0208"],
    PROG_IT: ["ITMI0201", "ITMI0202"],
}


@dataclass
class StudentSpec:
    student_id: str
    programme: str
    batch_year: int
    current_semester: int
    # Edge-case overrides, keyed by course code. Each value is a dict of fields to set.
    overrides: dict = field(default_factory=dict)
    cgpa_override: Optional[float] = None
    supplementary: list = field(default_factory=list)  # (course, session, internal, external)
    edge_tags: list = field(default_factory=list)


def build_specs() -> list[StudentSpec]:
    """32 students: 20 CSE, 12 IT; batches 2023 and 2024. Edge cases marked in edge_tags."""
    specs: list[StudentSpec] = []

    def add(n: int, programme: str, batch: int) -> StudentSpec:
        sem = 7 if batch == 2023 else 5  # semester in Odd 2026, from admission batch
        spec = StudentSpec(f"S{1000 + n}", programme, batch, sem)
        specs.append(spec)
        return spec

    # CSE 2023: S1001-S1010
    s = [add(n, PROG_CSE, 2023) for n in range(1, 11)]
    # CSE 2024: S1011-S1020
    [add(n, PROG_CSE, 2024) for n in range(11, 21)]
    # IT 2023: S1021-S1026
    i23 = [add(n, PROG_IT, 2023) for n in range(21, 27)]
    # IT 2024: S1027-S1032
    [add(n, PROG_IT, 2024) for n in range(27, 33)]

    e = {spec.student_id: spec for spec in specs}

    e["S1001"].overrides["CSDC0202"] = dict(held=40, attended=30, internal=20, external=25)
    e["S1001"].edge_tags.append("attendance exactly 75% (30 of 40)")

    e["S1002"].overrides["CSDC0202"] = dict(held=40, attended=29, internal=20, external=25)
    e["S1002"].edge_tags.append("attendance one class below 75% (29 of 40 = 72.5%)")

    e["S1003"].overrides["CSDC0204"] = dict(held=40, attended=34, internal=20, external=19)
    e["S1003"].edge_tags.append("total 39, just below pass mark 40")

    e["S1004"].overrides["CSDC0206"] = dict(held=40, attended=36, internal=22, external=0, absent=True)
    e["S1004"].edge_tags.append("absent from end-semester exam")

    for code in ("CSDC0202", "CSDC0204"):
        e["S1005"].overrides[code] = dict(held=40, attended=25, internal=18, external=40)
    e["S1005"].edge_tags.append("detained: attendance 62.5% in two courses")

    e["S1006"].overrides["CSDC0202"] = dict(held=40, attended=38, internal=10, external=20)
    e["S1006"].overrides["CSDC0204"] = dict(held=40, attended=37, internal=12, external=15)
    e["S1006"].overrides["CSDC0206"] = dict(held=40, attended=36, internal=8, external=19)
    e["S1006"].edge_tags.append("several backlogs: three failed courses")

    e["S1007"].cgpa_override = 7.50
    e["S1007"].edge_tags.append("CGPA exactly 7.50 (change-of-discipline cut-off, R15.2)")

    e["S1008"].overrides["CSDC0204"] = dict(held=40, attended=35, internal=12, external=15)
    e["S1008"].supplementary = [
        ("CSDC0204", "2026-JUL", 14, 25),
        ("CSDC0204", "2026-DEC", 15, 22),
    ]
    e["S1008"].edge_tags.append("two supplementary attempts, both failed (R14.2 II limit)")

    e["S1009"].overrides["CSDC0206"] = dict(held=40, attended=34, internal=30, external=15)
    e["S1009"].edge_tags.append("total 45 but end-semester 15 of 70 (below 30%, R13.3)")

    i23[0].overrides["ITMI0202"] = dict(held=40, attended=34, internal=19, external=21)
    i23[0].edge_tags.append("total exactly 40 with end-semester at 30% (boundary pass)")

    return specs


# ---------- LLM call ----------

def record_schema(course_count: int) -> dict:
    course = {
        "type": "object",
        "properties": {
            "course_code": {"type": "string"},
            "classes_held": {"type": "integer"},
            "classes_attended": {"type": "integer"},
            "internal_marks": {"type": "integer"},
            "external_marks": {"type": "integer"},
        },
        "required": ["course_code", "classes_held", "classes_attended", "internal_marks", "external_marks"],
    }
    return {
        "type": "object",
        "properties": {
            "full_name": {"type": "string"},
            "cgpa": {"type": "number"},
            "courses": {"type": "array", "items": course, "minItems": course_count, "maxItems": course_count},
        },
        "required": ["full_name", "cgpa", "courses"],
    }


def call_llm(prompt: str, schema: dict, seed: int) -> dict:
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "format": schema,
        "stream": False,
        "options": {"temperature": 0.9, "seed": seed},
    }).encode("utf-8")
    req = urllib.request.Request(OLLAMA_URL, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return json.loads(payload["message"]["content"])


# ---------- checks on the LLM output (before any code-side override) ----------

def check_llm_record(raw: dict, codes: list[str]) -> list[str]:
    errors: list[str] = []
    name = raw.get("full_name", "")
    if not name or len(name.split()) < 2:
        errors.append("full_name must have at least two words")
    cgpa = raw.get("cgpa")
    if not isinstance(cgpa, (int, float)) or not 6.0 <= cgpa <= 9.5:
        errors.append(f"cgpa {cgpa} outside 6.0-9.5")
    rows = raw.get("courses", [])
    if [r.get("course_code") for r in rows] != codes:
        errors.append(f"course codes {[r.get('course_code') for r in rows]} != {codes}")
    for r in rows:
        held, att = r.get("classes_held", 0), r.get("classes_attended", -1)
        if not 36 <= held <= 44:
            errors.append(f"{r.get('course_code')}: classes_held {held} outside 36-44")
        if not 0 <= att <= held:
            errors.append(f"{r.get('course_code')}: classes_attended {att} not between 0 and {held}")
        if not 0 <= r.get("internal_marks", -1) <= INTERNAL_MAX:
            errors.append(f"{r.get('course_code')}: internal_marks out of 0-{INTERNAL_MAX}")
        if not 0 <= r.get("external_marks", -1) <= ESE_MAX:
            errors.append(f"{r.get('course_code')}: external_marks out of 0-{ESE_MAX}")
    return errors


# ---------- code-side rules: override edge cases, derive results ----------

def derive_row(student_id: str, code: str, session: str, exam_type: str,
               held: int, attended: int, internal: int, external: int, absent: bool = False) -> dict:
    pct = attended * 100 / held
    if pct < ATTENDANCE_MIN_PCT:
        result, external = "DETAINED", 0  # cannot sit the end-semester exam (R8.2)
    elif absent:
        result, external = "ABSENT", 0
    elif internal + external >= PASS_TOTAL and external * 100 >= ESE_MIN_PCT * ESE_MAX:
        result = "PASS"
    else:
        result = "FAIL"
    total = internal + external
    return {
        "student_id": student_id, "course_code": code, "exam_session": session, "exam_type": exam_type,
        "internal_marks": internal, "external_marks": external, "total_marks": total,
        "max_marks": INTERNAL_MAX + ESE_MAX, "result": result,
        "_held": held, "_attended": attended,
    }


def build_student(spec: StudentSpec, raw: dict, codes: list[str]) -> tuple[dict, list[dict], list[dict], list[dict]]:
    """Return (student row, attendance rows, regular result rows, supplementary result rows)."""
    cgpa = spec.cgpa_override if spec.cgpa_override is not None else round(float(raw["cgpa"]), 2)
    attendance, results = [], []
    for code, r in zip(codes, raw["courses"]):
        ov = spec.overrides.get(code, {})
        held = ov.get("held", r["classes_held"])
        attended = ov.get("attended", r["classes_attended"])
        internal = ov.get("internal", r["internal_marks"])
        external = ov.get("external", r["external_marks"])
        absent = ov.get("absent", False)
        row = derive_row(spec.student_id, code, REGULAR_SESSION, "REGULAR", held, attended, internal, external, absent)
        attendance.append({"student_id": spec.student_id, "course_code": code,
                           "classes_held": held, "classes_attended": attended})
        results.append(row)

    supp = []
    for code, session, internal, external in spec.supplementary:
        supp.append(derive_row(spec.student_id, code, session, "SUPPLEMENTARY", 40, 40, internal, external))

    # A backlog is a regular course not passed, with no later passing supplementary attempt.
    cleared = {r["course_code"] for r in supp if r["result"] == "PASS"}
    backlogs = sum(1 for r in results if r["result"] != "PASS" and r["course_code"] not in cleared)
    student = {
        "student_id": spec.student_id, "full_name": raw["full_name"], "programme": spec.programme,
        "batch_year": spec.batch_year, "current_semester": spec.current_semester,
        "cgpa": f"{cgpa:.2f}", "active_backlogs": backlogs,
    }
    return student, attendance, results, supp


def strip_private(row: dict) -> dict:
    return {k: v for k, v in row.items() if not k.startswith("_")}


# ---------- main ----------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "students")
    parser.add_argument("--limit", type=int, default=None, help="generate only the first N students")
    args = parser.parse_args()

    prompt_template = PROMPT_FILE.read_text(encoding="utf-8")
    specs = build_specs()[: args.limit] if args.limit else build_specs()
    course_rows = [
        {"course_code": c, "course_name": n, "programme": p, "semester": str(s), "credits": str(cr)}
        for c, n, p, s, cr in COURSES
    ]

    students, attendance, results, log = [], [], [], []
    names_seen: set[str] = set()
    for idx, spec in enumerate(specs):
        codes = COURSE_CODES_BY_PROGRAMME[spec.programme]
        prompt = prompt_template.format(
            course_count=len(codes), course_codes=", ".join(codes),
            programme=spec.programme, batch_year=spec.batch_year,
            used_names=", ".join(sorted(names_seen)) or "none yet",
        )
        schema = record_schema(len(codes))
        accepted, attempts_log = None, []
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                raw = call_llm(prompt, schema, seed=1000 * idx + attempt)
            except Exception as exc:  # network or JSON failure counts as a failed attempt
                attempts_log.append({"attempt": attempt, "errors": [f"LLM call failed: {exc}"]})
                continue
            errors = check_llm_record(raw, codes)
            if raw.get("full_name", "").lower() in names_seen:
                errors.append("duplicate name")
            if errors:
                attempts_log.append({"attempt": attempt, "errors": errors})
                continue
            accepted = raw
            attempts_log.append({"attempt": attempt, "errors": []})
            break
        if accepted is None:
            print(f"FAILED {spec.student_id}: no valid record after {MAX_ATTEMPTS} attempts")
            for a in attempts_log:
                print("  attempt", a["attempt"], "-", "; ".join(a["errors"]))
            return 1
        names_seen.add(accepted["full_name"].lower())
        st, att, res, supp = build_student(spec, accepted, codes)
        students.append(st)
        attendance.extend(att)
        results.extend(res)
        results.extend(supp)
        log.append({"student_id": spec.student_id, "attempts": attempts_log,
                    "edge_cases": spec.edge_tags})
        print(f"{spec.student_id} ok after {len(attempts_log)} attempt(s)")

    # Final check with the team's validator. Nothing is written unless this passes.
    data = Dataset(
        students=[(i + 2, s) for i, s in enumerate(students)],
        courses=[(i + 2, c) for i, c in enumerate(course_rows)],
        attendance=[(i + 2, a) for i, a in enumerate(attendance)],
        results=[(i + 2, strip_private(r)) for i, r in enumerate(results)],
    )
    # Results in CSV must match the derived values, so the validator checks what is written.
    errors, skipped = validate(data, pass_mark_pct=Fraction(PASS_TOTAL), ese=(Fraction(ESE_MIN_PCT), ESE_MAX))
    if errors:
        print(f"VALIDATION FAILED: {len(errors)} violation(s)")
        for e in errors[:20]:
            print("  -", e)
        return 1

    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "students.csv", list(students[0].keys()), students)
    write_csv(out / "courses.csv", list(course_rows[0].keys()), course_rows)
    write_csv(out / "attendance.csv", list(attendance[0].keys()), attendance)
    write_csv(out / "results.csv", list(strip_private(results[0]).keys()), [strip_private(r) for r in results])
    (out / "generation_log.json").write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": MODEL,
        "prompt_sha256": hashlib.sha256(prompt_template.encode("utf-8")).hexdigest(),
        "students": log,
        "validator_skipped_checks": skipped,
    }, indent=2), encoding="utf-8")
    print(f"wrote {len(students)} students, {len(attendance)} attendance, {len(results)} results to {out}")
    if skipped:
        print("skipped checks:", "; ".join(skipped))
    return 0


def write_csv(path: Path, header: list[str], rows: list[dict]) -> None:
    import csv
    with path.open("w", newline="", encoding="utf-8") as handle:
        w = csv.DictWriter(handle, fieldnames=header)
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    raise SystemExit(main())
