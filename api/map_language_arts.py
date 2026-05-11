"""
MAP Language Arts API 路由
"""
from fastapi import APIRouter, HTTPException

from models.schemas import (
    MapLanguageArtsEvaluateRequest,
    MapLanguageArtsEvaluationResponse,
    MapLanguageArtsGenerateRequest,
    MapLanguageArtsGenerateResponse,
)
from services.map_language_arts_service import get_map_language_arts_service

router = APIRouter(prefix="/api/map/language-arts", tags=["MAP Language Arts"])

map_language_arts_service = get_map_language_arts_service()


@router.get("/skills")
async def get_language_arts_skills():
    """获取 MAP Language Arts skills 明细"""
    return {"skills": map_language_arts_service.get_skills()}


@router.get("/skills/tree")
async def get_language_arts_skill_tree():
    """获取 MAP Language Arts Grade -> Topic -> Skill -> Detail 树"""
    return map_language_arts_service.get_skill_tree()


@router.post("/generate", response_model=MapLanguageArtsGenerateResponse)
async def generate_language_arts_practice(request: MapLanguageArtsGenerateRequest):
    """生成 MAP Language Arts 练习题"""
    result = await map_language_arts_service.generate_practice(request)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/evaluate", response_model=MapLanguageArtsEvaluationResponse)
async def evaluate_language_arts_practice(request: MapLanguageArtsEvaluateRequest):
    """评估 MAP Language Arts 答题结果并生成诊断报告"""
    return await map_language_arts_service.evaluate_practice(request)
