import asyncio
import types

from database import GenerationJobRepository, SQLiteDatabase
from services.english_service import EnglishService
from services.generation_job_service import GenerationJobService
from services.vocabulary_skills_service import VocabularySkillsService


def make_job_service(tmp_path):
    database = SQLiteDatabase(tmp_path / "learning-center.sqlite3")
    return GenerationJobService(GenerationJobRepository(database), ttl_seconds=3600)


def test_generation_job_is_visible_across_repository_instances_and_supports_cursor(tmp_path):
    database_path = tmp_path / "learning-center.sqlite3"
    first = GenerationJobService(
        GenerationJobRepository(SQLiteDatabase(database_path)),
        ttl_seconds=3600,
    )
    created = first.create_job(
        kind="daily_word",
        requested_count=5,
        request={"count": 5, "mode": "cloze"},
        plan={"selected_words": ["a", "b", "c", "d", "e"]},
        metadata={"mode": "cloze"},
    )
    assert created["status"] == "queued"
    assert first.mark_generating(created["job_id"]) is True
    first.append_questions(created["job_id"], [{"answer": value} for value in ["a", "b", "c"]])

    second = GenerationJobService(
        GenerationJobRepository(SQLiteDatabase(database_path)),
        ttl_seconds=3600,
    )
    progress = second.get_job(created["job_id"], kind="daily_word", after=2)
    assert progress["status"] == "generating"
    assert progress["generated_count"] == 3
    assert progress["next_cursor"] == 3
    assert [item["answer"] for item in progress["questions"]] == ["c"]

    second.append_questions(created["job_id"], [{"answer": "d"}, {"answer": "e"}])
    completed = first.get_job(created["job_id"], kind="daily_word", after=3)
    assert completed["status"] == "completed"
    assert [item["answer"] for item in completed["questions"]] == ["d", "e"]


def test_generation_job_keeps_partial_questions_when_a_later_batch_fails(tmp_path):
    jobs = make_job_service(tmp_path)
    created = jobs.create_job(
        kind="vocabulary_skills",
        requested_count=10,
        request={"question_count": 10},
        plan={"selected_details": []},
    )
    jobs.mark_generating(created["job_id"])
    jobs.append_questions(created["job_id"], [{"question_id": value} for value in [1, 2, 3]])
    failed = jobs.mark_failed(created["job_id"], "later batch failed")

    assert failed["status"] == "partial_failed"
    assert failed["generated_count"] == 3
    assert failed["error"] == "later batch failed"
    assert len(failed["questions"]) == 3


def test_stale_generation_job_is_failed_instead_of_loading_forever(tmp_path):
    database = SQLiteDatabase(tmp_path / "learning-center.sqlite3")
    jobs = GenerationJobService(
        GenerationJobRepository(database),
        ttl_seconds=3600,
        stale_seconds=1,
    )
    created = jobs.create_job(
        kind="daily_word",
        requested_count=3,
        request={"count": 3},
        plan={"selected_words": ["a", "b", "c"]},
    )
    with database.transaction() as connection:
        connection.execute(
            "UPDATE generation_jobs SET updated_at='2000-01-01T00:00:00Z' WHERE id=?",
            (created["job_id"],),
        )

    failed = jobs.get_job(created["job_id"], kind="daily_word")
    assert failed["status"] == "failed"
    assert failed["error"] == "生成任务超时或服务已重启"


def test_daily_word_runner_uses_three_then_larger_batches(tmp_path):
    jobs = make_job_service(tmp_path)
    selected_words = [f"word-{index}" for index in range(10)]
    created = jobs.create_job(
        kind="daily_word",
        requested_count=10,
        request={"count": 10, "mode": "cloze"},
        plan={"selected_words": selected_words},
    )
    service = EnglishService.__new__(EnglishService)
    service.generation_job_service = jobs
    calls = []

    async def fake_batch(self, plan, start, count):
        calls.append((start, count))
        return [{"answer": word, "options": [word]} for word in plan["selected_words"][start:start + count]]

    service.generate_prepared_batch = types.MethodType(fake_batch, service)
    asyncio.run(service.run_generation_job(created["job_id"]))

    completed = jobs.get_job(created["job_id"], kind="daily_word")
    assert calls == [(0, 3), (3, 5), (8, 2)]
    assert completed["status"] == "completed"
    assert completed["generated_count"] == 10


def test_vocabulary_runner_assigns_global_question_ids_across_batches(tmp_path):
    jobs = make_job_service(tmp_path)
    request = {
        "grade_level": "Grade 6",
        "topic": "Vocabulary",
        "skill": "Prefixes and suffixes",
        "difficulty": "medium",
        "question_count": 10,
        "option_count": 4,
        "include_explanation": True,
    }
    created = jobs.create_job(
        kind="vocabulary_skills",
        requested_count=10,
        request=request,
        plan={"selected_details": [{"id": "detail-1", "detail": "Use prefixes"}]},
    )
    service = VocabularySkillsService.__new__(VocabularySkillsService)
    service.generation_job_service = jobs
    calls = []

    async def fake_batch(self, request_model, plan, start, count):
        calls.append((start, count))
        return [{"question_id": start + offset + 1} for offset in range(count)]

    service.generate_prepared_batch = types.MethodType(fake_batch, service)
    asyncio.run(service.run_generation_job(created["job_id"]))

    completed = jobs.get_job(created["job_id"], kind="vocabulary_skills")
    assert calls == [(0, 3), (3, 5), (8, 2)]
    assert completed["status"] == "completed"
    assert [item["question_id"] for item in completed["questions"]] == list(range(1, 11))


def test_daily_word_generation_job_api_returns_job_then_supports_polling(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    import api.english as english_api
    from main import app

    jobs = make_job_service(tmp_path)

    class FakeEnglishService:
        @staticmethod
        def prepare_generation_job(count, library, mode):
            return {
                "mode": mode,
                "library_name": library or "Test Library",
                "library_file_name": "test-library",
                "selected_words": [f"word-{index}" for index in range(count)],
            }

        @staticmethod
        async def run_generation_job(job_id):
            jobs.mark_generating(job_id)
            jobs.append_questions(
                job_id,
                [
                    {
                        "sentence": f"Question {index}",
                        "options": ["A", "B", "C", "D"],
                        "answer": "A",
                    }
                    for index in range(5)
                ],
            )

    monkeypatch.setattr(english_api, "english_service", FakeEnglishService())
    monkeypatch.setattr(english_api, "generation_job_service", jobs)

    with TestClient(app) as client:
        created = client.post(
            "/api/english/generation-jobs",
            json={"count": 5, "mode": "cloze", "library": None},
        )
        assert created.status_code == 202
        job_id = created.json()["job_id"]

        polled = client.get(f"/learningcenter/api/english/generation-jobs/{job_id}?after=3")
        assert polled.status_code == 200
        payload = polled.json()
        assert payload["status"] == "completed"
        assert payload["generated_count"] == 5
        assert len(payload["questions"]) == 2
