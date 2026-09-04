import asyncio
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import api.reading as reading_api
from core.ai_generator import AIGenerator
from main import app
from services.reading_service import ReadingService


class FakeReader:
    outline = []


class FakeAI:
    async def generate_json(self, prompt, **_kwargs):
        if "Detect the chapter starts" in prompt:
            return {"chapters": []}
        if "Create " in prompt and "comprehension questions" in prompt:
            return {
                "questions": [
                    {
                        "question_text": f"What did you notice in moment {index + 1}?",
                        "question_type": "inference" if index % 2 else "recall",
                        "purpose": "Explain an idea using the story.",
                        "reference_answer": "A grounded explanation from the selected chapter.",
                        "evidence": [{"page": 1, "excerpt": "Chapter One"}],
                    }
                    for index in range(6)
                ]
            }
        if "gentle follow-up" in prompt:
            return {
                "feedback": "That extra detail makes your idea clear.",
                "understanding_level": "clear",
                "parent_note": "Used a relevant story detail after prompting.",
            }
        if "Evaluate a child's reading answer" in prompt:
            return {
                "feedback": "Good start—your idea connects to the story.",
                "understanding_level": "mostly_clear",
                "parent_note": "Understands the main event and can add evidence.",
                "follow_up_question": "Which detail in the chapter helped you think that?",
            }
        if "Summarize this child's" in prompt:
            return {
                "overall_level": "clear",
                "student_summary": "You explained your idea and found a useful detail. Keep asking what clues made you think that.",
                "parent_summary": "The child understood the main event and strengthened the answer after one prompt.",
                "strengths": ["Explains ideas in their own words"],
                "review_next": ["Use page evidence on the first try"],
                "next_steps": ["Read the next chapter and track the character's goal"],
            }
        raise AssertionError(f"Unexpected prompt: {prompt[:100]}")


class TocAI:
    def __init__(self):
        self.prompt = ""

    async def generate_json(self, prompt, **_kwargs):
        self.prompt = prompt
        return {
            "chapters": [
                {"title": "Dawn", "start_page": 3},
                {"title": "1962", "start_page": 5},
                {"title": "1963", "start_page": 8},
            ]
        }


class FakeTranscriptions:
    def create(self, **_kwargs):
        return SimpleNamespace(text="The character was trying to help a friend.")


class FakeOpenAI:
    def __init__(self):
        self.audio = SimpleNamespace(transcriptions=FakeTranscriptions())


def make_service(tmp_path, monkeypatch):
    service = ReadingService(
        data_root=tmp_path / "data",
        asset_dir=tmp_path / "assets",
        ai_generator=FakeAI(),
        transcription_client=FakeOpenAI(),
    )
    pages = [
        "Chapter One\nMilo found a small boat and decided to help his friend.",
        "They crossed the river even though the wind was strong.",
        "Chapter Two\nMilo returned home and told the truth about the trip.",
        "His family listened and made a new plan together.",
    ]
    monkeypatch.setattr(service, "_extract_pages", lambda _path: (FakeReader(), pages))
    return service


def test_reading_service_full_guided_flow(tmp_path, monkeypatch):
    asyncio.run(_exercise_full_guided_flow(tmp_path, monkeypatch))


async def _exercise_full_guided_flow(tmp_path, monkeypatch):
    service = make_service(tmp_path, monkeypatch)
    book = await service.create_book(
        b"%PDF-fake-reading-test",
        "application/pdf",
        title="Milo's Journey",
        author="Test Author",
        age_level="Age 9–11",
    )
    assert book["status"] == "draft"
    assert [chapter["title"] for chapter in book["chapters"]] == ["Chapter One", "Chapter Two"]

    service.upload_cover(book["id"], b"\x89PNG\r\n\x1a\ncover", "image/png")
    published = service.set_status(book["id"], "published")
    assert published["has_cover"] is True
    assert len(service.list_public_books()) == 1

    session = await service.start_session(book["id"], [book["chapters"][0]["id"]], 4)
    assert len(session["questions"]) == 4
    assert "reference_answer" not in session["questions"][0]
    token = session["access_token"]
    question_id = session["questions"][0]["id"]

    first = await service.answer_question(
        session["id"], token, question_id, "Milo wanted to help.", "text", False
    )
    assert first["questions"][0]["follow_up_question"]
    assert first["questions"][0]["answered_at"] is None

    followed = await service.answer_question(
        session["id"], token, question_id, "The chapter says he crossed the river.", "voice", True
    )
    assert followed["questions"][0]["answered_at"]
    assert followed["questions"][0]["follow_up_feedback"]

    completed = await service.finish_session(session["id"], token)
    assert completed["status"] == "completed"
    assert completed["overall_level"] == "clear"
    assert completed["evaluation"]["strengths"]
    assert "parent_summary" not in completed
    report = service.get_admin_session(session["id"])
    assert report["questions"][0]["parent_note"]
    assert report["parent_summary"]
    with pytest.raises(ValueError):
        service.get_public_session(session["id"], "wrong-token-that-is-long-enough")

    transcript = await service.transcribe_audio(b"voice-data", "audio/webm")
    assert "help a friend" in transcript


def test_reading_routes_are_protected_and_public_flow_works(tmp_path, monkeypatch):
    service = make_service(tmp_path, monkeypatch)
    monkeypatch.setattr(reading_api, "get_reading_service", lambda: service)

    with TestClient(app, follow_redirects=False) as client:
        assert client.get("/english/reading").status_code == 200
        assert client.get("/learningcenter/english/reading").status_code == 200
        assert client.get("/admin/learningcenter/reading").status_code == 303
        assert client.get("/api/admin/reading/books").status_code == 401
        assert client.get("/api/reading/books").json() == {"books": [], "total": 0}

        assert client.post("/api/admin/session", json={"password": "0418"}).status_code == 200
        assert client.get("/admin/learningcenter/reading").status_code == 200
        uploaded = client.post(
            "/api/admin/reading/books",
            params={"title": "Route Book", "author": "Route Author"},
            content=b"%PDF-route-test",
            headers={"Content-Type": "application/pdf"},
        )
        assert uploaded.status_code == 201
        book = uploaded.json()
        assert len(book["chapters"]) == 2
        assert client.put(
            f"/api/admin/reading/books/{book['id']}/status", json={"status": "published"}
        ).status_code == 200

        public = client.get("/api/reading/books").json()
        assert public["total"] == 1
        started = client.post(
            "/api/reading/sessions",
            json={"book_id": book["id"], "chapter_ids": [book["chapters"][0]["id"]], "question_count": 3},
        )
        assert started.status_code == 201
        payload = started.json()
        assert client.get(
            f"/api/reading/sessions/{payload['id']}", params={"access_token": payload["access_token"]}
        ).status_code == 200
        assert client.get("/api/admin/reading/sessions").json()["total"] == 1
        redetected = client.post(f"/api/admin/reading/books/{book['id']}/redetect-chapters")
        assert redetected.status_code == 200
        assert redetected.json()["status"] == "draft"
        assert len(redetected.json()["chapters"]) == 2


def test_ai_json_parser_accepts_compatible_provider_code_fences():
    assert AIGenerator._parse_json_content('```json\n{"chapters":[{"title":"One"}]}\n```') == {
        "chapters": [{"title": "One"}]
    }
    assert AIGenerator._parse_json_content('Here is the result:\n{"ok":true}') == {"ok": True}


def test_toc_detection_sends_a_focused_prompt(tmp_path):
    ai = TocAI()
    service = ReadingService(
        data_root=tmp_path / "data", asset_dir=tmp_path / "assets", ai_generator=ai
    )
    pages = [
        "Title page",
        "Table of Contents Dawn 3 1962 5 1963 8 Acknowledgments 10",
        "D A W N The story begins.",
        "More text.",
        "1962 A new year begins.",
        "More text.",
        "More text.",
        "1963 Another year begins.",
    ]
    chapters = asyncio.run(service._ai_starts(pages))
    assert [chapter["title"] for chapter in chapters] == ["Dawn", "1962", "1963"]
    assert len(ai.prompt) < 6000
    assert "Table of Contents" in ai.prompt
