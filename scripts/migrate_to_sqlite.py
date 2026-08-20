#!/usr/bin/env python3
"""Run the idempotent legacy JSON/TXT to SQLite migration."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database import database_for_data_root, migrate_legacy_data

if __name__ == "__main__":
    result = migrate_legacy_data()
    database = database_for_data_root()
    with database.read() as connection:
        result["record_counts"] = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "libraries", "library_items", "skills", "practice_reports",
                "generation_jobs",
                "todo_subjects", "todo_templates", "todo_tasks", "todo_task_history",
                "todo_reports", "points_ledger",
            )
        }
        result["integrity_check"] = connection.execute("PRAGMA integrity_check").fetchone()[0]
        result["foreign_key_violations"] = len(connection.execute("PRAGMA foreign_key_check").fetchall())
    print(json.dumps(result, ensure_ascii=False, indent=2))
