"""Gallery metadata and persistent image asset management."""

from __future__ import annotations

import hashlib
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from config import config
from database import GalleryRepository, database_for_data_root


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class GalleryService:
    MAX_IMAGE_BYTES = 15 * 1024 * 1024
    CONTENT_TYPES = {
        "image/jpeg": ("jpg", b"\xff\xd8\xff"),
        "image/png": ("png", b"\x89PNG\r\n\x1a\n"),
        "image/webp": ("webp", b"RIFF"),
    }

    def __init__(self, data_dir: str | Path | None = None):
        self.data_dir = Path(data_dir or config.DATA_DIR).resolve()
        self.asset_dir = (
            self.data_dir / "gallery-assets"
            if data_dir is not None
            else Path(config.GALLERY_ASSET_DIR).resolve()
        )
        self.repository = GalleryRepository(database_for_data_root(self.data_dir))

    @staticmethod
    def _public_item(item: Dict[str, Any]) -> Dict[str, Any]:
        result = dict(item)
        result.pop("image_asset", None)
        result["image_url"] = f"/api/site/gallery/items/{item['id']}/image"
        return result

    def list_items(self) -> List[Dict[str, Any]]:
        return [self._public_item(item) for item in self.repository.read()]

    def create_item(
        self,
        content: bytes,
        content_type: str,
        *,
        title: str,
        caption: str,
        location: str,
        shot_date: str | None,
        alt: str,
    ) -> Dict[str, Any]:
        content_type = content_type.split(";", 1)[0].strip().lower()
        image_type = self.CONTENT_TYPES.get(content_type)
        if image_type is None:
            raise ValueError("仅支持 JPG、PNG 或 WebP 图片")
        if not content:
            raise ValueError("图片内容为空")
        if len(content) > self.MAX_IMAGE_BYTES:
            raise ValueError("单张图片不能超过 15MB")
        extension, signature = image_type
        if not content.startswith(signature) or (extension == "webp" and content[8:12] != b"WEBP"):
            raise ValueError("图片内容与文件类型不匹配")

        self.asset_dir.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(content).hexdigest()[:20]
        filename = f"gallery-{digest}.{extension}"
        destination = self.asset_dir / filename
        if not destination.exists():
            temporary = self.asset_dir / f".{filename}.{uuid.uuid4().hex}.tmp"
            try:
                with temporary.open("wb") as handle:
                    handle.write(content)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, destination)
            finally:
                if temporary.exists():
                    temporary.unlink()

        now = _utc_now()
        item = {
            "id": uuid.uuid4().hex,
            "title": title.strip(),
            "caption": caption.strip(),
            "location": location.strip(),
            "shot_date": shot_date or None,
            "alt": alt.strip(),
            "image_asset": filename,
            "mime_type": content_type,
            "created_at": now,
            "updated_at": now,
        }
        items = self.repository.read()
        items.insert(0, item)
        self.repository.write(items)
        return self._public_item(item)

    def update_item(self, item_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        items = self.repository.read()
        for item in items:
            if item.get("id") == item_id:
                for key in ("title", "caption", "location", "shot_date", "alt"):
                    if key in updates:
                        value = updates[key]
                        item[key] = value.strip() if isinstance(value, str) else value
                item["updated_at"] = _utc_now()
                self.repository.write(items)
                return self._public_item(item)
        raise ValueError("Gallery 内容不存在")

    def remove_item(self, item_id: str) -> Dict[str, Any]:
        items = self.repository.read()
        for index, item in enumerate(items):
            if item.get("id") == item_id:
                removed = items.pop(index)
                # The asset remains in data/gallery-assets for recovery and audit.
                self.repository.write(items)
                return self._public_item(removed)
        raise ValueError("Gallery 内容不存在")

    def image_path(self, item_id: str) -> Path:
        for item in self.repository.read():
            if item.get("id") != item_id:
                continue
            filename = item.get("image_asset")
            if not isinstance(filename, str) or filename != Path(filename).name:
                break
            candidate = self.asset_dir / filename
            if candidate.is_file():
                return candidate
            break
        raise ValueError("Gallery 图片不存在")


_gallery_service: GalleryService | None = None


def get_gallery_service() -> GalleryService:
    global _gallery_service
    if _gallery_service is None:
        _gallery_service = GalleryService()
    return _gallery_service
