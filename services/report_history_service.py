"""
SQLite 报告历史服务
保存 Word Palace 与 MAP Test 的每日练习记录。
"""
import json
import os
import threading
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from config import config
from database import ReportRepository, database_for_data_root, migrate_legacy_data


class ReportHistoryService:
    """SQLite 报告历史服务"""

    def __init__(self):
        self.data_dir = config.DATA_DIR
        self.file_path = os.path.join(self.data_dir, "report_history.json")
        self._database = database_for_data_root(self.data_dir)
        migrate_legacy_data(self.data_dir, self._database)
        self._repository = ReportRepository(self._database)
        self._lock = threading.RLock()
        os.makedirs(self.data_dir, exist_ok=True)

    def add_report(self, report: Dict[str, Any]) -> Dict[str, Any]:
        now = datetime.now()
        row = {
            "id": str(uuid.uuid4()),
            "created_at": now.isoformat(timespec="seconds"),
            "date": now.strftime("%Y-%m-%d"),
            **report
        }

        with self._lock:
            data = self._read_unlocked()
            data.setdefault("reports", []).append(row)
            self._write_unlocked(data)
        return row

    def list_reports(
        self,
        module: Optional[str] = None,
        days: int = 30,
        limit: int = 200
    ) -> List[Dict[str, Any]]:
        cutoff = datetime.now() - timedelta(days=max(days, 1))
        with self._lock:
            reports = self._read_unlocked().get("reports", [])

        filtered = []
        for report in reports:
            if module and report.get("module") != module:
                continue
            try:
                created_at = datetime.fromisoformat(report.get("created_at", ""))
            except ValueError:
                created_at = datetime.min
            if created_at >= cutoff:
                filtered.append(report)

        filtered.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return filtered[:limit]

    def get_history(self, module: Optional[str] = None, days: int = 30) -> Dict[str, Any]:
        reports = self.list_reports(module=module, days=days)
        return {
            "daily": self._build_daily_summary(reports),
            "reports": reports
        }

    def _build_daily_summary(self, reports: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        grouped: Dict[str, Dict[str, Any]] = {}
        for report in reports:
            date_key = report.get("date") or report.get("created_at", "")[:10]
            module_key = report.get("module", "unknown")
            day = grouped.setdefault(date_key, {
                "date": date_key,
                "sessions": 0,
                "total_questions": 0,
                "correct_count": 0,
                "accuracy": "0%",
                "modules": {}
            })
            module_row = day["modules"].setdefault(module_key, {
                "module": module_key,
                "module_label": report.get("module_label", module_key),
                "sessions": 0,
                "total_questions": 0,
                "correct_count": 0,
                "accuracy": "0%"
            })
            total = int(report.get("total_count") or report.get("total_questions") or 0)
            correct = int(report.get("correct_count") or report.get("correct") or 0)

            day["sessions"] += 1
            day["total_questions"] += total
            day["correct_count"] += correct
            module_row["sessions"] += 1
            module_row["total_questions"] += total
            module_row["correct_count"] += correct

        for day in grouped.values():
            day["accuracy"] = self._format_accuracy(day["correct_count"], day["total_questions"])
            modules = []
            for module_row in day["modules"].values():
                module_row["accuracy"] = self._format_accuracy(module_row["correct_count"], module_row["total_questions"])
                modules.append(module_row)
            modules.sort(key=lambda x: x.get("module_label", ""))
            day["modules"] = modules

        return sorted(grouped.values(), key=lambda x: x.get("date", ""), reverse=True)

    def _format_accuracy(self, correct: int, total: int) -> str:
        if total <= 0:
            return "0%"
        return f"{round(correct / total * 100)}%"

    def _read_unlocked(self) -> Dict[str, Any]:
        try:
            data = self._repository.read_all()
            if not isinstance(data, dict):
                return {"version": 1, "reports": []}
            data.setdefault("reports", [])
            return data
        except Exception:
            return {"version": 1, "reports": []}

    def _write_unlocked(self, data: Dict[str, Any]) -> None:
        self._repository.replace_all(data)


_report_history_service: Optional[ReportHistoryService] = None


def get_report_history_service() -> ReportHistoryService:
    global _report_history_service
    if _report_history_service is None:
        _report_history_service = ReportHistoryService()
    return _report_history_service
