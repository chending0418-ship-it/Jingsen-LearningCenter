"""Word banks, server-side matching, and one Daily Report per completed attempt."""

import json
import random
import time
import unicodedata
from datetime import datetime
from uuid import uuid4

from database import ReportRepository, SQLiteDatabase


MAX_PAIRS = 50
ATTEMPT_TTL_SECONDS = 24 * 60 * 60
MODULE = "word_matching"


def _normalized(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _parse_pairs(text: str) -> list[tuple[str, str]]:
    pairs = []
    words = set()
    meanings = set()
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        word, _, meaning = line.partition(",")
        word, meaning = word.strip(), meaning.strip()
        if not word or not meaning:
            raise ValueError(f"第 {number} 行需要填写单词和释义，格式为 word,meaning。")
        if len(word) > 100 or len(meaning) > 300:
            raise ValueError(f"第 {number} 行超长。单词最多 100 字符，释义最多 300 字符。")
        word_key, meaning_key = _normalized(word), _normalized(meaning)
        if word_key in words or meaning_key in meanings:
            raise ValueError(f"第 {number} 行的单词或释义重复。每个单词和释义只能出现一次。")
        words.add(word_key)
        meanings.add(meaning_key)
        pairs.append((word, meaning))
    if not 2 <= len(pairs) <= MAX_PAIRS:
        raise ValueError(f"每组词库需要 2 至 {MAX_PAIRS} 对单词和释义。")
    return pairs


class WordMatchingService:
    def __init__(self, database: SQLiteDatabase):
        self.database = database
        self.reports = ReportRepository(database)

    def list_banks(self) -> list[dict]:
        with self.database.read() as connection:
            rows = connection.execute("SELECT id, name, pairs_json FROM word_matching_banks ORDER BY name_key")
            return [
                {"id": row["id"], "name": row["name"], "pair_count": len(json.loads(row["pairs_json"]))}
                for row in rows
            ]

    def get_bank(self, bank_id: str) -> dict:
        with self.database.read() as connection:
            row = connection.execute(
                "SELECT name, pairs_json FROM word_matching_banks WHERE id=?", (bank_id,)
            ).fetchone()
        if row is None:
            raise LookupError("这组词库不存在。")
        return {
            "id": bank_id,
            "name": row["name"],
            "pairs_text": "\n".join(f"{word},{meaning}" for word, meaning in json.loads(row["pairs_json"])),
        }

    def save_bank(self, name: str, pairs_text: str, bank_id: str | None = None) -> dict:
        name = name.strip()
        if not name:
            raise ValueError("请输入词库名称。")
        pairs = _parse_pairs(pairs_text)
        name_key = _normalized(name)
        pairs_json = json.dumps(pairs, ensure_ascii=False)
        with self.database.transaction() as connection:
            duplicate = connection.execute(
                "SELECT id FROM word_matching_banks WHERE name_key=?", (name_key,)
            ).fetchone()
            if duplicate is not None and duplicate["id"] != bank_id:
                raise ValueError("已有同名词库。请选择该词库进行编辑，或换一个名称。")
            if bank_id is None:
                bank_id = uuid4().hex
                connection.execute(
                    "INSERT INTO word_matching_banks(id,name,name_key,pairs_json) VALUES(?,?,?,?)",
                    (bank_id, name, name_key, pairs_json),
                )
            elif not connection.execute(
                "UPDATE word_matching_banks SET name=?,name_key=?,pairs_json=? WHERE id=?",
                (name, name_key, pairs_json, bank_id),
            ).rowcount:
                raise LookupError("这组词库不存在。")
        return {"id": bank_id, "name": name, "pair_count": len(pairs)}

    def start_attempt(self, bank_id: str) -> dict:
        attempt_id = uuid4().hex
        now = int(time.time())
        with self.database.transaction() as connection:
            bank = connection.execute(
                "SELECT name, pairs_json FROM word_matching_banks WHERE id=?", (bank_id,)
            ).fetchone()
            if bank is None:
                raise LookupError("This word bank is no longer available. Choose another bank.")
            pairs = json.loads(bank["pairs_json"])
            random.shuffle(pairs)
            options = [{"id": str(index), "word": word} for index, (word, _) in enumerate(pairs, 1)]
            meanings = [{"answer_id": str(index), "meaning": meaning} for index, (_, meaning) in enumerate(pairs, 1)]
            random.shuffle(meanings)
            questions = [{"id": str(index), **item} for index, item in enumerate(meanings, 1)]
            snapshot = {"bank_name": bank["name"], "options": options, "questions": questions}
            connection.execute("DELETE FROM word_matching_attempts WHERE expires_at<=?", (now,))
            connection.execute(
                "INSERT INTO word_matching_attempts(id,snapshot_json,expires_at) VALUES(?,?,?)",
                (attempt_id, json.dumps(snapshot, ensure_ascii=False), now + ATTEMPT_TTL_SECONDS),
            )
        return {
            "id": attempt_id,
            "bank_name": snapshot["bank_name"],
            "options": options,
            "questions": [{"id": item["id"], "meaning": item["meaning"]} for item in questions],
        }

    def grade_attempt(self, attempt_id: str, answers: dict[str, str]) -> dict:
        with self.database.transaction() as connection:
            existing = self.reports.get(attempt_id, connection)
            if existing and existing["module"] == MODULE:
                return existing
            attempt = connection.execute(
                "SELECT snapshot_json FROM word_matching_attempts WHERE id=? AND expires_at>?",
                (attempt_id, int(time.time())),
            ).fetchone()
            if attempt is None:
                raise LookupError("This practice has expired. Start a new round to try again.")
            snapshot = json.loads(attempt["snapshot_json"])
            questions = snapshot["questions"]
            words = {item["id"]: item["word"] for item in snapshot["options"]}
            if set(answers) != {item["id"] for item in questions} or set(answers.values()) != set(words):
                raise ValueError("Match each meaning with a different word before submitting.")

            results = []
            for item in questions:
                answer = answers[item["id"]]
                results.append({
                    "question_id": item["id"],
                    "meaning": item["meaning"],
                    "user_answer": words[answer],
                    "correct_answer": words[item["answer_id"]],
                    "is_correct": answer == item["answer_id"],
                })
            correct = sum(item["is_correct"] for item in results)
            now = datetime.now()
            report = {
                "id": attempt_id,
                "created_at": now.isoformat(timespec="seconds"),
                "date": now.date().isoformat(),
                "module": MODULE,
                "module_label": "Word Matching",
                "title": snapshot["bank_name"],
                "total_count": len(results),
                "correct_count": correct,
                "accuracy": f"{round(correct / len(results) * 100)}%",
                "question_results": results,
            }
            self.reports.append(report, connection)
            connection.execute("DELETE FROM word_matching_attempts WHERE id=?", (attempt_id,))
            return report
