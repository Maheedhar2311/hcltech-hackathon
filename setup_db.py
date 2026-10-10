"""Create the SQLite database and load the reference data (Source Register and rules).

Usage:
    python3 scripts/setup_db.py                     # schema + register + rules
    python3 scripts/setup_db.py --students data/students

Order matters: the Source Register first, then rules (each rule cites a
registered document), then students (their scope uses the same database).
Each step is all-or-nothing. A failing step stops the script and reports why.
"""

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app.storage.rules import RuleLoadError, load_rules_csv  # noqa: E402
from app.storage.source_register import SourceRegisterError, load_source_register  # noqa: E402
from app.storage.students import StudentDataError, load_dataset  # noqa: E402

SCHEMA = ROOT / "src" / "app" / "storage" / "schema.sql"
DOCS = ROOT / "data" / "documents"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=ROOT / "data" / "app.sqlite3")
    parser.add_argument("--register", type=Path, default=DOCS / "source_register.csv")
    parser.add_argument("--rules", type=Path, default=DOCS / "rules.csv")
    parser.add_argument("--students", type=Path, default=None, help="folder with the four student CSVs")
    args = parser.parse_args()

    args.db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(args.db)
    try:
        conn.executescript(SCHEMA.read_text(encoding="utf-8"))
        print(f"schema ready: {args.db}")
        # Safe to run again: a table that already has rows is left alone.
        if conn.execute("SELECT COUNT(*) FROM source_register").fetchone()[0] == 0:
            n = load_source_register(conn, args.register)
            print(f"source register: {n} documents loaded")
        else:
            print("source register: already loaded, skipped")
        if conn.execute("SELECT COUNT(*) FROM rule_registry").fetchone()[0] == 0:
            n = load_rules_csv(conn, args.rules)
            print(f"rules: {n} rules loaded")
        else:
            print("rules: already loaded, skipped")
        if args.students:
            counts = load_dataset(conn, args.students)
            print("students:", ", ".join(f"{k}={v}" for k, v in counts.items()))
    except (SourceRegisterError, RuleLoadError, StudentDataError) as exc:
        print("STOPPED. Nothing from the failing step was written.")
        for error in exc.errors:
            print(f"  - {error}")
        return 1
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
