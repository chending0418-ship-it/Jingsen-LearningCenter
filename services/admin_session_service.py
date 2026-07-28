"""现有 Admin 密码的服务端会话实现。"""

import base64
import hashlib
import hmac
import json
import time
from typing import Optional

from fastapi import HTTPException, Request, Response, status

from config import config


COOKIE_NAME = "jlc_admin_session"


def _secret() -> bytes:
    configured = config.ADMIN_SESSION_SECRET.strip()
    if configured:
        return configured.encode("utf-8")
    # 保持本地零配置可用；生产环境应通过 ADMIN_SESSION_SECRET 设置独立随机值。
    return hashlib.sha256(f"jlc-admin:{config.ADMIN_PASSWORD}".encode("utf-8")).digest()


def _encode(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    body = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    signature = hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{body}.{signature}"


def _decode(token: str) -> Optional[dict]:
    try:
        body, signature = token.rsplit(".", 1)
        expected = hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        padding = "=" * (-len(body) % 4)
        payload = json.loads(base64.urlsafe_b64decode(body + padding))
        if payload.get("scope") != "admin" or int(payload.get("exp", 0)) <= int(time.time()):
            return None
        return payload
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def verify_admin_password(password: str) -> bool:
    return hmac.compare_digest(password, config.ADMIN_PASSWORD)


def create_admin_session(response: Response) -> int:
    expires_at = int(time.time()) + max(1, config.ADMIN_SESSION_HOURS) * 3600
    response.set_cookie(
        key=COOKIE_NAME,
        value=_encode({"scope": "admin", "exp": expires_at}),
        max_age=max(1, config.ADMIN_SESSION_HOURS) * 3600,
        httponly=True,
        secure=config.ADMIN_COOKIE_SECURE,
        samesite="lax",
        path="/",
    )
    return expires_at


def clear_admin_session(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/", samesite="lax")


def is_admin_authenticated(request: Request) -> bool:
    token = request.cookies.get(COOKIE_NAME, "")
    return bool(token and _decode(token))


def require_admin_session(request: Request) -> None:
    if not is_admin_authenticated(request):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin 会话无效或已过期",
        )
