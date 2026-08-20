"""模型目录查询与默认模型 SQLite 持久化。

API Key 只在服务端使用；浏览器只能获取经过筛选的模型元数据。
Admin 选择保存在 SQLite，与词库、报告和 Todo 使用同一数据库的独立表。
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional
from urllib.parse import urlsplit, urlunsplit

import fcntl
import httpx

from config import config
from database import ModelSettingsRepository, database_for_data_root, migrate_legacy_data


class ModelSettingsError(RuntimeError):
    def __init__(self, message: str, *, kind: str = "validation"):
        super().__init__(message)
        self.kind = kind


class ModelSettingsService:
    def __init__(
        self,
        settings_path: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        fallback_model: Optional[str] = None,
        request_timeout: Optional[float] = None,
        http_transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        self.settings_path = Path(settings_path or config.MODEL_SETTINGS_FILE).resolve()
        self.lock_path = self.settings_path.parent / ".model-settings.lock"
        if self.settings_path.parent == Path(config.DATA_DIR).resolve():
            self._database = database_for_data_root(config.DATA_DIR)
            migrate_legacy_data(config.DATA_DIR, self._database)
        else:
            self._database = database_for_data_root(self.settings_path.parent)
            if self.settings_path.is_file() and not ModelSettingsRepository(self._database).read().get("selected_model"):
                with self.settings_path.open("r", encoding="utf-8") as handle:
                    ModelSettingsRepository(self._database).write(json.load(handle))
        self._repository = ModelSettingsRepository(self._database)
        self.api_key = config.OPENAI_API_KEY if api_key is None else api_key
        self.base_url = config.fix_base_url() if base_url is None else base_url
        self.fallback_model = (fallback_model or config.MODEL_NAME).strip()
        self.request_timeout = request_timeout or config.MODEL_LIST_TIMEOUT
        self.http_transport = http_transport
        self._thread_lock = threading.RLock()

    @contextmanager
    def _guard(self) -> Iterator[None]:
        with self._thread_lock:
            self.settings_path.parent.mkdir(parents=True, exist_ok=True)
            with self.lock_path.open("a+", encoding="utf-8") as lock_file:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _read_unlocked(self) -> Dict[str, Any]:
        try:
            payload = self._repository.read()
        except Exception as exc:
            raise ModelSettingsError(
                f"模型设置文件无法读取: {self.settings_path.name}",
                kind="storage",
            ) from exc
        if not isinstance(payload, dict):
            raise ModelSettingsError("模型设置文件格式无效", kind="storage")
        selected = payload.get("selected_model")
        if selected is not None and (not isinstance(selected, str) or not selected.strip()):
            raise ModelSettingsError("模型设置中的 selected_model 无效", kind="storage")
        return {
            "version": 1,
            "selected_model": selected.strip() if isinstance(selected, str) else None,
            "updated_at": payload.get("updated_at"),
        }

    def _atomic_write_unlocked(self, payload: Dict[str, Any]) -> None:
        try:
            self._repository.write(payload)
        except Exception as exc:
            raise ModelSettingsError("模型设置数据库无法写入", kind="storage") from exc

    def get_settings(self) -> Dict[str, Any]:
        with self._guard():
            payload = self._read_unlocked()
        selected = payload.get("selected_model") or self.fallback_model
        return {
            "selected_model": selected,
            "fallback_model": self.fallback_model,
            "source": "admin" if payload.get("selected_model") else "environment",
            "updated_at": payload.get("updated_at"),
            "models_endpoint": self.models_endpoint(),
        }

    def get_selected_model(self) -> str:
        return self.get_settings()["selected_model"]

    def set_selected_model(self, model_id: str) -> Dict[str, Any]:
        normalized = model_id.strip()
        if not normalized:
            raise ModelSettingsError("模型 ID 不能为空")
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        with self._guard():
            self._atomic_write_unlocked(
                {
                    "version": 1,
                    "selected_model": normalized,
                    "updated_at": now,
                }
            )
        return self.get_settings()

    def models_endpoint(self) -> str:
        raw = (self.base_url or "").strip().rstrip("/")
        if not raw:
            raise ModelSettingsError("未配置 OPENAI_BASE_URL", kind="configuration")
        parsed = urlsplit(raw)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ModelSettingsError("OPENAI_BASE_URL 格式无效", kind="configuration")
        path = parsed.path.rstrip("/")
        if path.endswith("/models"):
            target_path = path
        elif path.endswith("/v1"):
            target_path = f"{path}/models"
        else:
            target_path = f"{path}/v1/models"
        return urlunsplit((parsed.scheme, parsed.netloc, target_path, "", ""))

    @staticmethod
    def _normalize_models(payload: Any) -> List[Dict[str, Any]]:
        if isinstance(payload, list):
            rows = payload
        elif isinstance(payload, dict) and isinstance(payload.get("data"), list):
            rows = payload["data"]
        elif isinstance(payload, dict) and isinstance(payload.get("models"), list):
            rows = payload["models"]
        else:
            raise ModelSettingsError("模型接口返回格式无效", kind="upstream")

        normalized: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            if isinstance(row, str):
                model_id = row.strip()
                metadata: Dict[str, Any] = {}
            elif isinstance(row, dict):
                model_id = str(row.get("id") or row.get("name") or row.get("model") or "").strip()
                metadata = row
            else:
                continue
            if not model_id or len(model_id) > 255:
                continue
            normalized[model_id] = {
                "id": model_id,
                "owned_by": str(metadata.get("owned_by") or metadata.get("provider") or ""),
                "object": str(metadata.get("object") or "model"),
                "created": metadata.get("created") if isinstance(metadata.get("created"), (int, float)) else None,
            }
        if not normalized:
            raise ModelSettingsError("当前令牌没有返回可用模型", kind="upstream")
        return sorted(normalized.values(), key=lambda item: item["id"].casefold())

    async def fetch_available_models(self) -> Dict[str, Any]:
        if not self.api_key.strip():
            raise ModelSettingsError("未配置 OPENAI_API_KEY", kind="configuration")
        endpoint = self.models_endpoint()
        try:
            async with httpx.AsyncClient(
                timeout=self.request_timeout,
                transport=self.http_transport,
            ) as client:
                response = await client.get(
                    endpoint,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                    },
                )
        except httpx.TimeoutException as exc:
            raise ModelSettingsError("获取模型列表超时", kind="upstream") from exc
        except httpx.HTTPError as exc:
            raise ModelSettingsError("无法连接模型服务", kind="upstream") from exc

        if response.status_code != 200:
            raise ModelSettingsError(
                f"模型服务返回 HTTP {response.status_code}",
                kind="upstream",
            )
        try:
            models = self._normalize_models(response.json())
        except json.JSONDecodeError as exc:
            raise ModelSettingsError("模型服务没有返回有效 JSON", kind="upstream") from exc

        settings = self.get_settings()
        available_ids = {item["id"] for item in models}
        return {
            **settings,
            "models": models,
            "total": len(models),
            "selected_available": settings["selected_model"] in available_ids,
        }


_model_settings_service: Optional[ModelSettingsService] = None


def get_model_settings_service() -> ModelSettingsService:
    global _model_settings_service
    if _model_settings_service is None:
        _model_settings_service = ModelSettingsService()
    return _model_settings_service
