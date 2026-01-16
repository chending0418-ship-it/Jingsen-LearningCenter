"""
语文学科 API 路由
"""
from fastapi import APIRouter, Query
from services.chinese_service import ChineseService
from models.schemas import QuestionsResponse, SubmitRequest, GradeResponse
from typing import List

router = APIRouter(prefix="/api/chinese", tags=["Chinese"])

# 初始化服务
chinese_service = ChineseService()


@router.get("/generate", response_model=QuestionsResponse)
async def generate_chinese_exam(
    count: int = Query(5, ge=1, le=10, description="题目组数"),
    library: str = Query("chinese_words", description="词库名称"),
    mode: str = Query("conj_fill", description="题型模式: word_discrim(词语辨析) 或 conj_fill(关联词填空)")
):
    """
    生成语文考题
    
    - **count**: 题目数量 (1-10)
    - **library**: 词库名称 (chinese_words/chinese_idioms)
    - **mode**: 题型模式 (word_discrim/idiom_fill)
    """
    result = await chinese_service.generate_exam(count, library, mode)
    
    return {
        "questions": result.get("questions", []),
        "total": len(result.get("questions", [])),
        "subject": "chinese",
        "mode": mode
    }


@router.post("/grade", response_model=GradeResponse)
async def grade_chinese_exam(request: SubmitRequest):
    """
    批改语文考题并生成总结
    """
    return await chinese_service.grade_exam(request)


@router.get("/poetry")
async def generate_poetry_questions(
    count: int = Query(5, ge=1, le=20, description="题目数量")
):
    """
    生成古诗词题目 (开发中)
    """
    return await chinese_service.generate_poetry_questions(count)


@router.get("/comprehension")
async def generate_comprehension_questions(
    count: int = Query(5, ge=1, le=20, description="题目数量")
):
    """
    生成阅读理解题目 (开发中)
    """
    return await chinese_service.generate_comprehension_questions(count)
