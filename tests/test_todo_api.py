from datetime import date

from fastapi.testclient import TestClient

import services.learning_todo_service as todo_service_module
from config import config
from main import app
from services.learning_todo_service import LearningTodoService


def test_admin_session_protects_todo_admin_api_and_public_child_api_stays_open(tmp_path, monkeypatch):
    service = LearningTodoService(
        data_dir=str(tmp_path / "data" / "learning-todo"),
        today_provider=lambda: date(2026, 7, 28),
    )
    monkeypatch.setattr(todo_service_module, "_learning_todo_service", service)
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "0418")
    monkeypatch.setattr(config, "ADMIN_SESSION_SECRET", "test-session-secret")

    with TestClient(app) as client:
        assert client.get("/api/admin/todo/overview").status_code == 401
        assert client.post("/api/admin/session", json={"password": "wrong"}).status_code == 401

        login = client.post("/api/admin/session", json={"password": "0418"})
        assert login.status_code == 200
        assert login.json()["authenticated"] is True

        created = client.post(
            "/api/admin/todo/tasks",
            json={
                "title": "API 测试任务",
                "subject_id": "sub_english",
                "planned_date": "2026-07-28",
                "reward_goal": "独立检查答案并订正",
                "reward_points": 5,
                "repeat": "once",
            },
        )
        assert created.status_code == 201
        task_id = created.json()["id"]

        public_today = client.get("/api/todo/today")
        assert public_today.status_code == 200
        assert [task["id"] for task in public_today.json()["today_pending_tasks"]] == [task_id]
        assert public_today.json()["reward"]["next_points"] == 1
        assert "parent_note" not in public_today.json()["today_pending_tasks"][0]
        assert "history" not in public_today.json()["today_pending_tasks"][0]
        assert public_today.json()["today_pending_tasks"][0]["reward_goal"] == "独立检查答案并订正"
        assert public_today.json()["today_pending_tasks"][0]["reward_points"] == 5

        completed = client.post(f"/api/todo/tasks/{task_id}/complete", json={})
        assert completed.status_code == 200
        assert completed.json()["completed_local_date"] == "2026-07-28"

        confirmed = client.post(f"/api/admin/todo/tasks/{task_id}/reward/confirm", json={})
        assert confirmed.status_code == 200
        assert confirmed.json()["reward_awarded_points"] == 5

        reward = client.get("/api/todo/reward")
        assert reward.status_code == 200
        assert reward.json()["total_points"] == 6
        assert reward.json()["completion_points"] == 1
        assert reward.json()["task_reward_points"] == 5
        assert reward.json()["today_points"] == 1
        assert reward.json()["current_streak"] == 1

        prefixed = client.get("/learningcenter/api/admin/todo/overview")
        assert prefixed.status_code == 200
        assert prefixed.json()["completed"] == 1

        assert client.delete("/api/admin/session").status_code == 200
        assert client.get("/api/admin/todo/overview").status_code == 401
