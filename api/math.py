"""
数学学科 API 路由
"""
from typing import Optional

from fastapi import APIRouter, Query, Depends, Header, HTTPException, Response
from services.math_service import MathService
from models.schemas import QuestionsResponse
from models.math_schemas import MathAnswerRequest, MathHintRequest, MathSessionCreate
from services.admin_session_service import require_admin_session
from services.factorization_service import get_factorization_service, MathSessionNotFound, MathSubmissionConflict

router = APIRouter(prefix="/api/math", tags=["Math"])
admin_router = APIRouter(prefix="/api/admin/math", tags=["Math Admin"], dependencies=[Depends(require_admin_session)])

# 初始化服务
math_service = MathService()


@router.get("/generate", response_model=QuestionsResponse)
async def generate_math_exam(
    count: int = Query(10, ge=1, le=50, description="题目数量"),
    topic: str = Query("algebra", description="题目主题: algebra/geometry/calculus"),
    difficulty: str = Query("medium", description="难度级别: easy/medium/hard")
):
    """
    生成数学考题 (开发中)
    
    - **count**: 题目数量 (1-50)
    - **topic**: 题目主题 (algebra/geometry/calculus)
    - **difficulty**: 难度级别 (easy/medium/hard)
    """
    result = await math_service.generate_exam(count, topic, difficulty)
    
    return {
        "questions": result.get("questions", []),
        "total": len(result.get("questions", [])),
        "subject": "math"
    }


@router.get("/calculation")
async def generate_calculation_questions(
    count: int = Query(5, ge=1, le=20, description="题目数量")
):
    """
    生成计算题 (开发中)
    """
    return await math_service.generate_calculation_questions(count)


@router.get("/word-problems")
async def generate_word_problems(
    count: int = Query(5, ge=1, le=20, description="题目数量")
):
    """
    生成应用题 (开发中)
    """
    return await math_service.generate_word_problems(count)


def _private_response(response: Response):
    response.headers["Cache-Control"] = "no-store"


def _math_call(operation):
    try:
        return operation()
    except MathSessionNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MathSubmissionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/factorization/sessions", status_code=201, dependencies=[Depends(_private_response)])
def start_factorization(payload: MathSessionCreate):
    return get_factorization_service().start_session()


@router.get("/factorization/sessions/{session_id}", dependencies=[Depends(_private_response)])
def get_factorization(session_id: str, x_math_session: str = Header(..., min_length=20, max_length=100)):
    return _math_call(lambda: get_factorization_service().get_session(session_id, x_math_session))


@router.post("/factorization/sessions/{session_id}/answers", dependencies=[Depends(_private_response)])
def answer_factorization(session_id: str, payload: MathAnswerRequest, x_math_session: str = Header(..., min_length=20, max_length=100)):
    return _math_call(lambda: get_factorization_service().answer_question(
        session_id, x_math_session, payload.question_id, payload.answer, payload.scratch, payload.skipped,
    ))


@router.post("/factorization/sessions/{session_id}/hints", dependencies=[Depends(_private_response)])
def hint_factorization(session_id: str, payload: MathHintRequest, x_math_session: str = Header(..., min_length=20, max_length=100)):
    return _math_call(lambda: get_factorization_service().reveal_hint(
        session_id, x_math_session, payload.question_id, payload.level,
    ))


@admin_router.get("/sessions", dependencies=[Depends(_private_response)])
def list_math_history(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), status: Optional[str] = Query(None, pattern="^(active|completed)$")):
    return get_factorization_service().list_sessions(limit, offset, status)


@admin_router.get("/sessions/{session_id}", dependencies=[Depends(_private_response)])
def get_math_history(session_id: str):
    return _math_call(lambda: get_factorization_service().get_admin_session(session_id))
