"""Fast synthetic student data without an LLM (fallback to scripts/generate_students/generate.py).

Same 32 students, edge cases, rules and validator as the LLM generator. The only
difference: names and raw numbers come from a fixed list and a seeded random
generator, not from the model. This is NOT LLM-generated data, so the data card
must say so (guide Section 4.2 asks for LLM generation).

Usage:
    python3 scripts/generate_students/generate_fixed.py --out data/students
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "src"))

from app.storage.students import Dataset, validate  # noqa: E402
from generate import (  # noqa: E402
    COURSE_CODES_BY_PROGRAMME,
    COURSES,
    MODEL,
    ESE_MAX,
    ESE_MIN_PCT,
    PASS_TOTAL,
    build_specs,
    build_student,
    strip_private,
)

NAMES = [
    "Aarav Mehta", "Diya Kapoor", "Kabir Sethi", "Anika Bajwa", "Rohan Grewal", "Meera Chadha",
    "Ishan Vohra", "Tanvi Arora", "Yash Malhotra", "Riya Sandhu", "Arjun Talwar", "Saanvi Khurana",
    "Dev Puri", "Navya Bhatia", "Vihaan Saini", "Kiara Lamba", "Aditya Wadhwa", "Pooja Dhillon",
    "Harsh Nanda", "Ira Gill", "Shaurya Bedi", "Ananya Chawla", "Veer Ahuja", "Sia Sood",
    "Krish Oberoi", "Myra Batra", "Atharv Kalra", "Trisha Mongia", "Reyansh Dang", "Eshita Juneja",
    "Tejas Rana", "Mahika Khanna",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "students")
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    specs = build_specs()
    assert len(NAMES) == len(specs), "need one name per student"
    course_rows = [
        {"course_code": c, "course_name": n, "programme": p, "semester": str(s), "credits": str(cr)}
        for c, n, p, s, cr in COURSES
    ]

    students, attendance, results = [], [], []
    for spec, name in zip(specs, NAMES):
        codes = COURSE_CODES_BY_PROGRAMME[spec.programme]
        raw = {
            "full_name": name,
            "cgpa": round(rng.uniform(6.0, 9.5), 2),
            "courses": [],
        }
        for _ in codes:
            held = rng.randint(36, 44)
            attended = rng.randint(int(held * 0.8), held)
            raw["courses"].append({
                "classes_held": held,
                "classes_attended": attended,
                "internal_marks": rng.randint(12, 30),
                "external_marks": rng.randint(25, 70),
            })
        st, att, res, supp = build_student(spec, raw, codes)
        students.append(st)
        attendance.extend(att)
        results.extend(res)
        results.extend(supp)

    data = Dataset(
        students=[(i + 2, s) for i, s in enumerate(students)],
        courses=[(i + 2, c) for i, c in enumerate(course_rows)],
        attendance=[(i + 2, a) for i, a in enumerate(attendance)],
        results=[(i + 2, strip_private(r)) for i, r in enumerate(results)],
    )
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
        "method": "deterministic fallback (seeded random, fixed names). NOT LLM-generated.",
        "model": None,
        "seed": args.seed,
        "students": len(students),
        "edge_cases": {s.student_id: s.edge_tags for s in specs if s.edge_tags},
        "validator_skipped_checks": skipped,
    }, indent=2), encoding="utf-8")
    print(f"wrote {len(students)} students, {len(attendance)} attendance rows, {len(results)} result rows to {out}")
    if skipped:
        print("skipped checks:", "; ".join(skipped))
    return 0


def write_csv(path: Path, header: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        w = csv.DictWriter(handle, fieldnames=header)
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    raise SystemExit(main())
