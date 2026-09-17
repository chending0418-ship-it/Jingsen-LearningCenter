"""Transactional storage for ten-question math practice sessions."""

import json

from database.sqlite import SQLiteDatabase, _dump


class MathRepository:
    def __init__(self, database: SQLiteDatabase):
        self.database = database

    def create(self, session: dict, questions: list[dict]):
        if len(questions) != 10:
            raise ValueError("每次训练必须正好 10 道题")
        with self.database.transaction() as conn:
            conn.execute(
                "INSERT INTO math_sessions(id,access_token_hash,created_at) VALUES(?,?,?)",
                (session["id"], session["access_token_hash"], session["created_at"]),
            )
            conn.executemany(
                "INSERT INTO math_session_questions(id,session_id,position,question_json) VALUES(?,?,?,?)",
                [(q["id"], session["id"], q["position"], _dump(q)) for q in questions],
            )

    def get(self, session_id, connection=None):
        if connection is None:
            with self.database.read() as conn:
                return self.get(session_id, conn)
        row = connection.execute("SELECT * FROM math_sessions WHERE id=?", (session_id,)).fetchone()
        if not row:
            return None
        session = dict(row)
        session["questions"] = []
        for row in connection.execute("SELECT * FROM math_session_questions WHERE session_id=? ORDER BY position", (session_id,)):
            item = dict(row)
            question = json.loads(item.pop("question_json"))
            question.update(item)
            question["scratch"] = json.loads(question.pop("scratch_json"))
            raw_result = question.pop("result_json")
            question["result"] = json.loads(raw_result) if raw_result else None
            session["questions"].append(question)
        return session

    @staticmethod
    def save_hint(conn, question_id, hint_level):
        conn.execute("UPDATE math_session_questions SET hints_used=MAX(hints_used,?) WHERE id=? AND answered_at IS NULL",
                     (hint_level, question_id))

    @staticmethod
    def save_answer(conn, question_id, answer, scratch, result, now):
        conn.execute(
            "UPDATE math_session_questions SET student_answer=?,scratch_json=?,result_json=?,answered_at=? WHERE id=? AND answered_at IS NULL",
            (answer, _dump(scratch), _dump(result), now, question_id),
        )

    @staticmethod
    def complete(conn, session_id, correct, independent, now):
        conn.execute(
            "UPDATE math_sessions SET status='completed',completed_at=?,correct_count=?,independent_correct_count=? WHERE id=?",
            (now, correct, independent, session_id),
        )

    def list_sessions(self, limit=20, offset=0, status=None):
        clause = " WHERE s.status=?" if status else ""
        params = (status,) if status else ()
        with self.database.read() as conn:
            total = conn.execute("SELECT COUNT(*) FROM math_sessions s" + clause, params).fetchone()[0]
            rows = conn.execute(
                """SELECT s.id,s.status,s.question_count,s.created_at,s.completed_at,s.correct_count,s.independent_correct_count,
                          (SELECT COUNT(*) FROM math_session_questions q WHERE q.session_id=s.id AND q.answered_at IS NOT NULL) AS answered_count
                   FROM math_sessions s""" + clause + " ORDER BY s.created_at DESC,s.id DESC LIMIT ? OFFSET ?",
                (*params, limit, offset),
            ).fetchall()
            summary = dict(conn.execute(
                """SELECT COUNT(*) AS completed_sessions, COALESCE(SUM(question_count),0) AS total_questions,
                          COALESCE(SUM(correct_count),0) AS correct_count,
                          COALESCE(SUM(independent_correct_count),0) AS independent_correct_count
                   FROM math_sessions WHERE status='completed'"""
            ).fetchone())
        return {"sessions": [dict(row) for row in rows], "total": total, "limit": limit, "offset": offset, "summary": summary}
