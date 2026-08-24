"""Learning Todo 的 SQLite 持久化服务。

旧 JSON 只作为首次迁移源；内部 ZIP 备份继续使用 JSON 作为可移植导出格式。
"""

from __future__ import annotations

import calendar
import hashlib
import json
import os
import re
import shutil
import tempfile
import threading
import uuid
import zipfile
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional
from zoneinfo import ZoneInfo

import fcntl

from config import config
from database import TodoRepository, database_for_todo_root, migrate_todo_legacy_data


DEFAULT_SUBJECTS = [
    {"id": "sub_english", "name": "英语", "color": "#3B82F6", "sort_order": 10, "enabled": True},
    {"id": "sub_math", "name": "数学", "color": "#E07A1F", "sort_order": 20, "enabled": True},
    {"id": "sub_chinese", "name": "中文", "color": "#D84A45", "sort_order": 30, "enabled": True},
    {"id": "sub_reading", "name": "阅读", "color": "#2D8A62", "sort_order": 40, "enabled": True},
    {"id": "sub_science", "name": "科学", "color": "#7656B5", "sort_order": 50, "enabled": True},
    {"id": "sub_other", "name": "其他", "color": "#6B7280", "sort_order": 60, "enabled": True},
]

ACTIVE_LIFECYCLE = "active"
INACTIVE_LIFECYCLES = {"cancelled", "voided"}
REPEAT_KINDS = {"once", "daily", "weekly", "monthly"}
POINT_TRANSACTION_TYPES = {"spend", "correction"}
STREAK_CORRECTION_ACTIONS = {"none", "preserve", "clear"}


class TodoDataError(ValueError):
    """Todo 数据文件不合法或操作无法完成。"""


class LearningTodoService:
    def __init__(
        self,
        data_dir: Optional[str] = None,
        timezone_name: Optional[str] = None,
        today_provider: Optional[Callable[[], date | str]] = None,
    ):
        self.data_dir = Path(data_dir or config.TODO_DATA_DIR).resolve()
        self.tasks_dir = self.data_dir / "tasks"
        self.backups_dir = self.data_dir / "backups"
        self.settings_path = self.data_dir / "settings.json"
        self.subjects_path = self.data_dir / "subjects.json"
        self.templates_path = self.data_dir / "templates.json"
        self.reports_path = self.data_dir / "reports.json"
        self.points_ledger_path = self.data_dir / "points-ledger.json"
        self.lock_path = self.data_dir / ".storage.lock"
        self._database = database_for_todo_root(self.data_dir)
        migrate_todo_legacy_data(self.data_dir, self._database)
        self._repository = TodoRepository(self._database)
        self.timezone_name = timezone_name or config.TODO_TIMEZONE
        self.timezone = ZoneInfo(self.timezone_name)
        self.today_provider = today_provider
        self._thread_lock = threading.RLock()
        self._bootstrap()

    @contextmanager
    def _guard(self) -> Iterator[None]:
        """线程锁 + 文件锁，兼容多 worker 并发写入。"""
        with self._thread_lock:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            with self.lock_path.open("a+", encoding="utf-8") as lock_file:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def _local_now(self) -> datetime:
        return datetime.now(self.timezone)

    def today(self) -> str:
        if self.today_provider:
            value = self.today_provider()
            return value.isoformat() if isinstance(value, date) else str(value)
        return self._local_now().date().isoformat()

    @staticmethod
    def _parse_date(value: str | date) -> date:
        if isinstance(value, date):
            return value
        try:
            return date.fromisoformat(str(value))
        except ValueError as exc:
            raise TodoDataError(f"日期格式无效: {value}") from exc

    @staticmethod
    def _month_key(value: str | date) -> str:
        return LearningTodoService._parse_date(value).strftime("%Y-%m")

    @staticmethod
    def _iter_months(start: date, end: date) -> Iterator[str]:
        cursor = date(start.year, start.month, 1)
        limit = date(end.year, end.month, 1)
        while cursor <= limit:
            yield cursor.strftime("%Y-%m")
            cursor = date(cursor.year + (cursor.month == 12), 1 if cursor.month == 12 else cursor.month + 1, 1)

    def _atomic_write_json(self, path: Path, payload: Dict[str, Any]) -> None:
        if path == self.settings_path:
            self._repository.write_settings(payload)
        elif path == self.subjects_path:
            self._repository.replace_subjects(payload)
        elif path == self.templates_path:
            self._repository.replace_templates(payload)
        elif path == self.reports_path:
            self._repository.replace_reports(payload)
        elif path == self.points_ledger_path:
            self._repository.replace_ledger(payload)
        elif path.parent == self.tasks_dir:
            self._repository.replace_tasks(path.stem, payload)
        else:
            raise TodoDataError(f"不支持的 Todo 数据路径: {path}")
        return
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def _read_json(self, path: Path, fallback: Dict[str, Any]) -> Dict[str, Any]:
        if path == self.settings_path:
            payload = self._repository.read_settings() or fallback
        elif path == self.subjects_path:
            payload = self._repository.read_subjects()
        elif path == self.templates_path:
            payload = self._repository.read_templates()
        elif path == self.reports_path:
            payload = self._repository.read_reports()
        elif path == self.points_ledger_path:
            payload = self._repository.read_ledger()
        elif path.parent == self.tasks_dir:
            payload = self._repository.read_tasks(path.stem)
        else:
            raise TodoDataError(f"不支持的 Todo 数据路径: {path}")
        return payload
        if not path.exists():
            return json.loads(json.dumps(fallback))
        try:
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            raise TodoDataError(f"Todo JSON 文件损坏: {path}") from exc
        if not isinstance(payload, dict):
            raise TodoDataError(f"Todo JSON 顶层必须是对象: {path}")
        return payload

    def _settings_unlocked(self) -> Dict[str, Any]:
        payload = self._read_json(
            self.settings_path,
            {
                "version": 1,
                "timezone": self.timezone_name,
                "recurrence_horizon_days": 400,
                "backup_retention": 50,
            },
        )
        payload.setdefault("version", 1)
        payload.setdefault("timezone", self.timezone_name)
        payload.setdefault("recurrence_horizon_days", 400)
        payload.setdefault("backup_retention", 50)
        return payload

    def _subjects_unlocked(self) -> Dict[str, Any]:
        return self._read_json(self.subjects_path, {"version": 1, "subjects": []})

    def _templates_unlocked(self) -> Dict[str, Any]:
        return self._read_json(self.templates_path, {"version": 1, "templates": []})

    def _reports_unlocked(self) -> Dict[str, Any]:
        return self._read_json(self.reports_path, {"version": 1, "reports": []})

    def _points_ledger_unlocked(self) -> Dict[str, Any]:
        payload = self._read_json(self.points_ledger_path, {"version": 1, "transactions": []})
        payload.setdefault("version", 1)
        payload.setdefault("transactions", [])
        if not isinstance(payload["transactions"], list):
            raise TodoDataError("points-ledger.json 的 transactions 必须是数组")
        for transaction in payload["transactions"]:
            if not isinstance(transaction, dict):
                raise TodoDataError("points-ledger.json 包含无效流水")
            transaction_type = transaction.get("type")
            if transaction_type not in POINT_TRANSACTION_TYPES:
                raise TodoDataError("points-ledger.json 包含未知流水类型")
            points = transaction.get("points")
            if not isinstance(points, int) or isinstance(points, bool):
                raise TodoDataError("points-ledger.json 包含无效积分")
            if not str(transaction.get("purpose") or "").strip():
                raise TodoDataError("points-ledger.json 包含空用途")
            if transaction_type == "spend" and points <= 0:
                raise TodoDataError("points-ledger.json 包含无效支出积分")
            if transaction_type == "correction":
                streak_action = transaction.get("streak_action", "none")
                if streak_action not in STREAK_CORRECTION_ACTIONS:
                    raise TodoDataError("points-ledger.json 包含无效连续记录修正")
                if points == 0 and streak_action == "none":
                    raise TodoDataError("points-ledger.json 包含空修正")
                try:
                    self._parse_date(transaction.get("effective_date", ""))
                except TodoDataError as exc:
                    raise TodoDataError("points-ledger.json 包含无效修正日期") from exc
        return payload

    def _month_path(self, month: str) -> Path:
        if not re.fullmatch(r"\d{4}-\d{2}", month):
            raise TodoDataError(f"月份格式无效: {month}")
        return self.tasks_dir / f"{month}.json"

    def _month_payload_unlocked(self, month: str) -> Dict[str, Any]:
        payload = self._read_json(
            self._month_path(month),
            {"version": 1, "month": month, "tasks": []},
        )
        payload.setdefault("version", 1)
        payload.setdefault("month", month)
        payload.setdefault("tasks", [])
        if payload["month"] != month or not isinstance(payload["tasks"], list):
            raise TodoDataError(f"Todo 月任务文件结构无效: {self._month_path(month)}")
        return payload

    def _month_names_unlocked(self) -> List[str]:
        return self._repository.list_months()

    def _managed_json_paths_unlocked(self) -> List[Path]:
        paths = [self.settings_path, self.subjects_path, self.templates_path, self.reports_path, self.points_ledger_path]
        paths.extend(self._month_path(month) for month in self._month_names_unlocked())
        return paths

    def _bootstrap(self) -> None:
        with self._guard():
            self.tasks_dir.mkdir(parents=True, exist_ok=True)
            self.backups_dir.mkdir(parents=True, exist_ok=True)

            # 启动时校验所有已有 JSON，损坏时拒绝静默覆盖。
            for path in sorted(self.data_dir.rglob("*.json")):
                self._read_json(path, {})

            if not self._repository.read_settings():
                self._atomic_write_json(
                    self.settings_path,
                    {
                        "version": 1,
                        "timezone": self.timezone_name,
                        "recurrence_horizon_days": 400,
                        "backup_retention": 50,
                        "updated_at": self._now(),
                    },
                )
            if not self._repository.read_subjects().get("subjects"):
                now = self._now()
                subjects = [{**subject, "created_at": now, "updated_at": now} for subject in DEFAULT_SUBJECTS]
                self._atomic_write_json(self.subjects_path, {"version": 1, "subjects": subjects})
            if not self._repository.read_templates().get("templates"):
                self._atomic_write_json(self.templates_path, {"version": 1, "templates": []})
            if not self._repository.read_reports().get("reports"):
                self._atomic_write_json(self.reports_path, {"version": 1, "reports": []})
            if not self._repository.read_ledger().get("transactions"):
                self._atomic_write_json(self.points_ledger_path, {"version": 1, "transactions": []})

            # 验证必要字段，防止错误数据延迟到请求时才暴露。
            if not isinstance(self._subjects_unlocked().get("subjects"), list):
                raise TodoDataError("subjects.json 的 subjects 必须是数组")
            if not isinstance(self._templates_unlocked().get("templates"), list):
                raise TodoDataError("templates.json 的 templates 必须是数组")
            if not isinstance(self._reports_unlocked().get("reports"), list):
                raise TodoDataError("reports.json 的 reports 必须是数组")
            self._points_ledger_unlocked()
            for month in self._month_names_unlocked():
                self._month_payload_unlocked(month)

    def validate_storage(self) -> Dict[str, Any]:
        with self._guard():
            checked = []
            for path in self._managed_json_paths_unlocked():
                self._read_json(path, {})
                checked.append(str(path.relative_to(self.data_dir)))
            return {
                "ok": True,
                "data_dir": str(self.data_dir),
                "database_path": str(self._database.path),
                "checked_records": checked,
                "checked_count": len(checked),
            }

    def _all_tasks_unlocked(self) -> List[Dict[str, Any]]:
        tasks: List[Dict[str, Any]] = []
        for month in self._month_names_unlocked():
            tasks.extend(self._month_payload_unlocked(month)["tasks"])
        return tasks

    def _find_task_unlocked(self, task_id: str) -> tuple[Dict[str, Any], str]:
        for month in self._month_names_unlocked():
            payload = self._month_payload_unlocked(month)
            for task in payload["tasks"]:
                if task.get("id") == task_id:
                    return task, month
        raise TodoDataError("任务不存在")

    def _write_task_unlocked(self, task: Dict[str, Any], previous_month: Optional[str] = None) -> None:
        target_month = self._month_key(task["planned_date"])
        if previous_month and previous_month != target_month:
            old_payload = self._month_payload_unlocked(previous_month)
            old_payload["tasks"] = [row for row in old_payload["tasks"] if row.get("id") != task["id"]]
            self._atomic_write_json(self._month_path(previous_month), old_payload)

        payload = self._month_payload_unlocked(target_month)
        for index, row in enumerate(payload["tasks"]):
            if row.get("id") == task["id"]:
                payload["tasks"][index] = task
                break
        else:
            payload["tasks"].append(task)
        payload["tasks"].sort(key=lambda row: (row.get("planned_date", ""), row.get("created_at", ""), row.get("id", "")))
        self._atomic_write_json(self._month_path(target_month), payload)

    def _write_tasks_grouped_unlocked(self, tasks: Iterable[Dict[str, Any]]) -> None:
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for task in tasks:
            grouped.setdefault(self._month_key(task["planned_date"]), []).append(task)
        for month, month_tasks in grouped.items():
            payload = self._month_payload_unlocked(month)
            by_id = {row.get("id"): row for row in payload["tasks"]}
            by_id.update({row["id"]: row for row in month_tasks})
            payload["tasks"] = sorted(
                by_id.values(),
                key=lambda row: (row.get("planned_date", ""), row.get("created_at", ""), row.get("id", "")),
            )
            self._atomic_write_json(self._month_path(month), payload)

    @staticmethod
    def _event(task: Dict[str, Any], event_type: str, at: str, **details: Any) -> None:
        task.setdefault("history", []).append({"type": event_type, "at": at, **details})

    def _subject_map_unlocked(self) -> Dict[str, Dict[str, Any]]:
        return {subject["id"]: subject for subject in self._subjects_unlocked()["subjects"]}

    def _require_subject_unlocked(self, subject_id: str, enabled_only: bool = False) -> Dict[str, Any]:
        subject = self._subject_map_unlocked().get(subject_id)
        if not subject:
            raise TodoDataError("科目不存在")
        if enabled_only and not subject.get("enabled", True):
            raise TodoDataError("该科目已停用")
        return subject

    @staticmethod
    def _is_active(task: Dict[str, Any]) -> bool:
        return task.get("lifecycle_status", ACTIVE_LIFECYCLE) == ACTIVE_LIFECYCLE

    def _task_status(self, task: Dict[str, Any], today: Optional[str] = None) -> str:
        if task.get("lifecycle_status") == "cancelled":
            return "cancelled"
        if task.get("lifecycle_status") == "voided":
            return "voided"
        if task.get("completed_at"):
            return "completed"
        if task["planned_date"] < (today or self.today()):
            return "overdue"
        return "pending"

    def _enrich_task_unlocked(self, task: Dict[str, Any]) -> Dict[str, Any]:
        result = json.loads(json.dumps(task))
        result.setdefault("reward_goal", "")
        result.setdefault("reward_points", 0)
        result.setdefault("reward_granted_at", None)
        result.setdefault("reward_granted_local_date", None)
        result.setdefault("reward_awarded_points", 0)
        if result.get("reward_granted_at"):
            result["reward_status"] = "granted"
        elif result.get("reward_goal") and int(result.get("reward_points") or 0) > 0:
            result["reward_status"] = "pending"
        else:
            result["reward_status"] = "none"
        subject = self._subject_map_unlocked().get(task.get("subject_id"), {})
        result["subject_name"] = subject.get("name", "其他")
        result["subject_color"] = subject.get("color", "#6B7280")
        if task.get("template_id"):
            template = next(
                (
                    row for row in self._templates_unlocked()["templates"]
                    if row.get("id") == task.get("template_id")
                ),
                None,
            )
            if template:
                result["repeat"] = template.get("repeat", result.get("repeat", "once"))
                result["repeat_weekdays"] = template.get("repeat_weekdays", result.get("repeat_weekdays", []))
                result["repeat_month_day"] = template.get("repeat_month_day")
                result["end_date"] = template.get("end_date")
        result["status"] = self._task_status(task)
        if result["status"] == "overdue":
            result["overdue_days"] = max(
                0,
                (self._parse_date(self.today()) - self._parse_date(task["planned_date"])).days,
            )
        else:
            result["overdue_days"] = 0
        return result

    def _public_task_unlocked(self, task: Dict[str, Any]) -> Dict[str, Any]:
        result = self._enrich_task_unlocked(task)
        for private_key in (
            "parent_note",
            "history",
            "template_id",
            "occurrence_key",
            "voided_at",
            "voided_local_date",
            "cancelled_at",
            "cancelled_local_date",
        ):
            result.pop(private_key, None)
        return result

    def _new_task(
        self,
        *,
        title: str,
        subject_id: str,
        planned_date: str,
        description: str = "",
        parent_note: str = "",
        reward_goal: str = "",
        reward_points: int = 0,
        repeat: str = "once",
        repeat_weekdays: Optional[List[int]] = None,
        template_id: Optional[str] = None,
        occurrence_key: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        now = self._now()
        task = {
            "id": task_id or f"task_{uuid.uuid4().hex}",
            "title": title.strip(),
            "subject_id": subject_id,
            "planned_date": planned_date,
            "description": description.strip(),
            "parent_note": parent_note.strip(),
            "reward_goal": reward_goal.strip(),
            "reward_points": int(reward_points),
            "reward_granted_at": None,
            "reward_granted_local_date": None,
            "reward_awarded_points": 0,
            "template_id": template_id,
            "occurrence_key": occurrence_key,
            "repeat": repeat,
            "repeat_weekdays": sorted(set(repeat_weekdays or [])),
            "lifecycle_status": ACTIVE_LIFECYCLE,
            "completed_at": None,
            "completed_local_date": None,
            "created_at": now,
            "updated_at": now,
            "version": 1,
            "history": [{"type": "created", "at": now}],
        }
        return task

    @staticmethod
    def _normalize_reward_configuration(goal: Any, points: Any) -> tuple[str, int]:
        reward_goal = str(goal or "").strip()
        try:
            reward_points = int(points or 0)
        except (TypeError, ValueError) as exc:
            raise TodoDataError("奖励点数必须是整数") from exc
        if reward_points < 0 or reward_points > 100000:
            raise TodoDataError("奖励点数必须在 0 到 100000 之间")
        if bool(reward_goal) != (reward_points > 0):
            raise TodoDataError("奖励目标和大于 0 的奖励点数必须同时填写；不设置奖励时请同时留空")
        return reward_goal, reward_points

    @staticmethod
    def _is_last_day(value: date) -> bool:
        return value.day == calendar.monthrange(value.year, value.month)[1]

    @staticmethod
    def _weekday_sunday_zero(value: date) -> int:
        return (value.weekday() + 1) % 7

    def _recurrence_dates(self, template: Dict[str, Any], through: date) -> Iterator[date]:
        start = self._parse_date(template["start_date"])
        end = min(through, self._parse_date(template["end_date"])) if template.get("end_date") else through
        if end < start:
            return
        kind = template["repeat"]
        cursor = start
        weekdays = set(template.get("repeat_weekdays") or [])
        month_day = template.get("repeat_month_day")
        while cursor <= end:
            include = kind == "daily"
            if kind == "weekly":
                include = self._weekday_sunday_zero(cursor) in weekdays
            elif kind == "monthly":
                if month_day == "last":
                    include = self._is_last_day(cursor)
                else:
                    include = cursor.day == int(month_day or start.day)
            if include:
                yield cursor
            cursor += timedelta(days=1)

    @staticmethod
    def _occurrence_id(template_id: str, occurrence_date: str) -> str:
        digest = hashlib.sha256(f"{template_id}:{occurrence_date}".encode("utf-8")).hexdigest()[:24]
        return f"task_{digest}"

    def _ensure_templates_through_unlocked(self, through: date) -> int:
        templates_payload = self._templates_unlocked()
        templates = [row for row in templates_payload["templates"] if row.get("active", True)]
        if not templates:
            return 0
        all_tasks = self._all_tasks_unlocked()
        existing = {
            (task.get("template_id"), task.get("occurrence_key")): task
            for task in all_tasks
            if task.get("template_id") and task.get("occurrence_key")
        }
        created: List[Dict[str, Any]] = []
        reactivated: List[Dict[str, Any]] = []
        for template in templates:
            for occurrence in self._recurrence_dates(template, through):
                occurrence_date = occurrence.isoformat()
                key = (template["id"], occurrence_date)
                if key in existing:
                    continue
                task = self._new_task(
                    title=template["title"],
                    subject_id=template["subject_id"],
                    planned_date=occurrence_date,
                    description=template.get("description", ""),
                    parent_note=template.get("parent_note", ""),
                    reward_goal=template.get("reward_goal", ""),
                    reward_points=template.get("reward_points", 0),
                    repeat=template["repeat"],
                    repeat_weekdays=template.get("repeat_weekdays", []),
                    template_id=template["id"],
                    occurrence_key=occurrence_date,
                    task_id=self._occurrence_id(template["id"], occurrence_date),
                )
                created.append(task)
                existing[key] = task
        if created or reactivated:
            self._write_tasks_grouped_unlocked([*created, *reactivated])
        return len(created)

    def _backup_locked(self, reason: str) -> Dict[str, Any]:
        safe_reason = re.sub(r"[^a-zA-Z0-9_-]+", "-", reason).strip("-") or "manual"
        stamp = self._local_now().strftime("%Y%m%d-%H%M%S-%f")
        filename = f"{stamp}-{safe_reason}.zip"
        destination = self.backups_dir / filename
        fd, temporary = tempfile.mkstemp(prefix=".tmp-backup-", suffix=".zip", dir=str(self.backups_dir))
        os.close(fd)
        try:
            with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for path in self._managed_json_paths_unlocked():
                    archive.writestr(path.relative_to(self.data_dir).as_posix(), json.dumps(self._read_json(path, {}), ensure_ascii=False, indent=2) + "\n")
                archive.writestr(
                    "backup-metadata.json",
                    json.dumps(
                        {"version": 1, "created_at": self._now(), "reason": reason},
                        ensure_ascii=False,
                        indent=2,
                    ),
                )
            os.replace(temporary, destination)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

        retention = int(self._settings_unlocked().get("backup_retention", 50))
        backups = sorted(self.backups_dir.glob("*.zip"), key=lambda path: path.stat().st_mtime, reverse=True)
        for expired in backups[retention:]:
            expired.unlink(missing_ok=True)
        return self._backup_info(destination)

    @staticmethod
    def _backup_info(path: Path) -> Dict[str, Any]:
        stat = path.stat()
        return {
            "name": path.name,
            "created_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat().replace("+00:00", "Z"),
            "size_bytes": stat.st_size,
        }

    def create_backup(self, reason: str = "manual") -> Dict[str, Any]:
        with self._guard():
            return self._backup_locked(reason)

    def list_backups(self) -> List[Dict[str, Any]]:
        with self._guard():
            return [
                self._backup_info(path)
                for path in sorted(self.backups_dir.glob("*.zip"), key=lambda item: item.stat().st_mtime, reverse=True)
            ]

    def restore_backup(self, backup_name: str) -> Dict[str, Any]:
        if Path(backup_name).name != backup_name:
            raise TodoDataError("备份名称无效")
        with self._guard():
            backup_path = self.backups_dir / backup_name
            if not backup_path.is_file():
                raise TodoDataError("备份不存在")
            archive_fd, archive_copy_name = tempfile.mkstemp(
                prefix="todo-restore-source-",
                suffix=".zip",
                dir=str(self.data_dir.parent),
            )
            os.close(archive_fd)
            archive_copy = Path(archive_copy_name)
            shutil.copy2(backup_path, archive_copy)
            self._backup_locked("before-restore")
            extract_dir = Path(tempfile.mkdtemp(prefix="todo-restore-", dir=str(self.data_dir.parent)))
            try:
                with zipfile.ZipFile(archive_copy, "r") as archive:
                    for member in archive.infolist():
                        member_path = Path(member.filename)
                        if member_path.is_absolute() or ".." in member_path.parts:
                            raise TodoDataError("备份中包含不安全路径")
                    archive.extractall(extract_dir)
                restored_payloads = {}
                for path in extract_dir.rglob("*.json"):
                    if path.name == "backup-metadata.json":
                        continue
                    with path.open("r", encoding="utf-8") as handle:
                        restored_payloads[path.relative_to(extract_dir).as_posix()] = json.load(handle)

                # 先解除旧任务对模板和科目的引用，再恢复静态 Todo 数据。
                self._repository.delete_all_tasks()

                for managed in [
                    self.settings_path,
                    self.subjects_path,
                    self.templates_path,
                    self.reports_path,
                    self.points_ledger_path,
                ]:
                    relative = managed.relative_to(self.data_dir).as_posix()
                    if relative in restored_payloads:
                        self._atomic_write_json(managed, restored_payloads[relative])
                    elif managed == self.points_ledger_path:
                        # 兼容积分支出功能上线前创建的旧备份。
                        self._atomic_write_json(managed, {"version": 1, "transactions": []})
                # subjects 第一次写入负责补齐备份中的科目；模板替换后再写一次，
                # 才能清理仅被旧模板引用、但不属于备份的科目。
                subjects_relative = self.subjects_path.relative_to(self.data_dir).as_posix()
                if subjects_relative in restored_payloads:
                    self._repository.replace_subjects(restored_payloads[subjects_relative])
                for relative, payload in restored_payloads.items():
                    match = re.fullmatch(r"tasks/(\d{4}-\d{2})\.json", relative)
                    if match:
                        self._repository.replace_tasks(match.group(1), payload)
                self._bootstrap_unlocked_validate()
            finally:
                shutil.rmtree(extract_dir, ignore_errors=True)
                archive_copy.unlink(missing_ok=True)
            return {"restored": True, "backup": backup_name}

    def _bootstrap_unlocked_validate(self) -> None:
        self._subjects_unlocked()
        self._templates_unlocked()
        self._reports_unlocked()
        self._points_ledger_unlocked()
        for month in self._month_names_unlocked():
            self._month_payload_unlocked(month)

    def list_subjects(self, include_disabled: bool = True) -> List[Dict[str, Any]]:
        with self._guard():
            subjects = self._subjects_unlocked()["subjects"]
            if not include_disabled:
                subjects = [row for row in subjects if row.get("enabled", True)]
            return sorted(subjects, key=lambda row: (row.get("sort_order", 0), row.get("created_at", "")))

    def create_subject(self, name: str, color: str, sort_order: Optional[int] = None) -> Dict[str, Any]:
        with self._guard():
            payload = self._subjects_unlocked()
            normalized = name.strip()
            if any(row.get("name", "").casefold() == normalized.casefold() for row in payload["subjects"]):
                raise TodoDataError("科目名称已存在")
            self._backup_locked("before-subject-create")
            now = self._now()
            subject = {
                "id": f"sub_{uuid.uuid4().hex}",
                "name": normalized,
                "color": color.upper(),
                "sort_order": sort_order if sort_order is not None else (len(payload["subjects"]) + 1) * 10,
                "enabled": True,
                "created_at": now,
                "updated_at": now,
            }
            payload["subjects"].append(subject)
            self._atomic_write_json(self.subjects_path, payload)
            return subject

    def update_subject(self, subject_id: str, changes: Dict[str, Any]) -> Dict[str, Any]:
        with self._guard():
            payload = self._subjects_unlocked()
            subject = next((row for row in payload["subjects"] if row.get("id") == subject_id), None)
            if not subject:
                raise TodoDataError("科目不存在")
            if "name" in changes and changes["name"] is not None:
                normalized = changes["name"].strip()
                if any(
                    row.get("id") != subject_id and row.get("name", "").casefold() == normalized.casefold()
                    for row in payload["subjects"]
                ):
                    raise TodoDataError("科目名称已存在")
                changes["name"] = normalized
            self._backup_locked("before-subject-update")
            for key in ("name", "color", "sort_order", "enabled"):
                if key in changes and changes[key] is not None:
                    subject[key] = changes[key].upper() if key == "color" else changes[key]
            subject["updated_at"] = self._now()
            self._atomic_write_json(self.subjects_path, payload)
            return subject

    def _normalize_repeat(
        self,
        planned_date: str,
        repeat: str,
        repeat_weekdays: Optional[List[int]],
        repeat_month_day: Optional[int | str],
    ) -> tuple[List[int], Optional[int | str]]:
        if repeat not in REPEAT_KINDS:
            raise TodoDataError("重复方式无效")
        weekdays = sorted(set(repeat_weekdays or []))
        if any(day < 0 or day > 6 for day in weekdays):
            raise TodoDataError("重复星期无效")
        if repeat == "weekly" and not weekdays:
            raise TodoDataError("每周重复任务至少选择一个星期")
        planned = self._parse_date(planned_date)
        month_day = repeat_month_day
        if repeat == "monthly":
            if month_day is None:
                month_day = "last" if self._is_last_day(planned) else planned.day
            if month_day != "last" and not 1 <= int(month_day) <= 31:
                raise TodoDataError("每月重复日期无效")
        return weekdays, month_day

    def create_task(self, data: Dict[str, Any]) -> Dict[str, Any]:
        with self._guard():
            self._require_subject_unlocked(data["subject_id"], enabled_only=True)
            planned_date = self._parse_date(data["planned_date"]).isoformat()
            repeat = data.get("repeat", "once")
            weekdays, month_day = self._normalize_repeat(
                planned_date,
                repeat,
                data.get("repeat_weekdays"),
                data.get("repeat_month_day"),
            )
            end_date = data.get("end_date")
            if end_date:
                end_date = self._parse_date(end_date).isoformat()
                if end_date < planned_date:
                    raise TodoDataError("结束日期不能早于开始日期")
            reward_goal, reward_points = self._normalize_reward_configuration(
                data.get("reward_goal", ""),
                data.get("reward_points", 0),
            )
            self._backup_locked("before-task-create")
            if repeat == "once":
                task = self._new_task(
                    title=data["title"],
                    subject_id=data["subject_id"],
                    planned_date=planned_date,
                    description=data.get("description", ""),
                    parent_note=data.get("parent_note", ""),
                    reward_goal=reward_goal,
                    reward_points=reward_points,
                )
                self._write_task_unlocked(task)
                return self._enrich_task_unlocked(task)

            now = self._now()
            template = {
                "id": f"tpl_{uuid.uuid4().hex}",
                "title": data["title"].strip(),
                "subject_id": data["subject_id"],
                "description": data.get("description", "").strip(),
                "parent_note": data.get("parent_note", "").strip(),
                "reward_goal": reward_goal,
                "reward_points": reward_points,
                "repeat": repeat,
                "repeat_weekdays": weekdays,
                "repeat_month_day": month_day,
                "start_date": planned_date,
                "end_date": end_date,
                "active": True,
                "created_at": now,
                "updated_at": now,
            }
            templates = self._templates_unlocked()
            templates["templates"].append(template)
            self._atomic_write_json(self.templates_path, templates)
            settings = self._settings_unlocked()
            horizon = self._parse_date(self.today()) + timedelta(days=int(settings["recurrence_horizon_days"]))
            if end_date:
                horizon = min(horizon, self._parse_date(end_date))
            self._ensure_templates_through_unlocked(max(horizon, self._parse_date(planned_date)))
            occurrences = [
                task
                for task in self._all_tasks_unlocked()
                if task.get("template_id") == template["id"]
            ]
            if not occurrences:
                raise TodoDataError("重复任务未能生成任何任务实例")
            first = sorted(occurrences, key=lambda row: row["planned_date"])[0]
            return self._enrich_task_unlocked(first)

    def list_templates(self, include_inactive: bool = False) -> List[Dict[str, Any]]:
        with self._guard():
            templates = self._templates_unlocked()["templates"]
            if not include_inactive:
                templates = [row for row in templates if row.get("active", True)]
            return sorted(templates, key=lambda row: (row.get("start_date", ""), row.get("created_at", "")))

    def _first_template_task_id(self, template_id: str) -> str:
        with self._guard():
            self._materialize_default_horizon_unlocked()
            tasks = [row for row in self._all_tasks_unlocked() if row.get("template_id") == template_id]
            if not tasks:
                raise TodoDataError("重复任务模板没有可操作的任务实例")
            return sorted(tasks, key=lambda row: row["planned_date"])[0]["id"]

    def update_template(self, template_id: str, changes: Dict[str, Any]) -> Dict[str, Any]:
        task_id = self._first_template_task_id(template_id)
        self.update_task(task_id, changes, scope="series")
        with self._guard():
            template = next(
                (row for row in self._templates_unlocked()["templates"] if row.get("id") == template_id),
                None,
            )
            if not template:
                raise TodoDataError("重复任务模板不存在")
            return template

    def deactivate_template(self, template_id: str) -> Dict[str, Any]:
        task_id = self._first_template_task_id(template_id)
        self.void_task(task_id, scope="series")
        with self._guard():
            template = next(
                (row for row in self._templates_unlocked()["templates"] if row.get("id") == template_id),
                None,
            )
            if not template:
                raise TodoDataError("重复任务模板不存在")
            return template

    def _materialize_default_horizon_unlocked(self, requested_end: Optional[str] = None) -> None:
        settings = self._settings_unlocked()
        horizon = self._parse_date(self.today()) + timedelta(days=int(settings["recurrence_horizon_days"]))
        if requested_end:
            horizon = max(horizon, self._parse_date(requested_end))
        self._ensure_templates_through_unlocked(horizon)

    def list_tasks(
        self,
        *,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        subject_id: Optional[str] = None,
        status: Optional[str] = None,
        include_inactive: bool = False,
    ) -> List[Dict[str, Any]]:
        with self._guard():
            self._materialize_default_horizon_unlocked(to_date)
            tasks = self._all_tasks_unlocked()
            if not include_inactive:
                tasks = [task for task in tasks if self._is_active(task)]
            if from_date:
                tasks = [task for task in tasks if task["planned_date"] >= from_date]
            if to_date:
                tasks = [task for task in tasks if task["planned_date"] <= to_date]
            if subject_id:
                tasks = [task for task in tasks if task.get("subject_id") == subject_id]
            if status:
                tasks = [task for task in tasks if self._task_status(task) == status]
            return [
                self._enrich_task_unlocked(task)
                for task in sorted(tasks, key=lambda row: (row["planned_date"], row.get("created_at", ""), row["id"]))
            ]

    def get_task(self, task_id: str) -> Dict[str, Any]:
        with self._guard():
            task, _ = self._find_task_unlocked(task_id)
            return self._enrich_task_unlocked(task)

    def _apply_task_changes_unlocked(self, task: Dict[str, Any], changes: Dict[str, Any]) -> None:
        now = self._now()
        before = {key: task.get(key) for key in changes}
        for key in ("title", "subject_id", "planned_date", "description", "parent_note", "reward_goal", "reward_points"):
            if key in changes and changes[key] is not None:
                if key in {"reward_goal", "reward_points"} and task.get("reward_granted_at"):
                    continue
                task[key] = changes[key].strip() if isinstance(changes[key], str) and key != "planned_date" else changes[key]
        if "repeat" in changes and changes["repeat"] is not None:
            task["repeat"] = changes["repeat"]
        if "repeat_weekdays" in changes and changes["repeat_weekdays"] is not None:
            task["repeat_weekdays"] = sorted(set(changes["repeat_weekdays"]))
        task["updated_at"] = now
        task["version"] = int(task.get("version", 1)) + 1
        self._event(task, "updated", now, before=before)

    def update_task(self, task_id: str, changes: Dict[str, Any], scope: str = "this") -> Dict[str, Any]:
        if scope not in {"this", "future", "series"}:
            raise TodoDataError("修改范围无效")
        with self._guard():
            task, previous_month = self._find_task_unlocked(task_id)
            if changes.get("subject_id"):
                self._require_subject_unlocked(changes["subject_id"], enabled_only=True)
            if changes.get("planned_date"):
                changes["planned_date"] = self._parse_date(changes["planned_date"]).isoformat()
            reward_change = "reward_goal" in changes or "reward_points" in changes
            if reward_change and (scope == "this" or not task.get("template_id")):
                reward_goal, reward_points = self._normalize_reward_configuration(
                    changes.get("reward_goal", task.get("reward_goal", "")),
                    changes.get("reward_points", task.get("reward_points", 0)),
                )
                if task.get("reward_granted_at") and (
                    reward_goal != task.get("reward_goal", "")
                    or reward_points != int(task.get("reward_points") or 0)
                ):
                    raise TodoDataError("已发放的任务奖励不能修改")
                changes["reward_goal"] = reward_goal
                changes["reward_points"] = reward_points
            self._backup_locked("before-task-update")

            template_id = task.get("template_id")
            if scope == "this" or not template_id:
                self._apply_task_changes_unlocked(task, changes)
                self._write_task_unlocked(task, previous_month)
                return self._enrich_task_unlocked(task)
            if changes.get("repeat") == "once":
                raise TodoDataError("重复计划不能批量修改为单次任务")

            templates = self._templates_unlocked()
            template = next((row for row in templates["templates"] if row.get("id") == template_id), None)
            if not template:
                raise TodoDataError("重复任务模板不存在")
            if reward_change:
                reward_goal, reward_points = self._normalize_reward_configuration(
                    changes.get("reward_goal", template.get("reward_goal", "")),
                    changes.get("reward_points", template.get("reward_points", 0)),
                )
                changes["reward_goal"] = reward_goal
                changes["reward_points"] = reward_points
            boundary = task["planned_date"] if scope == "future" else template["start_date"]
            now = self._now()

            target_template = template
            if scope == "future":
                template["end_date"] = (self._parse_date(boundary) - timedelta(days=1)).isoformat()
                template["updated_at"] = now
                target_template = {
                    **template,
                    "id": f"tpl_{uuid.uuid4().hex}",
                    "start_date": changes.get("planned_date") or boundary,
                    "end_date": changes.get("end_date"),
                    "created_at": now,
                    "updated_at": now,
                    "active": True,
                }
                templates["templates"].append(target_template)

            for key in ("title", "subject_id", "description", "parent_note", "reward_goal", "reward_points", "repeat", "repeat_weekdays", "repeat_month_day"):
                if key in changes and changes[key] is not None:
                    target_template[key] = changes[key]
            if "end_date" in changes:
                target_template["end_date"] = changes["end_date"]
            target_template["updated_at"] = now
            repeat = target_template.get("repeat", "once")
            weekdays, month_day = self._normalize_repeat(
                target_template["start_date"],
                repeat,
                target_template.get("repeat_weekdays"),
                target_template.get("repeat_month_day"),
            )
            target_template["repeat_weekdays"] = weekdays
            target_template["repeat_month_day"] = month_day
            self._atomic_write_json(self.templates_path, templates)

            instance_changes = dict(changes)
            if scope == "series":
                # 整个计划修改时，计划日期是编辑器当前实例日期，不能写到所有实例。
                instance_changes.pop("planned_date", None)
            settings = self._settings_unlocked()
            horizon = self._parse_date(self.today()) + timedelta(days=int(settings["recurrence_horizon_days"]))
            if target_template.get("end_date"):
                horizon = min(horizon, self._parse_date(target_template["end_date"]))
            allowed_series_dates = (
                {value.isoformat() for value in self._recurrence_dates(target_template, horizon)}
                if scope == "series"
                else set()
            )
            affected = []
            for instance in self._all_tasks_unlocked():
                if instance.get("template_id") != template_id or instance["planned_date"] < boundary:
                    continue
                if scope == "future":
                    instance["lifecycle_status"] = "voided"
                    instance["voided_at"] = now
                    instance["voided_local_date"] = self.today()
                    self._event(instance, "voided", now, reason="repeat-plan-split")
                else:
                    self._apply_task_changes_unlocked(instance, instance_changes)
                    if (
                        instance["planned_date"] >= self.today()
                        and instance["planned_date"] not in allowed_series_dates
                        and not instance.get("completed_at")
                    ):
                        instance["lifecycle_status"] = "voided"
                        instance["voided_at"] = now
                        instance["voided_local_date"] = self.today()
                        self._event(instance, "voided", now, reason="repeat-rule-changed")
                affected.append(instance)
            self._write_tasks_grouped_unlocked(affected)
            self._materialize_default_horizon_unlocked(target_template.get("end_date"))

            if scope == "future":
                new_occurrences = [
                    row for row in self._all_tasks_unlocked()
                    if row.get("template_id") == target_template["id"]
                ]
                if not new_occurrences:
                    raise TodoDataError("修改后的重复计划没有生成任务")
                return self._enrich_task_unlocked(sorted(new_occurrences, key=lambda row: row["planned_date"])[0])
            refreshed, _ = self._find_task_unlocked(task_id)
            return self._enrich_task_unlocked(refreshed)

    def _change_completion(self, task_id: str, completed: bool) -> Dict[str, Any]:
        with self._guard():
            task, month = self._find_task_unlocked(task_id)
            if not self._is_active(task):
                raise TodoDataError("已取消或作废的任务不能修改完成状态")
            self._backup_locked("before-task-completion")
            now = self._now()
            if completed:
                if not task.get("completed_at"):
                    task["completed_at"] = now
                    task["completed_local_date"] = self.today()
                    self._event(task, "completed", now, completed_local_date=task["completed_local_date"])
            else:
                if task.get("completed_at"):
                    previous = task.get("completed_at")
                    task["completed_at"] = None
                    task["completed_local_date"] = None
                    self._event(task, "completion-undone", now, previous_completed_at=previous)
            task["updated_at"] = now
            task["version"] = int(task.get("version", 1)) + 1
            self._write_task_unlocked(task, month)
            return self._enrich_task_unlocked(task)

    def complete_task(self, task_id: str) -> Dict[str, Any]:
        return self._change_completion(task_id, True)

    def undo_completion(self, task_id: str) -> Dict[str, Any]:
        return self._change_completion(task_id, False)

    def grant_task_reward(self, task_id: str) -> Dict[str, Any]:
        """家长确认任务奖励；奖励点数在发放时固化，重复请求不会重复加分。"""
        with self._guard():
            task, month = self._find_task_unlocked(task_id)
            if not self._is_active(task):
                raise TodoDataError("已取消或作废的任务不能发放奖励")
            if not task.get("completed_at"):
                raise TodoDataError("任务完成后才能确认奖励")
            reward_goal, reward_points = self._normalize_reward_configuration(
                task.get("reward_goal", ""),
                task.get("reward_points", 0),
            )
            if not reward_goal or reward_points <= 0:
                raise TodoDataError("该任务没有设置奖励")
            if task.get("reward_granted_at"):
                return self._enrich_task_unlocked(task)

            self._backup_locked("before-task-reward-grant")
            now = self._now()
            task["reward_granted_at"] = now
            task["reward_granted_local_date"] = self.today()
            task["reward_awarded_points"] = reward_points
            task["updated_at"] = now
            task["version"] = int(task.get("version", 1)) + 1
            self._event(
                task,
                "reward-granted",
                now,
                reward_goal=reward_goal,
                reward_awarded_points=reward_points,
            )
            self._write_task_unlocked(task, month)
            return self._enrich_task_unlocked(task)

    def void_task(self, task_id: str, scope: str = "this", lifecycle: str = "voided") -> Dict[str, Any]:
        if scope not in {"this", "future", "series"}:
            raise TodoDataError("作废范围无效")
        if lifecycle not in INACTIVE_LIFECYCLES:
            raise TodoDataError("任务生命周期状态无效")
        with self._guard():
            task, month = self._find_task_unlocked(task_id)
            self._backup_locked(f"before-task-{lifecycle}")
            now = self._now()
            local_today = self.today()
            affected = [task]
            template_id = task.get("template_id")
            if template_id and scope != "this":
                boundary = task["planned_date"]
                affected = [
                    row for row in self._all_tasks_unlocked()
                    if row.get("template_id") == template_id
                    and (scope == "series" or row["planned_date"] >= boundary)
                ]
                templates = self._templates_unlocked()
                template = next((row for row in templates["templates"] if row.get("id") == template_id), None)
                if template:
                    if scope == "series":
                        template["active"] = False
                    else:
                        template["end_date"] = (self._parse_date(boundary) - timedelta(days=1)).isoformat()
                    template["updated_at"] = now
                    self._atomic_write_json(self.templates_path, templates)
            for row in affected:
                row["lifecycle_status"] = lifecycle
                row[f"{lifecycle}_at"] = now
                row[f"{lifecycle}_local_date"] = local_today
                row["updated_at"] = now
                row["version"] = int(row.get("version", 1)) + 1
                self._event(row, lifecycle, now, scope=scope)
            if len(affected) == 1:
                task = affected[0]
                self._write_task_unlocked(task, self._month_key(task["planned_date"]))
            else:
                self._write_tasks_grouped_unlocked(affected)
                task = next((row for row in affected if row.get("id") == task_id), task)
            return self._enrich_task_unlocked(task)

    def task_history(self, task_id: str) -> Dict[str, Any]:
        with self._guard():
            task, _ = self._find_task_unlocked(task_id)
            return {"task": self._enrich_task_unlocked(task), "history": task.get("history", [])}

    def copy_day(self, source_date: str, target_date: str) -> List[Dict[str, Any]]:
        source_date = self._parse_date(source_date).isoformat()
        target_date = self._parse_date(target_date).isoformat()
        with self._guard():
            self._backup_locked("before-copy-day")
            source = [
                row for row in self._all_tasks_unlocked()
                if row["planned_date"] == source_date and self._is_active(row)
            ]
            copies = [
                self._new_task(
                    title=row["title"],
                    subject_id=row["subject_id"],
                    planned_date=target_date,
                    description=row.get("description", ""),
                    parent_note=row.get("parent_note", ""),
                    reward_goal=row.get("reward_goal", ""),
                    reward_points=row.get("reward_points", 0),
                )
                for row in source
            ]
            if copies:
                self._write_tasks_grouped_unlocked(copies)
            return [self._enrich_task_unlocked(row) for row in copies]

    def copy_last_week(self, target_week_start: str) -> List[Dict[str, Any]]:
        target = self._parse_date(target_week_start)
        source_start = target - timedelta(days=7)
        with self._guard():
            self._backup_locked("before-copy-week")
            all_tasks = self._all_tasks_unlocked()
            copies = []
            for offset in range(7):
                source_day = (source_start + timedelta(days=offset)).isoformat()
                target_day = (target + timedelta(days=offset)).isoformat()
                for row in all_tasks:
                    if row["planned_date"] != source_day or not self._is_active(row):
                        continue
                    copies.append(
                        self._new_task(
                            title=row["title"],
                            subject_id=row["subject_id"],
                            planned_date=target_day,
                            description=row.get("description", ""),
                            parent_note=row.get("parent_note", ""),
                            reward_goal=row.get("reward_goal", ""),
                            reward_points=row.get("reward_points", 0),
                        )
                    )
            if copies:
                self._write_tasks_grouped_unlocked(copies)
            return [self._enrich_task_unlocked(row) for row in copies]

    def today_payload(self) -> Dict[str, Any]:
        today = self.today()
        with self._guard():
            self._materialize_default_horizon_unlocked(today)
            all_tasks = self._all_tasks_unlocked()
            active = [row for row in all_tasks if self._is_active(row)]
            overdue = [row for row in active if row["planned_date"] < today and not row.get("completed_at")]
            pending = [row for row in active if row["planned_date"] == today and not row.get("completed_at")]
            completed = [row for row in active if row.get("completed_local_date") == today]
            key = lambda row: (row["planned_date"], row.get("created_at", ""), row["id"])
            return {
                "server_date": today,
                "timezone": self.timezone_name,
                "overdue_tasks": [self._public_task_unlocked(row) for row in sorted(overdue, key=key)],
                "today_pending_tasks": [self._public_task_unlocked(row) for row in sorted(pending, key=key)],
                "today_completed_tasks": [
                    self._public_task_unlocked(row)
                    for row in sorted(completed, key=lambda item: item.get("completed_at", ""), reverse=True)
                ],
                "reward": self._reward_summary_unlocked(all_tasks),
            }

    def _reward_summary_unlocked(self, all_tasks: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """按计划日计算积分；无任务日不加分也不中断。"""
        all_tasks = all_tasks if all_tasks is not None else self._all_tasks_unlocked()
        today = self.today()
        transactions = self._points_ledger_unlocked()["transactions"]
        streak_correction_dates: set[str] = set()
        for transaction in transactions:
            if transaction.get("type") != "correction":
                continue
            effective_date = str(transaction.get("effective_date") or "")
            if not effective_date or effective_date > today:
                continue
            action = transaction.get("streak_action", "none")
            if action == "preserve":
                streak_correction_dates.add(effective_date)
            elif action == "clear":
                streak_correction_dates.discard(effective_date)

        scheduled_by_date: Dict[str, List[Dict[str, Any]]] = {}
        for task in all_tasks:
            planned_date = task.get("planned_date")
            if not planned_date or planned_date > today or not self._counts_on_date(task, planned_date):
                continue
            scheduled_by_date.setdefault(planned_date, []).append(task)
        actual_scheduled_dates = set(scheduled_by_date)
        # 连续修正也能恢复因误删任务造成的历史缺口，因此允许创建一个可审计的虚拟计分日。
        for corrected_date in streak_correction_dates:
            scheduled_by_date.setdefault(corrected_date, [])

        completion_points = 0
        streak = 0
        today_points = 0
        today_has_tasks = today in actual_scheduled_dates
        today_completed = False
        last_scored_date: Optional[str] = None
        recent_scores = []

        for planned_date in sorted(scheduled_by_date):
            tasks = scheduled_by_date[planned_date]
            completed_on_time = planned_date in streak_correction_dates or (
                bool(tasks) and all(task.get("completed_local_date") == planned_date for task in tasks)
            )
            points = 0
            if completed_on_time:
                streak += 1
                points = streak
                completion_points += points
                last_scored_date = planned_date
                if planned_date == today:
                    today_points = points
                    today_completed = True
            elif planned_date < today:
                # 历史计划日没有全部按时完成，连续记录从下一次成功重新计算。
                streak = 0
            # 今天尚未完成时先不重置，完成前仍展示本次可获得的积分。
            recent_scores.append(
                {
                    "date": planned_date,
                    "points": points,
                    "completed": completed_on_time,
                    "corrected": planned_date in streak_correction_dates,
                }
            )

        task_reward_points = sum(max(0, int(task.get("reward_awarded_points") or 0)) for task in all_tasks)
        today_task_reward_points = sum(
            max(0, int(task.get("reward_awarded_points") or 0))
            for task in all_tasks
            if task.get("reward_granted_local_date") == today
        )
        correction_points = sum(
            transaction["points"]
            for transaction in transactions
            if transaction.get("type") == "correction"
        )
        earned_points = completion_points + task_reward_points + correction_points
        spent_points = sum(
            transaction["points"]
            for transaction in transactions
            if transaction.get("type") == "spend"
        )
        available_points = earned_points - spent_points
        return {
            # total_points 继续保留，兼容已经上线的孩子端；其含义调整为当前可用积分。
            "total_points": available_points,
            "available_points": available_points,
            "earned_points": earned_points,
            "spent_points": spent_points,
            "completion_points": completion_points,
            "task_reward_points": task_reward_points,
            "correction_points": correction_points,
            "today_task_reward_points": today_task_reward_points,
            "today_points": today_points,
            "current_streak": streak,
            "next_points": streak + 1,
            "today_has_tasks": today_has_tasks,
            "today_completed": today_completed,
            "last_scored_date": last_scored_date,
            "recent_scores": recent_scores[-31:],
            "rule": "可用积分 = 连续完成积分 + 家长确认的任务奖励积分 + 人工积分修正 - 已支出积分",
        }

    def reward_summary(self) -> Dict[str, Any]:
        with self._guard():
            self._materialize_default_horizon_unlocked(self.today())
            return self._reward_summary_unlocked()

    def points_account(self) -> Dict[str, Any]:
        """返回积分余额和仅供家长查看的支出流水。"""
        with self._guard():
            self._materialize_default_horizon_unlocked(self.today())
            summary = self._reward_summary_unlocked()
            transactions = sorted(
                self._points_ledger_unlocked()["transactions"],
                key=lambda row: (row.get("created_at", ""), row.get("id", "")),
                reverse=True,
            )
            return {**summary, "transactions": transactions}

    def spend_points(self, points: int, purpose: str) -> Dict[str, Any]:
        """登记一次积分兑换；支出不得超过提交时的可用余额。"""
        purpose = str(purpose or "").strip()
        if not isinstance(points, int) or isinstance(points, bool) or points <= 0:
            raise TodoDataError("支出积分必须是大于 0 的整数")
        if not purpose:
            raise TodoDataError("请填写积分用途")

        with self._guard():
            self._materialize_default_horizon_unlocked(self.today())
            summary = self._reward_summary_unlocked()
            if points > summary["available_points"]:
                raise TodoDataError(f"可用积分不足，当前可用 {summary['available_points']} 分")

            ledger = self._points_ledger_unlocked()
            self._backup_locked("before-points-spend")
            transaction = {
                "id": f"spend_{uuid.uuid4().hex}",
                "type": "spend",
                "points": points,
                "purpose": purpose,
                "created_at": self._now(),
                "local_date": self.today(),
            }
            ledger["transactions"].append(transaction)
            self._atomic_write_json(self.points_ledger_path, ledger)

            account = self._reward_summary_unlocked()
            transactions = sorted(
                ledger["transactions"],
                key=lambda row: (row.get("created_at", ""), row.get("id", "")),
                reverse=True,
            )
            return {"transaction": transaction, "account": {**account, "transactions": transactions}}

    def correct_points(
        self,
        effective_date: str,
        points: int,
        purpose: str,
        streak_action: str = "none",
    ) -> Dict[str, Any]:
        """登记带生效日期的积分/连续记录修正，并保留完整审计流水。"""
        purpose = str(purpose or "").strip()
        if not isinstance(points, int) or isinstance(points, bool) or abs(points) > 1000000:
            raise TodoDataError("积分修正必须是 -1000000 到 1000000 之间的整数")
        if not purpose:
            raise TodoDataError("请填写修正原因")
        if streak_action not in STREAK_CORRECTION_ACTIONS:
            raise TodoDataError("连续记录修正类型无效")
        if points == 0 and streak_action == "none":
            raise TodoDataError("请填写积分调整，或选择连续记录修正")

        parsed_date = self._parse_date(effective_date)
        today = self._parse_date(self.today())
        if parsed_date > today:
            raise TodoDataError("不能修正未来日期")
        normalized_date = parsed_date.isoformat()

        with self._guard():
            self._materialize_default_horizon_unlocked(self.today())
            before = self._reward_summary_unlocked()
            ledger = self._points_ledger_unlocked()
            self._backup_locked("before-points-correction")
            transaction = {
                "id": f"correction_{uuid.uuid4().hex}",
                "type": "correction",
                "points": points,
                "purpose": purpose,
                "effective_date": normalized_date,
                "streak_action": streak_action,
                "created_at": self._now(),
                "local_date": self.today(),
            }
            ledger["transactions"].append(transaction)
            self._atomic_write_json(self.points_ledger_path, ledger)

            account = self._reward_summary_unlocked()
            transactions = sorted(
                ledger["transactions"],
                key=lambda row: (row.get("created_at", ""), row.get("id", "")),
                reverse=True,
            )
            impact = {
                "available_points": account["available_points"] - before["available_points"],
                "completion_points": account["completion_points"] - before["completion_points"],
                "correction_points": account["correction_points"] - before["correction_points"],
                "current_streak": account["current_streak"] - before["current_streak"],
            }
            return {
                "transaction": transaction,
                "impact": impact,
                "account": {**account, "transactions": transactions},
            }

    def overview(self) -> Dict[str, Any]:
        today = self.today()
        with self._guard():
            self._materialize_default_horizon_unlocked(today)
            active = [row for row in self._all_tasks_unlocked() if self._is_active(row)]
            today_tasks = [row for row in active if row["planned_date"] == today]
            completed = [row for row in today_tasks if row.get("completed_at")]
            overdue = [row for row in active if row["planned_date"] < today and not row.get("completed_at")]
            return {
                "server_date": today,
                "timezone": self.timezone_name,
                "total": len(today_tasks),
                "completed": len(completed),
                "pending": len(today_tasks) - len(completed),
                "overdue": len(overdue),
                "completion_rate": round(len(completed) / len(today_tasks) * 100, 1) if today_tasks else 0,
            }

    @staticmethod
    def _inactive_date(task: Dict[str, Any]) -> Optional[str]:
        if task.get("lifecycle_status") == "voided":
            return task.get("voided_local_date")
        if task.get("lifecycle_status") == "cancelled":
            return task.get("cancelled_local_date")
        return None

    def _counts_on_date(self, task: Dict[str, Any], day: str) -> bool:
        inactive_date = self._inactive_date(task)
        return not inactive_date or inactive_date > day

    def _day_info_unlocked(self, day: str, all_tasks: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        all_tasks = all_tasks if all_tasks is not None else self._all_tasks_unlocked()
        today = self.today()
        scheduled = [
            row for row in all_tasks
            if row["planned_date"] == day and self._counts_on_date(row, day)
        ]
        completed = [row for row in scheduled if row.get("completed_at")]
        on_time = [row for row in scheduled if row.get("completed_local_date") == day]
        overdue_at_end = [
            row for row in all_tasks
            if row["planned_date"] < day
            and self._counts_on_date(row, day)
            and (not row.get("completed_local_date") or row["completed_local_date"] > day)
        ]
        unfinished_scheduled = [row for row in scheduled if row.get("completed_local_date") != day]
        if day > today:
            color = "future"
        elif overdue_at_end or unfinished_scheduled:
            color = "yellow"
        elif scheduled and len(on_time) == len(scheduled):
            color = "green"
        else:
            color = "gray"
        return {
            "date": day,
            "weekday": self._weekday_sunday_zero(self._parse_date(day)),
            "total": len(scheduled),
            "completed": len(completed),
            "on_time": len(on_time),
            "carryover": len(overdue_at_end),
            "has_overdue": bool(overdue_at_end),
            "color": color,
        }

    def day_view(self, day: str) -> Dict[str, Any]:
        day = self._parse_date(day).isoformat()
        with self._guard():
            self._materialize_default_horizon_unlocked(day)
            all_tasks = self._all_tasks_unlocked()
            scheduled = [
                row for row in all_tasks
                if row["planned_date"] == day and self._counts_on_date(row, day)
            ]
            overdue = [
                row for row in all_tasks
                if row["planned_date"] < day
                and self._counts_on_date(row, day)
                and (not row.get("completed_local_date") or row["completed_local_date"] > day)
            ]
            return {
                **self._day_info_unlocked(day, all_tasks),
                "tasks": [self._enrich_task_unlocked(row) for row in scheduled],
                "overdue_tasks": [self._enrich_task_unlocked(row) for row in overdue],
            }

    def week_view(self, week_start: str) -> Dict[str, Any]:
        start = self._parse_date(week_start)
        end = start + timedelta(days=6)
        with self._guard():
            self._materialize_default_horizon_unlocked(end.isoformat())
            all_tasks = self._all_tasks_unlocked()
            days = [
                self._day_info_unlocked((start + timedelta(days=offset)).isoformat(), all_tasks)
                for offset in range(7)
            ]
            return {"start_date": start.isoformat(), "end_date": end.isoformat(), "days": days}

    def month_view(self, month: str) -> Dict[str, Any]:
        if not re.fullmatch(r"\d{4}-\d{2}", month):
            raise TodoDataError("月份格式无效")
        year, month_number = map(int, month.split("-"))
        total_days = calendar.monthrange(year, month_number)[1]
        end = date(year, month_number, total_days)
        with self._guard():
            self._materialize_default_horizon_unlocked(end.isoformat())
            all_tasks = self._all_tasks_unlocked()
            days = [
                self._day_info_unlocked(date(year, month_number, day_number).isoformat(), all_tasks)
                for day_number in range(1, total_days + 1)
            ]
            return {"month": month, "days_in_month": total_days, "days": days}

    def _stats_unlocked(self, start: date, end: date) -> Dict[str, Any]:
        all_tasks = self._all_tasks_unlocked()
        tasks = [
            row for row in all_tasks
            if start.isoformat() <= row["planned_date"] <= end.isoformat()
            and self._counts_on_date(row, row["planned_date"])
        ]
        completed = [row for row in tasks if row.get("completed_at")]
        on_time = [row for row in completed if row.get("completed_local_date") == row["planned_date"]]
        late = [row for row in completed if row.get("completed_local_date", "") > row["planned_date"]]
        current_unfinished = [
            row for row in tasks
            if not row.get("completed_at") and row["planned_date"] <= self.today() and self._is_active(row)
        ]
        subject_map = self._subject_map_unlocked()
        by_subject = []
        for subject_id, subject in sorted(subject_map.items(), key=lambda item: item[1].get("sort_order", 0)):
            subject_tasks = [row for row in tasks if row.get("subject_id") == subject_id]
            subject_done = [row for row in subject_tasks if row.get("completed_at")]
            by_subject.append(
                {
                    "subject_id": subject_id,
                    "name": subject["name"],
                    "color": subject["color"],
                    "total": len(subject_tasks),
                    "completed": len(subject_done),
                    "completion_rate": round(len(subject_done) / len(subject_tasks) * 100, 1) if subject_tasks else 0,
                }
            )
        grid_days = []
        cursor = start
        visible_end = min(end, self._parse_date(self.today()))
        while cursor <= visible_end:
            grid_days.append(self._day_info_unlocked(cursor.isoformat(), all_tasks))
            cursor += timedelta(days=1)
        total = len(tasks)
        return {
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "total": total,
            "completed": len(completed),
            "on_time_completed": len(on_time),
            "late_completed": len(late),
            "current_unfinished": len(current_unfinished),
            "completion_rate": round(len(completed) / total * 100, 1) if total else 0,
            "on_time_rate": round(len(on_time) / total * 100, 1) if total else 0,
            "subjects": by_subject,
            "green_days": sum(day["color"] == "green" for day in grid_days),
            "yellow_days": sum(day["color"] == "yellow" for day in grid_days),
        }

    def week_stats(self, week_start: str) -> Dict[str, Any]:
        start = self._parse_date(week_start)
        end = start + timedelta(days=6)
        with self._guard():
            self._materialize_default_horizon_unlocked(end.isoformat())
            result = self._stats_unlocked(start, end)
            report = self._find_report_unlocked("week", start.isoformat())
            result["comment"] = report.get("comment", "") if report else ""
            return result

    def month_stats(self, month: str) -> Dict[str, Any]:
        if not re.fullmatch(r"\d{4}-\d{2}", month):
            raise TodoDataError("月份格式无效")
        year, month_number = map(int, month.split("-"))
        start = date(year, month_number, 1)
        end = date(year, month_number, calendar.monthrange(year, month_number)[1])
        with self._guard():
            self._materialize_default_horizon_unlocked(end.isoformat())
            result = self._stats_unlocked(start, end)
            report = self._find_report_unlocked("month", month)
            result["comment"] = report.get("comment", "") if report else ""
            result["grid"] = [
                self._day_info_unlocked(date(year, month_number, day_number).isoformat())
                for day_number in range(1, end.day + 1)
            ]
            return result

    def _find_report_unlocked(self, period_type: str, period_key: str) -> Optional[Dict[str, Any]]:
        return next(
            (
                row for row in self._reports_unlocked()["reports"]
                if row.get("period_type") == period_type and row.get("period_key") == period_key
            ),
            None,
        )

    def get_report(self, period_type: str, period_key: str) -> Dict[str, Any]:
        if period_type not in {"week", "month"}:
            raise TodoDataError("评语周期无效")
        with self._guard():
            report = self._find_report_unlocked(period_type, period_key)
            return report or {"period_type": period_type, "period_key": period_key, "comment": "", "updated_at": None}

    def save_report(self, period_type: str, period_key: str, comment: str) -> Dict[str, Any]:
        if period_type not in {"week", "month"}:
            raise TodoDataError("评语周期无效")
        with self._guard():
            self._backup_locked("before-report-update")
            payload = self._reports_unlocked()
            report = next(
                (
                    row for row in payload["reports"]
                    if row.get("period_type") == period_type and row.get("period_key") == period_key
                ),
                None,
            )
            now = self._now()
            if report:
                report["comment"] = comment
                report["updated_at"] = now
            else:
                report = {
                    "period_type": period_type,
                    "period_key": period_key,
                    "comment": comment,
                    "created_at": now,
                    "updated_at": now,
                }
                payload["reports"].append(report)
            self._atomic_write_json(self.reports_path, payload)
            return report

    def get_settings(self) -> Dict[str, Any]:
        with self._guard():
            return self._settings_unlocked()

    def update_settings(self, changes: Dict[str, Any]) -> Dict[str, Any]:
        with self._guard():
            self._backup_locked("before-settings-update")
            settings = self._settings_unlocked()
            for key in ("recurrence_horizon_days", "backup_retention"):
                if key in changes and changes[key] is not None:
                    settings[key] = int(changes[key])
            settings["updated_at"] = self._now()
            self._atomic_write_json(self.settings_path, settings)
            return settings


_learning_todo_service: Optional[LearningTodoService] = None


def get_learning_todo_service() -> LearningTodoService:
    global _learning_todo_service
    if _learning_todo_service is None:
        _learning_todo_service = LearningTodoService()
    return _learning_todo_service
