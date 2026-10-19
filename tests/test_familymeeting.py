import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.familymeeting as api
from services.familymeeting_service import FamilyMeetingService, MeetingError, make_password_hash


@pytest.fixture
def meeting(tmp_path):
    service = FamilyMeetingService(tmp_path / "meetings.sqlite3", make_password_hash("test-only-pass"))
    access = service.create("测试家庭会议", "2026-10-19")
    return service, access["id"], access["tokens"]


def publish(service, room, token, text, revision=0):
    return service.save_answers(room, token, {"worries": text}, revision, True)


def test_drafts_are_private_and_cannot_be_read_from_owner_or_other_parent(meeting):
    service, room, tokens = meeting
    service.save_answers(room, tokens["dad"], {"worries": "爸爸未提交的私密草稿"}, 0)
    for role in ("mom", "owner"):
        state = service.state(room, tokens[role])
        assert "私密草稿" not in json.dumps(state, ensure_ascii=False)
        assert "answers" not in state["participants"]["dad"]
    assert service.state(room, tokens["dad"])["own"]["answers"]["worries"] == "爸爸未提交的私密草稿"


def test_both_submissions_and_password_button_are_required(meeting):
    service, room, tokens = meeting
    publish(service, room, tokens["dad"], "爸爸已提交的想法")
    with pytest.raises(MeetingError) as error:
        service.unlock(room, tokens["dad"], "test-only-pass")
    assert error.value.status == 409
    publish(service, room, tokens["mom"], "妈妈已提交的想法")
    for role in tokens:
        state = service.state(room, tokens[role])
        assert state["can_open"] is True
        assert state["unlocked"] is False
        assert "answers" not in state["participants"]["dad"]
    with pytest.raises(MeetingError) as error:
        service.unlock(room, tokens["dad"], "wrong")
    assert error.value.status == 403
    grant = service.unlock(room, tokens["dad"], "test-only-pass")["view_grant"]
    state = service.state(room, tokens["dad"], grant)
    assert state["unlocked"] is True
    assert state["participants"]["mom"]["answers"]["worries"] == "妈妈已提交的想法"
    # Another device/person cannot reuse a different role's view grant.
    assert service.state(room, tokens["mom"], grant)["unlocked"] is False
    assert service.state(room, tokens["owner"])["unlocked"] is False


def test_changing_a_submission_requires_resubmission_before_first_open(meeting):
    service, room, tokens = meeting
    publish(service, room, tokens["dad"], "原提交")
    publish(service, room, tokens["mom"], "另一方提交")
    service.save_answers(room, tokens["dad"], {"worries": "修改中"}, 1)
    assert service.state(room, tokens["mom"])["can_open"] is False
    with pytest.raises(MeetingError):
        service.unlock(room, tokens["mom"], "test-only-pass")
    publish(service, room, tokens["dad"], "修改后的提交", 2)
    assert service.state(room, tokens["mom"])["can_open"] is True


def test_after_open_only_published_updates_are_shared(meeting):
    service, room, tokens = meeting
    publish(service, room, tokens["dad"], "已发布")
    publish(service, room, tokens["mom"], "另一方")
    grant = service.unlock(room, tokens["mom"], "test-only-pass")["view_grant"]
    service.save_answers(room, tokens["dad"], {"worries": "尚未提交的新想法"}, 1)
    assert service.state(room, tokens["mom"], grant)["participants"]["dad"]["answers"]["worries"] == "已发布"
    publish(service, room, tokens["dad"], "更新后发布", 2)
    assert service.state(room, tokens["mom"], grant)["participants"]["dad"]["answers"]["worries"] == "更新后发布"


def test_wrong_password_attempts_are_rate_limited_and_persist(meeting):
    service, room, tokens = meeting
    for role in ("dad", "mom"):
        publish(service, room, tokens[role], role)
    for _ in range(5):
        with pytest.raises(MeetingError) as error:
            service.unlock(room, tokens["owner"], "wrong")
        assert error.value.status == 403
    with pytest.raises(MeetingError) as error:
        service.unlock(room, tokens["owner"], "test-only-pass")
    assert error.value.status == 429


def test_optimistic_versions_prevent_lost_answers_and_notes(meeting):
    service, room, tokens = meeting
    publish(service, room, tokens["dad"], "最新答案")
    with pytest.raises(MeetingError) as error:
        service.save_answers(room, tokens["dad"], {"worries": "旧设备答案"}, 0)
    assert error.value.status == 409
    publish(service, room, tokens["mom"], "妈妈")
    grant = service.unlock(room, tokens["dad"], "test-only-pass")["view_grant"]
    service.save_notes(room, tokens["dad"], grant, {"common": "共同尊重孩子", "direction": "finish", "child_state": "pending"}, 0)
    with pytest.raises(MeetingError) as error:
        service.save_notes(room, tokens["dad"], grant, {"common": "旧版本"}, 0)
    assert error.value.status == 409
    assert service.state(room, tokens["dad"], grant)["notes"]["direction"] == "finish"


def test_private_notes_require_password_grant(meeting):
    service, room, tokens = meeting
    with pytest.raises(MeetingError) as error:
        service.save_notes(room, tokens["owner"], "", {"common": "不应写入"}, 0)
    assert error.value.status == 403


@pytest.mark.parametrize("bad_answers", [
    {"goals": ["孩子的兴趣与快乐"] * 2},
    {"annual_budget": -1},
    {"annual_budget": True},
    {"weekly_hours": float("inf")},
    {"unknown_field": "hidden"},
    {"review_date": "2026-99-99"},
    {"preferred_path": "invented"},
    {"path_views": {"outside": {"stance": "invented"}}},
    {"worries": "长" * 6001},
])
def test_invalid_answers_rejected_without_overwriting(meeting, bad_answers):
    service, room, tokens = meeting
    with pytest.raises(MeetingError):
        service.save_answers(room, tokens["dad"], bad_answers, 0)
    assert service.state(room, tokens["dad"])["own"]["revision"] == 0


def test_tokens_are_scoped_to_meeting_and_owner_cannot_impersonate(meeting):
    service, room, tokens = meeting
    other = service.create("另一个家庭会议", "2026-10-19")
    for token in ("", "a" * 64, "中" * 64, other["tokens"]["dad"]):
        with pytest.raises(MeetingError) as error:
            service.state(room, token)
        assert error.value.status == 403
    with pytest.raises(MeetingError):
        publish(service, room, tokens["owner"], "替别人写")


def test_routes_require_admin_for_creation_and_never_expose_unlock_hash(meeting, monkeypatch):
    service, room, tokens = meeting
    monkeypatch.setattr(api, "get_familymeeting_service", lambda: service)
    app = FastAPI()
    app.include_router(api.router)
    with TestClient(app) as client:
        page = client.get("/baseball/familymeeting/query")
        assert page.status_code == 200
        assert page.headers["cache-control"] == "no-store"
        assert "noindex" in page.headers["x-robots-tag"]
        assert service.unlock_hash not in page.text
        assert client.post("/api/baseball/familymeeting/meetings", json={"meeting_date": "2026-10-19"}).status_code == 401
        assert client.get(f"/api/baseball/familymeeting/meetings/{room}").status_code == 403
        response = client.get(f"/api/baseball/familymeeting/meetings/{room}", headers={"Authorization": f"Bearer {tokens['dad']}"})
        assert response.status_code == 200
        assert response.json()["role"] == "dad"
        assert "secret" not in response.json()
        assert client.get("/baseball/familymeeting/assets/other.txt").status_code == 404
        assert client.get("/baseball/familymeeting/assets/questions.json").json()["paths"][-1]["id"] == "finish"


def test_nonempty_submission_and_reopening_persist_on_disk(meeting):
    service, room, tokens = meeting
    with pytest.raises(MeetingError):
        service.save_answers(room, tokens["dad"], {}, 0, True)
    publish(service, room, tokens["dad"], "重启后保留")
    reopened = FamilyMeetingService(service.path, service.unlock_hash)
    assert reopened.state(room, tokens["dad"])["own"]["answers"]["worries"] == "重启后保留"
