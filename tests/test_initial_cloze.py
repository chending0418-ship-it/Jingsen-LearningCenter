from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from config import config
from database import GenerationJobRepository, SQLiteDatabase
from services.generation_job_service import GenerationJobService
from services.initial_cloze_service import InitialClozeService
from services.library_admin_service import LibraryAdminService
from services.report_history_service import ReportHistoryService


BASE = "/learningcenter/api/english/initial-cloze"
PASSAGE = "An octopus can change its color to hide. It has eight arms and lives in the ocean."
WORDS = ["octopus", "ocean"]


class PassageGenerator:
    def __init__(self):
        self.reviews = [["octopus"], ["ocean"]]
        self.prompts = []

    async def generate_json(self, prompt, **options):
        self.prompts.append(prompt)
        if prompt.startswith("Solve"):
            assert all(word not in prompt for word in WORDS)
            return {"answers": self.reviews}
        return {"passage": PASSAGE}


@pytest.fixture
def practice(tmp_path, monkeypatch):
    database_path = tmp_path / "initial-cloze.sqlite3"
    monkeypatch.setenv("OPENAI_API_KEY", "offline-test-fixture")
    monkeypatch.setenv("SQLITE_DATABASE_PATH", str(database_path))
    monkeypatch.setattr(config, "OPENAI_API_KEY", "offline-test-fixture")
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    from api import admin, english, report_history
    from main import app

    jobs = GenerationJobService(GenerationJobRepository(SQLiteDatabase(database_path)))
    libraries = LibraryAdminService()
    generator = PassageGenerator()
    monkeypatch.setattr(english, "generation_job_service", jobs)
    monkeypatch.setattr(admin, "library_admin_service", libraries)
    monkeypatch.setattr(english.english_service, "library_admin_service", libraries)
    monkeypatch.setattr(english.english_service, "ai_generator", generator)
    monkeypatch.setattr(report_history, "report_history_service", ReportHistoryService())
    with TestClient(app) as client:
        assert client.post("/api/admin/session", json={"password": config.ADMIN_PASSWORD}).status_code == 200
        response = client.post("/api/admin/libraries", json={
            "name": "Sea Life", "subject": "english", "items": WORDS + ["Octopus", "sea level"],
        })
        assert response.status_code == 200
        yield client, jobs, generator


def start(client, count=2):
    return client.post(f"{BASE}/jobs", json={"library": "Sea Life", "count": count})


def test_shared_library_to_passage_to_daily_report(practice):
    client, jobs, generator = practice
    assert client.post("/api/admin/word-matching/banks", json={
        "name": "Matching Only", "pairs_text": "atlas,map book\nviolin,string instrument",
    }).status_code == 201
    assert client.get("/api/english/libraries").json() == ["Sea Life"]
    assert client.get(f"{BASE}/capacity", params={"library": "Sea Life"}).json() == {"max_blanks": 2}
    assert client.get(f"{BASE}/capacity", params={"library": "Matching Only"}).status_code == 400
    assert start(client, 3).status_code == 400
    assert start(client, 21).status_code == 422
    assert not generator.prompts

    created = start(client)
    assert created.status_code == 202
    assert created.json()["status"] == "queued"
    assert all(word not in created.text for word in WORDS)
    job_id = created.json()["job_id"]
    response = client.get(f"{BASE}/jobs/{job_id}")
    assert response.status_code == 200
    job = response.json()
    assert job["status"] == "completed"
    assert job["metadata"] == {"library": "Sea Life", "blank_count": 2}
    assert all(word not in response.text for word in WORDS)
    assert len(generator.prompts) == 2
    question, = job["questions"]
    assert question["segments"] == ["An ", " can change its color to hide. It has eight arms and lives in the ", "."]
    assert [set(blank) for blank in question["blanks"]] == [{"id", "initial"}] * 2
    assert [blank["initial"] for blank in question["blanks"]] == ["o", "o"]
    first, second = (blank["id"] for blank in question["blanks"])
    assert first != second

    url = f"{BASE}/jobs/{job_id}/grade"
    assert client.post(url, json={"answers": {first: "octopus"}}).status_code == 400
    answers = {first: " OCTOPUS ", second: "oasis"}
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: client.post(url, json={"answers": answers}), range(2)))
    assert all(response.status_code == 200 for response in responses)
    report = responses[0].json()
    assert report == responses[1].json()
    assert report["correct_count"] == 1 and report["total_count"] == 2
    assert report["question_results"] == [
        {"blank_id": 1, "user_answer": "OCTOPUS", "correct_answer": "octopus", "is_correct": True},
        {"blank_id": 2, "user_answer": "oasis", "correct_answer": "ocean", "is_correct": False},
    ]
    history = client.get("/api/reports/history?module=initial_cloze").json()
    assert history["reports"] == [report]
    assert history["daily"][0]["sessions"] == 1
    assert client.get(f"/api/english/generation-jobs/{job_id}").status_code == 404

    jobs.repository.cleanup_expired("9999-01-01T00:00:00Z")
    assert client.post(url, json={"answers": answers}).json() == report


def test_ambiguity_or_wrong_answer_never_publishes_passage(practice):
    client, _, generator = practice
    generator.reviews = [["octopus"], ["ocean", "outdoors"]]
    job_id = start(client).json()["job_id"]
    job = client.get(f"{BASE}/jobs/{job_id}").json()
    assert job["status"] == "failed"
    assert job["questions"] == []
    assert len(generator.prompts) == 4
    assert client.post(f"{BASE}/jobs/{job_id}/grade", json={"answers": {}}).status_code == 404
    assert not client.get("/api/reports/history?module=initial_cloze").json()["reports"]


@pytest.mark.parametrize("passage", [
    "An octopus lives in the ocean. The octopus has eight arms.",
    "It has eight arms and lives in the ocean.",
    "There is an octopus in the ocean, next to [[3]].",
    "There is an octopus in the ocean, next to another OCTOPUS.",
    "An octopus-shaped rock sat in the ocean.",
    "An octopus in the ocean floated past an ocean-going ship.",
    {"text": PASSAGE},
])
def test_invalid_drafts_cannot_leak_words_or_change_the_blank_count(passage):
    assert InitialClozeService._mask_passage(passage, WORDS) is None


def test_expired_passage_cannot_create_a_report(practice):
    client, jobs, _ = practice
    job_id = start(client).json()["job_id"]
    with jobs.repository.database.transaction() as connection:
        connection.execute("UPDATE generation_jobs SET expires_at='2000-01-01T00:00:00Z' WHERE id=?", (job_id,))
    assert client.post(f"{BASE}/jobs/{job_id}/grade", json={"answers": {}}).status_code == 404
    assert not client.get("/api/reports/history?module=initial_cloze").json()["reports"]
