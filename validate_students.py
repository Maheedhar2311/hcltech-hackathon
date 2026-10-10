"""Validate a folder of student CSVs without writing anything (task C2').

Usage:
    python3 scripts/validate_students.py --dir test_students/

Exit code 0 if valid, 1 if any violation is found, 2 if files are missing.
"""

import argparse
import sys
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from app.storage.students import read_dataset, validate  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", required=True, type=Path, help="folder with the four CSV files")
    parser.add_argument(
        "--pass-mark",
        type=str,
        default=None,
        help="pass mark percentage, e.g. 40. Use the value from the rule registry. Omit to skip the result check.",
    )
    parser.add_argument("--esem-min", type=str, default=None, help="end-semester minimum percent, e.g. 30 (R13.3)")
    parser.add_argument("--external-max", type=int, default=70, help="end-semester maximum marks (assumed 70; not in the documents)")
    args = parser.parse_args()

    try:
        data = read_dataset(args.dir)
    except FileNotFoundError as exc:
        print(f"Missing file: {exc.filename}")
        return 2

    pass_mark = Fraction(args.pass_mark) if args.pass_mark else None
    ese = (Fraction(args.esem_min), args.external_max) if args.esem_min else None
    errors, skipped = validate(data, pass_mark, ese)

    counts = {
        "students": len(data.students),
        "courses": len(data.courses),
        "attendance": len(data.attendance),
        "results": len(data.results),
    }
    print("Rows read:", ", ".join(f"{k}={v}" for k, v in counts.items()))
    for check in skipped:
        print(f"SKIPPED: {check}")
    if errors:
        print(f"FAILED: {len(errors)} violation(s)")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("OK: no violations found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
