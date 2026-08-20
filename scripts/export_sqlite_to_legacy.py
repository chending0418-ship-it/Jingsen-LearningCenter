#!/usr/bin/env python3
"""Export SQLite data to legacy JSON/TXT files for rollback or inspection."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database import (
    LibraryRepository,
    ModelSettingsRepository,
    ReportRepository,
    SkillsRepository,
    TodoRepository,
    database_for_data_root,
)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="将 SQLite 导出为旧版 JSON/TXT 数据目录")
    parser.add_argument("output_dir", type=Path, help="必须是新的或空的导出目录")
    args = parser.parse_args()
    destination = args.output_dir.resolve()
    if destination.exists() and any(destination.iterdir()):
        parser.error(f"导出目录必须为空: {destination}")
    destination.mkdir(parents=True, exist_ok=True)

    database = database_for_data_root()
    libraries = LibraryRepository(database)
    active = libraries.read_registry()
    archived = libraries.read_archive()
    write_json(destination / "library_registry.json", active)
    write_json(destination / "library_archive.json", archived)
    for row in active["libraries"]:
        items = libraries.get_items(row["file_name"])
        separator = "\n" if row.get("subject") == "chinese" else ", "
        (destination / f"{row['file_name']}.txt").write_text(separator.join(items), encoding="utf-8")

    skills = SkillsRepository(database)
    index = skills.read_index()
    write_json(destination / "skills" / "index.json", index)
    for source in index["files"]:
        write_json(destination / "skills" / source["file"], skills.read_source(source["file"]))

    write_json(destination / "report_history.json", ReportRepository(database).read_all())
    write_json(destination / "model-settings.json", ModelSettingsRepository(database).read())

    todo = TodoRepository(database)
    todo_root = destination / "learning-todo"
    write_json(todo_root / "settings.json", todo.read_settings())
    write_json(todo_root / "subjects.json", todo.read_subjects())
    write_json(todo_root / "templates.json", todo.read_templates())
    write_json(todo_root / "reports.json", todo.read_reports())
    write_json(todo_root / "points-ledger.json", todo.read_ledger())
    for month in todo.list_months():
        write_json(todo_root / "tasks" / f"{month}.json", todo.read_tasks(month))

    print(json.dumps({"ok": True, "database": str(database.path), "output_dir": str(destination)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
