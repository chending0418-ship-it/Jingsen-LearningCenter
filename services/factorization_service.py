"""Math training with immutable first submissions and durable parent reports."""

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from database import database_for_data_root
from database.math import MathRepository
from services.factorization_engine import generate_questions, grade_answer


class MathSessionNotFound(ValueError):
    pass


class MathSubmissionConflict(ValueError):
    pass


def _now():
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")


class FactorizationService:
    def __init__(self, data_root=None):
        self.database = database_for_data_root(data_root)
        self.repository = MathRepository(self.database)

    @staticmethod
    def _authorize(session, token):
        if not session or not hmac.compare_digest(session["access_token_hash"], hashlib.sha256(token.encode()).hexdigest()):
            raise MathSessionNotFound("训练不存在或访问凭证无效")

    def start_session(self):
        token = secrets.token_urlsafe(32)
        row = {"id": str(uuid.uuid4()), "created_at": _now(), "access_token_hash": hashlib.sha256(token.encode()).hexdigest()}
        self.repository.create(row, generate_questions())
        result = self.get_session(row["id"], token)
        result["access_token"] = token
        return result

    @staticmethod
    def _view(session, admin=False):
        result = {key: value for key, value in session.items() if key not in ("access_token_hash", "questions")}
        result["questions"] = []
        for question in session["questions"]:
            item = {key: question[key] for key in ("id", "position", "expression", "is_challenge", "hints_used", "student_answer", "scratch", "answered_at", "result")}
            item["visible_hints"] = question["hints"][:question["hints_used"]]
            item["hint_count"] = len(question["hints"])
            if admin or question["answered_at"]:
                item.update({key: question[key] for key in ("skill", "skill_label", "correct_answer", "solution_steps")})
            result["questions"].append(item)
        answers = [q for q in result["questions"] if q["answered_at"]]
        result["answered_count"] = len(answers)
        result["correct_count"] = sum(bool(q["result"]["correct"]) for q in answers)
        result["independent_correct_count"] = sum(bool(q["result"]["correct"]) and q["hints_used"] == 0 for q in answers)
        result["accuracy"] = round(result["correct_count"] / 10 * 100) if session["status"] == "completed" else None
        result["independent_accuracy"] = round(result["independent_correct_count"] / 10 * 100) if session["status"] == "completed" else None
        return result

    def get_session(self, session_id, token):
        session = self.repository.get(session_id)
        self._authorize(session, token)
        return self._view(session)

    def get_admin_session(self, session_id):
        session = self.repository.get(session_id)
        if not session:
            raise MathSessionNotFound("训练记录不存在")
        return self._view(session, admin=True)

    def list_sessions(self, limit=20, offset=0, status=None):
        result = self.repository.list_sessions(limit, offset, status)
        for session in result["sessions"]:
            session["accuracy"] = session["correct_count"] * 10 if session["status"] == "completed" else None
        summary = result["summary"]
        summary["accuracy"] = round(summary["correct_count"] / summary["total_questions"] * 100, 1) if summary["total_questions"] else None
        summary["incorrect_count"] = summary["total_questions"] - summary["correct_count"]
        return result

    @staticmethod
    def _question(session, question_id):
        question = next((q for q in session["questions"] if q["id"] == question_id), None)
        if not question:
            raise MathSessionNotFound("题目不存在")
        return question

    @staticmethod
    def _require_current(session, question):
        current = next((q for q in session["questions"] if not q["answered_at"]), None)
        if not current or current["id"] != question["id"]:
            raise MathSubmissionConflict("请先完成当前题目")

    def reveal_hint(self, session_id, token, question_id, level):
        with self.database.transaction() as conn:
            session = self.repository.get(session_id, conn)
            self._authorize(session, token)
            question = self._question(session, question_id)
            if question["answered_at"]:
                return self._view(session)
            self._require_current(session, question)
            if level > len(question["hints"]) or level > question["hints_used"] + 1:
                raise ValueError("请按顺序查看提示")
            self.repository.save_hint(conn, question_id, level)
            return self._view(self.repository.get(session_id, conn))

    def answer_question(self, session_id, token, question_id, answer, scratch=None, skipped=False):
        answer = answer.strip()
        scratch = scratch or []
        with self.database.transaction() as conn:
            session = self.repository.get(session_id, conn)
            self._authorize(session, token)
            question = self._question(session, question_id)
            if question["answered_at"]:
                same = (question["student_answer"] == answer and question["scratch"] == scratch
                        and (question["result"]["error_code"] == "skipped") == skipped)
                if not same:
                    raise MathSubmissionConflict("本题首次答案已保存，不能覆盖历史记录")
                return self._view(session)
            self._require_current(session, question)
            result = grade_answer(question, answer, skipped)
            now = _now()
            self.repository.save_answer(conn, question_id, answer, scratch, result, now)
            session = self.repository.get(session_id, conn)
            if all(q["answered_at"] for q in session["questions"]):
                correct = sum(q["result"]["correct"] for q in session["questions"])
                independent = sum(q["result"]["correct"] and q["hints_used"] == 0 for q in session["questions"])
                self.repository.complete(conn, session_id, correct, independent, now)
                session = self.repository.get(session_id, conn)
            return self._view(session)


_service = None


def get_factorization_service():
    global _service
    if _service is None:
        _service = FactorizationService()
    return _service
