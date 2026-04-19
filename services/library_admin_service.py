"""
词库管理服务模块（本地文件持久化版）
提供词库元数据、词条存储、启用状态管理
"""

import json
import os
import random
import tempfile
import threading
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional

from config import config


ALLOWED_LIBRARY_TYPES = {
    "english": {"cloze", "match"},
    "chinese": {"word_discrim", "conj_fill", "idiom_fill"}
}


class LibraryAdminService:
    """词库管理服务（本地文件持久化）"""

    def __init__(self):
        self.data_dir = config.DATA_DIR
        self.registry_path = os.path.join(self.data_dir, "library_registry.json")
        self._lock = threading.RLock()

        os.makedirs(self.data_dir, exist_ok=True)
        self._bootstrap_from_files_if_needed()

    def _now(self) -> str:
        return datetime.utcnow().isoformat() + "Z"

    def _atomic_write_text(self, path: str, content: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd, temp_path = tempfile.mkstemp(prefix=".tmp_", dir=os.path.dirname(path), text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(temp_path, path)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def _atomic_write_json(self, path: str, payload: Dict[str, Any]) -> None:
        self._atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))

    def _read_registry_unlocked(self) -> Dict[str, Any]:
        if not os.path.exists(self.registry_path):
            return {"version": 1, "libraries": []}
        with open(self.registry_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"version": 1, "libraries": []}
        data.setdefault("version", 1)
        data.setdefault("libraries", [])
        if not isinstance(data["libraries"], list):
            data["libraries"] = []
        return data

    def _write_registry_unlocked(self, registry: Dict[str, Any]) -> None:
        registry.setdefault("version", 1)
        registry.setdefault("libraries", [])
        self._atomic_write_json(self.registry_path, registry)

    def _infer_subject(self, library_name: str) -> str:
        return "chinese" if library_name.startswith("chinese_") else "english"

    def _infer_library_type(self, library_name: str, subject: str) -> Optional[str]:
        if subject == "english":
            if "match" in library_name:
                return "match"
            if "cloze" in library_name:
                return "cloze"
            return None

        if subject == "chinese":
            if "conjunction" in library_name or "conj" in library_name:
                return "conj_fill"
            if "idiom" in library_name:
                return "idiom_fill"
            if "word" in library_name:
                return "word_discrim"
        return None

    def _validate_library_type(self, subject: str, library_type: Optional[str]) -> None:
        if library_type is None:
            return
        allowed = ALLOWED_LIBRARY_TYPES.get(subject, set())
        if library_type not in allowed:
            allowed_text = "/".join(sorted(allowed)) if allowed else "无"
            raise ValueError(f"{subject} 学科不支持词库类型 {library_type}，仅支持: {allowed_text}")

    def _parse_items_from_file(self, file_name: str, subject: str) -> List[str]:
        file_path = os.path.join(self.data_dir, f"{file_name}.txt")
        if not os.path.exists(file_path):
            return []

        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read().strip()

        if not content:
            return []

        if subject == "english":
            raw = content.replace("，", ",").split(",")
            return [x.strip() for x in raw if x.strip()]

        return [x.strip() for x in content.splitlines() if x.strip() and not x.strip().startswith("#")]

    def _write_items_file(self, file_name: str, subject: str, items: List[str]) -> None:
        file_path = os.path.join(self.data_dir, f"{file_name}.txt")
        if subject == "english":
            content = ", ".join(items)
        else:
            content = "\n".join(items)
        self._atomic_write_text(file_path, content)

    def _clean_items(self, items: List[str]) -> List[str]:
        cleaned = [x.strip() for x in items if x and x.strip()]
        if not cleaned:
            raise ValueError("词条不能为空，至少需要 1 条")
        return cleaned

    def _list_txt_names(self) -> List[str]:
        names: List[str] = []
        for filename in sorted(os.listdir(self.data_dir)):
            if filename.endswith(".txt"):
                names.append(filename[:-4])
        return names

    def _normalize_library_entry(self, entry: Dict[str, Any], now: str) -> Dict[str, Any]:
        name = (entry.get("name") or entry.get("file_name") or "").strip()
        if not name:
            return {}

        subject = entry.get("subject") or self._infer_subject(name)
        if subject not in ["english", "chinese"]:
            subject = self._infer_subject(name)

        library_type = entry.get("library_type")
        if library_type is None:
            library_type = self._infer_library_type(name, subject)

        try:
            self._validate_library_type(subject, library_type)
        except ValueError:
            library_type = None

        return {
            "id": entry.get("id") or uuid.uuid4().hex,
            "subject": subject,
            "name": name,
            "file_name": name,
            "enabled": bool(entry.get("enabled", True)),
            "library_type": library_type,
            "created_at": entry.get("created_at") or now,
            "updated_at": entry.get("updated_at") or now,
        }

    def _bootstrap_from_files_if_needed(self) -> None:
        with self._lock:
            registry = self._read_registry_unlocked()
            now = self._now()
            normalized: List[Dict[str, Any]] = []
            changed = False

            for raw in registry.get("libraries", []):
                if not isinstance(raw, dict):
                    changed = True
                    continue
                normalized_item = self._normalize_library_entry(raw, now)
                if not normalized_item:
                    changed = True
                    continue
                if normalized_item != raw:
                    changed = True
                normalized.append(normalized_item)

            # 若 registry 为空，自动从 data/*.txt 导入
            if not normalized:
                for name in self._list_txt_names():
                    subject = self._infer_subject(name)
                    items = self._parse_items_from_file(name, subject)
                    library_type = self._infer_library_type(name, subject)
                    try:
                        self._validate_library_type(subject, library_type)
                    except ValueError:
                        library_type = None

                    normalized.append({
                        "id": uuid.uuid4().hex,
                        "subject": subject,
                        "name": name,
                        "file_name": name,
                        "enabled": len(items) > 0,
                        "library_type": library_type,
                        "created_at": now,
                        "updated_at": now,
                    })
                changed = True

            # 若 registry 有条目但 data 下新增了 txt，也补充进来
            existing_names = {x["name"] for x in normalized}
            for name in self._list_txt_names():
                if name in existing_names:
                    continue
                subject = self._infer_subject(name)
                items = self._parse_items_from_file(name, subject)
                normalized.append({
                    "id": uuid.uuid4().hex,
                    "subject": subject,
                    "name": name,
                    "file_name": name,
                    "enabled": len(items) > 0,
                    "library_type": self._infer_library_type(name, subject),
                    "created_at": now,
                    "updated_at": now,
                })
                changed = True

            registry["libraries"] = sorted(normalized, key=lambda x: x.get("created_at", ""))
            if changed or not os.path.exists(self.registry_path):
                self._write_registry_unlocked(registry)

    def _library_with_count(self, row: Dict[str, Any]) -> Dict[str, Any]:
        subject = row["subject"]
        items = self._parse_items_from_file(row["file_name"], subject)
        return {
            "id": row["id"],
            "subject": subject,
            "name": row["name"],
            "file_name": row["file_name"],
            "enabled": row["enabled"],
            "library_type": row.get("library_type"),
            "total_items": len(items),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _find_library_by_id(self, libraries: List[Dict[str, Any]], library_id: str) -> Optional[Dict[str, Any]]:
        for lib in libraries:
            if lib.get("id") == library_id:
                return lib
        return None

    def _find_library_by_name(self, libraries: List[Dict[str, Any]], name: str) -> Optional[Dict[str, Any]]:
        for lib in libraries:
            if lib.get("name") == name:
                return lib
        return None

    def _find_library_by_file_name(self, libraries: List[Dict[str, Any]], file_name: str) -> Optional[Dict[str, Any]]:
        for lib in libraries:
            if lib.get("file_name") == file_name:
                return lib
        return None

    def list_libraries(self, subject: Optional[str] = None, include_disabled: bool = True) -> List[Dict[str, Any]]:
        with self._lock:
            registry = self._read_registry_unlocked()
            rows = sorted(registry.get("libraries", []), key=lambda x: x.get("created_at", ""))
            if subject:
                rows = [x for x in rows if x.get("subject") == subject]
            if not include_disabled:
                rows = [x for x in rows if bool(x.get("enabled"))]
            return [self._library_with_count(row) for row in rows]

    def get_library(self, library_id: str) -> Dict[str, Any]:
        with self._lock:
            registry = self._read_registry_unlocked()
            row = self._find_library_by_id(registry.get("libraries", []), library_id)
            if not row:
                raise ValueError("词库不存在")

            result = self._library_with_count(row)
            result["items"] = self._parse_items_from_file(row["file_name"], row["subject"])
            return result

    def create_library(
        self,
        subject: str,
        name: str,
        items: List[str],
        enabled: bool = True,
        library_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        if subject not in ["english", "chinese"]:
            raise ValueError("subject 仅支持 english 或 chinese")

        self._validate_library_type(subject, library_type)
        cleaned = self._clean_items(items)

        with self._lock:
            registry = self._read_registry_unlocked()
            libraries = registry.get("libraries", [])

            if self._find_library_by_name(libraries, name):
                raise ValueError("词库名称已存在")

            if self._find_library_by_file_name(libraries, name):
                raise ValueError("词库文件名已存在")

            now = self._now()
            entry = {
                "id": uuid.uuid4().hex,
                "subject": subject,
                "name": name,
                "file_name": name,
                "enabled": enabled,
                "library_type": library_type,
                "created_at": now,
                "updated_at": now,
            }

            self._write_items_file(name, subject, cleaned)
            libraries.append(entry)
            registry["libraries"] = sorted(libraries, key=lambda x: x.get("created_at", ""))
            self._write_registry_unlocked(registry)

            result = self._library_with_count(entry)
            result["items"] = cleaned
            return result

    def update_library(
        self,
        library_id: str,
        name: Optional[str] = None,
        library_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            registry = self._read_registry_unlocked()
            libraries = registry.get("libraries", [])
            target = self._find_library_by_id(libraries, library_id)
            if not target:
                raise ValueError("词库不存在")

            if name and name != target["name"]:
                by_name = self._find_library_by_name(libraries, name)
                if by_name and by_name.get("id") != library_id:
                    raise ValueError("词库名称已存在")

                old_path = os.path.join(self.data_dir, f"{target['file_name']}.txt")
                new_path = os.path.join(self.data_dir, f"{name}.txt")
                if os.path.exists(new_path):
                    raise ValueError("目标词库文件已存在")
                if os.path.exists(old_path):
                    os.replace(old_path, new_path)

                target["name"] = name
                target["file_name"] = name

            if library_type is not None:
                self._validate_library_type(target["subject"], library_type)
                target["library_type"] = library_type

            target["updated_at"] = self._now()
            self._write_registry_unlocked(registry)
            return self._library_with_count(target)

    def set_library_enabled(self, library_id: str, enabled: bool) -> Dict[str, Any]:
        with self._lock:
            registry = self._read_registry_unlocked()
            target = self._find_library_by_id(registry.get("libraries", []), library_id)
            if not target:
                raise ValueError("词库不存在")

            target["enabled"] = enabled
            target["updated_at"] = self._now()
            self._write_registry_unlocked(registry)
            return self._library_with_count(target)

    def replace_library_items(self, library_id: str, items: List[str]) -> Dict[str, Any]:
        cleaned = self._clean_items(items)

        with self._lock:
            registry = self._read_registry_unlocked()
            target = self._find_library_by_id(registry.get("libraries", []), library_id)
            if not target:
                raise ValueError("词库不存在")

            self._write_items_file(target["file_name"], target["subject"], cleaned)
            target["updated_at"] = self._now()
            self._write_registry_unlocked(registry)

            result = self._library_with_count(target)
            result["items"] = cleaned
            return result

    def get_enabled_library_names(self, subject: str, library_type: Optional[str] = None) -> List[str]:
        with self._lock:
            registry = self._read_registry_unlocked()
            enabled_rows = [
                x for x in registry.get("libraries", [])
                if x.get("subject") == subject and bool(x.get("enabled"))
            ]

            if library_type:
                typed = [x for x in enabled_rows if x.get("library_type") == library_type]
                if typed:
                    enabled_rows = typed

            enabled_rows = sorted(enabled_rows, key=lambda x: x.get("created_at", ""))
            return [x["name"] for x in enabled_rows]

    def resolve_enabled_library(
        self,
        subject: str,
        requested_library: Optional[str] = None,
        library_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            registry = self._read_registry_unlocked()
            libraries = registry.get("libraries", [])

            if requested_library:
                target = self._find_library_by_name(libraries, requested_library)
                if not target or target.get("subject") != subject:
                    raise ValueError(f"词库不存在: {requested_library}")
                if not target.get("enabled"):
                    raise ValueError(f"词库未启用: {requested_library}")
                if library_type and target.get("library_type") and target.get("library_type") != library_type:
                    raise ValueError(f"词库类型不匹配: {requested_library} 不支持 {library_type}")
                return self._library_with_count(target)

            enabled_rows = [
                x for x in libraries
                if x.get("subject") == subject and bool(x.get("enabled"))
            ]
            enabled_rows = sorted(enabled_rows, key=lambda x: x.get("created_at", ""))

            if not enabled_rows:
                raise ValueError(f"{subject} 学科暂无启用词库")

            if library_type:
                typed = [x for x in enabled_rows if x.get("library_type") == library_type]
                if typed:
                    return self._library_with_count(typed[0])

            return self._library_with_count(enabled_rows[0])

    def get_random_library_items(self, file_name: str, count: int) -> List[str]:
        with self._lock:
            registry = self._read_registry_unlocked()
            lib = self._find_library_by_file_name(registry.get("libraries", []), file_name)
            if not lib:
                return []
            items = self._parse_items_from_file(file_name, lib.get("subject", "english"))

        if not items:
            return []

        safe_count = min(count, len(items))
        return random.sample(items, safe_count)

    def get_public_library_info(self, file_name: str) -> Dict[str, Any]:
        with self._lock:
            registry = self._read_registry_unlocked()
            lib = self._find_library_by_file_name(registry.get("libraries", []), file_name)
            if not lib:
                raise ValueError("词库不存在")

            total_words = len(self._parse_items_from_file(file_name, lib.get("subject", "english")))
            file_path = os.path.join(self.data_dir, f"{file_name}.txt")

        return {
            "name": file_name,
            "total_words": total_words,
            "is_cached": False,
            "file_path": file_path,
        }


_library_admin_service_instance: Optional[LibraryAdminService] = None


def get_library_admin_service() -> LibraryAdminService:
    global _library_admin_service_instance
    if _library_admin_service_instance is None:
        _library_admin_service_instance = LibraryAdminService()
    return _library_admin_service_instance
