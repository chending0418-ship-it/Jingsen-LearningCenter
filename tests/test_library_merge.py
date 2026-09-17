import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from config import config
from database import ReportRepository
from services.library_admin_service import LibraryAdminService


@pytest.fixture
def service(tmp_path, monkeypatch):
    monkeypatch.delenv("SQLITE_DATABASE_PATH", raising=False)
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path / "data"))
    return LibraryAdminService()


def seed(service):
    return [
        service.create_library("english", "First", [" Apple ", "banana", "BANANA", "Ice cream"]),
        service.create_library("english", "Second", ["apple", "Cherry", "ice cream"], enabled=False),
        service.create_library("english", "Third", ["date", "cherry"]),
    ]


def snapshot(service):
    with service._database.read() as connection:
        return {
            table: [tuple(row) for row in connection.execute(f"SELECT * FROM {table} ORDER BY 1")]
            for table in ("libraries", "library_items", "practice_reports")
        }


def request_sources(libraries, actions=("keep", "disable", "archive")):
    return [{"library_id": lib["id"], "action": action} for lib, action in zip(libraries, actions)]


@pytest.mark.parametrize("action", ["keep", "disable", "archive"])
@pytest.mark.parametrize("enabled", [True, False])
def test_merge_deduplicates_in_order_and_preserves_sources(service, action, enabled):
    libraries = seed(service)
    sources = request_sources(libraries, [action] * 3)
    before = snapshot(service)
    preview = service.preview_library_merge(sources, "  Combined  ", enabled)
    assert preview["items"] == ["Apple", "banana", "Ice cream", "Cherry", "date"]
    assert preview["total_source_items"] == 9
    assert preview["total_items"] == 5 and preview["duplicate_count"] == 4
    assert snapshot(service) == before  # Preview has no persistence side effects.
    created = service.merge_libraries(sources, "Combined", preview["preview_token"], enabled)
    assert created["id"] not in {lib["id"] for lib in libraries}
    assert created["subject"] == "english" and created["library_type"] is None
    assert created["enabled"] is enabled and created["archived"] is False
    assert created["items"] == preview["items"]
    for original in libraries:
        current = service.get_library(original["id"])
        assert current["items"] == original["items"]
        assert current["archived"] == (action == "archive")
        assert current["enabled"] == (original["enabled"] if action == "keep" else False)
        if action == "keep":
            assert current == original
        if action == "archive":
            assert current["archived_at"]
            restored = service.set_library_archived(original["id"], False)
            assert restored["enabled"] is False
            assert service.get_library(original["id"])["items"] == original["items"]
    restarted = LibraryAdminService()
    assert restarted.get_library(created["id"])["items"] == preview["items"]
    if enabled:
        resolved = restarted.resolve_enabled_library("english", "Combined")
        assert restarted.get_library_items(resolved["file_name"]) == preview["items"]
    else:
        assert "Combined" not in restarted.get_enabled_library_names("english")


def test_mixed_actions_do_not_change_unselected_libraries_or_source_items(service):
    libraries = seed(service)
    ReportRepository(service._database).replace_all({"reports": [
        {"id": "existing-english-report", "module": "word_palace", "correct_count": 2, "total_count": 3}
    ]})
    unrelated = service.create_library("chinese", "chinese_other", ["保留"])
    sources = request_sources(libraries)
    before = snapshot(service)
    preview = service.preview_library_merge(sources, "Mixed")
    created = service.merge_libraries(sources, "Mixed", preview["preview_token"])
    assert service.get_library(libraries[0]["id"])["enabled"] is True
    assert service.get_library(libraries[1]["id"])["enabled"] is False
    assert service.get_library(libraries[2]["id"])["archived"] is True
    assert service.get_library(unrelated["id"]) == unrelated
    after = snapshot(service)
    assert [row for row in after["library_items"] if row[1] != created["id"]] == before["library_items"]
    assert after["practice_reports"] == before["practice_reports"]
    assert service.get_enabled_library_names("english") == ["First", "Mixed"]


@pytest.mark.parametrize("invalid", ["one", "duplicate", "missing", "chinese", "archived", "name", "archived_name", "blank", "path", "action", "empty"])
def test_invalid_merge_never_writes(service, invalid):
    libraries = seed(service)
    sources = request_sources(libraries)
    name = "Combined"
    if invalid == "one":
        sources = sources[:1]
    elif invalid == "duplicate":
        sources[1]["library_id"] = sources[0]["library_id"]
    elif invalid == "missing":
        sources[1]["library_id"] = "missing"
    elif invalid == "chinese":
        sources[1]["library_id"] = service.create_library("chinese", "chinese_words", ["例子"])["id"]
    elif invalid == "archived":
        service.set_library_archived(libraries[1]["id"], True)
    elif invalid == "name":
        name = libraries[0]["name"]
    elif invalid == "archived_name":
        extra = service.create_library("english", "Combined", ["old"])
        service.set_library_archived(extra["id"], True)
    elif invalid == "blank":
        name = "   "
    elif invalid == "path":
        name = "../combined"
    elif invalid == "action":
        sources[0]["action"] = "delete"
    elif invalid == "empty":
        with service._database.transaction() as connection:
            connection.execute("DELETE FROM library_items")
    before = snapshot(service)
    with pytest.raises(ValueError):
        service.preview_library_merge(sources, name)
    with pytest.raises(ValueError):
        service.merge_libraries(sources, name, "x" * 64)
    assert snapshot(service) == before


@pytest.mark.parametrize("change", ["items", "status", "rename", "selection", "action", "new_name", "enabled"])
def test_changed_source_or_settings_requires_new_preview(service, change):
    libraries = seed(service)
    sources = request_sources(libraries)
    preview = service.preview_library_merge(sources, "Combined")
    name, enabled = "Combined", True
    if change == "items":
        service.replace_library_items(libraries[0]["id"], ["changed"])
    elif change == "status":
        service.set_library_enabled(libraries[0]["id"], False)
    elif change == "rename":
        service.update_library(libraries[0]["id"], name="Renamed")
    elif change == "selection":
        sources = sources[:2]
    elif change == "action":
        sources[0]["action"] = "archive"
    elif change == "new_name":
        name = "Another"
    elif change == "enabled":
        enabled = False
    before = snapshot(service)
    with pytest.raises(ValueError, match="重新预览"):
        service.merge_libraries(sources, name, preview["preview_token"], enabled)
    assert snapshot(service) == before


def test_database_failure_rolls_back_new_library_items_and_source_statuses(service):
    libraries = seed(service)
    sources = request_sources(libraries, ["disable", "archive", "keep"])
    preview = service.preview_library_merge(sources, "Combined")
    with service._database.transaction() as connection:
        connection.execute("""CREATE TRIGGER reject_archive BEFORE UPDATE OF archived ON libraries
            WHEN NEW.archived = 1 BEGIN SELECT RAISE(ABORT, 'simulated disk failure'); END""")
    before = snapshot(service)
    with pytest.raises(sqlite3.IntegrityError, match="simulated disk failure"):
        service.merge_libraries(sources, "Combined", preview["preview_token"])
    assert snapshot(service) == before


def test_concurrent_duplicate_submissions_create_only_one_library(service):
    libraries = seed(service)
    other_worker = LibraryAdminService()
    sources = request_sources(libraries)
    preview = service.preview_library_merge(sources, "Combined")

    def merge(worker):
        try:
            return worker.merge_libraries(sources, "Combined", preview["preview_token"])
        except ValueError as error:
            return str(error)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(merge, [service, other_worker]))
    assert sum(isinstance(result, dict) for result in results) == 1
    assert len([lib for lib in service.list_libraries() if lib["name"] == "Combined"]) == 1
    assert service.get_library(libraries[2]["id"])["items"] == libraries[2]["items"]


def test_merge_api_auth_validation_prefix_and_page(service, monkeypatch):
    import api.admin as admin_api
    from main import app

    monkeypatch.setattr(admin_api, "library_admin_service", service)
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "merge-test-password")
    monkeypatch.setattr(config, "ADMIN_SESSION_SECRET", "merge-test-session-secret")
    monkeypatch.setattr(config, "ADMIN_COOKIE_SECURE", False)
    sources = request_sources(seed(service))
    body = {"name": "API combined", "sources": sources, "enabled": True}
    with TestClient(app) as client:
        for prefix in ("", "/learningcenter"):
            for suffix in ("merge-preview", "merge"):
                assert client.post(f"{prefix}/api/admin/libraries/{suffix}", json=body).status_code == 401
        assert client.get("/admin/learningcenter/merge", follow_redirects=False).status_code == 303
        assert client.post("/api/admin/session", json={"password": "merge-test-password"}).status_code == 200
        page = client.get("/admin/learningcenter/merge")
        assert page.status_code == 200 and "合并英语词库" in page.text
        assert client.post("/api/admin/libraries/merge", json=body).status_code == 422
        assert client.post("/api/admin/libraries/merge-preview", json={**body, "sources": sources[:1]}).status_code == 422
        assert client.post("/api/admin/libraries/merge-preview", json={**body, "sources": [{"library_id": "x", "action": "delete"}] * 2}).status_code == 422
        assert client.post("/api/admin/libraries/merge-preview", json={**body, "sources": sources[:1] + [{"library_id": "missing"}]}).status_code == 404
        preview = client.post("/learningcenter/api/admin/libraries/merge-preview", json=body)
        assert preview.status_code == 200
        request = {**body, "preview_token": preview.json()["preview_token"]}
        created = client.post("/learningcenter/api/admin/libraries/merge", json=request)
        assert created.status_code == 200
        assert created.json()["total_items"] == 5
        assert client.get(f"/api/admin/libraries/{created.json()['id']}").json()["items"] == preview.json()["items"]
        assert client.post("/api/admin/libraries/merge", json=request).status_code == 400
