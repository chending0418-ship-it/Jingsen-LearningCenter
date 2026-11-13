from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3
import time

import pytest
from fastapi.testclient import TestClient

from config import config
from database import SQLiteDatabase
from services.library_admin_service import LibraryAdminService
from services.report_history_service import ReportHistoryService
from services.word_matching_service import WordMatchingService


PUBLIC = "/learningcenter/api/english/word-matching"
ADMIN = "/api/admin/word-matching/banks"
PAIRS = {
    "蒸发": "evaporation",
    "气体变成液体, 如露水": "condensation",
    "水从云里落下": "precipitation",
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "offline-test-fixture")
    monkeypatch.setenv("SQLITE_DATABASE_PATH", str(tmp_path / "matching.sqlite3"))
    monkeypatch.setattr(config, "OPENAI_API_KEY", "offline-test-fixture")
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "matching-test-password")
    monkeypatch.setattr(config, "ADMIN_COOKIE_SECURE", False)
    from api import admin, english, report_history
    from main import app

    monkeypatch.setattr(report_history, "report_history_service", ReportHistoryService())
    libraries = LibraryAdminService()
    monkeypatch.setattr(admin, "library_admin_service", libraries)
    monkeypatch.setattr(english.english_service, "library_admin_service", libraries)
    with TestClient(app) as test_client:
        yield test_client


def login(client):
    assert client.post("/api/admin/session", json={"password": config.ADMIN_PASSWORD}).status_code == 200


def answers_for(attempt):
    return {item["id"]: PAIRS[item["meaning"]] for item in attempt["questions"]}


def test_admin_to_practice_to_daily_report(client):
    payload = {"name": "  科学 Packet3 ", "pairs_text": "\n".join(f"{word},{meaning}" for meaning, word in PAIRS.items())}
    assert client.get("/admin/learningcenter/word-matching", follow_redirects=False).status_code == 303
    assert client.get(ADMIN).status_code == 401
    assert client.post(ADMIN, json=payload).status_code == 401
    assert client.get(f"{PUBLIC}/banks").json() == {"banks": []}
    login(client)
    assert client.get("/admin/learningcenter/word-matching").status_code == 200
    created = client.post(ADMIN, json=payload)
    assert created.status_code == 201
    bank = created.json()
    bank_id = bank["id"]
    assert bank["name"] == "科学 Packet3" and bank["pair_count"] == 3
    assert client.get(f"{ADMIN}/{bank_id}").json()["pairs_text"] == payload["pairs_text"]
    assert client.post(ADMIN, json=payload | {"name": "科学 packet3"}).status_code == 400
    assert client.delete("/api/admin/session").status_code == 200
    assert client.get(f"{ADMIN}/{bank_id}").status_code == 401
    assert client.get(f"{PUBLIC}/banks").json()["banks"] == [bank]

    response = client.post(f"{PUBLIC}/attempts", json={"bank_id": bank_id})
    assert response.status_code == 201
    attempt = response.json()
    assert set(attempt) == {"id", "bank_name", "questions"}
    assert len(attempt["questions"]) == len(PAIRS)
    assert not any(word in response.text for word in PAIRS.values())
    assert all(set(item) == {"id", "meaning"} for item in attempt["questions"])
    grade_url = f"{PUBLIC}/attempts/{attempt['id']}/grade"
    assert client.post(grade_url, json={"answers": {}}).status_code == 400
    answers = answers_for(attempt)
    first, second, third = answers
    assert client.post(grade_url, json={"answers": answers | {first: "  "}}).status_code == 400
    assert client.post(grade_url, json={"answers": answers | {"forged": "anything"}}).status_code == 400
    assert client.post(grade_url, json={"answers": answers | {first: "a" * 101}}).status_code == 422

    login(client)
    assert client.put(f"{ADMIN}/{bank_id}", json={"name": "Edited", "pairs_text": "alpha,一\nbeta,二"}).status_code == 200
    next_attempt = client.post(f"{PUBLIC}/attempts", json={"bank_id": bank_id}).json()
    assert next_attempt["bank_name"] == "Edited"
    assert {item["meaning"] for item in next_attempt["questions"]} == {"一", "二"}
    answers[first] = answers[second] = "misspelled"
    answers[third] = "  " + answers[third].upper() + "  "
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: client.post(grade_url, json={"answers": answers}), range(2)))
    assert all(response.status_code == 200 for response in results)
    report = results[0].json()
    assert results[1].json() == report
    assert report["title"] == "科学 Packet3"
    assert report["correct_count"] == 1 and report["accuracy"] == "33%"
    assert {item["question_id"] for item in report["question_results"] if item["is_correct"]} == {third}
    assert {item["user_answer"] for item in report["question_results"] if not item["is_correct"]} == {"misspelled"}
    assert {item["correct_answer"] for item in report["question_results"]} == set(PAIRS.values())

    history = client.get("/learningcenter/api/reports/history?module=word_matching").json()
    assert history["reports"] == [report]
    day, = history["daily"]
    assert day["sessions"] == 1 and day["total_questions"] == 3
    assert day["modules"][0]["module_label"] == "Word Matching"


def test_word_bank_visibility_is_saved_per_bank(client):
    login(client)
    payload = {
        "name": "Science", "pairs_text": "water,水\nice,冰",
        "show_word_bank": True,
    }
    created = client.post(ADMIN, json=payload)
    assert created.status_code == 201
    bank_id = created.json()["id"]
    editor_url = f"{ADMIN}/{bank_id}"
    assert client.get(editor_url).json()["show_word_bank"] is True
    assert client.put(editor_url, json={"name": "Science", "pairs_text": "water,水\nice,冰"}).status_code == 200
    other = client.post(ADMIN, json={"name": "Other", "pairs_text": "alpha,一\nbeta,二"}).json()

    start_url = f"{PUBLIC}/attempts"
    shown = client.post(start_url, json={"bank_id": bank_id}).json()
    assert shown["word_bank"] == ["ice", "water"]
    assert all(set(question) == {"id", "meaning"} for question in shown["questions"])
    assert "word_bank" not in client.post(start_url, json={"bank_id": other["id"]}).json()

    assert client.put(editor_url, json=payload | {"show_word_bank": False}).status_code == 200
    assert client.get(editor_url).json()["show_word_bank"] is False
    assert "word_bank" not in client.post(start_url, json={"bank_id": bank_id}).json()

    answers = {question["id"]: {"水": "water", "冰": "ice"}[question["meaning"]] for question in shown["questions"]}
    report = client.post(f"{start_url}/{shown['id']}/grade", json={"answers": answers})
    assert report.status_code == 200 and report.json()["correct_count"] == 2


def test_existing_word_bank_defaults_to_hidden(tmp_path):
    path = tmp_path / "schema-v9.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("""
            CREATE TABLE word_matching_banks (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                name_key TEXT NOT NULL UNIQUE,
                pairs_json TEXT NOT NULL
            )
        """)
        connection.execute(
            "INSERT INTO word_matching_banks VALUES (?, ?, ?, ?)",
            ("legacy", "Legacy", "legacy", json.dumps([["water", "水"], ["ice", "冰"]])),
        )
    service = WordMatchingService(SQLiteDatabase(path))
    bank = service.get_bank("legacy")
    assert bank["show_word_bank"] is False
    assert bank["pairs_text"] == "water,水\nice,冰"
    assert "word_bank" not in service.start_attempt("legacy")
    with SQLiteDatabase(path).read() as connection:
        assert connection.execute("SELECT count(*) FROM schema_migrations WHERE version=10").fetchone()[0] == 1


def test_matching_and_daily_word_banks_are_separate(client):
    login(client)
    old_url = "/api/admin/libraries"
    old_bank = {"subject": "english", "name": "Shared name", "items": ["legacy", "library"]}
    assert client.post(old_url, json=old_bank).status_code == 200
    assert client.get(f"{PUBLIC}/banks").json()["banks"] == []
    matching_bank = {"name": "Shared name", "pairs_text": "alpha,one\nbeta,two"}
    assert client.post(ADMIN, json=matching_bank).status_code == 201
    assert client.post(ADMIN, json=matching_bank | {"name": "Matching only"}).status_code == 201

    assert client.get("/api/english/libraries").json() == ["Shared name"]
    assert {bank["name"] for bank in client.get(f"{PUBLIC}/banks").json()["banks"]} == {"Shared name", "Matching only"}
    libraries = client.get(old_url).json()["libraries"]
    assert [library["name"] for library in libraries] == ["Shared name"]
    assert client.get(f"{old_url}/{libraries[0]['id']}").json()["items"] == old_bank["items"]


@pytest.mark.parametrize("text, error", [
    ("alpha,一\nbeta", "第 2 行"),
    ("alpha,一\n\nALPHA,二", "第 3 行"),
    ("alpha,one\nbeta,ＯＮＥ", "第 2 行"),
    ("alpha,一", "2 至 50"),
    ("\n".join(f"word{i},meaning{i}" for i in range(51)), "2 至 50"),
])
def test_invalid_bank_is_never_written(client, text, error):
    login(client)
    response = client.post(ADMIN, json={"name": "Test", "pairs_text": text})
    assert response.status_code == 400 and error in response.json()["detail"]
    assert client.get(f"{PUBLIC}/banks").json()["banks"] == []


def test_schema_upgrade_expiration_and_other_reports(tmp_path, monkeypatch):
    path = tmp_path / "existing.sqlite3"
    monkeypatch.setenv("SQLITE_DATABASE_PATH", str(path))
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    # Simulate an existing SQLite database whose v6 schema has no matching tables.
    reports = ReportHistoryService()
    legacy = reports.add_report({"module": "word_palace", "details": [{"word": "hello"}]})
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TABLE word_matching_attempts")
        connection.execute("DROP TABLE word_matching_banks")
        connection.execute("DELETE FROM schema_migrations WHERE version=7")

    service = WordMatchingService(SQLiteDatabase(path))
    assert service.list_banks() == []
    bank = service.save_bank("test", "\n".join(f"{word},{meaning}" for meaning, word in PAIRS.items()))
    old = service.start_attempt(bank["id"])
    with service.database.transaction() as connection:
        connection.execute("UPDATE word_matching_attempts SET expires_at=0 WHERE id=?", (old["id"],))
    with pytest.raises(LookupError, match="expired"):
        service.grade_attempt(old["id"], answers_for(old))
    attempt = service.start_attempt(bank["id"])
    with ThreadPoolExecutor(max_workers=2) as pool:
        grade = pool.submit(service.grade_attempt, attempt["id"], answers_for(attempt))
        other = pool.submit(reports.add_report, {"module": "map_language_arts"})
        assert grade.result()["correct_count"] == 3
        new = other.result()
    assert {item["id"] for item in reports.list_reports()} == {legacy["id"], attempt["id"], new["id"]}
    assert reports.list_reports(module="word_palace") == [legacy]
    with service.database.read() as connection:
        assert not connection.execute("SELECT 1 FROM word_matching_attempts").fetchone()
        assert connection.execute("SELECT count(*) FROM schema_migrations WHERE version=7").fetchone()[0] == 1


def test_open_multiple_choice_attempt_can_still_be_submitted(tmp_path):
    service = WordMatchingService(SQLiteDatabase(tmp_path / "legacy-attempt.sqlite3"))
    snapshot = {
        "bank_name": "Before update",
        "options": [{"id": "1", "word": "water"}, {"id": "2", "word": "ice"}],
        "questions": [
            {"id": "1", "meaning": "冰", "answer_id": "2"},
            {"id": "2", "meaning": "水", "answer_id": "1"},
        ],
    }
    with service.database.transaction() as connection:
        connection.execute(
            "INSERT INTO word_matching_attempts(id, snapshot_json, expires_at) VALUES (?, ?, ?)",
            ("legacy", json.dumps(snapshot), int(time.time()) + 60),
        )
    report = service.grade_attempt("legacy", {"1": "2", "2": "1"})
    assert report["correct_count"] == 2
    assert [item["user_answer"] for item in report["question_results"]] == ["ice", "water"]
