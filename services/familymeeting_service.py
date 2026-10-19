"""Private, independently drafted family meetings; no AI or shared-schema migration."""

import base64
import hashlib
import hmac
import json
import math
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path


SCHEMA = json.loads((Path(__file__).resolve().parents[1] / "static/familymeeting/questions.json").read_text())
FIELDS = {field["id"]: field for section in SCHEMA["sections"] for field in section["fields"]}
PATH_IDS = {path["id"] for path in SCHEMA["paths"]}
STANCES = {stance["id"] for stance in SCHEMA["stances"]}
NOTE_KEYS = {"common", "differences", "unknowns", "direction", "conditions", "child_state", "next_action", "owner", "due_date", "review_date", "fallback"}
ROLES = ("owner", "dad", "mom")


class MeetingError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message
        super().__init__(message)


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def make_password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 260000).hex()
    return f"pbkdf2_sha256${salt}${digest}"


def verify_password(password, encoded):
    try:
        algorithm, salt, digest = encoded.split("$")
        if algorithm != "pbkdf2_sha256" or not salt or len(digest) != 64:
            return False
        return hmac.compare_digest(make_password_hash(password, salt), encoded)
    except (TypeError, ValueError):
        return False


class FamilyMeetingService:
    def __init__(self, database_path, unlock_hash=None):
        self.path = Path(database_path)
        self.unlock_hash = unlock_hash if unlock_hash is not None else os.environ.get("FAMILYMEETING_UNLOCK_HASH", "")

    @contextmanager
    def connection(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA foreign_keys=ON")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS family_meetings (
                    id TEXT PRIMARY KEY, secret TEXT NOT NULL, title TEXT NOT NULL,
                    meeting_date TEXT NOT NULL, created_at TEXT NOT NULL,
                    opened_at TEXT, notes TEXT NOT NULL DEFAULT '{}',
                    notes_revision INTEGER NOT NULL DEFAULT 0,
                    unlock_failures INTEGER NOT NULL DEFAULT 0,
                    locked_until REAL NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS family_meeting_answers (
                    meeting_id TEXT NOT NULL REFERENCES family_meetings(id) ON DELETE CASCADE,
                    role TEXT NOT NULL CHECK(role IN ('dad','mom')),
                    draft TEXT NOT NULL DEFAULT '{}', published TEXT,
                    revision INTEGER NOT NULL DEFAULT 0,
                    published_revision INTEGER, updated_at TEXT, submitted_at TEXT,
                    PRIMARY KEY(meeting_id, role)
                );
            """)
            os.chmod(self.path, 0o600)
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def token(meeting, role):
        return hmac.new(meeting["secret"].encode(), f"invite:{role}".encode(), hashlib.sha256).hexdigest()

    def authorize(self, db, meeting_id, token):
        meeting = db.execute("SELECT * FROM family_meetings WHERE id=?", (meeting_id,)).fetchone()
        if not meeting or not isinstance(token, str) or len(token) != 64 or any(c not in "0123456789abcdef" for c in token):
            raise MeetingError(403, "会议链接无效，请使用自己的专属链接。")
        for role in ROLES:
            if hmac.compare_digest(self.token(meeting, role), token):
                return meeting, role
        raise MeetingError(403, "会议链接无效，请使用自己的专属链接。")

    def create(self, title, meeting_date):
        title = str(title).strip()[:100] or "棒球家庭会议"
        try:
            date.fromisoformat(meeting_date)
        except (TypeError, ValueError):
            raise MeetingError(422, "请选择有效的会议日期。")
        meeting_id = secrets.token_urlsafe(18)
        with self.connection() as db:
            db.execute("INSERT INTO family_meetings(id,secret,title,meeting_date,created_at) VALUES(?,?,?,?,?)", (meeting_id, secrets.token_hex(32), title, meeting_date, utc_now()))
            db.executemany("INSERT INTO family_meeting_answers(meeting_id,role) VALUES(?,?)", [(meeting_id, role) for role in ("dad", "mom")])
            meeting = db.execute("SELECT * FROM family_meetings WHERE id=?", (meeting_id,)).fetchone()
            return self.access_payload(meeting)

    def access_payload(self, meeting):
        return {"id": meeting["id"], "title": meeting["title"], "meeting_date": meeting["meeting_date"], "tokens": {role: self.token(meeting, role) for role in ROLES}}

    def admin_access(self, meeting_id):
        with self.connection() as db:
            meeting = db.execute("SELECT * FROM family_meetings WHERE id=?", (meeting_id,)).fetchone()
            if not meeting:
                raise MeetingError(404, "会议不存在。")
            return self.access_payload(meeting)

    def list_meetings(self):
        with self.connection() as db:
            return [dict(row) for row in db.execute("SELECT id,title,meeting_date,created_at,opened_at FROM family_meetings ORDER BY created_at DESC,id DESC LIMIT 40")]

    def view_grant(self, meeting, role):
        payload = base64.urlsafe_b64encode(json.dumps({"role": role, "exp": int(time.time()) + 43200}, separators=(",", ":")).encode()).decode().rstrip("=")
        signature = hmac.new(meeting["secret"].encode(), f"view:{payload}".encode(), hashlib.sha256).hexdigest()
        return f"{payload}.{signature}"

    def has_view_grant(self, meeting, role, grant):
        try:
            payload, signature = grant.split(".")
            expected = hmac.new(meeting["secret"].encode(), f"view:{payload}".encode(), hashlib.sha256).hexdigest()
            decoded = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
            return bool(meeting["opened_at"] and hmac.compare_digest(signature, expected) and decoded["role"] == role and decoded["exp"] > time.time())
        except (AttributeError, KeyError, TypeError, ValueError):
            return False

    def state(self, meeting_id, token, grant=""):
        with self.connection() as db:
            meeting, role = self.authorize(db, meeting_id, token)
            unlocked = self.has_view_grant(meeting, role, grant)
            rows = db.execute("SELECT * FROM family_meeting_answers WHERE meeting_id=? ORDER BY role", (meeting_id,)).fetchall()
            answers = {}
            own = None
            for row in rows:
                ready = row["published"] is not None and row["published_revision"] == row["revision"]
                answers[row["role"]] = {"ready": ready, "submitted_at": row["submitted_at"], "has_submission": row["published"] is not None}
                if unlocked:
                    answers[row["role"]]["answers"] = json.loads(row["published"] or "{}")
                if row["role"] == role:
                    own = {"answers": json.loads(row["draft"]), "revision": row["revision"], "updated_at": row["updated_at"], "ready": ready}
            return {"id": meeting_id, "title": meeting["title"], "meeting_date": meeting["meeting_date"], "role": role, "own": own, "participants": answers, "can_open": all(a["ready"] for a in answers.values()) or bool(meeting["opened_at"]), "opened_at": meeting["opened_at"], "unlocked": unlocked, "notes": json.loads(meeting["notes"]) if unlocked else None, "notes_revision": meeting["notes_revision"] if unlocked else None}

    def clean_answers(self, answers):
        if not isinstance(answers, dict) or len(json.dumps(answers, ensure_ascii=False).encode()) > 100000:
            raise MeetingError(422, "答案格式不正确，或内容过长。")
        clean = {}
        for key, value in answers.items():
            field = FIELDS.get(key)
            if not field:
                raise MeetingError(422, "答案包含未识别的问题，请刷新页面后重试。")
            kind = field["type"]
            if value is None or value == "":
                continue
            if kind in {"text", "date", "select", "path_select"}:
                if not isinstance(value, str) or len(value) > 6000:
                    raise MeetingError(422, "单个答案最多填写6000字。")
                value = value.strip()
                if kind == "date" and value:
                    try:
                        date.fromisoformat(value)
                    except ValueError:
                        raise MeetingError(422, "日期格式不正确。")
                if kind == "select" and value not in field["options"]:
                    raise MeetingError(422, "请选择有效的选项。")
                if kind == "path_select" and value not in PATH_IDS | {"unknown"}:
                    raise MeetingError(422, "请选择有效的道路。")
            elif kind == "number":
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not field["min"] <= value <= field["max"]:
                    raise MeetingError(422, "请填写有效范围内的数字。")
            elif kind == "rank":
                if not isinstance(value, list) or len(value) > 3 or any(not isinstance(item, str) or item not in field["options"] for item in value) or len(set(value)) != len(value):
                    raise MeetingError(422, "请依次选择最多三个不同选项。")
            elif kind == "paths":
                if not isinstance(value, dict) or set(value) - PATH_IDS:
                    raise MeetingError(422, "道路选择格式不正确。")
                for item in value.values():
                    if not isinstance(item, dict) or set(item) - {"stance", "conditions"} or item.get("stance", "") not in STANCES | {""} or not isinstance(item.get("conditions", ""), str) or len(item.get("conditions", "")) > 3000:
                        raise MeetingError(422, "请检查道路态度和接受条件。")
            clean[key] = value
        return clean

    def save_answers(self, meeting_id, token, answers, revision, submit=False):
        clean = self.clean_answers(answers)
        if submit and not any(value not in (None, "", [], {}) for value in clean.values()):
            raise MeetingError(422, "至少记录一项想法后再提交；不确定的问题可以留空。")
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            meeting, role = self.authorize(db, meeting_id, token)
            if role == "owner":
                raise MeetingError(403, "请使用爸爸或妈妈的专属链接填写。")
            row = db.execute("SELECT * FROM family_meeting_answers WHERE meeting_id=? AND role=?", (meeting_id, role)).fetchone()
            if row["revision"] != revision:
                raise MeetingError(409, "另一台设备更新了这份答案。请先下载本机草稿备份，再刷新读取最新版本。")
            raw, now = json.dumps(clean, ensure_ascii=False), utc_now()
            if submit:
                db.execute("UPDATE family_meeting_answers SET draft=?,published=?,revision=revision+1,published_revision=revision+1,updated_at=?,submitted_at=? WHERE meeting_id=? AND role=?", (raw, raw, now, now, meeting_id, role))
            else:
                db.execute("UPDATE family_meeting_answers SET draft=?,revision=revision+1,updated_at=? WHERE meeting_id=? AND role=?", (raw, now, meeting_id, role))
            return {"revision": revision + 1, "updated_at": now, "ready": bool(submit)}

    def unlock(self, meeting_id, token, password):
        error = None
        result = None
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            meeting, role = self.authorize(db, meeting_id, token)
            if meeting["locked_until"] > time.time():
                raise MeetingError(429, "尝试次数较多，请三分钟后再试。")
            rows = db.execute("SELECT published,published_revision,revision FROM family_meeting_answers WHERE meeting_id=?", (meeting_id,)).fetchall()
            if not meeting["opened_at"] and (len(rows) != 2 or not all(r["published"] is not None and r["published_revision"] == r["revision"] for r in rows)):
                raise MeetingError(409, "双方各自提交后，才可以开始共同查看。")
            if not self.unlock_hash:
                raise MeetingError(503, "会议密码尚未配置，请联系网站管理员。")
            if not verify_password(password, self.unlock_hash):
                failures = meeting["unlock_failures"] + 1
                locked_until = time.time() + 180 if failures >= 5 else 0
                db.execute("UPDATE family_meetings SET unlock_failures=?,locked_until=? WHERE id=?", (0 if locked_until else failures, locked_until, meeting_id))
                error = MeetingError(403, "密码不正确，请重新输入。")
            else:
                opened_at = meeting["opened_at"] or utc_now()
                db.execute("UPDATE family_meetings SET opened_at=?,unlock_failures=0,locked_until=0 WHERE id=?", (opened_at, meeting_id))
                result = {"view_grant": self.view_grant(meeting, role), "opened_at": opened_at}
        if error:
            raise error
        return result

    def save_notes(self, meeting_id, token, grant, notes, revision):
        if not isinstance(notes, dict) or set(notes) - NOTE_KEYS:
            raise MeetingError(422, "会议记录格式不正确。")
        if any(not isinstance(value, str) or len(value) > 8000 for value in notes.values()):
            raise MeetingError(422, "单项会议记录最多填写8000字。")
        if notes.get("direction", "") not in PATH_IDS | {"", "undecided"} or notes.get("child_state", "") not in {"", "pending", "heard", "confirmed"}:
            raise MeetingError(422, "请选择有效的方向和孩子参与状态。")
        for field in ("due_date", "review_date"):
            if notes.get(field):
                try:
                    date.fromisoformat(notes[field])
                except ValueError:
                    raise MeetingError(422, "请填写有效日期。")
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            meeting, role = self.authorize(db, meeting_id, token)
            if not self.has_view_grant(meeting, role, grant):
                raise MeetingError(403, "请先输入密码，开始共同查看。")
            if meeting["notes_revision"] != revision:
                raise MeetingError(409, "另一台设备更新了会议记录。请先导出本机内容，再刷新后合并。")
            db.execute("UPDATE family_meetings SET notes=?,notes_revision=notes_revision+1 WHERE id=?", (json.dumps(notes, ensure_ascii=False), meeting_id))
            return {"notes_revision": revision + 1}


def get_familymeeting_service():
    from config import config
    return FamilyMeetingService(os.environ.get("FAMILYMEETING_DATABASE_PATH", str(Path(config.DATA_DIR) / "family-meetings.sqlite3")))
