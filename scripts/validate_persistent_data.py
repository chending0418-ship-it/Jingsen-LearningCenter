#!/usr/bin/env python3
"""校验和比对 Jingsen Learning Center 的服务器持久数据。

覆盖 data/ 下的词库、Skills、Daily Reports 与 Learning Todo。清单验证允许
新版本增加文件，但清单中已有文件必须存在且内容哈希保持不变。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_json_files(data_dir: Path) -> list[str]:
    checked: list[str] = []
    for path in sorted(data_dir.rglob("*.json")):
        try:
            with path.open("r", encoding="utf-8") as handle:
                json.load(handle)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"JSON 校验失败: {path}: {exc}") from exc
        checked.append(path.relative_to(data_dir).as_posix())
    return checked


def validate_sqlite_files(data_dir: Path) -> list[str]:
    checked = []
    for path in sorted(data_dir.rglob("*.sqlite3")):
        try:
            connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=15)
            integrity = connection.execute("PRAGMA integrity_check").fetchone()
            foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
            connection.close()
        except sqlite3.Error as exc:
            raise ValueError(f"SQLite 校验失败: {path}: {exc}") from exc
        if not integrity or integrity[0] != "ok" or foreign_keys:
            raise ValueError(f"SQLite 完整性校验失败: {path}")
        checked.append(path.relative_to(data_dir).as_posix())
    return checked


def build_manifest(data_dir: Path) -> dict[str, Any]:
    files = []
    for path in sorted(item for item in data_dir.rglob("*") if item.is_file()):
        relative = path.relative_to(data_dir).as_posix()
        if relative == "learning-todo/.storage.lock" or relative.endswith((".sqlite3-wal", ".sqlite3-shm")):
            continue
        files.append(
            {
                "path": relative,
                "size": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return {"version": 1, "root": "data", "files": files}


def verify_manifest(data_dir: Path, manifest_path: Path) -> None:
    with manifest_path.open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), list):
        raise ValueError(f"数据清单格式无效: {manifest_path}")
    failures = []
    for item in manifest["files"]:
        relative = Path(str(item.get("path", "")))
        if relative.is_absolute() or ".." in relative.parts:
            failures.append(f"不安全路径: {relative}")
            continue
        target = data_dir / relative
        if not target.is_file():
            failures.append(f"文件缺失: {relative.as_posix()}")
            continue
        actual = sha256_file(target)
        if actual != item.get("sha256"):
            failures.append(f"内容变化: {relative.as_posix()}")
    if failures:
        raise ValueError("持久数据清单验证失败:\n- " + "\n- ".join(failures))


def validate_required_files(data_dir: Path, required_files: list[str]) -> list[str]:
    checked = []
    failures = []
    for value in required_files:
        relative = Path(value)
        if relative.is_absolute() or not relative.parts or ".." in relative.parts:
            failures.append(f"不安全的必需文件路径: {value}")
            continue
        target = data_dir / relative
        if not target.is_file():
            failures.append(f"必需文件缺失: {relative.as_posix()}")
            continue
        checked.append(relative.as_posix())
    if failures:
        raise ValueError("持久数据必需文件校验失败:\n- " + "\n- ".join(failures))
    return checked


def summary(data_dir: Path, json_files: list[str], required_files: list[str]) -> dict[str, Any]:
    return {
        "data_dir": str(data_dir),
        "json_files": len(json_files),
        "sqlite_databases": len(list(data_dir.rglob("*.sqlite3"))),
        "library_text_files": len(list(data_dir.glob("*.txt"))),
        "library_registry": (data_dir / "library_registry.json").is_file(),
        "library_archive": (data_dir / "library_archive.json").is_file(),
        "skills_directory": (data_dir / "skills").is_dir(),
        "daily_reports": (data_dir / "report_history.json").is_file(),
        "model_settings": (data_dir / "model-settings.json").is_file(),
        "gallery_assets": len(list((data_dir / "gallery-assets").glob("*"))),
        "todo_directory": (data_dir / "learning-todo").is_dir(),
        "todo_task_months": len(list((data_dir / "learning-todo" / "tasks").glob("*.json"))),
        "todo_backups": len(list((data_dir / "learning-todo" / "backups").glob("*.zip"))),
        "required_files_verified": required_files,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("data_dir", type=Path)
    parser.add_argument("--manifest-out", type=Path)
    parser.add_argument("--verify-manifest", type=Path, action="append", default=[])
    parser.add_argument("--require-file", action="append", default=[])
    args = parser.parse_args()

    data_dir = args.data_dir.resolve()
    if not data_dir.is_dir():
        print(f"错误：数据目录不存在: {data_dir}", file=sys.stderr)
        return 1

    try:
        json_files = validate_json_files(data_dir)
        validate_sqlite_files(data_dir)
        required_files = validate_required_files(data_dir, args.require_file)
        for manifest_path in args.verify_manifest:
            verify_manifest(data_dir, manifest_path.resolve())
        if args.manifest_out:
            manifest_path = args.manifest_out.resolve()
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            with manifest_path.open("w", encoding="utf-8") as handle:
                json.dump(build_manifest(data_dir), handle, ensure_ascii=False, indent=2)
                handle.write("\n")
        print(json.dumps(summary(data_dir, json_files, required_files), ensure_ascii=False, indent=2))
    except ValueError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
