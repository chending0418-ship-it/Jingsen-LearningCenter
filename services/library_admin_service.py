"""
词库管理服务模块（PostgreSQL 版）
提供词库元数据、词条存储、启用状态管理
"""
import json
import os
import random
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional

from sqlalchemy import (
    MetaData,
    Table,
    Column,
    String,
    Integer,
    Boolean,
    Text,
    ForeignKey,
    UniqueConstraint,
    create_engine,
    select,
    func,
    and_,
)

from config import config


ALLOWED_LIBRARY_TYPES = {
    "english": {"cloze", "match"},
    "chinese": {"word_discrim", "conj_fill", "idiom_fill"}
}


class LibraryAdminService:
    """词库管理服务（数据库持久化）"""

    def __init__(self):
        self.data_dir = config.DATA_DIR
        self.registry_path = os.path.join(self.data_dir, "library_registry.json")

        database_url = config.database_url_for_sqlalchemy()
        if not database_url:
            raise ValueError("DATABASE_URL 未配置，无法使用 PostgreSQL 词库存储")

        self.engine = create_engine(database_url, future=True, pool_pre_ping=True)
        self.metadata = MetaData()

        self.libraries = Table(
            "libraries",
            self.metadata,
            Column("id", String(64), primary_key=True),
            Column("subject", String(32), nullable=False),
            Column("name", String(255), nullable=False, unique=True),
            Column("file_name", String(255), nullable=False, unique=True),
            Column("enabled", Boolean, nullable=False, default=True),
            Column("library_type", String(64), nullable=True),
            Column("created_at", String(64), nullable=False),
            Column("updated_at", String(64), nullable=False),
        )

        self.library_items = Table(
            "library_items",
            self.metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("library_id", String(64), ForeignKey("libraries.id", ondelete="CASCADE"), nullable=False),
            Column("item_order", Integer, nullable=False, default=0),
            Column("item_text", Text, nullable=False),
            UniqueConstraint("library_id", "item_order", name="uq_library_items_order"),
        )

        self.metadata.create_all(self.engine)
        self._bootstrap_from_files_if_needed()

    def _now(self) -> str:
        return datetime.utcnow().isoformat() + "Z"

    def _read_registry(self) -> Dict[str, Any]:
        if not os.path.exists(self.registry_path):
            return {"version": 1, "libraries": []}
        with open(self.registry_path, "r", encoding="utf-8") as f:
            return json.load(f)

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

    def _clean_items(self, items: List[str]) -> List[str]:
        cleaned = [x.strip() for x in items if x and x.strip()]
        if not cleaned:
            raise ValueError("词条不能为空，至少需要 1 条")
        return cleaned

    def _bootstrap_from_files_if_needed(self) -> None:
        os.makedirs(self.data_dir, exist_ok=True)
        with self.engine.begin() as conn:
            total = conn.execute(select(func.count()).select_from(self.libraries)).scalar_one()
            if total > 0:
                return

            registry = self._read_registry()
            registry_map = {
                x.get("name"): x for x in registry.get("libraries", []) if x.get("name")
            }
            now = self._now()

            for filename in sorted(os.listdir(self.data_dir)):
                if not filename.endswith(".txt"):
                    continue

                name = filename[:-4]
                subject = self._infer_subject(name)
                items = self._parse_items_from_file(name, subject)
                meta = registry_map.get(name, {})

                library_type = meta.get("library_type")
                if library_type is None:
                    library_type = self._infer_library_type(name, subject)

                try:
                    self._validate_library_type(subject, library_type)
                except ValueError:
                    library_type = None

                lib_id = meta.get("id") or uuid.uuid4().hex
                created_at = meta.get("created_at") or now
                updated_at = meta.get("updated_at") or now
                enabled = bool(meta.get("enabled", len(items) > 0))

                conn.execute(
                    self.libraries.insert().values(
                        id=lib_id,
                        subject=subject,
                        name=name,
                        file_name=name,
                        enabled=enabled,
                        library_type=library_type,
                        created_at=created_at,
                        updated_at=updated_at,
                    )
                )

                if items:
                    conn.execute(
                        self.library_items.insert(),
                        [
                            {
                                "library_id": lib_id,
                                "item_order": idx,
                                "item_text": item,
                            }
                            for idx, item in enumerate(items)
                        ],
                    )

    def _library_with_count(self, conn, row) -> Dict[str, Any]:
        total_items = conn.execute(
            select(func.count()).select_from(self.library_items).where(self.library_items.c.library_id == row.id)
        ).scalar_one()
        return {
            "id": row.id,
            "subject": row.subject,
            "name": row.name,
            "file_name": row.file_name,
            "enabled": row.enabled,
            "library_type": row.library_type,
            "total_items": total_items,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    def _get_library_by_id(self, conn, library_id: str):
        return conn.execute(
            select(self.libraries).where(self.libraries.c.id == library_id)
        ).mappings().first()

    def _get_library_by_name(self, conn, name: str):
        return conn.execute(
            select(self.libraries).where(self.libraries.c.name == name)
        ).mappings().first()

    def _get_library_by_file_name(self, conn, file_name: str):
        return conn.execute(
            select(self.libraries).where(self.libraries.c.file_name == file_name)
        ).mappings().first()

    def list_libraries(self, subject: Optional[str] = None, include_disabled: bool = True) -> List[Dict[str, Any]]:
        with self.engine.connect() as conn:
            stmt = select(self.libraries).order_by(self.libraries.c.created_at.asc())
            conditions = []
            if subject:
                conditions.append(self.libraries.c.subject == subject)
            if not include_disabled:
                conditions.append(self.libraries.c.enabled.is_(True))
            if conditions:
                stmt = stmt.where(and_(*conditions))

            rows = conn.execute(stmt).mappings().all()
            return [self._library_with_count(conn, row) for row in rows]

    def get_library(self, library_id: str) -> Dict[str, Any]:
        with self.engine.connect() as conn:
            row = self._get_library_by_id(conn, library_id)
            if not row:
                raise ValueError("词库不存在")

            result = self._library_with_count(conn, row)
            items = conn.execute(
                select(self.library_items.c.item_text)
                .where(self.library_items.c.library_id == library_id)
                .order_by(self.library_items.c.item_order.asc(), self.library_items.c.id.asc())
            ).scalars().all()
            result["items"] = items
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

        with self.engine.begin() as conn:
            if self._get_library_by_name(conn, name):
                raise ValueError("词库名称已存在")

            now = self._now()
            lib_id = uuid.uuid4().hex

            conn.execute(
                self.libraries.insert().values(
                    id=lib_id,
                    subject=subject,
                    name=name,
                    file_name=name,
                    enabled=enabled,
                    library_type=library_type,
                    created_at=now,
                    updated_at=now,
                )
            )

            conn.execute(
                self.library_items.insert(),
                [
                    {
                        "library_id": lib_id,
                        "item_order": idx,
                        "item_text": item,
                    }
                    for idx, item in enumerate(cleaned)
                ],
            )

        return self.get_library(lib_id)

    def update_library(
        self,
        library_id: str,
        name: Optional[str] = None,
        library_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        with self.engine.begin() as conn:
            target = self._get_library_by_id(conn, library_id)
            if not target:
                raise ValueError("词库不存在")

            updates: Dict[str, Any] = {}

            if name and name != target["name"]:
                if self._get_library_by_name(conn, name):
                    raise ValueError("词库名称已存在")
                updates["name"] = name
                updates["file_name"] = name

            if library_type is not None:
                self._validate_library_type(target["subject"], library_type)
                updates["library_type"] = library_type

            if updates:
                updates["updated_at"] = self._now()
                conn.execute(
                    self.libraries.update().where(self.libraries.c.id == library_id).values(**updates)
                )

        return self.get_library(library_id)

    def set_library_enabled(self, library_id: str, enabled: bool) -> Dict[str, Any]:
        with self.engine.begin() as conn:
            target = self._get_library_by_id(conn, library_id)
            if not target:
                raise ValueError("词库不存在")

            conn.execute(
                self.libraries.update()
                .where(self.libraries.c.id == library_id)
                .values(enabled=enabled, updated_at=self._now())
            )

        return self.get_library(library_id)

    def replace_library_items(self, library_id: str, items: List[str]) -> Dict[str, Any]:
        cleaned = self._clean_items(items)

        with self.engine.begin() as conn:
            target = self._get_library_by_id(conn, library_id)
            if not target:
                raise ValueError("词库不存在")

            conn.execute(
                self.library_items.delete().where(self.library_items.c.library_id == library_id)
            )
            conn.execute(
                self.library_items.insert(),
                [
                    {
                        "library_id": library_id,
                        "item_order": idx,
                        "item_text": item,
                    }
                    for idx, item in enumerate(cleaned)
                ],
            )
            conn.execute(
                self.libraries.update()
                .where(self.libraries.c.id == library_id)
                .values(updated_at=self._now())
            )

        return self.get_library(library_id)

    def get_enabled_library_names(self, subject: str, library_type: Optional[str] = None) -> List[str]:
        with self.engine.connect() as conn:
            conditions = [self.libraries.c.subject == subject, self.libraries.c.enabled.is_(True)]
            if library_type:
                typed_count = conn.execute(
                    select(func.count())
                    .select_from(self.libraries)
                    .where(
                        and_(
                            self.libraries.c.subject == subject,
                            self.libraries.c.enabled.is_(True),
                            self.libraries.c.library_type == library_type,
                        )
                    )
                ).scalar_one()
                if typed_count > 0:
                    conditions.append(self.libraries.c.library_type == library_type)

            rows = conn.execute(
                select(self.libraries.c.name)
                .where(and_(*conditions))
                .order_by(self.libraries.c.created_at.asc())
            ).scalars().all()
            return rows

    def resolve_enabled_library(
        self,
        subject: str,
        requested_library: Optional[str] = None,
        library_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        with self.engine.connect() as conn:
            if requested_library:
                target = self._get_library_by_name(conn, requested_library)
                if not target or target["subject"] != subject:
                    raise ValueError(f"词库不存在: {requested_library}")
                if not target["enabled"]:
                    raise ValueError(f"词库未启用: {requested_library}")
                if library_type and target.get("library_type") and target.get("library_type") != library_type:
                    raise ValueError(f"词库类型不匹配: {requested_library} 不支持 {library_type}")
                return self._library_with_count(conn, target)

            conditions = [self.libraries.c.subject == subject, self.libraries.c.enabled.is_(True)]
            enabled_rows = conn.execute(select(self.libraries).where(and_(*conditions)).order_by(self.libraries.c.created_at.asc())).mappings().all()
            if not enabled_rows:
                raise ValueError(f"{subject} 学科暂无启用词库")

            if library_type:
                typed = [x for x in enabled_rows if x.get("library_type") == library_type]
                if typed:
                    return self._library_with_count(conn, typed[0])

            return self._library_with_count(conn, enabled_rows[0])

    def get_random_library_items(self, file_name: str, count: int) -> List[str]:
        with self.engine.connect() as conn:
            lib = self._get_library_by_file_name(conn, file_name)
            if not lib:
                return []

            items = conn.execute(
                select(self.library_items.c.item_text)
                .where(self.library_items.c.library_id == lib["id"])
                .order_by(self.library_items.c.item_order.asc(), self.library_items.c.id.asc())
            ).scalars().all()

        if not items:
            return []

        safe_count = min(count, len(items))
        return random.sample(items, safe_count)

    def get_public_library_info(self, file_name: str) -> Dict[str, Any]:
        with self.engine.connect() as conn:
            lib = self._get_library_by_file_name(conn, file_name)
            if not lib:
                raise ValueError("词库不存在")
            total_words = conn.execute(
                select(func.count()).select_from(self.library_items).where(self.library_items.c.library_id == lib["id"])
            ).scalar_one()

        return {
            "name": file_name,
            "total_words": total_words,
            "is_cached": False,
            "file_path": f"db://{file_name}",
        }


_library_admin_service_instance: Optional[LibraryAdminService] = None


def get_library_admin_service() -> LibraryAdminService:
    global _library_admin_service_instance
    if _library_admin_service_instance is None:
        _library_admin_service_instance = LibraryAdminService()
    return _library_admin_service_instance
