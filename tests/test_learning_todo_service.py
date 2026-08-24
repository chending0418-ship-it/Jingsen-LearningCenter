from datetime import date
from pathlib import Path

import pytest

from services.learning_todo_service import LearningTodoService, TodoDataError


@pytest.fixture
def fixed_today():
    return lambda: date(2026, 7, 28)


@pytest.fixture
def service(tmp_path, fixed_today):
    return LearningTodoService(
        data_dir=str(tmp_path / "data" / "learning-todo"),
        today_provider=fixed_today,
    )


def test_storage_is_isolated_from_existing_learning_data(tmp_path, fixed_today):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    library = data_dir / "library_registry.json"
    reports = data_dir / "report_history.json"
    skill = data_dir / "skills" / "index.json"
    skill.parent.mkdir()
    library.write_text('{"libraries":["keep"]}', encoding="utf-8")
    reports.write_text('{"reports":["keep"]}', encoding="utf-8")
    skill.write_text('{"skills":["keep"]}', encoding="utf-8")
    before = {path: path.read_bytes() for path in (library, reports, skill)}

    todo = LearningTodoService(
        data_dir=str(data_dir / "learning-todo"),
        today_provider=fixed_today,
    )
    todo.create_task(
        {
            "title": "隔离测试",
            "subject_id": "sub_english",
            "planned_date": "2026-07-28",
            "repeat": "once",
        }
    )

    assert todo.data_dir == (data_dir / "learning-todo").resolve()
    assert all(path.read_bytes() == content for path, content in before.items())
    assert todo._database.path.is_file()
    assert not (data_dir / "learning-todo" / "tasks" / "2026-07.json").exists()


def test_weekly_recurrence_generates_independent_instances_across_month(service):
    service.create_task(
        {
            "title": "每周学习",
            "subject_id": "sub_reading",
            "planned_date": "2026-07-26",
            "description": "每天一项",
            "repeat": "weekly",
            "repeat_weekdays": [0, 1, 2, 3, 4, 5, 6],
            "end_date": "2026-08-02",
        }
    )

    tasks = service.list_tasks(from_date="2026-07-26", to_date="2026-08-02")
    assert len(tasks) == 8
    assert len({task["id"] for task in tasks}) == 8
    assert {task["planned_date"] for task in tasks} == {
        "2026-07-26",
        "2026-07-27",
        "2026-07-28",
        "2026-07-29",
        "2026-07-30",
        "2026-07-31",
        "2026-08-01",
        "2026-08-02",
    }
    assert service._repository.list_months() == ["2026-07", "2026-08"]


def test_overdue_complete_and_manual_uncomplete(service):
    task = service.create_task(
        {
            "title": "昨天的英语作业",
            "subject_id": "sub_english",
            "planned_date": "2026-07-27",
            "repeat": "once",
        }
    )
    payload = service.today_payload()
    assert [item["id"] for item in payload["overdue_tasks"]] == [task["id"]]
    assert payload["overdue_tasks"][0]["overdue_days"] == 1

    completed = service.complete_task(task["id"])
    assert completed["completed_local_date"] == "2026-07-28"
    payload = service.today_payload()
    assert not payload["overdue_tasks"]
    assert [item["id"] for item in payload["today_completed_tasks"]] == [task["id"]]

    undone = service.undo_completion(task["id"])
    assert undone["completed_at"] is None
    assert [item["id"] for item in service.today_payload()["overdue_tasks"]] == [task["id"]]


def test_historical_day_stays_yellow_after_late_completion(service):
    task = service.create_task(
        {
            "title": "补做任务",
            "subject_id": "sub_math",
            "planned_date": "2026-07-27",
            "repeat": "once",
        }
    )
    service.complete_task(task["id"])

    historical = service.day_view("2026-07-27")
    assert historical["completed"] == 1
    assert historical["on_time"] == 0
    assert historical["color"] == "yellow"


def test_today_pending_is_yellow_but_not_marked_as_overdue(service):
    service.create_task(
        {
            "title": "今天待完成",
            "subject_id": "sub_math",
            "planned_date": "2026-07-28",
            "repeat": "once",
        }
    )
    today = service.day_view("2026-07-28")
    assert today["color"] == "yellow"
    assert today["carryover"] == 0
    assert today["has_overdue"] is False


def test_void_future_scope_persists_for_single_recurring_instance(service):
    task = service.create_task(
        {
            "title": "单实例重复任务",
            "subject_id": "sub_english",
            "planned_date": "2026-07-28",
            "repeat": "weekly",
            "repeat_weekdays": [2],
            "end_date": "2026-07-28",
        }
    )
    service.void_task(task["id"], scope="future")
    assert service.list_tasks(from_date="2026-07-28", to_date="2026-07-28") == []
    stored = service.get_task(task["id"])
    assert stored["lifecycle_status"] == "voided"


def test_series_edit_does_not_collapse_all_instances_to_one_date(service):
    first = service.create_task(
        {
            "title": "原计划",
            "subject_id": "sub_reading",
            "planned_date": "2026-07-28",
            "repeat": "weekly",
            "repeat_weekdays": [0, 1, 2, 3, 4, 5, 6],
            "end_date": "2026-08-02",
        }
    )
    service.update_task(
        first["id"],
        {
            "title": "仅周二",
            "planned_date": "2026-07-28",
            "repeat": "weekly",
            "repeat_weekdays": [2],
            "end_date": "2026-08-02",
        },
        scope="series",
    )

    active = service.list_tasks(from_date="2026-07-28", to_date="2026-08-02")
    assert [(task["planned_date"], task["title"]) for task in active] == [("2026-07-28", "仅周二")]


def test_monthly_last_day_handles_short_months_and_leap_year(tmp_path):
    service = LearningTodoService(
        data_dir=str(tmp_path / "data" / "learning-todo"),
        today_provider=lambda: date(2028, 1, 31),
    )
    service.create_task(
        {
            "title": "月末总结",
            "subject_id": "sub_other",
            "planned_date": "2028-01-31",
            "repeat": "monthly",
            "repeat_month_day": "last",
            "end_date": "2028-03-31",
        }
    )
    tasks = service.list_tasks(from_date="2028-01-01", to_date="2028-03-31")
    assert [task["planned_date"] for task in tasks] == ["2028-01-31", "2028-02-29", "2028-03-31"]


def test_copy_day_creates_fresh_uncompleted_instances(service):
    original = service.create_task(
        {
            "title": "复制来源",
            "subject_id": "sub_chinese",
            "planned_date": "2026-07-28",
            "repeat": "once",
        }
    )
    service.complete_task(original["id"])
    copies = service.copy_day("2026-07-28", "2026-07-29")

    assert len(copies) == 1
    assert copies[0]["id"] != original["id"]
    assert copies[0]["planned_date"] == "2026-07-29"
    assert copies[0]["completed_at"] is None
    assert copies[0]["repeat"] == "once"


def test_backup_restore_recovers_previous_task_state(service):
    first = service.create_task(
        {
            "title": "保留任务",
            "subject_id": "sub_chinese",
            "planned_date": "2026-07-28",
            "repeat": "once",
        }
    )
    backup = service.create_backup("test-restore")
    service.create_task(
        {
            "title": "恢复后消失",
            "subject_id": "sub_science",
            "planned_date": "2026-07-28",
            "repeat": "once",
        }
    )

    service.restore_backup(backup["name"])
    tasks = service.list_tasks(from_date="2026-07-28", to_date="2026-07-28")
    assert [task["id"] for task in tasks] == [first["id"]]
    assert service.validate_storage()["ok"] is True


def test_reward_points_grow_with_streak_and_restart_after_missed_task_day(tmp_path):
    current_day = [date(2026, 7, 25)]
    todo = LearningTodoService(
        data_dir=str(tmp_path / "data" / "learning-todo"),
        today_provider=lambda: current_day[0],
    )

    def create_today(title):
        return todo.create_task(
            {
                "title": title,
                "subject_id": "sub_english",
                "planned_date": current_day[0].isoformat(),
                "repeat": "once",
            }
        )

    first = create_today("第一天")
    todo.complete_task(first["id"])
    reward = todo.reward_summary()
    assert (reward["total_points"], reward["today_points"], reward["current_streak"], reward["next_points"]) == (
        1,
        1,
        1,
        2,
    )

    current_day[0] = date(2026, 7, 26)
    second = create_today("第二天")
    todo.complete_task(second["id"])
    reward = todo.reward_summary()
    assert (reward["total_points"], reward["today_points"], reward["current_streak"], reward["next_points"]) == (
        3,
        2,
        2,
        3,
    )

    current_day[0] = date(2026, 7, 27)
    create_today("中断日")
    reward = todo.reward_summary()
    assert reward["today_points"] == 0
    assert reward["current_streak"] == 2
    assert reward["next_points"] == 3

    current_day[0] = date(2026, 7, 28)
    restarted = create_today("重新开始")
    todo.complete_task(restarted["id"])
    reward = todo.reward_summary()
    assert (reward["total_points"], reward["today_points"], reward["current_streak"], reward["next_points"]) == (
        4,
        1,
        1,
        2,
    )

    # 7 月 29 日没有安排任务：不加分，也不打断连续记录。
    current_day[0] = date(2026, 7, 30)
    after_rest = create_today("无任务日之后")
    todo.complete_task(after_rest["id"])
    reward = todo.reward_summary()
    assert (reward["total_points"], reward["today_points"], reward["current_streak"]) == (6, 2, 2)

    # 当天尚未结束时先展示可争取的分数；完成后再正式计分。
    current_day[0] = date(2026, 7, 31)
    pending = create_today("今天尚未完成")
    reward = todo.reward_summary()
    assert (reward["today_points"], reward["current_streak"], reward["next_points"]) == (0, 2, 3)

    todo.complete_task(pending["id"])
    reward = todo.reward_summary()
    assert (reward["total_points"], reward["today_points"], reward["current_streak"], reward["next_points"]) == (
        9,
        3,
        3,
        4,
    )

    todo.undo_completion(pending["id"])
    reward = todo.reward_summary()
    assert (reward["total_points"], reward["today_points"], reward["current_streak"], reward["next_points"]) == (
        6,
        0,
        2,
        3,
    )


def test_points_correction_restores_yesterday_points_and_continuous_streak(tmp_path):
    current_day = [date(2026, 7, 25)]
    todo = LearningTodoService(
        data_dir=str(tmp_path / "data" / "learning-todo"),
        today_provider=lambda: current_day[0],
    )

    for day in (25, 26):
        current_day[0] = date(2026, 7, day)
        task = todo.create_task(
            {
                "title": f"第 {day} 日任务",
                "subject_id": "sub_english",
                "planned_date": current_day[0].isoformat(),
                "repeat": "once",
            }
        )
        todo.complete_task(task["id"])

    current_day[0] = date(2026, 7, 27)
    todo.create_task(
        {
            "title": "被误操作中断的任务日",
            "subject_id": "sub_math",
            "planned_date": "2026-07-27",
            "repeat": "once",
        }
    )
    current_day[0] = date(2026, 7, 28)
    todo.create_task(
        {
            "title": "今天待完成",
            "subject_id": "sub_reading",
            "planned_date": "2026-07-28",
            "repeat": "once",
        }
    )

    before = todo.reward_summary()
    assert (before["completion_points"], before["current_streak"], before["next_points"]) == (3, 0, 1)

    corrected = todo.correct_points(
        effective_date="2026-07-27",
        points=0,
        purpose="修正误操作",
        streak_action="preserve",
    )
    assert corrected["transaction"]["effective_date"] == "2026-07-27"
    assert corrected["impact"] == {
        "available_points": 3,
        "completion_points": 3,
        "correction_points": 0,
        "current_streak": 3,
    }
    account = corrected["account"]
    assert (account["completion_points"], account["current_streak"], account["next_points"]) == (6, 3, 4)
    assert account["recent_scores"][-2] == {
        "date": "2026-07-27",
        "points": 3,
        "completed": True,
        "corrected": True,
    }

    reloaded = LearningTodoService(
        data_dir=str(todo.data_dir),
        today_provider=lambda: current_day[0],
    )
    assert reloaded.reward_summary()["current_streak"] == 3

    reloaded.correct_points("2026-07-27", 2, "补发额外偏差", "none")
    assert reloaded.reward_summary()["correction_points"] == 2
    assert reloaded.reward_summary()["available_points"] == 8

    reloaded.correct_points("2026-07-27", -1, "扣回多发的一分", "none")
    assert reloaded.reward_summary()["correction_points"] == 1
    assert reloaded.reward_summary()["available_points"] == 7

    cleared = reloaded.correct_points("2026-07-27", 0, "取消连续修正", "clear")
    assert cleared["account"]["completion_points"] == 3
    assert cleared["account"]["current_streak"] == 0
    assert cleared["account"]["available_points"] == 4

    with pytest.raises(TodoDataError, match="未来日期"):
        reloaded.correct_points("2026-07-29", 1, "未来修正", "none")

    with pytest.raises(TodoDataError, match="积分调整"):
        reloaded.correct_points("2026-07-27", 0, "空修正", "none")


def test_parent_confirmed_task_reward_is_added_once_and_saved_as_snapshot(service):
    task = service.create_task(
        {
            "title": "高质量完成阅读摘记",
            "subject_id": "sub_reading",
            "planned_date": "2026-07-28",
            "reward_goal": "字迹整洁，并写出自己的理解",
            "reward_points": 8,
            "repeat": "once",
        }
    )
    assert task["reward_status"] == "pending"

    with pytest.raises(ValueError, match="完成后才能确认奖励"):
        service.grant_task_reward(task["id"])

    service.complete_task(task["id"])
    granted = service.grant_task_reward(task["id"])
    assert granted["reward_status"] == "granted"
    assert granted["reward_awarded_points"] == 8

    reward = service.reward_summary()
    assert reward["completion_points"] == 1
    assert reward["task_reward_points"] == 8
    assert reward["today_task_reward_points"] == 8
    assert reward["total_points"] == 9

    # 重复确认是幂等操作，不会重复加分。
    service.grant_task_reward(task["id"])
    assert service.reward_summary()["total_points"] == 9

    with pytest.raises(ValueError, match="已发放的任务奖励不能修改"):
        service.update_task(task["id"], {"reward_goal": "改成另一个目标", "reward_points": 20})

    history = service.task_history(task["id"])["history"]
    assert [event["type"] for event in history].count("reward-granted") == 1


def test_points_spending_is_persisted_bounded_and_restored(service):
    task = service.create_task(
        {
            "title": "获得可兑换积分",
            "subject_id": "sub_reading",
            "planned_date": "2026-07-28",
            "reward_goal": "完整复述故事",
            "reward_points": 8,
            "repeat": "once",
        }
    )
    service.complete_task(task["id"])
    service.grant_task_reward(task["id"])

    spent = service.spend_points(4, "兑换周末电影")
    assert spent["transaction"]["points"] == 4
    assert spent["transaction"]["purpose"] == "兑换周末电影"
    assert spent["account"]["earned_points"] == 9
    assert spent["account"]["spent_points"] == 4
    assert spent["account"]["available_points"] == 5
    assert spent["account"]["total_points"] == 5
    assert service._database.path.is_file()
    assert not service.points_ledger_path.exists()

    reloaded = LearningTodoService(
        data_dir=str(service.data_dir),
        today_provider=lambda: date(2026, 7, 28),
    )
    assert reloaded.points_account()["transactions"][0]["purpose"] == "兑换周末电影"

    with pytest.raises(TodoDataError, match="可用积分不足"):
        service.spend_points(6, "超额兑换")
    assert service.points_account()["spent_points"] == 4

    backup = service.create_backup("points-restore")
    service.spend_points(1, "临时兑换")
    assert service.reward_summary()["available_points"] == 4
    service.restore_backup(backup["name"])
    restored = service.points_account()
    assert restored["available_points"] == 5
    assert [row["purpose"] for row in restored["transactions"]] == ["兑换周末电影"]


def test_recurring_task_rewards_are_confirmed_per_instance(service):
    first = service.create_task(
        {
            "title": "每日阅读",
            "subject_id": "sub_reading",
            "planned_date": "2026-07-28",
            "reward_goal": "阅读后讲出一个新发现",
            "reward_points": 4,
            "repeat": "daily",
            "end_date": "2026-07-29",
        }
    )
    tasks = service.list_tasks(from_date="2026-07-28", to_date="2026-07-29")
    assert [task["reward_points"] for task in tasks] == [4, 4]

    service.complete_task(first["id"])
    service.grant_task_reward(first["id"])
    service.update_task(
        tasks[1]["id"],
        {"reward_goal": "阅读后写出两点收获", "reward_points": 6},
        scope="series",
    )

    updated = service.list_tasks(from_date="2026-07-28", to_date="2026-07-29")
    assert updated[0]["reward_awarded_points"] == 4
    assert updated[0]["reward_points"] == 4
    assert updated[1]["reward_points"] == 6
    assert updated[1]["reward_granted_at"] is None


def test_subject_and_template_upserts_preserve_existing_task_foreign_keys(service):
    service.create_task(
        {
            "title": "外键保留测试",
            "subject_id": "sub_reading",
            "planned_date": "2026-07-28",
            "repeat": "daily",
            "end_date": "2026-07-29",
        }
    )
    subjects = service._repository.read_subjects()
    reading = next(row for row in subjects["subjects"] if row["id"] == "sub_reading")
    reading["name"] = "阅读与表达"
    service._repository.replace_subjects(subjects)

    templates = service._repository.read_templates()
    templates["templates"][0]["title"] = "更新后的重复模板"
    service._repository.replace_templates(templates)

    tasks = service.list_tasks(from_date="2026-07-28", to_date="2026-07-29")
    assert len(tasks) == 2
    assert next(row for row in service._repository.read_subjects()["subjects"] if row["id"] == "sub_reading")["name"] == "阅读与表达"
    assert service._repository.read_templates()["templates"][0]["title"] == "更新后的重复模板"
