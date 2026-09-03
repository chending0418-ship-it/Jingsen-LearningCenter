"""Public homepage settings and replaceable hero asset management."""

from __future__ import annotations

import hashlib
import os
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from config import config
from database import HomepageSettingsRepository, database_for_data_root


DEFAULT_HOMEPAGE_SETTINGS: Dict[str, Any] = {
    "profile_label": "JINGSEN.CC / PERSONAL INDEX",
    "headline": "Curious by nature.\nAlways in motion.",
    "introduction": (
        "A growing collection of what I’m learning, what I’m seeing, "
        "and how I play the game."
    ),
    "ticker": "LEARN SOMETHING / SEE SOMETHING / PLAY SOMETHING / REPEAT ↗",
    "note": "LEARNING · MAKING · PLAYING",
    "hero_alt": "Notebook, camera and baseball arranged in a modern studio still life",
    "sections": [
        {
            "key": "learning",
            "eyebrow": "01 / STUDY",
            "title": "Learning Center",
            "description": "Practice, build momentum, and make progress visible—one session at a time.",
            "href": "/learningcenter",
            "action": "Start learning",
        },
        {
            "key": "gallery",
            "eyebrow": "02 / SEE",
            "title": "Gallery",
            "description": "Frames, places, details, and the small things worth keeping.",
            "href": "/gallery",
            "action": "View the archive",
        },
        {
            "key": "baseball",
            "eyebrow": "03 / PLAY",
            "title": "Baseball",
            "description": "Training notes, game-day energy, and a lifelong love of the diamond.",
            "href": "/baseball",
            "action": "Enter the field",
        },
    ],
    "hero_asset": None,
    "updated_at": None,
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class HomepageService:
    MAX_HERO_BYTES = 10 * 1024 * 1024
    CONTENT_TYPES = {
        "image/jpeg": ("jpg", b"\xff\xd8\xff"),
        "image/png": ("png", b"\x89PNG\r\n\x1a\n"),
        "image/webp": ("webp", b"RIFF"),
    }

    def __init__(self, data_dir: str | Path | None = None):
        self.data_dir = Path(data_dir or config.DATA_DIR).resolve()
        self.asset_dir = self.data_dir / "homepage-assets"
        self.repository = HomepageSettingsRepository(database_for_data_root(self.data_dir))

    def get_settings(self) -> Dict[str, Any]:
        saved = self.repository.read()
        result = deepcopy(DEFAULT_HOMEPAGE_SETTINGS)
        for key in ("profile_label", "headline", "introduction", "ticker", "note", "hero_alt", "updated_at"):
            if saved.get(key) is not None:
                result[key] = saved[key]
        if isinstance(saved.get("sections"), list) and len(saved["sections"]) == 3:
            result["sections"] = saved["sections"]
        asset = saved.get("hero_asset")
        if isinstance(asset, str) and asset == Path(asset).name and (self.asset_dir / asset).is_file():
            result["hero_asset"] = asset
        result["hero_url"] = f"/api/site/homepage/hero?v={result['updated_at'] or 'default'}"
        return result

    def update_settings(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        current = self.get_settings()
        updated = {**payload, "hero_asset": current.get("hero_asset"), "updated_at": _utc_now()}
        self.repository.write(updated)
        return self.get_settings()

    def save_hero(self, content: bytes, content_type: str) -> Dict[str, Any]:
        content_type = content_type.split(";", 1)[0].strip().lower()
        image_type = self.CONTENT_TYPES.get(content_type)
        if image_type is None:
            raise ValueError("仅支持 JPG、PNG 或 WebP 图片")
        if not content:
            raise ValueError("图片内容为空")
        if len(content) > self.MAX_HERO_BYTES:
            raise ValueError("图片不能超过 10MB")
        extension, signature = image_type
        if not content.startswith(signature) or (extension == "webp" and content[8:12] != b"WEBP"):
            raise ValueError("图片内容与文件类型不匹配")

        self.asset_dir.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(content).hexdigest()[:16]
        filename = f"homepage-hero-{digest}.{extension}"
        destination = self.asset_dir / filename
        temporary = self.asset_dir / f".{filename}.tmp"
        with temporary.open("wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)

        current = self.get_settings()
        current.pop("hero_url", None)
        current["hero_asset"] = filename
        current["updated_at"] = _utc_now()
        self.repository.write(current)
        return self.get_settings()

    def reset_hero(self) -> Dict[str, Any]:
        current = self.get_settings()
        current.pop("hero_url", None)
        current["hero_asset"] = None
        current["updated_at"] = _utc_now()
        self.repository.write(current)
        return self.get_settings()

    def hero_path(self) -> Path:
        settings = self.get_settings()
        asset = settings.get("hero_asset")
        if asset:
            candidate = self.asset_dir / asset
            if candidate.is_file():
                return candidate
        return Path(__file__).resolve().parents[1] / "static" / "assets" / "homepage-hero.webp"


_homepage_service: HomepageService | None = None


def get_homepage_service() -> HomepageService:
    global _homepage_service
    if _homepage_service is None:
        _homepage_service = HomepageService()
    return _homepage_service
