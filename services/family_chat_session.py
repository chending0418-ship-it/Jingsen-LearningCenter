"""Opaque family sessions, separate from administrative access."""
import hashlib
import hmac
import secrets
import time

from fastapi import HTTPException, Request, Response

from config import config
from database import database_for_data_root


COOKIE = "jlc_family_chat"
TTL = 30 * 24 * 3600


def digest(token):
    # Changing the family password invalidates all previously issued tokens.
    return hmac.new(config.FAMILY_CHAT_PASSWORD.encode(), token.encode(), hashlib.sha256).hexdigest()


def login(request: Request, response: Response, password: str):
    if not config.FAMILY_CHAT_PASSWORD.strip():
        raise HTTPException(503, "家庭学习空间尚未设置口令")
    now = int(time.time())
    address = request.client.host if request.client else "local"
    ok = secrets.compare_digest(password.encode(), config.FAMILY_CHAT_PASSWORD.encode())
    with database_for_data_root().transaction() as db:
        db.execute("DELETE FROM chat_login_limits WHERE since <= ?", (now - 300,))
        attempts = db.execute("SELECT failures FROM chat_login_limits WHERE address=?", (address,)).fetchone()
        if attempts and attempts["failures"] >= 10:
            raise HTTPException(429, "尝试次数过多，请五分钟后再试")
        if ok:
            db.execute("DELETE FROM chat_login_limits WHERE address=?", (address,))
            db.execute("DELETE FROM chat_sessions WHERE expires<=?", (now,))
            token = secrets.token_urlsafe(32)
            db.execute("INSERT INTO chat_sessions VALUES(?,?)", (digest(token), now + TTL))
        else:
            db.execute("""INSERT INTO chat_login_limits VALUES(?,?,1)
                          ON CONFLICT(address) DO UPDATE SET failures=failures+1""", (address, now))
    if not ok:
        raise HTTPException(401, "家庭口令有误")
    response.set_cookie(COOKIE, token, max_age=TTL, httponly=True, samesite="strict",
                        secure=config.ADMIN_COOKIE_SECURE or request.url.scheme == "https")


def require_family(request: Request):
    token = request.cookies.get(COOKIE, "")
    if len(token) == 43 and config.FAMILY_CHAT_PASSWORD.strip():
        with database_for_data_root().read() as db:
            if db.execute("SELECT 1 FROM chat_sessions WHERE digest=? AND expires>?",
                          (digest(token), time.time())).fetchone():
                return
    raise HTTPException(401, "请输入家庭口令")


def logout(request: Request, response: Response):
    with database_for_data_root().transaction() as db:
        db.execute("DELETE FROM chat_sessions WHERE digest=?", (digest(request.cookies.get(COOKIE, "")),))
    response.delete_cookie(COOKIE, samesite="strict")
