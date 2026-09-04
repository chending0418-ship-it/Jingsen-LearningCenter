import asyncio
import pytest
from fastapi.testclient import TestClient

import api.reading as reading_api
from core.ai_generator import AIGenerator
from main import app
from services.reading_service import ReadingService


class FakeReader:
    outline = []


class FakeAI:
    def __init__(self):
        self.prompts = []

    async def generate_json(self, prompt, **_kwargs):
        self.prompts.append(prompt)
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


def make_service(tmp_path, monkeypatch):
    service = ReadingService(
        data_root=tmp_path / "data",
        asset_dir=tmp_path / "assets",
        ai_generator=FakeAI(),
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

    session = await service.start_session(book["id"], [book["chapters"][0]["id"]], 4, "main_idea")
    assert len(session["questions"]) == 4
    assert session["question_focus"] == "main_idea"
    question_prompt = next(prompt for prompt in service.ai_generator.prompts if "comprehension questions" in prompt)
    assert "Focus: MAIN IDEA" in question_prompt
    assert "Never ask the child to quote, copy, recite" in question_prompt
    assert "reference_answer" not in session["questions"][0]
    token = session["access_token"]
    question_id = session["questions"][0]["id"]

    first = await service.answer_question(
        session["id"], token, question_id, "Milo wanted to help.", "text", False
    )
    assert first["questions"][0]["follow_up_question"]
    assert first["questions"][0]["answered_at"] is None
    evaluation_prompt = next(prompt for prompt in service.ai_generator.prompts if "Evaluate a child's reading answer" in prompt)
    assert "conceptual understanding" in evaluation_prompt
    assert "Never ask for an exact quote" in evaluation_prompt

    followed = await service.answer_question(
        session["id"], token, question_id, "The chapter says he crossed the river.", "text", True
    )
    assert followed["questions"][0]["answered_at"]
    assert followed["questions"][0]["follow_up_feedback"]
    with pytest.raises(ValueError, match="不需要补充回答"):
        await service.answer_question(
            session["id"], token, question_id, "One more answer.", "text", True
        )

    completed = await service.finish_session(session["id"], token)
    assert completed["status"] == "completed"
    assert completed["overall_level"] == "clear"
    assert completed["evaluation"]["strengths"]
    summary_prompt = next(prompt for prompt in service.ai_generator.prompts if "Summarize this child's" in prompt)
    assert "Never list attendance, completion, engagement" in summary_prompt
    assert "Do not invent improvement, effort, feelings" in summary_prompt
    assert "parent_summary" not in completed
    report = service.get_admin_session(session["id"])
    assert report["questions"][0]["parent_note"]
    assert report["parent_summary"]
    with pytest.raises(ValueError):
        service.get_public_session(session["id"], "wrong-token-that-is-long-enough")

def test_reading_routes_are_protected_and_public_flow_works(tmp_path, monkeypatch):
    service = make_service(tmp_path, monkeypatch)
    monkeypatch.setattr(reading_api, "get_reading_service", lambda: service)

    with TestClient(app, follow_redirects=False) as client:
        reading_page = client.get("/english/reading")
        assert reading_page.status_code == 200
        assert '<option value="3">3</option>' in reading_page.text
        assert '<option value="4" selected>4</option>' in reading_page.text
        assert '<option value="5">5</option>' in reading_page.text
        assert 'value="main_idea">Main Idea' in reading_page.text
        assert 'value="detail">Detail' in reading_page.text
        assert 'value="mixed" selected>Mixed' in reading_page.text
        assert "deep dive" not in reading_page.text
        assert "Let’s try that again." in reading_page.text
        assert "What your answers showed" in reading_page.text
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
            json={
                "book_id": book["id"], "chapter_ids": [book["chapters"][0]["id"]],
                "question_count": 3, "question_focus": "detail",
            },
        )
        assert started.status_code == 201
        payload = started.json()
        assert payload["question_count"] == 3
        assert payload["question_focus"] == "detail"
        detail_prompt = [
            prompt for prompt in service.ai_generator.prompts if "comprehension questions" in prompt
        ][-1]
        assert "Focus: DETAIL" in detail_prompt
        assert client.get(
            f"/api/reading/sessions/{payload['id']}", params={"access_token": payload["access_token"]}
        ).status_code == 200
        assert client.get("/api/admin/reading/sessions").json()["total"] == 1
        redetected = client.post(f"/api/admin/reading/books/{book['id']}/redetect-chapters")
        assert redetected.status_code == 200
        assert redetected.json()["status"] == "draft"
        assert len(redetected.json()["chapters"]) == 2

        assert client.post(
            "/api/reading/sessions",
            json={
                "book_id": book["id"], "chapter_ids": [book["chapters"][0]["id"]],
                "question_count": 6, "question_focus": "mixed",
            },
        ).status_code == 422


def test_ai_json_parser_accepts_compatible_provider_code_fences():
    assert AIGenerator._parse_json_content('```json\n{"chapters":[{"title":"One"}]}\n```') == {
        "chapters": [{"title": "One"}]
    }
    assert AIGenerator._parse_json_content('Here is the result:\n{"ok":true}') == {"ok": True}


def test_mixed_question_focus_balances_main_idea_and_detail():
    instructions = ReadingService._question_focus_instructions("mixed", 5)
    assert "3 main-idea questions" in instructions
    assert "2 meaningful-detail questions" in instructions


def test_summary_rejects_repeated_placeholder_answers(tmp_path, monkeypatch):
    asyncio.run(_exercise_placeholder_summary(tmp_path, monkeypatch))


async def _exercise_placeholder_summary(tmp_path, monkeypatch):
    service = make_service(tmp_path, monkeypatch)
    book = await service.create_book(
        b"%PDF-placeholder-summary-test", "application/pdf", title="Milo's Journey"
    )
    service.set_status(book["id"], "published")
    session = await service.start_session(
        book["id"], [book["chapters"][0]["id"]], 3, "mixed"
    )
    token = session["access_token"]
    model_calls_after_questions = len(service.ai_generator.prompts)

    for _ in range(3):
        question = next(item for item in session["questions"] if not item["answered_at"])
        session = await service.answer_question(
            session["id"], token, question["id"], "test", "text", False
        )
        assert session["questions"][question["position"]]["follow_up_question"]
        session = await service.answer_question(
            session["id"], token, question["id"], "test", "text", True
        )

    completed = await service.finish_session(session["id"], token)
    assert len(service.ai_generator.prompts) == model_calls_after_questions
    assert completed["overall_level"] == "needs_support"
    assert completed["evaluation"]["strengths"] == []
    assert "repeated test or placeholder words" in completed["student_summary"]
    assert "one question at a time in your own words" in completed["student_summary"]
    assert len(completed["evaluation"]["next_steps"]) == 2

    report = service.get_admin_session(session["id"])
    assert "does not provide evidence of reading comprehension" in report["parent_summary"]
    assert all(
        question["understanding_level"] == "needs_support"
        for question in report["questions"]
    )


def test_summary_strengths_must_be_comprehension_evidence():
    needs_support = [{"understanding_level": "needs_support"}]
    assert ReadingService._supported_strengths(
        ["Stayed engaged with every question", "Identified the character's goal"], needs_support
    ) == []

    clear = [{"understanding_level": "clear"}]
    assert ReadingService._supported_strengths(
        ["Kept trying", "Identified the character's goal"], clear
    ) == ["Identified the character's goal"]
    assert ReadingService._derived_overall_level([
        {"understanding_level": "needs_support"},
        {"understanding_level": "needs_support"},
        {"understanding_level": "mostly_clear"},
    ]) == "needs_support"
    summary = ReadingService._grounded_student_summary(
        "You kept trying and worked through the questions.",
        [{"understanding_level": "needs_support", "question_text": "Why did Phil change his plan?"}],
        "needs_support",
    )
    assert "kept trying" not in summary
    assert "Why did Phil change his plan?" in summary


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
