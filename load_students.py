"""Load a folder of student CSVs into the SQLite database (task C1').

Usage:
    python3 scripts/load_students.py --dir test_students/ --db data/app.sqlite3

Validates everything first. If any check fails, nothing is written and the
script exits with code 1 and prints every violation.
"""

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app.storage.students import StudentDataError, load_dataset  # noqa: E402

SCHEMA = ROOT / "src" / "app" / "storage" / "schema.sql"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", required=True, type=Path, help="folder with the four CSV files")
    parser.add_argument("--db", type=Path, default=ROOT / "data" / "app.sqlite3", help="SQLite file")
    args = parser.parse_args()

    args.db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(args.db)
    try:
        conn.executescript(SCHEMA.read_text(encoding="utf-8"))
        counts = load_dataset(conn, args.dir)
    except FileNotFoundError as exc:
        print(f"Missing file: {exc.filename}")
        return 2
    except StudentDataError as exc:
        print(f"Nothing loaded. {len(exc.errors)} violation(s):")
        for error in exc.errors:
            print(f"  - {error}")
        return 1
    finally:
        conn.close()

    print("Loaded:", ", ".join(f"{k}={v}" for k, v in counts.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
