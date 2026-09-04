import json
from concurrent.futures import ThreadPoolExecutor

from database import (
    LibraryRepository,
    ReportRepository,
    SQLiteDatabase,
    SkillsRepository,
    TodoRepository,
    migrate_legacy_data,
)


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_full_legacy_migration_creates_relational_records_without_changing_sources(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    registry = {
        "version": 1,
        "libraries": [{
            "id": "lib_active", "subject": "english", "name": "words",
            "file_name": "words", "enabled": True,
            "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z",
        }],
    }
    archive = {
        "version": 1,
        "libraries": [{
            "id": "lib_archived", "subject": "chinese", "name": "idioms",
            "file_name": "idioms", "enabled": False, "archived": True,
            "archived_at": "2026-01-02T00:00:00Z", "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-02T00:00:00Z", "items": ["一心一意", "一心一意"],
        }],
    }
    _write_json(data / "library_registry.json", registry)
    _write_json(data / "library_archive.json", archive)
    (data / "words.txt").write_text("alpha, beta, beta", encoding="utf-8")
    _write_json(data / "skills" / "index.json", {"version": 1, "files": [{"file": "reading.json", "module": "reading", "section": "main", "enabled": True}]})
    _write_json(data / "skills" / "reading.json", {"version": 1, "module": "reading", "section": "main", "skills": [{"id": "skill_1", "grade": "G3", "topic": "Main Idea", "skill": "Identify", "detail": "Find the main idea", "question_types": ["multiple_choice"], "tags": ["reading"], "enabled": True, "sort_order": 0}]})
    _write_json(data / "report_history.json", {"version": 1, "reports": [{"id": "report_1", "created_at": "2026-01-03T10:00:00", "date": "2026-01-03", "module": "reading", "total_count": 2, "correct_count": 2, "details": []}]})
    _write_json(data / "model-settings.json", {"version": 1, "selected_model": "gpt-test", "updated_at": "2026-01-03T10:00:00Z"})

    todo = data / "learning-todo"
    _write_json(todo / "settings.json", {"version": 1, "timezone": "Asia/Shanghai", "recurrence_horizon_days": 400, "backup_retention": 50})
    _write_json(todo / "subjects.json", {"version": 1, "subjects": [{"id": "sub_1", "name": "阅读", "color": "#123456", "sort_order": 1, "enabled": True}]})
    _write_json(todo / "templates.json", {"version": 1, "templates": [{"id": "tpl_1", "subject_id": "sub_1", "title": "每日阅读", "repeat": "daily", "repeat_weekdays": [1, 2], "active": True}]})
    _write_json(todo / "reports.json", {"version": 1, "reports": [{"id": "todo_report_1", "summary": "完成良好"}]})
    _write_json(todo / "points-ledger.json", {"version": 1, "transactions": [{"id": "spend_1", "type": "spend", "points": 2, "purpose": "兑换", "created_at": "2026-01-03T12:00:00Z"}]})
    _write_json(todo / "tasks" / "2026-01.json", {"version": 1, "month": "2026-01", "tasks": [{"id": "task_1", "subject_id": "sub_1", "template_id": "tpl_1", "title": "阅读", "planned_date": "2026-01-03", "lifecycle_status": "active", "history": [{"type": "created", "at": "2026-01-01T00:00:00Z"}]}]})

    source_bytes = {path: path.read_bytes() for path in data.rglob("*.json")}
    database = SQLiteDatabase(data / "learning-center.sqlite3")
    result = migrate_legacy_data(data, database)

    assert result["migrated"] is True
    assert LibraryRepository(database).get_items("words") == ["alpha", "beta", "beta"]
    assert LibraryRepository(database).read_archive()["libraries"][0]["items"] == ["一心一意", "一心一意"]
    assert SkillsRepository(database).read_source("reading.json")["skills"][0]["question_types"] == ["multiple_choice"]
    assert ReportRepository(database).read_all()["reports"][0]["details"] == []
    assert TodoRepository(database).read_tasks("2026-01")["tasks"][0]["history"][0]["type"] == "created"
    assert all(path.read_bytes() == content for path, content in source_bytes.items())

    with database.read() as connection:
        assert connection.execute("SELECT COUNT(*) FROM library_items").fetchone()[0] == 5
        assert connection.execute("SELECT COUNT(*) FROM skill_question_types").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM todo_task_history").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM schema_migrations WHERE version=2").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM schema_migrations WHERE version=3").fetchone()[0] == 1
        assert connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='generation_jobs'").fetchone()[0] == "generation_jobs"
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []

    assert migrate_legacy_data(data, database)["migrated"] is False


def test_concurrent_worker_startup_runs_legacy_migration_only_once(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    _write_json(data / "library_registry.json", {"version": 1, "libraries": []})
    _write_json(data / "library_archive.json", {"version": 1, "libraries": []})
    _write_json(data / "skills" / "index.json", {"version": 1, "files": []})
    database_path = data / "learning-center.sqlite3"

    def migrate_from_worker():
        return migrate_legacy_data(data, SQLiteDatabase(database_path))["migrated"]

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: migrate_from_worker(), range(2)))

    assert sorted(results) == [False, True]
    with SQLiteDatabase(database_path).read() as connection:
        assert connection.execute("SELECT COUNT(*) FROM app_state WHERE key LIKE 'legacy_migrated:%'").fetchone()[0] == 1
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
