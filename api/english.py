"""
英语学科 API 路由
"""
from fastapi import APIRouter, Query
from services.english_service import EnglishService
from models.schemas import QuestionsResponse, ErrorResponse, LibraryInfo, SubmitRequest, GradeResponse
from typing import List

router = APIRouter(prefix="/api/english", tags=["English"])

# 初始化服务
english_service = EnglishService()


@router.get("/generate", response_model=QuestionsResponse)
async def generate_english_exam(
    count: int = Query(10, ge=1, le=50, description="题目数量"),
    library: str = Query("4000-202603", description="词库名称"),
    mode: str = Query("cloze", description="题型模式: cloze(完形填空) 或 match(匹配题)")
):
    """
    生成英语考题
    
    - **count**: 题目数量 (1-50)
    - **library**: 词库名称 (默认: 4000-202603)
    - **mode**: 题型模式 (cloze/match)
    """
    result = await english_service.generate_exam(count, library, mode)
    
    if "error" in result:
        return {"questions": [], "total": 0, "error": result["error"]}
    
    return {
        "questions": result.get("questions", []),
        "total": len(result.get("questions", [])),
        "subject": "english",
        "mode": mode
    }


@router.post("/grade", response_model=GradeResponse)
async def grade_english_exam(request: SubmitRequest):
    """
    批改英语考题并生成总结
    """
    return await english_service.grade_exam(request)


@router.get("/libraries", response_model=List[str])
async def get_libraries():
    """
    获取所有可用的词库列表
    """
    return await english_service.get_library_list()


@router.get("/library/{library_name}", response_model=LibraryInfo)
async def get_library_info(library_name: str):
    """
    获取指定词库的详细信息
    
    - **library_name**: 词库名称
    """
    return await english_service.get_library_info(library_name)
