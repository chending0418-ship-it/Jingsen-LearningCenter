"""
语文学科 API 路由
"""
from fastapi import APIRouter, Query, HTTPException
from services.chinese_service import ChineseService
from models.schemas import QuestionsResponse, SubmitRequest, GradeResponse
from typing import Optional, List

router = APIRouter(prefix="/api/chinese", tags=["Chinese"])

# 初始化服务
chinese_service = ChineseService()


@router.get("/generate", response_model=QuestionsResponse)
async def generate_chinese_exam(
    count: int = Query(5, ge=1, le=10, description="题目组数"),
    library: Optional[str] = Query(None, description="词库名称，不传则根据题型自动选择已启用词库"),
    mode: str = Query("conj_fill", description="题型模式: word_discrim(词语辨析)、conj_fill(关联词填空)、idiom_fill(成语填空)")
):
    if mode not in ["word_discrim", "conj_fill", "idiom_fill"]:
        raise HTTPException(status_code=400, detail=f"不支持的题型: {mode}，仅支持 word_discrim/conj_fill/idiom_fill")
    """
    生成语文考题
    
    - **count**: 题目数量 (1-10)
    - **library**: 词库名称（可选，不传自动匹配已启用词库）
    - **mode**: 题型模式 (word_discrim/conj_fill/idiom_fill)
    """
    result = await chinese_service.generate_exam(count, library, mode)

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    questions = result.get("questions", [])
    if not questions:
        raise HTTPException(status_code=400, detail="未能生成题目，请检查词库内容后重试")

    return {
        "questions": questions,
        "total": len(questions),
        "subject": "chinese",
        "mode": mode
    }


@router.post("/grade", response_model=GradeResponse)
async def grade_chinese_exam(request: SubmitRequest):
    """
    批改语文考题并生成总结
    """
    return await chinese_service.grade_exam(request)


@router.get("/libraries", response_model=List[str])
async def get_chinese_libraries(
    mode: Optional[str] = Query(None, description="题型模式: word_discrim/conj_fill/idiom_fill")
):
    """
    获取语文可用且已启用词库列表
    """
    if mode and mode not in ["word_discrim", "conj_fill", "idiom_fill"]:
        raise HTTPException(status_code=400, detail=f"不支持的题型: {mode}，仅支持 word_discrim/conj_fill/idiom_fill")
    return await chinese_service.get_library_list(mode)


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
