"""
词库管理服务模块
提供词库元数据、词条存储、启用状态管理
"""
import json
import os
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional

from config import config


ALLOWED_LIBRARY_TYPES = {
    "english": {"cloze", "match"},
    "chinese": {"word_discrim", "conj_fill", "idiom_fill"}
}


class LibraryAdminService:
    """词库管理服务"""

    def __init__(self):
        self.data_dir = config.DATA_DIR
        self.registry_path = os.path.join(self.data_dir, "library_registry.json")
        self._ensure_registry_initialized()

    def _now(self) -> str:
        return datetime.utcnow().isoformat() + "Z"

    def _library_file_path(self, file_name: str) -> str:
        return os.path.join(self.data_dir, f"{file_name}.txt")

    def _read_registry(self) -> Dict[str, Any]:
        with open(self.registry_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _write_registry(self, data: Dict[str, Any]) -> None:
        with open(self.registry_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _infer_subject(self, library_name: str) -> str:
        return "chinese" if library_name.startswith("chinese_") else "english"

    def _infer_library_type(self, library_name: str, subject: str) -> Optional[str]:
        if subject == "chinese":
            if "conjunction" in library_name:
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
        file_path = self._library_file_path(file_name)
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

    def _save_items_to_file(self, file_name: str, subject: str, items: List[str]) -> None:
        file_path = self._library_file_path(file_name)
        cleaned = [x.strip() for x in items if x and x.strip()]

        if not cleaned:
            raise ValueError("词条不能为空，至少需要 1 条")

        if subject == "english":
            content = ",".join(cleaned)
        else:
            content = "\n".join(cleaned)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

    def _ensure_registry_initialized(self) -> None:
        os.makedirs(self.data_dir, exist_ok=True)

        if os.path.exists(self.registry_path):
            return

        libraries: List[Dict[str, Any]] = []
        now = self._now()

        for filename in os.listdir(self.data_dir):
            if not filename.endswith(".txt"):
                continue
            library_name = filename[:-4]
            subject = self._infer_subject(library_name)
            libraries.append({
                "id": uuid.uuid4().hex,
                "subject": subject,
                "name": library_name,
                "file_name": library_name,
                "enabled": False if library_name == "暂时不用" else True,
                "library_type": self._infer_library_type(library_name, subject),
                "created_at": now,
                "updated_at": now
            })

        self._write_registry({"version": 1, "libraries": libraries})

    def _with_item_count(self, lib: Dict[str, Any]) -> Dict[str, Any]:
        items = self._parse_items_from_file(lib["file_name"], lib["subject"])
        result = dict(lib)
        result["total_items"] = len(items)
        return result

    def list_libraries(self, subject: Optional[str] = None, include_disabled: bool = True) -> List[Dict[str, Any]]:
        data = self._read_registry()
        libs = data.get("libraries", [])

        if subject:
            libs = [x for x in libs if x.get("subject") == subject]

        if not include_disabled:
            libs = [x for x in libs if x.get("enabled") is True]

        return [self._with_item_count(x) for x in libs]

    def get_library(self, library_id: str) -> Dict[str, Any]:
        data = self._read_registry()
        target = next((x for x in data.get("libraries", []) if x.get("id") == library_id), None)
        if not target:
            raise ValueError("词库不存在")
        result = self._with_item_count(target)
        result["items"] = self._parse_items_from_file(target["file_name"], target["subject"])
        return result

    def create_library(
        self,
        subject: str,
        name: str,
        items: List[str],
        enabled: bool = True,
        library_type: Optional[str] = None
    ) -> Dict[str, Any]:
        if subject not in ["english", "chinese"]:
            raise ValueError("subject 仅支持 english 或 chinese")

        self._validate_library_type(subject, library_type)

        data = self._read_registry()
        libs = data.get("libraries", [])

        if any(x.get("name") == name for x in libs):
            raise ValueError("词库名称已存在")

        file_path = self._library_file_path(name)
        if os.path.exists(file_path):
            raise ValueError("同名词库文件已存在")

        now = self._now()
        new_lib = {
            "id": uuid.uuid4().hex,
            "subject": subject,
            "name": name,
            "file_name": name,
            "enabled": enabled,
            "library_type": library_type,
            "created_at": now,
            "updated_at": now
        }

        self._save_items_to_file(name, subject, items)
        libs.append(new_lib)
        data["libraries"] = libs
        self._write_registry(data)

        return self._with_item_count(new_lib)

    def update_library(
        self,
        library_id: str,
        name: Optional[str] = None,
        library_type: Optional[str] = None
    ) -> Dict[str, Any]:
        data = self._read_registry()
        libs = data.get("libraries", [])
        target = next((x for x in libs if x.get("id") == library_id), None)

        if not target:
            raise ValueError("词库不存在")

        if name and name != target["name"]:
            if any(x.get("name") == name for x in libs):
                raise ValueError("词库名称已存在")

            old_file = self._library_file_path(target["file_name"])
            new_file = self._library_file_path(name)
            if os.path.exists(new_file):
                raise ValueError("目标词库文件已存在")
            if os.path.exists(old_file):
                os.rename(old_file, new_file)

            target["name"] = name
            target["file_name"] = name

        if library_type is not None:
            self._validate_library_type(target["subject"], library_type)
            target["library_type"] = library_type

        target["updated_at"] = self._now()
        self._write_registry(data)
        return self._with_item_count(target)

    def set_library_enabled(self, library_id: str, enabled: bool) -> Dict[str, Any]:
        data = self._read_registry()
        libs = data.get("libraries", [])
        target = next((x for x in libs if x.get("id") == library_id), None)

        if not target:
            raise ValueError("词库不存在")

        target["enabled"] = enabled
        target["updated_at"] = self._now()
        self._write_registry(data)

        return self._with_item_count(target)

    def replace_library_items(self, library_id: str, items: List[str]) -> Dict[str, Any]:
        data = self._read_registry()
        libs = data.get("libraries", [])
        target = next((x for x in libs if x.get("id") == library_id), None)

        if not target:
            raise ValueError("词库不存在")

        self._save_items_to_file(target["file_name"], target["subject"], items)
        target["updated_at"] = self._now()
        self._write_registry(data)

        result = self._with_item_count(target)
        result["items"] = self._parse_items_from_file(target["file_name"], target["subject"])
        return result

    def get_enabled_library_names(self, subject: str, library_type: Optional[str] = None) -> List[str]:
        libs = self.list_libraries(subject=subject, include_disabled=False)
        if library_type:
            typed = [x for x in libs if x.get("library_type") == library_type]
            if typed:
                libs = typed
        return [x["name"] for x in libs]

    def resolve_enabled_library(
        self,
        subject: str,
        requested_library: Optional[str] = None,
        library_type: Optional[str] = None
    ) -> Dict[str, Any]:
        data = self._read_registry()
        libs = data.get("libraries", [])

        subject_libs = [x for x in libs if x.get("subject") == subject]

        if requested_library:
            target = next((x for x in subject_libs if x.get("name") == requested_library), None)
            if not target:
                raise ValueError(f"词库不存在: {requested_library}")
            if not target.get("enabled"):
                raise ValueError(f"词库未启用: {requested_library}")
            if library_type and target.get("library_type") and target.get("library_type") != library_type:
                raise ValueError(f"词库类型不匹配: {requested_library} 不支持 {library_type}")
            return self._with_item_count(target)

        enabled_libs = [x for x in subject_libs if x.get("enabled") is True]
        if not enabled_libs:
            raise ValueError(f"{subject} 学科暂无启用词库")

        if library_type:
            typed = [x for x in enabled_libs if x.get("library_type") == library_type]
            if typed:
                return self._with_item_count(typed[0])

        return self._with_item_count(enabled_libs[0])


_library_admin_service_instance: Optional[LibraryAdminService] = None


def get_library_admin_service() -> LibraryAdminService:
    global _library_admin_service_instance
    if _library_admin_service_instance is None:
        _library_admin_service_instance = LibraryAdminService()
    return _library_admin_service_instance
