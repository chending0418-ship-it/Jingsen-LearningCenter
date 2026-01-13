"""
数学学科 API 路由
"""
from fastapi import APIRouter, Query
from services.math_service import MathService
from models.schemas import QuestionsResponse

router = APIRouter(prefix="/api/math", tags=["Math"])

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
