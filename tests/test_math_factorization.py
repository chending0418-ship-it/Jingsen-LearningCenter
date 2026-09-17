import random
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from database import ReportRepository, SQLiteDatabase
from services.factorization_engine import MathInputError, generate_questions, grade_answer, parse_expression
from services.factorization_service import FactorizationService, MathSessionNotFound, MathSubmissionConflict


@pytest.mark.parametrize("answer", [
    "(x+2)(x-2)(x²+4)", "(x^2+4)*(x-2)*(x+2)",
    "-(2-x)(x+2)(x^2+4)", "（x+2）（x−2）（x²+4）",
])
def test_accepts_equivalent_factor_orders_signs_and_input_forms(answer):
    assert grade_answer({"expression": "x^4-16"}, answer)["correct"] is True


@pytest.mark.parametrize("expression,answer", [
    ("x^4-16", "(x^2-4)(x^2+4)"),
    ("x^4-16", "x^4-16"),
    ("6*x+12", "3(2x+4)"),
    ("x^4-2*x^2+1", "(x²-1)²"),
    ("x^2-1", "(x-1)(x+1)+0"),
])
def test_equivalence_alone_does_not_pass_incomplete_decomposition(expression, answer):
    assert grade_answer({"expression": expression}, answer)["error_code"] == "incomplete"


def test_wrong_and_complete_repeated_factor_answers():
    assert grade_answer({"expression": "x^4-16"}, "(x-2)²(x²+4)")["error_code"] == "not_equivalent"
    assert grade_answer({"expression": "x^4-2*x^2+1"}, "(x-1)²(x+1)²")["correct"]
    assert grade_answer({"expression": "6*x+12"}, "6(x+2)")["correct"]
    assert grade_answer({"expression": "x^4+4"}, "(x²+2x+2)(x²-2x+2)")["correct"]


@pytest.mark.parametrize("answer", [
    "", "(x+2", "x^999", "x^2^3", "x/0", "1.5x", "t=x²",
    "__import__('os').system('false')", "x.__class__", "x^8*x^8", "9^8*9^8",
    "(" * 15 + "x" + ")" * 15,
])
def test_parser_rejects_invalid_or_unbounded_input(answer):
    with pytest.raises(MathInputError):
        parse_expression(answer)


def test_generated_plans_have_ten_distinct_valid_questions_and_two_challenges():
    completion_variants = set()
    for seed in range(50):
        questions = generate_questions(random.Random(seed))
        assert len(questions) == 10
        assert [q["is_challenge"] for q in questions] == [False] * 8 + [True] * 2
        assert len({parse_expression(q["expression"]).coefficients for q in questions}) == 10
        assert questions[8]["skill"] == "substitution"
        assert questions[9]["skill"] == "completion"
        completion_variants.add("+1" if "+1" in questions[9]["hints"][1] else "term")
        for question in questions:
            assert grade_answer(question, question["correct_answer"])["correct"]
    assert completion_variants == {"+1", "term"}


@pytest.fixture
def service(tmp_path, monkeypatch):
    monkeypatch.delenv("SQLITE_DATABASE_PATH", raising=False)
    return FactorizationService(tmp_path / "data")


def submit_all(service, session):
    private = service.repository.get(session["id"])
    for question in private["questions"]:
        result = service.answer_question(session["id"], session["access_token"], question["id"], question["correct_answer"])
    return result


def test_completed_session_records_accuracy_mistakes_scratch_and_hints_independently(service):
    # An existing English report must remain byte-for-byte unchanged.
    reports = ReportRepository(service.database)
    reports.replace_all({"reports": [{"id": "english-existing", "module": "word_palace", "correct_count": 2, "total_count": 3}]})
    before = reports.read_all()
    session = service.start_session()
    assert session["question_count"] == 10
    assert "access_token_hash" not in session
    assert all("correct_answer" not in q and "solution_steps" not in q and "skill" not in q for q in session["questions"])
    private = service.repository.get(session["id"])
    for index, q in enumerate(private["questions"]):
        if index == 1:
            service.reveal_hint(session["id"], session["access_token"], q["id"], 1)
        answer = "0" if index == 0 else q["correct_answer"]
        result = service.answer_question(session["id"], session["access_token"], q["id"], answer, ["t=x²"] if index == 8 else [], skipped=index == 9)
    assert result["status"] == "completed"
    assert result["correct_count"] == 8 and result["accuracy"] == 80
    assert result["independent_correct_count"] == 7 and result["independent_accuracy"] == 70
    assert result["questions"][0]["result"]["error_code"] == "not_equivalent"
    assert result["questions"][8]["scratch"] == ["t=x²"]
    assert result["questions"][9]["result"]["error_code"] == "skipped"
    assert reports.read_all() == before
    summary = service.list_sessions()["summary"]
    assert summary["accuracy"] == 80 and summary["incorrect_count"] == 2
    restarted = FactorizationService(service.database.path.parent)
    assert restarted.get_session(session["id"], session["access_token"]) == result


def test_invalid_syntax_does_not_consume_attempt_and_cannot_change_first_submission(service):
    session = service.start_session()
    q = service.repository.get(session["id"])["questions"][0]
    with pytest.raises(MathInputError):
        service.answer_question(session["id"], session["access_token"], q["id"], "(x+")
    assert service.get_session(session["id"], session["access_token"])["answered_count"] == 0
    first = service.answer_question(session["id"], session["access_token"], q["id"], "0")
    assert service.answer_question(session["id"], session["access_token"], q["id"], "0") == first
    with pytest.raises(MathSubmissionConflict):
        service.answer_question(session["id"], session["access_token"], q["id"], q["correct_answer"])


def test_tokens_question_ownership_order_and_hint_idempotency(service):
    first, second = service.start_session(), service.start_session()
    with pytest.raises(MathSessionNotFound):
        service.get_session(first["id"], second["access_token"])
    with pytest.raises(MathSessionNotFound):
        service.answer_question(first["id"], first["access_token"], second["questions"][0]["id"], "0")
    with pytest.raises(MathSubmissionConflict):
        service.answer_question(first["id"], first["access_token"], first["questions"][1]["id"], "0")
    qid = first["questions"][0]["id"]
    with pytest.raises(ValueError):
        service.reveal_hint(first["id"], first["access_token"], qid, 2)
    for _ in range(2):
        hinted = service.reveal_hint(first["id"], first["access_token"], qid, 1)
    assert hinted["questions"][0]["hints_used"] == 1
    assert "correct_answer" not in hinted["questions"][0]


def test_concurrent_final_submission_is_saved_once(service):
    session = service.start_session()
    questions = service.repository.get(session["id"])["questions"]
    for q in questions[:-1]:
        service.answer_question(session["id"], session["access_token"], q["id"], q["correct_answer"])
    last = questions[-1]
    def submit(_):
        worker = FactorizationService(service.database.path.parent)
        return worker.answer_question(session["id"], session["access_token"], last["id"], last["correct_answer"])
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(submit, range(2)))
    assert all(result["accuracy"] == 100 for result in responses)
    assert service.list_sessions()["summary"]["completed_sessions"] == 1


def test_admin_pagination_and_in_progress_records(service):
    sessions = [service.start_session() for _ in range(3)]
    submit_all(service, sessions[0])
    assert service.list_sessions(limit=1, offset=1)["total"] == 3
    assert len(service.list_sessions(limit=1, offset=1)["sessions"]) == 1
    assert service.list_sessions(status="active")["total"] == 2
    assert service.list_sessions(status="completed")["sessions"][0]["accuracy"] == 100


def test_schema_v5_is_additive_and_survives_reinitialization(tmp_path):
    database = SQLiteDatabase(tmp_path / "legacy.sqlite3")
    database.initialize()
    with database.transaction() as conn:
        conn.execute("DELETE FROM schema_migrations WHERE version=5")
        conn.execute("DROP TABLE math_session_questions")
        conn.execute("DROP TABLE math_sessions")
        conn.execute("INSERT INTO app_state(key,value,updated_at) VALUES('keep','old-data','2026-09-01')")
    upgraded = SQLiteDatabase(database.path)
    upgraded.initialize()
    with upgraded.read() as conn:
        assert conn.execute("SELECT value FROM app_state WHERE key='keep'").fetchone()[0] == "old-data"
        assert conn.execute("SELECT COUNT(*) FROM schema_migrations WHERE version=5").fetchone()[0] == 1
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_math_api_admin_auth_paths_and_server_owned_results(service, monkeypatch):
    import api.math as math_api
    from config import config
    from main import app
    monkeypatch.setattr(math_api, "get_factorization_service", lambda: service)
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "math-test-only")
    monkeypatch.setattr(config, "ADMIN_COOKIE_SECURE", False)
    with TestClient(app) as client:
        for prefix in ("", "/learningcenter"):
            assert client.get(prefix + "/api/admin/math/sessions").status_code == 401
            assert client.get(prefix + "/math").status_code == 200
            assert client.post(prefix + "/api/math/factorization/sessions", json={"question_count": 9}).status_code == 422
        assert client.get("/admin/learningcenter/math", follow_redirects=False).status_code == 303
        response = client.post("/learningcenter/api/math/factorization/sessions", json={})
        assert response.status_code == 201 and response.headers["cache-control"] == "no-store"
        session = response.json()
        path = f'/api/math/factorization/sessions/{session["id"]}'
        assert client.get(path).status_code == 422
        headers = {"X-Math-Session": session["access_token"]}
        assert client.get(path, headers=headers).status_code == 200
        body = {"question_id": session["questions"][0]["id"], "answer": "0", "correct": True}
        assert client.post(path + "/answers", json=body, headers=headers).status_code == 422
        del body["correct"]
        result = client.post(path + "/answers", json=body, headers=headers)
        assert result.status_code == 200 and result.json()["correct_count"] == 0
        login = client.post("/api/admin/session", json={"password": "math-test-only"})
        assert login.status_code == 200
        assert client.get("/admin/learningcenter/math").status_code == 200
        detail = client.get(f'/api/admin/math/sessions/{session["id"]}').json()
        assert detail["questions"][0]["student_answer"] == "0"
        assert "access_token_hash" not in detail and "access_token" not in detail
        assert client.get("/api/admin/math/sessions").json()["total"] == 1
