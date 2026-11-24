"""The family shares one workspace. Each turn keeps its question and reply together."""
import time
from uuid import uuid4

from fastapi import HTTPException

from database import database_for_data_root


# Bound gateway cost while preserving the complete transcript in SQLite.
HISTORY_CHARS = 32000
STREAM_SECONDS = 90
STALE_SECONDS = STREAM_SECONDS + 30
SYSTEM_MESSAGE = "你是家庭学习助手。使用学生提问的语言，以清晰、适龄的方式帮助学生理解。需要排版时使用 Markdown，行内公式用 $…$，独立公式用 $$…$$。"


def workspace():
    with database_for_data_root().read() as db:
        projects = db.execute("SELECT * FROM chat_projects ORDER BY name, id")
        threads = db.execute("SELECT * FROM chat_threads ORDER BY updated_at DESC, rowid DESC")
        return {"projects": [dict(p) for p in projects], "threads": [dict(t) for t in threads]}


def save_project(project_id, name, instructions, *, create):
    with database_for_data_root().transaction() as db:
        if create:
            db.execute("INSERT INTO chat_projects VALUES(?,?,?)", (project_id, name, instructions))
        elif not db.execute("UPDATE chat_projects SET name=?, instructions=? WHERE id=?",
                            (name, instructions, project_id)).rowcount:
            raise HTTPException(404, "找不到项目")
    return {"id": project_id, "name": name, "instructions": instructions}


def check_project(db, project_id):
    if project_id and not db.execute("SELECT 1 FROM chat_projects WHERE id=?", (project_id,)).fetchone():
        raise HTTPException(404, "找不到项目")


def update_thread(thread_id, title, project_id):
    with database_for_data_root().transaction() as db:
        check_project(db, project_id)
        if not db.execute("UPDATE chat_threads SET title=?, project_id=? WHERE id=?",
                          (title, project_id, thread_id)).rowcount:
            raise HTTPException(404, "找不到对话")


def expire_pending(db, thread_id):
    db.execute("""UPDATE chat_turns SET status='failed'
                  WHERE thread_id=? AND status='pending' AND started_at < ?""",
               (thread_id, time.time() - STALE_SECONDS))


def transcript(thread_id):
    with database_for_data_root().transaction() as db:
        thread = db.execute("SELECT * FROM chat_threads WHERE id=?", (thread_id,)).fetchone()
        if not thread:
            raise HTTPException(404, "找不到对话")
        expire_pending(db, thread_id)
        rows = db.execute("SELECT id, question, answer, status FROM chat_turns WHERE thread_id=? ORDER BY rowid",
                          (thread_id,))
        return {**dict(thread), "turns": [dict(row) for row in rows]}


def start_turn(thread_id, turn_id, question, project_id, create_thread):
    """Reserve before gateway I/O, replay completed requests, fence retries by attempt."""
    now = int(time.time())
    with database_for_data_root().transaction() as db:
        thread = db.execute("SELECT project_id FROM chat_threads WHERE id=?", (thread_id,)).fetchone()
        if not thread:
            if not create_thread:
                raise HTTPException(404, "找不到对话")
            check_project(db, project_id)
            db.execute("INSERT INTO chat_threads VALUES(?,?,?,?)",
                       (thread_id, " ".join(question.split())[:36], project_id, now))
        else:
            project_id = thread["project_id"]
        expire_pending(db, thread_id)
        prior = db.execute("SELECT * FROM chat_turns WHERE id=?", (turn_id,)).fetchone()
        if prior:
            if prior["thread_id"] != thread_id or prior["question"] != question:
                raise HTTPException(409, "这次提问的标识已使用")
            if prior["status"] == "done":
                return None, prior["answer"]
        if db.execute("SELECT 1 FROM chat_turns WHERE thread_id=? AND status='pending'", (thread_id,)).fetchone():
            raise HTTPException(409, "这段对话正在生成回复，请稍后再发")
        attempt = uuid4().hex
        if prior:
            last = db.execute("SELECT id FROM chat_turns WHERE thread_id=? ORDER BY rowid DESC LIMIT 1",
                              (thread_id,)).fetchone()
            if last["id"] != turn_id:
                raise HTTPException(409, "只能重试最近一次提问")
            db.execute("UPDATE chat_turns SET status='pending', answer='', started_at=?, attempt=? WHERE id=?",
                       (now, attempt, turn_id))
        else:
            db.execute("""INSERT INTO chat_turns(id,thread_id,question,status,started_at,attempt)
                          VALUES(?,?,?,'pending',?,?)""", (turn_id, thread_id, question, now, attempt))
        db.execute("UPDATE chat_threads SET updated_at=? WHERE id=?", (now, thread_id))

        project = db.execute("SELECT instructions FROM chat_projects WHERE id=?", (project_id,)).fetchone()
        system = SYSTEM_MESSAGE
        if project and project["instructions"]:
            system += "\n本项目的学习指令：\n" + project["instructions"]
        remaining = HISTORY_CHARS - len(system) - len(question)
        history = []
        for row in db.execute("""SELECT question, answer FROM chat_turns
                                 WHERE thread_id=? AND status='done' ORDER BY rowid DESC""", (thread_id,)):
            remaining -= len(row["question"]) + len(row["answer"])
            if remaining < 0:
                break
            history.append(row)
        messages = [{"role": "system", "content": system}]
        for row in reversed(history):
            messages.extend([{"role": "user", "content": row["question"]},
                             {"role": "assistant", "content": row["answer"]}])
        messages.append({"role": "user", "content": question})
        return attempt, messages


def finish_turn(turn_id, attempt, answer, status):
    with database_for_data_root().transaction() as db:
        db.execute("""UPDATE chat_turns SET answer=?, status=?
                      WHERE id=? AND attempt=? AND status='pending'""", (answer, status, turn_id, attempt))
