"""Application service for incremental question generation jobs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from config import config
from database import GenerationJobRepository, database_for_data_root


ACTIVE_GENERATION_STATUSES = {"queued", "generating"}
TERMINAL_GENERATION_STATUSES = {"completed", "partial_failed", "failed", "cancelled"}


class GenerationJobNotFound(LookupError):
    pass


class GenerationJobService:
    def __init__(
        self,
        repository: Optional[GenerationJobRepository] = None,
        ttl_seconds: Optional[int] = None,
        stale_seconds: Optional[int] = None,
    ):
        if repository is None:
            repository = GenerationJobRepository(database_for_data_root(config.DATA_DIR))
        self.repository = repository
        self.ttl_seconds = int(ttl_seconds or config.GENERATION_JOB_TTL_SECONDS)
        self.stale_seconds = int(stale_seconds or config.GENERATION_JOB_STALE_SECONDS)

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _iso(value: datetime) -> str:
        return value.isoformat().replace("+00:00", "Z")

    def create_job(
        self,
        *,
        kind: str,
        requested_count: int,
        request: Dict[str, Any],
        plan: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        self.repository.cleanup_expired(self._iso(self._now()))
        record = self.repository.create(
            kind=kind,
            requested_count=requested_count,
            request=request,
            plan=plan,
            metadata=metadata or {},
            expires_at=self._iso(self._now() + timedelta(seconds=self.ttl_seconds)),
        )
        return self._public(record)

    def get_internal_job(self, job_id: str, kind: Optional[str] = None) -> Dict[str, Any]:
        record = self.repository.get(job_id, kind)
        if record is None:
            raise GenerationJobNotFound("生成任务不存在或已过期")
        return record

    def get_job(self, job_id: str, *, kind: Optional[str] = None, after: int = 0) -> Dict[str, Any]:
        record = self.get_internal_job(job_id, kind)
        if record["status"] in ACTIVE_GENERATION_STATUSES:
            try:
                updated_at = datetime.fromisoformat(str(record["updated_at"]).replace("Z", "+00:00"))
            except ValueError:
                updated_at = self._now() - timedelta(seconds=self.stale_seconds + 1)
            if (self._now() - updated_at).total_seconds() > self.stale_seconds:
                self.repository.fail(job_id, "生成任务超时或服务已重启")
                record = self.get_internal_job(job_id, kind)
        cursor = max(0, min(int(after), record["generated_count"]))
        return self._public(record, after=cursor)

    @staticmethod
    def _public(record: Dict[str, Any], after: int = 0) -> Dict[str, Any]:
        return {
            "job_id": record["job_id"],
            "kind": record["kind"],
            "status": record["status"],
            "requested_count": record["requested_count"],
            "generated_count": record["generated_count"],
            "questions": record["questions"][after:],
            "next_cursor": record["generated_count"],
            "metadata": record.get("metadata") or {},
            "error": record.get("error"),
        }

    def mark_generating(self, job_id: str) -> bool:
        return self.repository.mark_generating(job_id)

    def is_active(self, job_id: str) -> bool:
        return self.get_internal_job(job_id)["status"] in ACTIVE_GENERATION_STATUSES

    def append_questions(self, job_id: str, questions: List[Dict[str, Any]]) -> Dict[str, Any]:
        record = self.repository.append_questions(job_id, questions)
        if record is None:
            raise GenerationJobNotFound("生成任务不存在或已过期")
        return self._public(record)

    def mark_failed(self, job_id: str, error: str) -> Dict[str, Any]:
        record = self.repository.fail(job_id, error)
        if record is None:
            raise GenerationJobNotFound("生成任务不存在或已过期")
        return self._public(record)

    def cancel_job(self, job_id: str, *, kind: Optional[str] = None) -> Dict[str, Any]:
        record = self.repository.cancel(job_id, kind)
        if record is None:
            raise GenerationJobNotFound("生成任务不存在或已过期")
        return self._public(record)


_generation_job_service: Optional[GenerationJobService] = None


def get_generation_job_service() -> GenerationJobService:
    global _generation_job_service
    if _generation_job_service is None:
        _generation_job_service = GenerationJobService()
    return _generation_job_service
