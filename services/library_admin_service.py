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
    "chinese": {"word_discrim", "conj_fill", "idiom_fill"}
}


class LibraryAdminService:
    """词库管理服务（本地文件持久化）"""

    def __init__(self):
        self.data_dir = config.DATA_DIR
        self.registry_path = os.path.join(self.data_dir, "library_registry.json")
        self.archive_path = os.path.join(self.data_dir, "library_archive.json")
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

    def _read_archive_unlocked(self) -> Dict[str, Any]:
        if not os.path.exists(self.archive_path):
            return {"version": 1, "libraries": []}
        with open(self.archive_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"version": 1, "libraries": []}
        data.setdefault("version", 1)
        data.setdefault("libraries", [])
        if not isinstance(data["libraries"], list):
            data["libraries"] = []
        return data

    def _write_archive_unlocked(self, archive: Dict[str, Any]) -> None:
        archive.setdefault("version", 1)
        archive.setdefault("libraries", [])
        self._atomic_write_json(self.archive_path, archive)

    def _infer_subject(self, library_name: str) -> str:
        return "chinese" if library_name.startswith("chinese_") else "english"

    def _infer_library_type(self, library_name: str, subject: str) -> Optional[str]:
        if subject == "english":
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
        if subject == "english" or library_type is None:
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
            raw = content.replace("，", ",").replace("\n", ",").split(",")
            return list(dict.fromkeys(x.strip() for x in raw if x.strip()))

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
        if subject == "english":
            library_type = None
        elif library_type is None:
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

    def _normalize_archive_entry(self, entry: Dict[str, Any], now: str) -> Dict[str, Any]:
        normalized = self._normalize_library_entry(entry, now)
        if not normalized:
            return {}
        raw_items = entry.get("items")
        if isinstance(raw_items, list):
            items = [str(item).strip() for item in raw_items if str(item).strip()]
        else:
            items = self._parse_items_from_file(normalized["file_name"], normalized["subject"])
        return {
            **normalized,
            "enabled": False,
            "archived": True,
            "archived_at": entry.get("archived_at") or now,
            "items": items,
        }

    def _bootstrap_from_files_if_needed(self) -> None:
        with self._lock:
            registry = self._read_registry_unlocked()
            archive = self._read_archive_unlocked()
            now = self._now()
            normalized: List[Dict[str, Any]] = []
            normalized_archive: List[Dict[str, Any]] = []
            changed = False
            archive_changed = not os.path.exists(self.archive_path)

            for raw in archive.get("libraries", []):
                if not isinstance(raw, dict):
                    archive_changed = True
                    continue
                normalized_item = self._normalize_archive_entry(raw, now)
                if not normalized_item:
                    archive_changed = True
                    continue
                if normalized_item != raw:
                    archive_changed = True
                normalized_archive.append(normalized_item)

            archive_by_name = {row["name"]: row for row in normalized_archive}

            for raw in registry.get("libraries", []):
                if not isinstance(raw, dict):
                    changed = True
                    continue
                normalized_item = self._normalize_library_entry(raw, now)
                if not normalized_item:
                    changed = True
                    continue
                # 兼容早期同表 archived 字段，并修复跨文件写入中断造成的重复项。
                if raw.get("archived") or normalized_item["name"] in archive_by_name:
                    if normalized_item["name"] not in archive_by_name:
                        archived_item = self._normalize_archive_entry(raw, now)
                        archive_by_name[archived_item["name"]] = archived_item
                        normalized_archive.append(archived_item)
                        archive_changed = True
                    changed = True
                    continue
                if normalized_item != raw:
                    changed = True
                normalized.append(normalized_item)

            # 若 registry 为空，自动从 data/*.txt 导入
            if not normalized:
                for name in self._list_txt_names():
                    if name in archive_by_name:
                        continue
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
            existing_names = {x["name"] for x in normalized} | set(archive_by_name)
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
            archive["libraries"] = sorted(normalized_archive, key=lambda x: x.get("archived_at", ""))
            if archive_changed:
                self._write_archive_unlocked(archive)

    def _library_with_count(self, row: Dict[str, Any], *, archived: bool = False) -> Dict[str, Any]:
        subject = row["subject"]
        items = row.get("items", []) if archived else self._parse_items_from_file(row["file_name"], subject)
        return {
            "id": row["id"],
            "subject": subject,
            "name": row["name"],
            "file_name": row["file_name"],
            "enabled": False if archived else bool(row.get("enabled")),
            "archived": archived,
            "archived_at": row.get("archived_at") if archived else None,
            "library_type": None if subject == "english" else row.get("library_type"),
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

    def list_libraries(
        self,
        subject: Optional[str] = None,
        include_disabled: bool = True,
        include_archived: bool = False,
    ) -> List[Dict[str, Any]]:
        with self._lock:
            registry = self._read_registry_unlocked()
            rows = sorted(registry.get("libraries", []), key=lambda x: x.get("created_at", ""))
            if subject:
                rows = [x for x in rows if x.get("subject") == subject]
            if not include_disabled:
                rows = [x for x in rows if bool(x.get("enabled"))]
            result = [self._library_with_count(row) for row in rows]
            if include_archived:
                archived_rows = self._read_archive_unlocked().get("libraries", [])
                if subject:
                    archived_rows = [row for row in archived_rows if row.get("subject") == subject]
                result.extend(self._library_with_count(row, archived=True) for row in archived_rows)
            return result

    def get_library(self, library_id: str) -> Dict[str, Any]:
        with self._lock:
            registry = self._read_registry_unlocked()
            row = self._find_library_by_id(registry.get("libraries", []), library_id)
            archived = False
            if not row:
                row = self._find_library_by_id(self._read_archive_unlocked().get("libraries", []), library_id)
                archived = bool(row)
            if not row:
                raise ValueError("词库不存在")

            result = self._library_with_count(row, archived=archived)
            result["items"] = list(row.get("items", [])) if archived else self._parse_items_from_file(row["file_name"], row["subject"])
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

        if subject == "english":
            library_type = None
        self._validate_library_type(subject, library_type)
        cleaned = self._clean_items(items)

        with self._lock:
            registry = self._read_registry_unlocked()
            libraries = registry.get("libraries", [])
            archived_libraries = self._read_archive_unlocked().get("libraries", [])

            if self._find_library_by_name(libraries, name) or self._find_library_by_name(archived_libraries, name):
                raise ValueError("词库名称已存在")

            if self._find_library_by_file_name(libraries, name) or self._find_library_by_file_name(archived_libraries, name):
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
                if self._find_library_by_id(self._read_archive_unlocked().get("libraries", []), library_id):
                    raise ValueError("归档词库需先取消归档，才能编辑")
                raise ValueError("词库不存在")

            if name and name != target["name"]:
                by_name = self._find_library_by_name(libraries, name)
                if by_name and by_name.get("id") != library_id:
                    raise ValueError("词库名称已存在")
                archived_by_name = self._find_library_by_name(
                    self._read_archive_unlocked().get("libraries", []),
                    name,
                )
                if archived_by_name:
                    raise ValueError("归档词库中已存在同名词库")

                old_path = os.path.join(self.data_dir, f"{target['file_name']}.txt")
                new_path = os.path.join(self.data_dir, f"{name}.txt")
                if os.path.exists(new_path):
                    raise ValueError("目标词库文件已存在")
                if os.path.exists(old_path):
                    os.replace(old_path, new_path)

                target["name"] = name
                target["file_name"] = name

            if target["subject"] == "english":
                target["library_type"] = None
            elif library_type is not None:
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

    def set_library_archived(self, library_id: str, archived: bool) -> Dict[str, Any]:
        with self._lock:
            registry = self._read_registry_unlocked()
            archive = self._read_archive_unlocked()
            now = self._now()
            if archived:
                target = self._find_library_by_id(registry.get("libraries", []), library_id)
                if not target:
                    existing = self._find_library_by_id(archive.get("libraries", []), library_id)
                    if existing:
                        return self._library_with_count(existing, archived=True)
                    raise ValueError("词库不存在")
                archived_entry = {
                    **target,
                    "enabled": False,
                    "archived": True,
                    "archived_at": now,
                    "updated_at": now,
                    "items": self._parse_items_from_file(target["file_name"], target["subject"]),
                }
                archive["libraries"] = [
                    row for row in archive.get("libraries", [])
                    if row.get("id") != library_id and row.get("name") != target.get("name")
                ]
                archive["libraries"].append(archived_entry)
                self._write_archive_unlocked(archive)
                source_path = os.path.join(self.data_dir, f"{target['file_name']}.txt")
                if os.path.exists(source_path):
                    os.unlink(source_path)
                registry["libraries"] = [row for row in registry.get("libraries", []) if row.get("id") != library_id]
                self._write_registry_unlocked(registry)
                return self._library_with_count(archived_entry, archived=True)

            target = self._find_library_by_id(archive.get("libraries", []), library_id)
            if not target:
                existing = self._find_library_by_id(registry.get("libraries", []), library_id)
                if existing:
                    return self._library_with_count(existing)
                raise ValueError("归档词库不存在")
            if self._find_library_by_name(registry.get("libraries", []), target["name"]):
                raise ValueError("当前词库列表中已存在同名词库")
            restored = {
                key: value for key, value in target.items()
                if key not in {"archived", "archived_at", "items"}
            }
            restored["enabled"] = False
            restored["updated_at"] = now
            self._write_items_file(restored["file_name"], restored["subject"], list(target.get("items", [])))
            registry.setdefault("libraries", []).append(restored)
            registry["libraries"] = sorted(registry["libraries"], key=lambda row: row.get("created_at", ""))
            self._write_registry_unlocked(registry)
            archive["libraries"] = [row for row in archive.get("libraries", []) if row.get("id") != library_id]
            self._write_archive_unlocked(archive)
            return self._library_with_count(restored)

    def replace_library_items(self, library_id: str, items: List[str]) -> Dict[str, Any]:
        cleaned = self._clean_items(items)

        with self._lock:
            registry = self._read_registry_unlocked()
            target = self._find_library_by_id(registry.get("libraries", []), library_id)
            if not target:
                if self._find_library_by_id(self._read_archive_unlocked().get("libraries", []), library_id):
                    raise ValueError("归档词库需先取消归档，才能编辑词条")
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
                if x.get("subject") == subject
                and bool(x.get("enabled"))
                and len(self._parse_items_from_file(x.get("file_name", ""), subject)) > 0
            ]

            if library_type and subject != "english":
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
                    archived_target = self._find_library_by_name(
                        self._read_archive_unlocked().get("libraries", []), requested_library
                    )
                    if archived_target and archived_target.get("subject") == subject:
                        raise ValueError(f"词库已归档: {requested_library}")
                    raise ValueError(f"词库不存在: {requested_library}")
                if not target.get("enabled"):
                    raise ValueError(f"词库未启用: {requested_library}")
                if not self._parse_items_from_file(target["file_name"], subject):
                    raise ValueError(f"词库为空或文件不存在: {requested_library}")
                if subject != "english" and library_type and target.get("library_type") and target.get("library_type") != library_type:
                    raise ValueError(f"词库类型不匹配: {requested_library} 不支持 {library_type}")
                return self._library_with_count(target)

            enabled_rows = [
                x for x in libraries
                if x.get("subject") == subject
                and bool(x.get("enabled"))
                and len(self._parse_items_from_file(x.get("file_name", ""), subject)) > 0
            ]
            enabled_rows = sorted(enabled_rows, key=lambda x: x.get("created_at", ""))

            if not enabled_rows:
                raise ValueError(f"{subject} 学科暂无启用且非空词库")

            if library_type and subject != "english":
                typed = [x for x in enabled_rows if x.get("library_type") == library_type]
                if typed:
                    return self._library_with_count(typed[0])

            return self._library_with_count(enabled_rows[0])

    def get_random_library_items(self, file_name: str, count: int) -> List[str]:
        items = self.get_library_items(file_name)

        if not items:
            return []

        safe_count = min(count, len(items))
        return random.sample(items, safe_count)

    def get_library_items(self, file_name: str) -> List[str]:
        with self._lock:
            registry = self._read_registry_unlocked()
            lib = self._find_library_by_file_name(registry.get("libraries", []), file_name)
            if not lib:
                return []
            return self._parse_items_from_file(file_name, lib.get("subject", "english"))

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
