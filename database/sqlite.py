"""Relational SQLite persistence with lossless legacy JSON/TXT migration."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional

from config import config


SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS app_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS data_migration_sources (
    source_path TEXT PRIMARY KEY,
    sha256 TEXT NOT NULL,
    imported_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS libraries (
    id TEXT PRIMARY KEY,
    subject TEXT NOT NULL,
    name TEXT NOT NULL UNIQUE,
    legacy_file_name TEXT UNIQUE,
    library_type TEXT,
    enabled INTEGER NOT NULL CHECK(enabled IN (0, 1)),
    archived INTEGER NOT NULL CHECK(archived IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT,
    extra_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_libraries_subject_status
    ON libraries(subject, archived, enabled);
CREATE TABLE IF NOT EXISTS library_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    library_id TEXT NOT NULL,
    content TEXT NOT NULL,
    normalized_content TEXT NOT NULL,
    sort_order INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(library_id) REFERENCES libraries(id) ON DELETE CASCADE,
    UNIQUE(library_id, sort_order)
);
CREATE INDEX IF NOT EXISTS idx_library_items_lookup
    ON library_items(library_id, normalized_content);

CREATE TABLE IF NOT EXISTS skill_sections (
    source_file TEXT PRIMARY KEY,
    module TEXT,
    section TEXT,
    title TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL DEFAULT 0,
    index_entry_json TEXT NOT NULL DEFAULT '{}',
    source_metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS skills (
    id TEXT PRIMARY KEY,
    source_file TEXT NOT NULL,
    module TEXT,
    section TEXT,
    grade TEXT,
    topic TEXT,
    skill TEXT,
    detail TEXT,
    difficulty TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL DEFAULT 0,
    extra_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(source_file) REFERENCES skill_sections(source_file) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_skills_filters
    ON skills(module, section, grade, topic, skill, enabled, sort_order);
CREATE TABLE IF NOT EXISTS skill_question_types (
    skill_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    value TEXT NOT NULL,
    PRIMARY KEY(skill_id, position),
    FOREIGN KEY(skill_id) REFERENCES skills(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS skill_tags (
    skill_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    value TEXT NOT NULL,
    PRIMARY KEY(skill_id, position),
    FOREIGN KEY(skill_id) REFERENCES skills(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS practice_reports (
    id TEXT PRIMARY KEY,
    position INTEGER NOT NULL,
    created_at TEXT,
    report_date TEXT,
    module TEXT,
    module_label TEXT,
    total_count INTEGER,
    correct_count INTEGER,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_practice_reports_history
    ON practice_reports(module, created_at DESC);
CREATE TABLE IF NOT EXISTS practice_report_items (
    report_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY(report_id, position),
    FOREIGN KEY(report_id) REFERENCES practice_reports(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS generation_jobs (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    status TEXT NOT NULL,
    requested_count INTEGER NOT NULL,
    generated_count INTEGER NOT NULL DEFAULT 0,
    request_json TEXT NOT NULL,
    plan_json TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    questions_json TEXT NOT NULL DEFAULT '[]',
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_generation_jobs_expiry
    ON generation_jobs(expires_at);

CREATE TABLE IF NOT EXISTS model_settings (
    id INTEGER PRIMARY KEY CHECK(id = 1),
    selected_model TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS todo_settings (
    id INTEGER PRIMARY KEY CHECK(id = 1),
    timezone TEXT NOT NULL,
    recurrence_horizon_days INTEGER NOT NULL,
    backup_retention INTEGER NOT NULL,
    updated_at TEXT,
    extra_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS todo_subjects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    color TEXT NOT NULL,
    sort_order INTEGER NOT NULL,
    enabled INTEGER NOT NULL CHECK(enabled IN (0, 1)),
    payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS todo_templates (
    id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,
    title TEXT NOT NULL,
    start_date TEXT,
    end_date TEXT,
    repeat_kind TEXT NOT NULL,
    active INTEGER NOT NULL CHECK(active IN (0, 1)),
    payload_json TEXT NOT NULL,
    FOREIGN KEY(subject_id) REFERENCES todo_subjects(id)
);
CREATE INDEX IF NOT EXISTS idx_todo_templates_active
    ON todo_templates(active, start_date, end_date);
CREATE TABLE IF NOT EXISTS todo_template_weekdays (
    template_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    weekday INTEGER NOT NULL,
    PRIMARY KEY(template_id, position),
    FOREIGN KEY(template_id) REFERENCES todo_templates(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS todo_tasks (
    id TEXT PRIMARY KEY,
    position INTEGER NOT NULL,
    subject_id TEXT NOT NULL,
    template_id TEXT,
    title TEXT NOT NULL,
    planned_date TEXT NOT NULL,
    lifecycle_status TEXT NOT NULL,
    completed_at TEXT,
    payload_json TEXT NOT NULL,
    FOREIGN KEY(subject_id) REFERENCES todo_subjects(id),
    FOREIGN KEY(template_id) REFERENCES todo_templates(id)
);
CREATE INDEX IF NOT EXISTS idx_todo_tasks_calendar
    ON todo_tasks(planned_date, lifecycle_status, subject_id);
CREATE TABLE IF NOT EXISTS todo_task_history (
    task_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    event_at TEXT,
    details_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY(task_id, position),
    FOREIGN KEY(task_id) REFERENCES todo_tasks(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS todo_reports (
    record_key TEXT PRIMARY KEY,
    position INTEGER NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS points_ledger (
    record_key TEXT PRIMARY KEY,
    position INTEGER NOT NULL,
    transaction_type TEXT NOT NULL,
    points INTEGER NOT NULL,
    purpose TEXT NOT NULL,
    created_at TEXT,
    payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reading_books (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    author TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    age_level TEXT NOT NULL DEFAULT '',
    language TEXT NOT NULL DEFAULT 'English',
    pdf_asset TEXT NOT NULL,
    cover_asset TEXT,
    pdf_sha256 TEXT NOT NULL UNIQUE,
    page_count INTEGER NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('draft', 'published', 'archived')),
    extraction_status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    extra_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_reading_books_status
    ON reading_books(status, updated_at DESC);
CREATE TABLE IF NOT EXISTS reading_chapters (
    id TEXT PRIMARY KEY,
    book_id TEXT NOT NULL,
    title TEXT NOT NULL,
    start_page INTEGER NOT NULL,
    end_page INTEGER NOT NULL,
    sort_order INTEGER NOT NULL,
    detection_source TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0,
    content_text TEXT NOT NULL DEFAULT '',
    extra_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(book_id) REFERENCES reading_books(id) ON DELETE CASCADE,
    UNIQUE(book_id, sort_order)
);
CREATE INDEX IF NOT EXISTS idx_reading_chapters_book
    ON reading_chapters(book_id, sort_order);
CREATE TABLE IF NOT EXISTS reading_sessions (
    id TEXT PRIMARY KEY,
    access_token_hash TEXT NOT NULL,
    book_id TEXT NOT NULL,
    chapter_ids_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('active', 'completed', 'abandoned')),
    question_count INTEGER NOT NULL,
    overall_level TEXT,
    student_summary TEXT,
    parent_summary TEXT,
    evaluation_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    FOREIGN KEY(book_id) REFERENCES reading_books(id)
);
CREATE INDEX IF NOT EXISTS idx_reading_sessions_history
    ON reading_sessions(created_at DESC, book_id);
CREATE TABLE IF NOT EXISTS reading_session_questions (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    question_text TEXT NOT NULL,
    question_type TEXT NOT NULL,
    purpose TEXT NOT NULL DEFAULT '',
    reference_answer TEXT NOT NULL DEFAULT '',
    evidence_json TEXT NOT NULL DEFAULT '[]',
    child_answer TEXT,
    input_mode TEXT,
    feedback TEXT,
    understanding_level TEXT,
    parent_note TEXT,
    follow_up_question TEXT,
    follow_up_answer TEXT,
    follow_up_feedback TEXT,
    answered_at TEXT,
    extra_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(session_id) REFERENCES reading_sessions(id) ON DELETE CASCADE,
    UNIQUE(session_id, position)
);
CREATE INDEX IF NOT EXISTS idx_reading_questions_session
    ON reading_session_questions(session_id, position);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _load(value: str | None, fallback: Any) -> Any:
    if value is None:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _stable_key(prefix: str, value: Any, position: int) -> str:
    digest = hashlib.sha256(_dump(value).encode("utf-8")).hexdigest()[:24]
    return f"{prefix}_{position}_{digest}"


class SQLiteDatabase:
    def __init__(self, path: str | Path):
        self.path = Path(path).resolve()
        self._init_lock = threading.Lock()
        self._initialized = False

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(self.path), timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 15000")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    def initialize(self) -> None:
        if self._initialized:
            return
        with self._init_lock:
            if self._initialized:
                return
            for attempt in range(6):
                try:
                    with self.connect() as connection:
                        connection.execute("PRAGMA journal_mode = WAL")
                        connection.executescript(SCHEMA)
                        connection.execute(
                            "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES(1, ?)",
                            (_now(),),
                        )
                        connection.execute(
                            "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES(2, ?)",
                            (_now(),),
                        )
                        connection.execute(
                            "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES(3, ?)",
                            (_now(),),
                        )
                    break
                except sqlite3.OperationalError as exc:
                    if "locked" not in str(exc).lower() or attempt == 5:
                        raise
                    time.sleep(0.05 * (attempt + 1))
            self._initialized = True

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        self.initialize()
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @contextmanager
    def read(self) -> Iterator[sqlite3.Connection]:
        self.initialize()
        connection = self.connect()
        try:
            yield connection
        finally:
            connection.close()


_database_cache: dict[str, SQLiteDatabase] = {}
_database_cache_lock = threading.Lock()


def _cached_database(path: Path) -> SQLiteDatabase:
    key = str(path.resolve())
    with _database_cache_lock:
        database = _database_cache.get(key)
        if database is None:
            database = SQLiteDatabase(path)
            _database_cache[key] = database
    database.initialize()
    return database


def database_for_data_root(data_root: str | Path | None = None) -> SQLiteDatabase:
    root = Path(data_root or config.DATA_DIR).resolve()
    override = os.environ.get("SQLITE_DATABASE_PATH")
    path = Path(override).expanduser().resolve() if override else root / "learning-center.sqlite3"
    return _cached_database(path)


def database_for_todo_root(todo_root: str | Path) -> SQLiteDatabase:
    root = Path(todo_root).resolve()
    configured_todo = Path(config.TODO_DATA_DIR).resolve()
    if root == configured_todo:
        return database_for_data_root(config.DATA_DIR)
    return _cached_database(root / "learning-center.sqlite3")


class LibraryRepository:
    def __init__(self, database: SQLiteDatabase):
        self.database = database
        self._pending_items: dict[str, list[str]] = {}

    @staticmethod
    def _row_payload(row: sqlite3.Row) -> Dict[str, Any]:
        payload = _load(row["extra_json"], {})
        payload.update({
            "id": row["id"],
            "subject": row["subject"],
            "name": row["name"],
            "file_name": row["legacy_file_name"] or row["name"],
            "enabled": bool(row["enabled"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        })
        if row["library_type"] is not None:
            payload["library_type"] = row["library_type"]
        return payload

    def _upsert_library(self, connection: sqlite3.Connection, item: Dict[str, Any], archived: bool) -> None:
        known = {"id", "subject", "name", "file_name", "library_type", "enabled", "archived", "archived_at", "created_at", "updated_at", "items"}
        extra = {key: value for key, value in item.items() if key not in known}
        connection.execute(
            """
            INSERT INTO libraries(id, subject, name, legacy_file_name, library_type, enabled,
                archived, created_at, updated_at, archived_at, extra_json)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET subject=excluded.subject, name=excluded.name,
                legacy_file_name=excluded.legacy_file_name, library_type=excluded.library_type,
                enabled=excluded.enabled, archived=excluded.archived,
                created_at=excluded.created_at, updated_at=excluded.updated_at,
                archived_at=excluded.archived_at, extra_json=excluded.extra_json
            """,
            (
                str(item["id"]), str(item.get("subject") or "english"), str(item["name"]),
                str(item.get("file_name") or item["name"]), item.get("library_type"),
                0 if archived else int(bool(item.get("enabled"))), int(archived),
                str(item.get("created_at") or _now()), str(item.get("updated_at") or _now()),
                item.get("archived_at") if archived else None, _dump(extra),
            ),
        )

    def _replace_items(self, connection: sqlite3.Connection, library_id: str, items: Iterable[str]) -> None:
        connection.execute("DELETE FROM library_items WHERE library_id = ?", (library_id,))
        now = _now()
        connection.executemany(
            """INSERT INTO library_items(library_id, content, normalized_content, sort_order, created_at, updated_at)
               VALUES(?, ?, ?, ?, ?, ?)""",
            [
                (library_id, value, value.strip().casefold(), position, now, now)
                for position, raw in enumerate(items)
                if (value := str(raw).strip())
            ],
        )

    def replace_registry(self, payload: Dict[str, Any], connection: sqlite3.Connection | None = None) -> None:
        def operation(conn: sqlite3.Connection) -> None:
            rows = [row for row in payload.get("libraries", []) if isinstance(row, dict)]
            ids = [str(row["id"]) for row in rows]
            for row in rows:
                self._upsert_library(conn, row, False)
            if ids:
                placeholders = ",".join("?" for _ in ids)
                conn.execute(f"DELETE FROM libraries WHERE archived = 0 AND id NOT IN ({placeholders})", ids)
            else:
                conn.execute("DELETE FROM libraries WHERE archived = 0")
            for row in rows:
                file_name = str(row.get("file_name") or row.get("name"))
                if file_name in self._pending_items:
                    self._replace_items(conn, str(row["id"]), self._pending_items.pop(file_name))
        if connection is not None:
            operation(connection)
        else:
            with self.database.transaction() as conn:
                operation(conn)

    def replace_archive(self, payload: Dict[str, Any], connection: sqlite3.Connection | None = None) -> None:
        def operation(conn: sqlite3.Connection) -> None:
            rows = [row for row in payload.get("libraries", []) if isinstance(row, dict)]
            ids = [str(row["id"]) for row in rows]
            for row in rows:
                self._upsert_library(conn, row, True)
                if isinstance(row.get("items"), list):
                    self._replace_items(conn, str(row["id"]), row["items"])
            if ids:
                placeholders = ",".join("?" for _ in ids)
                conn.execute(f"DELETE FROM libraries WHERE archived = 1 AND id NOT IN ({placeholders})", ids)
            else:
                conn.execute("DELETE FROM libraries WHERE archived = 1")
        if connection is not None:
            operation(connection)
        else:
            with self.database.transaction() as conn:
                operation(conn)

    def read_registry(self) -> Dict[str, Any]:
        with self.database.read() as connection:
            rows = connection.execute("SELECT * FROM libraries WHERE archived = 0 ORDER BY created_at, id").fetchall()
        return {"version": 1, "libraries": [self._row_payload(row) for row in rows]}

    def read_archive(self) -> Dict[str, Any]:
        with self.database.read() as connection:
            rows = connection.execute("SELECT * FROM libraries WHERE archived = 1 ORDER BY archived_at, id").fetchall()
            result = []
            for row in rows:
                payload = self._row_payload(row)
                payload.update({"enabled": False, "archived": True, "archived_at": row["archived_at"]})
                payload["items"] = [
                    item["content"] for item in connection.execute(
                        "SELECT content FROM library_items WHERE library_id = ? ORDER BY sort_order", (row["id"],)
                    ).fetchall()
                ]
                result.append(payload)
        return {"version": 1, "libraries": result}

    def get_items(self, file_name: str) -> List[str]:
        with self.database.read() as connection:
            row = connection.execute("SELECT id FROM libraries WHERE legacy_file_name = ?", (file_name,)).fetchone()
            if row is None:
                return list(self._pending_items.get(file_name, []))
            return [
                item["content"] for item in connection.execute(
                    "SELECT content FROM library_items WHERE library_id = ? ORDER BY sort_order", (row["id"],)
                ).fetchall()
            ]

    def replace_items(self, file_name: str, items: List[str]) -> None:
        with self.database.transaction() as connection:
            row = connection.execute("SELECT id FROM libraries WHERE legacy_file_name = ?", (file_name,)).fetchone()
            if row is None:
                self._pending_items[file_name] = list(items)
                return
            self._replace_items(connection, str(row["id"]), items)

    def list_file_names(self) -> List[str]:
        with self.database.read() as connection:
            rows = connection.execute("SELECT legacy_file_name FROM libraries WHERE archived = 0 ORDER BY legacy_file_name").fetchall()
        return [str(row["legacy_file_name"]) for row in rows if row["legacy_file_name"]]


class SkillsRepository:
    def __init__(self, database: SQLiteDatabase):
        self.database = database

    def replace_index(self, payload: Dict[str, Any], connection: sqlite3.Connection | None = None) -> None:
        def operation(conn: sqlite3.Connection) -> None:
            files = [row for row in payload.get("files", []) if isinstance(row, dict) and row.get("file")]
            for position, row in enumerate(files):
                conn.execute(
                    """INSERT INTO skill_sections(source_file,module,section,title,enabled,sort_order,index_entry_json)
                       VALUES(?,?,?,?,?,?,?) ON CONFLICT(source_file) DO UPDATE SET module=excluded.module,
                       section=excluded.section,title=excluded.title,enabled=excluded.enabled,
                       sort_order=excluded.sort_order,index_entry_json=excluded.index_entry_json""",
                    (row["file"], row.get("module"), row.get("section"), row.get("title"), int(bool(row.get("enabled", True))), position, _dump(row)),
                )
        if connection is not None:
            operation(connection)
        else:
            with self.database.transaction() as conn:
                operation(conn)

    def read_index(self) -> Dict[str, Any]:
        with self.database.read() as connection:
            rows = connection.execute("SELECT index_entry_json FROM skill_sections ORDER BY sort_order, source_file").fetchall()
        return {"version": 1, "files": [_load(row["index_entry_json"], {}) for row in rows]}

    def replace_source(self, source_file: str, payload: Dict[str, Any], connection: sqlite3.Connection | None = None) -> None:
        def operation(conn: sqlite3.Connection) -> None:
            metadata = {key: value for key, value in payload.items() if key != "skills"}
            conn.execute(
                """INSERT INTO skill_sections(source_file,module,section,title,source_metadata_json)
                   VALUES(?,?,?,?,?) ON CONFLICT(source_file) DO UPDATE SET module=excluded.module,
                   section=excluded.section,title=excluded.title,source_metadata_json=excluded.source_metadata_json""",
                (source_file, payload.get("module"), payload.get("section"), payload.get("title"), _dump(metadata)),
            )
            conn.execute("DELETE FROM skills WHERE source_file = ?", (source_file,))
            for position, raw in enumerate(payload.get("skills", [])):
                if not isinstance(raw, dict):
                    continue
                item = dict(raw)
                skill_id = str(item.get("id") or _stable_key(source_file, item, position))
                question_types = list(item.pop("question_types", []) or [])
                tags = list(item.pop("tags", []) or [])
                known = {"id", "module", "section", "grade", "topic", "skill", "detail", "difficulty", "enabled", "sort_order"}
                extra = {key: value for key, value in item.items() if key not in known}
                sort_order = item.get("sort_order")
                if sort_order is None:
                    sort_order = position
                conn.execute(
                    """INSERT INTO skills(id,source_file,module,section,grade,topic,skill,detail,difficulty,enabled,sort_order,extra_json)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (skill_id, source_file, item.get("module") or payload.get("module"), item.get("section") or payload.get("section"),
                     item.get("grade"), item.get("topic"), item.get("skill"), item.get("detail"), item.get("difficulty"),
                     int(bool(item.get("enabled", True))), int(sort_order), _dump(extra)),
                )
                conn.executemany("INSERT INTO skill_question_types(skill_id,position,value) VALUES(?,?,?)", [(skill_id, i, str(value)) for i, value in enumerate(question_types)])
                conn.executemany("INSERT INTO skill_tags(skill_id,position,value) VALUES(?,?,?)", [(skill_id, i, str(value)) for i, value in enumerate(tags)])
        if connection is not None:
            operation(connection)
        else:
            with self.database.transaction() as conn:
                operation(conn)

    def read_source(self, source_file: str) -> Dict[str, Any]:
        with self.database.read() as connection:
            source = connection.execute("SELECT * FROM skill_sections WHERE source_file = ?", (source_file,)).fetchone()
            if source is None:
                return {"version": 1, "skills": []}
            payload = _load(source["source_metadata_json"], {"version": 1})
            skills = []
            for row in connection.execute("SELECT * FROM skills WHERE source_file = ? ORDER BY sort_order, id", (source_file,)).fetchall():
                item = _load(row["extra_json"], {})
                item.update({
                    "id": row["id"], "module": row["module"], "section": row["section"],
                    "grade": row["grade"], "topic": row["topic"], "skill": row["skill"],
                    "detail": row["detail"], "difficulty": row["difficulty"],
                    "enabled": bool(row["enabled"]), "sort_order": row["sort_order"],
                })
                item["question_types"] = [value["value"] for value in connection.execute("SELECT value FROM skill_question_types WHERE skill_id=? ORDER BY position", (row["id"],)).fetchall()]
                item["tags"] = [value["value"] for value in connection.execute("SELECT value FROM skill_tags WHERE skill_id=? ORDER BY position", (row["id"],)).fetchall()]
                skills.append(item)
            payload["skills"] = skills
            return payload


class ReportRepository:
    def __init__(self, database: SQLiteDatabase):
        self.database = database

    def replace_all(self, payload: Dict[str, Any], connection: sqlite3.Connection | None = None) -> None:
        def operation(conn: sqlite3.Connection) -> None:
            conn.execute("DELETE FROM practice_reports")
            for position, raw in enumerate(payload.get("reports", [])):
                if not isinstance(raw, dict):
                    continue
                item = dict(raw)
                report_id = str(item.get("id") or _stable_key("report", item, position))
                details = item.get("details")
                conn.execute(
                    """INSERT INTO practice_reports(id,position,created_at,report_date,module,module_label,total_count,correct_count,payload_json)
                       VALUES(?,?,?,?,?,?,?,?,?)""",
                    (report_id, position, item.get("created_at"), item.get("date"), item.get("module"), item.get("module_label"),
                     int(item.get("total_count") or item.get("total_questions") or 0), int(item.get("correct_count") or item.get("correct") or 0), _dump(item)),
                )
                if isinstance(details, list):
                    conn.executemany("INSERT INTO practice_report_items(report_id,position,payload_json) VALUES(?,?,?)", [(report_id, i, _dump(value)) for i, value in enumerate(details)])
        if connection is not None:
            operation(connection)
        else:
            with self.database.transaction() as conn:
                operation(conn)

    def read_all(self) -> Dict[str, Any]:
        with self.database.read() as connection:
            reports = []
            for row in connection.execute("SELECT * FROM practice_reports ORDER BY position").fetchall():
                item = _load(row["payload_json"], {})
                details = [_load(value["payload_json"], {}) for value in connection.execute("SELECT payload_json FROM practice_report_items WHERE report_id=? ORDER BY position", (row["id"],)).fetchall()]
                if details:
                    item["details"] = details
                reports.append(item)
        return {"version": 1, "reports": reports}


class GenerationJobRepository:
    """Transactional storage for cross-worker incremental generation jobs."""

    ACTIVE_STATUSES = {"queued", "generating"}

    def __init__(self, database: SQLiteDatabase):
        self.database = database

    @staticmethod
    def _payload(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "job_id": row["id"],
            "kind": row["kind"],
            "status": row["status"],
            "requested_count": int(row["requested_count"]),
            "generated_count": int(row["generated_count"]),
            "request": _load(row["request_json"], {}),
            "plan": _load(row["plan_json"], {}),
            "metadata": _load(row["metadata_json"], {}),
            "questions": _load(row["questions_json"], []),
            "error": row["error"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "expires_at": row["expires_at"],
        }

    def create(
        self,
        *,
        kind: str,
        requested_count: int,
        request: Dict[str, Any],
        plan: Dict[str, Any],
        metadata: Dict[str, Any],
        expires_at: str,
    ) -> Dict[str, Any]:
        job_id = uuid.uuid4().hex
        now = _now()
        with self.database.transaction() as connection:
            connection.execute(
                """INSERT INTO generation_jobs(
                       id,kind,status,requested_count,generated_count,request_json,plan_json,
                       metadata_json,questions_json,error,created_at,updated_at,expires_at
                   ) VALUES(?,?,'queued',?,0,?,?,?,'[]',NULL,?,?,?)""",
                (
                    job_id,
                    kind,
                    requested_count,
                    _dump(request),
                    _dump(plan),
                    _dump(metadata),
                    now,
                    now,
                    expires_at,
                ),
            )
        return self.get(job_id)

    def get(self, job_id: str, kind: str | None = None) -> Optional[Dict[str, Any]]:
        with self.database.read() as connection:
            if kind:
                row = connection.execute(
                    "SELECT * FROM generation_jobs WHERE id=? AND kind=?",
                    (job_id, kind),
                ).fetchone()
            else:
                row = connection.execute(
                    "SELECT * FROM generation_jobs WHERE id=?",
                    (job_id,),
                ).fetchone()
        return self._payload(row) if row else None

    def mark_generating(self, job_id: str) -> bool:
        with self.database.transaction() as connection:
            cursor = connection.execute(
                "UPDATE generation_jobs SET status='generating',updated_at=? WHERE id=? AND status='queued'",
                (_now(), job_id),
            )
            if cursor.rowcount:
                return True
            row = connection.execute("SELECT status FROM generation_jobs WHERE id=?", (job_id,)).fetchone()
            return bool(row and row["status"] == "generating")

    def append_questions(self, job_id: str, questions: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not questions:
            return self.get(job_id)
        with self.database.transaction() as connection:
            row = connection.execute("SELECT * FROM generation_jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                return None
            if row["status"] not in self.ACTIVE_STATUSES:
                return self._payload(row)
            existing = _load(row["questions_json"], [])
            remaining = max(0, int(row["requested_count"]) - len(existing))
            existing.extend(questions[:remaining])
            generated_count = len(existing)
            status = "completed" if generated_count >= int(row["requested_count"]) else "generating"
            connection.execute(
                """UPDATE generation_jobs
                   SET status=?,generated_count=?,questions_json=?,updated_at=? WHERE id=?""",
                (status, generated_count, _dump(existing), _now(), job_id),
            )
        return self.get(job_id)

    def fail(self, job_id: str, error: str) -> Optional[Dict[str, Any]]:
        with self.database.transaction() as connection:
            connection.execute(
                """UPDATE generation_jobs
                   SET status=CASE WHEN generated_count>0 THEN 'partial_failed' ELSE 'failed' END,
                       error=?,updated_at=?
                   WHERE id=? AND status IN ('queued','generating')""",
                (str(error)[:1000], _now(), job_id),
            )
        return self.get(job_id)

    def cancel(self, job_id: str, kind: str | None = None) -> Optional[Dict[str, Any]]:
        with self.database.transaction() as connection:
            if kind:
                connection.execute(
                    """UPDATE generation_jobs SET status='cancelled',updated_at=?
                       WHERE id=? AND kind=? AND status IN ('queued','generating')""",
                    (_now(), job_id, kind),
                )
            else:
                connection.execute(
                    """UPDATE generation_jobs SET status='cancelled',updated_at=?
                       WHERE id=? AND status IN ('queued','generating')""",
                    (_now(), job_id),
                )
        return self.get(job_id, kind)

    def cleanup_expired(self, before: str) -> int:
        with self.database.transaction() as connection:
            cursor = connection.execute("DELETE FROM generation_jobs WHERE expires_at<?", (before,))
            return int(cursor.rowcount or 0)


class ModelSettingsRepository:
    def __init__(self, database: SQLiteDatabase):
        self.database = database

    def read(self) -> Dict[str, Any]:
        with self.database.read() as connection:
            row = connection.execute("SELECT selected_model,updated_at FROM model_settings WHERE id=1").fetchone()
        return {"version": 1, "selected_model": row["selected_model"] if row else None, "updated_at": row["updated_at"] if row else None}

    def write(self, payload: Dict[str, Any], connection: sqlite3.Connection | None = None) -> None:
        def operation(conn: sqlite3.Connection) -> None:
            conn.execute("INSERT INTO model_settings(id,selected_model,updated_at) VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET selected_model=excluded.selected_model,updated_at=excluded.updated_at", (payload.get("selected_model"), payload.get("updated_at")))
        if connection is not None:
            operation(connection)
        else:
            with self.database.transaction() as conn:
                operation(conn)


class HomepageSettingsRepository:
    """Store the public homepage document in the generic app-state table."""

    STATE_KEY = "homepage_settings"

    def __init__(self, database: SQLiteDatabase):
        self.database = database

    def read(self) -> Dict[str, Any]:
        with self.database.read() as connection:
            row = connection.execute(
                "SELECT value FROM app_state WHERE key = ?",
                (self.STATE_KEY,),
            ).fetchone()
        return _load(row["value"], {}) if row else {}

    def write(self, payload: Dict[str, Any]) -> None:
        now = _now()
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO app_state(key, value, updated_at) VALUES(?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (self.STATE_KEY, _dump(payload), now),
            )


class GalleryRepository:
    """Store Gallery metadata as one ordered document in app_state."""

    STATE_KEY = "gallery_items"

    def __init__(self, database: SQLiteDatabase):
        self.database = database

    def read(self) -> List[Dict[str, Any]]:
        with self.database.read() as connection:
            row = connection.execute(
                "SELECT value FROM app_state WHERE key = ?",
                (self.STATE_KEY,),
            ).fetchone()
        payload = _load(row["value"], []) if row else []
        return payload if isinstance(payload, list) else []

    def write(self, items: List[Dict[str, Any]]) -> None:
        now = _now()
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO app_state(key, value, updated_at) VALUES(?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (self.STATE_KEY, _dump(items), now),
            )


class ReadingRepository:
    """Persistence for uploaded books, detected chapters, and guided reading reports."""

    def __init__(self, database: SQLiteDatabase):
        self.database = database

    @staticmethod
    def _chapter_payload(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": row["id"],
            "book_id": row["book_id"],
            "title": row["title"],
            "start_page": row["start_page"],
            "end_page": row["end_page"],
            "sort_order": row["sort_order"],
            "detection_source": row["detection_source"],
            "confidence": row["confidence"],
            "content_text": row["content_text"],
            "extra": _load(row["extra_json"], {}),
        }

    @staticmethod
    def _book_payload(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": row["id"],
            "title": row["title"],
            "author": row["author"],
            "description": row["description"],
            "age_level": row["age_level"],
            "language": row["language"],
            "pdf_asset": row["pdf_asset"],
            "cover_asset": row["cover_asset"],
            "pdf_sha256": row["pdf_sha256"],
            "page_count": row["page_count"],
            "status": row["status"],
            "extraction_status": row["extraction_status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "extra": _load(row["extra_json"], {}),
        }

    def create_book(self, book: Dict[str, Any], chapters: List[Dict[str, Any]]) -> Dict[str, Any]:
        with self.database.transaction() as connection:
            connection.execute(
                """INSERT INTO reading_books(
                       id,title,author,description,age_level,language,pdf_asset,cover_asset,
                       pdf_sha256,page_count,status,extraction_status,created_at,updated_at,extra_json
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    book["id"], book["title"], book.get("author", ""),
                    book.get("description", ""), book.get("age_level", ""),
                    book.get("language", "English"), book["pdf_asset"],
                    book.get("cover_asset"), book["pdf_sha256"], int(book["page_count"]),
                    book.get("status", "draft"), book.get("extraction_status", "ready"),
                    book["created_at"], book["updated_at"], _dump(book.get("extra", {})),
                ),
            )
            self._replace_chapters(connection, book["id"], chapters)
        return self.get_book(book["id"])  # type: ignore[return-value]

    def _replace_chapters(
        self, connection: sqlite3.Connection, book_id: str, chapters: List[Dict[str, Any]]
    ) -> None:
        connection.execute("DELETE FROM reading_chapters WHERE book_id=?", (book_id,))
        for position, chapter in enumerate(chapters):
            connection.execute(
                """INSERT INTO reading_chapters(
                       id,book_id,title,start_page,end_page,sort_order,detection_source,
                       confidence,content_text,extra_json
                   ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    chapter.get("id") or uuid.uuid4().hex, book_id, chapter["title"],
                    int(chapter["start_page"]), int(chapter["end_page"]),
                    int(chapter.get("sort_order", position)),
                    chapter.get("detection_source", "admin"),
                    float(chapter.get("confidence", 1.0)), chapter.get("content_text", ""),
                    _dump(chapter.get("extra", {})),
                ),
            )

    def replace_chapters(self, book_id: str, chapters: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        with self.database.transaction() as connection:
            if not connection.execute("SELECT 1 FROM reading_books WHERE id=?", (book_id,)).fetchone():
                return None
            self._replace_chapters(connection, book_id, chapters)
            connection.execute(
                "UPDATE reading_books SET updated_at=?,extraction_status='ready' WHERE id=?",
                (_now(), book_id),
            )
        return self.get_book(book_id)

    def get_book(self, book_id: str) -> Optional[Dict[str, Any]]:
        with self.database.read() as connection:
            row = connection.execute("SELECT * FROM reading_books WHERE id=?", (book_id,)).fetchone()
            if row is None:
                return None
            payload = self._book_payload(row)
            chapters = connection.execute(
                "SELECT * FROM reading_chapters WHERE book_id=? ORDER BY sort_order,id", (book_id,)
            ).fetchall()
        payload["chapters"] = [self._chapter_payload(chapter) for chapter in chapters]
        return payload

    def find_book_by_sha256(self, digest: str) -> Optional[Dict[str, Any]]:
        with self.database.read() as connection:
            row = connection.execute("SELECT id FROM reading_books WHERE pdf_sha256=?", (digest,)).fetchone()
        return self.get_book(row["id"]) if row else None

    def list_books(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        query = "SELECT * FROM reading_books"
        parameters: List[Any] = []
        if status:
            query += " WHERE status=?"
            parameters.append(status)
        query += " ORDER BY updated_at DESC,title"
        with self.database.read() as connection:
            rows = connection.execute(query, parameters).fetchall()
            if not rows:
                return []
            ids = [row["id"] for row in rows]
            placeholders = ",".join("?" for _ in ids)
            chapter_rows = connection.execute(
                f"SELECT * FROM reading_chapters WHERE book_id IN ({placeholders}) ORDER BY book_id,sort_order,id",
                ids,
            ).fetchall()
        chapters_by_book: Dict[str, List[Dict[str, Any]]] = {book_id: [] for book_id in ids}
        for chapter in chapter_rows:
            chapters_by_book[chapter["book_id"]].append(self._chapter_payload(chapter))
        books = []
        for row in rows:
            payload = self._book_payload(row)
            payload["chapters"] = chapters_by_book[row["id"]]
            books.append(payload)
        return books

    def update_book(self, book_id: str, values: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        allowed = {"title", "author", "description", "age_level", "language", "status", "extraction_status", "cover_asset"}
        updates = {key: value for key, value in values.items() if key in allowed}
        if not updates:
            return self.get_book(book_id)
        updates["updated_at"] = _now()
        assignments = ",".join(f"{key}=?" for key in updates)
        with self.database.transaction() as connection:
            cursor = connection.execute(
                f"UPDATE reading_books SET {assignments} WHERE id=?",
                [*updates.values(), book_id],
            )
            if not cursor.rowcount:
                return None
        return self.get_book(book_id)

    @staticmethod
    def _question_payload(row: sqlite3.Row, include_private: bool) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "id": row["id"], "position": row["position"],
            "question_text": row["question_text"], "question_type": row["question_type"],
            "purpose": row["purpose"], "child_answer": row["child_answer"],
            "input_mode": row["input_mode"], "feedback": row["feedback"],
            "understanding_level": row["understanding_level"],
            "follow_up_question": row["follow_up_question"],
            "follow_up_answer": row["follow_up_answer"],
            "follow_up_feedback": row["follow_up_feedback"], "answered_at": row["answered_at"],
        }
        if include_private:
            payload.update({
                "reference_answer": row["reference_answer"],
                "evidence": _load(row["evidence_json"], []),
                "parent_note": row["parent_note"],
            })
        return payload

    @classmethod
    def _session_payload(cls, row: sqlite3.Row, questions: List[sqlite3.Row], include_private: bool) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "id": row["id"], "book_id": row["book_id"],
            "chapter_ids": _load(row["chapter_ids_json"], []), "status": row["status"],
            "question_count": row["question_count"], "overall_level": row["overall_level"],
            "student_summary": row["student_summary"], "created_at": row["created_at"],
            "updated_at": row["updated_at"], "completed_at": row["completed_at"],
            "questions": [cls._question_payload(question, include_private) for question in questions],
        }
        if include_private:
            payload["parent_summary"] = row["parent_summary"]
            payload["evaluation"] = _load(row["evaluation_json"], {})
        return payload

    def create_session(self, session: Dict[str, Any], questions: List[Dict[str, Any]]) -> Dict[str, Any]:
        with self.database.transaction() as connection:
            connection.execute(
                """INSERT INTO reading_sessions(
                       id,access_token_hash,book_id,chapter_ids_json,status,question_count,
                       created_at,updated_at,evaluation_json
                   ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    session["id"], session["access_token_hash"], session["book_id"],
                    _dump(session["chapter_ids"]), "active", len(questions),
                    session["created_at"], session["updated_at"], "{}",
                ),
            )
            for position, question in enumerate(questions):
                connection.execute(
                    """INSERT INTO reading_session_questions(
                           id,session_id,position,question_text,question_type,purpose,
                           reference_answer,evidence_json,extra_json
                       ) VALUES(?,?,?,?,?,?,?,?,?)""",
                    (
                        question.get("id") or uuid.uuid4().hex, session["id"], position,
                        question["question_text"], question.get("question_type", "understanding"),
                        question.get("purpose", ""), question.get("reference_answer", ""),
                        _dump(question.get("evidence", [])), _dump(question.get("extra", {})),
                    ),
                )
        return self.get_session(session["id"], include_private=True)  # type: ignore[return-value]

    def get_session(self, session_id: str, include_private: bool = False) -> Optional[Dict[str, Any]]:
        with self.database.read() as connection:
            row = connection.execute("SELECT * FROM reading_sessions WHERE id=?", (session_id,)).fetchone()
            if row is None:
                return None
            questions = connection.execute(
                "SELECT * FROM reading_session_questions WHERE session_id=? ORDER BY position,id",
                (session_id,),
            ).fetchall()
        return self._session_payload(row, questions, include_private)

    def get_session_token_hash(self, session_id: str) -> Optional[str]:
        with self.database.read() as connection:
            row = connection.execute(
                "SELECT access_token_hash FROM reading_sessions WHERE id=?", (session_id,)
            ).fetchone()
        return row["access_token_hash"] if row else None

    def list_sessions(self) -> List[Dict[str, Any]]:
        with self.database.read() as connection:
            rows = connection.execute("SELECT * FROM reading_sessions ORDER BY created_at DESC").fetchall()
            if not rows:
                return []
            ids = [row["id"] for row in rows]
            placeholders = ",".join("?" for _ in ids)
            question_rows = connection.execute(
                f"SELECT * FROM reading_session_questions WHERE session_id IN ({placeholders}) ORDER BY session_id,position,id",
                ids,
            ).fetchall()
        questions_by_session: Dict[str, List[sqlite3.Row]] = {session_id: [] for session_id in ids}
        for question in question_rows:
            questions_by_session[question["session_id"]].append(question)
        return [
            self._session_payload(row, questions_by_session[row["id"]], include_private=True)
            for row in rows
        ]

    def update_question(self, session_id: str, question_id: str, values: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        allowed = {
            "child_answer", "input_mode", "feedback", "understanding_level", "parent_note",
            "follow_up_question", "follow_up_answer", "follow_up_feedback", "answered_at",
        }
        updates = {key: value for key, value in values.items() if key in allowed}
        if not updates:
            return self.get_session(session_id, include_private=True)
        with self.database.transaction() as connection:
            cursor = connection.execute(
                f"UPDATE reading_session_questions SET {','.join(f'{key}=?' for key in updates)} WHERE id=? AND session_id=?",
                [*updates.values(), question_id, session_id],
            )
            if not cursor.rowcount:
                return None
            connection.execute("UPDATE reading_sessions SET updated_at=? WHERE id=?", (_now(), session_id))
        return self.get_session(session_id, include_private=True)

    def complete_session(self, session_id: str, evaluation: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        now = _now()
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """UPDATE reading_sessions SET status='completed',overall_level=?,student_summary=?,
                       parent_summary=?,evaluation_json=?,updated_at=?,completed_at=? WHERE id=?""",
                (
                    evaluation.get("overall_level"), evaluation.get("student_summary", ""),
                    evaluation.get("parent_summary", ""), _dump(evaluation), now, now, session_id,
                ),
            )
            if not cursor.rowcount:
                return None
        return self.get_session(session_id, include_private=True)


class TodoRepository:
    def __init__(self, database: SQLiteDatabase):
        self.database = database

    def read_settings(self) -> Dict[str, Any]:
        with self.database.read() as connection:
            row = connection.execute("SELECT * FROM todo_settings WHERE id=1").fetchone()
        if row is None:
            return {}
        payload = _load(row["extra_json"], {})
        payload.update({"version": 1, "timezone": row["timezone"], "recurrence_horizon_days": row["recurrence_horizon_days"], "backup_retention": row["backup_retention"], "updated_at": row["updated_at"]})
        return payload

    def write_settings(self, payload: Dict[str, Any], connection: sqlite3.Connection | None = None) -> None:
        known = {"version", "timezone", "recurrence_horizon_days", "backup_retention", "updated_at"}
        extra = {key: value for key, value in payload.items() if key not in known}
        def operation(conn: sqlite3.Connection) -> None:
            conn.execute("""INSERT INTO todo_settings(id,timezone,recurrence_horizon_days,backup_retention,updated_at,extra_json)
                VALUES(1,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET timezone=excluded.timezone,
                recurrence_horizon_days=excluded.recurrence_horizon_days,backup_retention=excluded.backup_retention,
                updated_at=excluded.updated_at,extra_json=excluded.extra_json""",
                (payload.get("timezone", "Asia/Shanghai"), int(payload.get("recurrence_horizon_days", 400)), int(payload.get("backup_retention", 50)), payload.get("updated_at"), _dump(extra)))
        if connection is not None: operation(connection)
        else:
            with self.database.transaction() as conn: operation(conn)

    def replace_subjects(self, payload: Dict[str, Any], connection: sqlite3.Connection | None = None) -> None:
        def operation(conn: sqlite3.Connection) -> None:
            rows = [row for row in payload.get("subjects", []) if isinstance(row, dict) and row.get("id")]
            for position, row in enumerate(rows):
                conn.execute(
                    """INSERT INTO todo_subjects(id,name,color,sort_order,enabled,payload_json)
                       VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,
                       color=excluded.color,sort_order=excluded.sort_order,enabled=excluded.enabled,
                       payload_json=excluded.payload_json""",
                    (row["id"], row.get("name", ""), row.get("color", "#6B7280"), int(row.get("sort_order", position)), int(bool(row.get("enabled", True))), _dump(row)),
                )
            ids = [str(row["id"]) for row in rows]
            exclusion = ""
            parameters: list[Any] = []
            if ids:
                exclusion = f"id NOT IN ({','.join('?' for _ in ids)}) AND "
                parameters.extend(ids)
            conn.execute(
                f"""DELETE FROM todo_subjects
                    WHERE {exclusion}
                    NOT EXISTS(SELECT 1 FROM todo_templates WHERE todo_templates.subject_id=todo_subjects.id)
                    AND NOT EXISTS(SELECT 1 FROM todo_tasks WHERE todo_tasks.subject_id=todo_subjects.id)""",
                parameters,
            )
        if connection is not None: operation(connection)
        else:
            with self.database.transaction() as conn: operation(conn)

    def read_subjects(self) -> Dict[str, Any]:
        with self.database.read() as connection:
            rows = connection.execute("SELECT payload_json FROM todo_subjects ORDER BY sort_order,id").fetchall()
        return {"version": 1, "subjects": [_load(row["payload_json"], {}) for row in rows]}

    def replace_templates(self, payload: Dict[str, Any], connection: sqlite3.Connection | None = None) -> None:
        def operation(conn: sqlite3.Connection) -> None:
            rows = [row for row in payload.get("templates", []) if isinstance(row, dict) and row.get("id")]
            for row in rows:
                if not isinstance(row, dict) or not row.get("id"): continue
                weekdays = list(row.get("repeat_weekdays", []) or [])
                stored = dict(row); stored.pop("repeat_weekdays", None)
                conn.execute(
                    """INSERT INTO todo_templates(id,subject_id,title,start_date,end_date,repeat_kind,active,payload_json)
                       VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET subject_id=excluded.subject_id,
                       title=excluded.title,start_date=excluded.start_date,end_date=excluded.end_date,
                       repeat_kind=excluded.repeat_kind,active=excluded.active,payload_json=excluded.payload_json""",
                    (row["id"], row.get("subject_id"), row.get("title", ""), row.get("start_date"), row.get("end_date"), row.get("repeat", "once"), int(bool(row.get("active", True))), _dump(stored)),
                )
                conn.execute("DELETE FROM todo_template_weekdays WHERE template_id=?", (row["id"],))
                conn.executemany("INSERT INTO todo_template_weekdays(template_id,position,weekday) VALUES(?,?,?)", [(row["id"], i, int(value)) for i, value in enumerate(weekdays)])
            ids = [str(row["id"]) for row in rows]
            if ids:
                placeholders = ",".join("?" for _ in ids)
                conn.execute(
                    f"""DELETE FROM todo_templates WHERE id NOT IN ({placeholders})
                        AND NOT EXISTS(SELECT 1 FROM todo_tasks WHERE todo_tasks.template_id=todo_templates.id)""",
                    ids,
                )
            else:
                conn.execute(
                    "DELETE FROM todo_templates WHERE NOT EXISTS(SELECT 1 FROM todo_tasks WHERE todo_tasks.template_id=todo_templates.id)"
                )
        if connection is not None: operation(connection)
        else:
            with self.database.transaction() as conn: operation(conn)

    def read_templates(self) -> Dict[str, Any]:
        with self.database.read() as connection:
            result = []
            for row in connection.execute("SELECT id,payload_json FROM todo_templates ORDER BY start_date,id").fetchall():
                item = _load(row["payload_json"], {})
                item["repeat_weekdays"] = [value["weekday"] for value in connection.execute("SELECT weekday FROM todo_template_weekdays WHERE template_id=? ORDER BY position", (row["id"],)).fetchall()]
                result.append(item)
        return {"version": 1, "templates": result}

    def replace_tasks(self, month: str, payload: Dict[str, Any], connection: sqlite3.Connection | None = None) -> None:
        def operation(conn: sqlite3.Connection) -> None:
            conn.execute("DELETE FROM todo_tasks WHERE substr(planned_date,1,7)=?", (month,))
            for position, row in enumerate(payload.get("tasks", [])):
                if not isinstance(row, dict) or not row.get("id"): continue
                history = list(row.get("history", []) or [])
                stored = dict(row); stored.pop("history", None)
                conn.execute("INSERT INTO todo_tasks(id,position,subject_id,template_id,title,planned_date,lifecycle_status,completed_at,payload_json) VALUES(?,?,?,?,?,?,?,?,?)", (row["id"], position, row.get("subject_id"), row.get("template_id"), row.get("title", ""), row.get("planned_date"), row.get("lifecycle_status", "active"), row.get("completed_at"), _dump(stored)))
                for history_position, event in enumerate(history):
                    details = {key: value for key, value in event.items() if key not in {"type", "at"}}
                    conn.execute("INSERT INTO todo_task_history(task_id,position,event_type,event_at,details_json) VALUES(?,?,?,?,?)", (row["id"], history_position, event.get("type", "unknown"), event.get("at"), _dump(details)))
        if connection is not None: operation(connection)
        else:
            with self.database.transaction() as conn: operation(conn)

    def read_tasks(self, month: str) -> Dict[str, Any]:
        with self.database.read() as connection:
            result = []
            for row in connection.execute("SELECT id,payload_json FROM todo_tasks WHERE substr(planned_date,1,7)=? ORDER BY position,id", (month,)).fetchall():
                item = _load(row["payload_json"], {})
                item["history"] = []
                for event in connection.execute("SELECT * FROM todo_task_history WHERE task_id=? ORDER BY position", (row["id"],)).fetchall():
                    item["history"].append({"type": event["event_type"], "at": event["event_at"], **_load(event["details_json"], {})})
                result.append(item)
        return {"version": 1, "month": month, "tasks": result}

    def list_months(self) -> List[str]:
        with self.database.read() as connection:
            rows = connection.execute("SELECT DISTINCT substr(planned_date,1,7) AS month FROM todo_tasks WHERE planned_date IS NOT NULL ORDER BY month").fetchall()
        return [row["month"] for row in rows if row["month"]]

    def delete_all_tasks(self, connection: sqlite3.Connection | None = None) -> None:
        if connection is not None: connection.execute("DELETE FROM todo_tasks")
        else:
            with self.database.transaction() as conn: conn.execute("DELETE FROM todo_tasks")

    def _replace_payload_rows(self, table: str, list_name: str, payload: Dict[str, Any], connection: sqlite3.Connection | None = None) -> None:
        def operation(conn: sqlite3.Connection) -> None:
            conn.execute(f"DELETE FROM {table}")
            for position, row in enumerate(payload.get(list_name, [])):
                if not isinstance(row, dict): continue
                key = str(row.get("id") or _stable_key(table, row, position))
                if table == "todo_reports":
                    conn.execute("INSERT INTO todo_reports(record_key,position,payload_json) VALUES(?,?,?)", (key, position, _dump(row)))
                else:
                    conn.execute("INSERT INTO points_ledger(record_key,position,transaction_type,points,purpose,created_at,payload_json) VALUES(?,?,?,?,?,?,?)", (key, position, row.get("type", "spend"), int(row.get("points", 0)), str(row.get("purpose", "")), row.get("created_at"), _dump(row)))
        if connection is not None: operation(connection)
        else:
            with self.database.transaction() as conn: operation(conn)

    def replace_reports(self, payload: Dict[str, Any], connection: sqlite3.Connection | None = None) -> None:
        self._replace_payload_rows("todo_reports", "reports", payload, connection)

    def replace_ledger(self, payload: Dict[str, Any], connection: sqlite3.Connection | None = None) -> None:
        self._replace_payload_rows("points_ledger", "transactions", payload, connection)

    def _read_payload_rows(self, table: str, list_name: str) -> Dict[str, Any]:
        with self.database.read() as connection:
            rows = connection.execute(f"SELECT payload_json FROM {table} ORDER BY position").fetchall()
        return {"version": 1, list_name: [_load(row["payload_json"], {}) for row in rows]}

    def read_reports(self) -> Dict[str, Any]: return self._read_payload_rows("todo_reports", "reports")
    def read_ledger(self) -> Dict[str, Any]: return self._read_payload_rows("points_ledger", "transactions")


def _read_json(path: Path, fallback: Dict[str, Any]) -> Dict[str, Any]:
    if not path.is_file(): return dict(fallback)
    with path.open("r", encoding="utf-8") as handle: payload = json.load(handle)
    if not isinstance(payload, dict): raise ValueError(f"JSON 顶层必须是对象: {path}")
    return payload


def _record_source(connection: sqlite3.Connection, path: Path) -> None:
    if not path.is_file(): return
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    connection.execute("INSERT OR REPLACE INTO data_migration_sources(source_path,sha256,imported_at) VALUES(?,?,?)", (str(path.resolve()), digest, _now()))


def _parse_legacy_items(path: Path, subject: str) -> List[str]:
    if not path.is_file(): return []
    content = path.read_text(encoding="utf-8").strip()
    if not content: return []
    separator = r"[,，\r\n]+" if subject == "chinese" else r"[,\r\n]+"
    return [item.strip() for item in re.split(separator, content) if item.strip()]


def migrate_todo_legacy_data(todo_root: str | Path, database: SQLiteDatabase | None = None) -> Dict[str, Any]:
    root = Path(todo_root).resolve()
    db = database or database_for_todo_root(root)
    repository = TodoRepository(db)
    state_key = f"todo_legacy_migrated:{root}"
    with db.read() as connection:
        if connection.execute("SELECT 1 FROM app_state WHERE key=?", (state_key,)).fetchone():
            return {"todo_migrated": False}
    with db.transaction() as connection:
        # 多个 Gunicorn worker 可能同时通过事务外的快速检查；写事务拿到锁后
        # 必须再次确认，确保只有一个 worker 执行首次迁移。
        if connection.execute("SELECT 1 FROM app_state WHERE key=?", (state_key,)).fetchone():
            return {"todo_migrated": False}
        settings = _read_json(root / "settings.json", {})
        if settings: repository.write_settings(settings, connection)
        subjects = _read_json(root / "subjects.json", {"subjects": []})
        if subjects.get("subjects"): repository.replace_subjects(subjects, connection)
        templates = _read_json(root / "templates.json", {"templates": []})
        if templates.get("templates"): repository.replace_templates(templates, connection)
        repository.replace_reports(_read_json(root / "reports.json", {"reports": []}), connection)
        repository.replace_ledger(_read_json(root / "points-ledger.json", {"transactions": []}), connection)
        for path in sorted((root / "tasks").glob("*.json")):
            repository.replace_tasks(path.stem, _read_json(path, {"tasks": []}), connection)
        for path in [root / "settings.json", root / "subjects.json", root / "templates.json", root / "reports.json", root / "points-ledger.json", *sorted((root / "tasks").glob("*.json"))]:
            _record_source(connection, path)
        connection.execute("INSERT INTO app_state(key,value,updated_at) VALUES(?,?,?)", (state_key, "1", _now()))
    return {"todo_migrated": True}


def migrate_legacy_data(data_root: str | Path | None = None, database: SQLiteDatabase | None = None) -> Dict[str, Any]:
    root = Path(data_root or config.DATA_DIR).resolve()
    db = database or database_for_data_root(root)
    state_key = f"legacy_migrated:{root}"
    with db.read() as connection:
        if connection.execute("SELECT 1 FROM app_state WHERE key=?", (state_key,)).fetchone():
            return {"database_path": str(db.path), "migrated": False}

    library_repository = LibraryRepository(db)
    skills_repository = SkillsRepository(db)
    report_repository = ReportRepository(db)
    model_repository = ModelSettingsRepository(db)
    registry_path = root / "library_registry.json"
    archive_path = root / "library_archive.json"
    registry = _read_json(registry_path, {"version": 1, "libraries": []})
    archive = _read_json(archive_path, {"version": 1, "libraries": []})
    active_rows = [dict(row) for row in registry.get("libraries", []) if isinstance(row, dict)]
    archived_rows = [dict(row) for row in archive.get("libraries", []) if isinstance(row, dict)]
    known_names = {str(row.get("file_name") or row.get("name")) for row in [*active_rows, *archived_rows]}
    for path in sorted(root.glob("*.txt")):
        if path.stem in known_names: continue
        subject = "chinese" if path.stem.startswith("chinese_") else "english"
        now = _now()
        active_rows.append({"id": uuid.uuid5(uuid.NAMESPACE_URL, f"jingsen-library:{path.stem}").hex, "subject": subject, "name": path.stem, "file_name": path.stem, "enabled": True, "created_at": now, "updated_at": now})

    with db.transaction() as connection:
        # 这是多 worker 启动时的权威检查。第二个 worker 会等待第一个事务
        # 提交，然后在这里直接退出，不会重复导入或触发主键冲突。
        if connection.execute("SELECT 1 FROM app_state WHERE key=?", (state_key,)).fetchone():
            return {"database_path": str(db.path), "migrated": False}
        library_repository.replace_registry({"version": 1, "libraries": active_rows}, connection)
        library_repository.replace_archive({"version": 1, "libraries": archived_rows}, connection)
        for row in active_rows:
            items = _parse_legacy_items(root / f"{row.get('file_name') or row.get('name')}.txt", str(row.get("subject") or "english"))
            library_repository._replace_items(connection, str(row["id"]), items)
        for row in archived_rows:
            items = row.get("items") if isinstance(row.get("items"), list) else _parse_legacy_items(root / f"{row.get('file_name') or row.get('name')}.txt", str(row.get("subject") or "english"))
            library_repository._replace_items(connection, str(row["id"]), items)

        index_path = root / "skills" / "index.json"
        index = _read_json(index_path, {"version": 1, "files": []})
        skills_repository.replace_index(index, connection)
        for entry in index.get("files", []):
            if isinstance(entry, dict) and entry.get("file"):
                source_path = root / "skills" / str(entry["file"])
                skills_repository.replace_source(str(entry["file"]), _read_json(source_path, {"skills": []}), connection)
                _record_source(connection, source_path)

        report_path = root / "report_history.json"
        report_repository.replace_all(_read_json(report_path, {"reports": []}), connection)
        model_path = root / "model-settings.json"
        model_payload = _read_json(model_path, {})
        if model_payload: model_repository.write(model_payload, connection)
        for path in (registry_path, archive_path, index_path, report_path, model_path, *sorted(root.glob("*.txt"))):
            _record_source(connection, path)
        connection.execute("INSERT INTO app_state(key,value,updated_at) VALUES(?,?,?)", (state_key, "1", _now()))

    todo_result = migrate_todo_legacy_data(root / "learning-todo", db)
    return {"database_path": str(db.path), "migrated": True, **todo_result}
