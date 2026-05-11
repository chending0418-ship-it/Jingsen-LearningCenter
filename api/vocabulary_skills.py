"""
Word Palace Vocabulary Skills API 路由
"""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from models.schemas import (
    VocabularySkillsEvaluateRequest,
    VocabularySkillsEvaluationResponse,
    VocabularySkillsGenerateRequest,
    VocabularySkillsGenerateResponse,
)
from services.vocabulary_skills_service import get_vocabulary_skills_service

router = APIRouter(prefix="/api/word-palace/vocabulary-skills", tags=["Vocabulary Skills"])

vocabulary_skills_service = get_vocabulary_skills_service()


@router.get("/skills")
async def get_vocabulary_skills(
    grade: Optional[str] = Query(None),
    topic: Optional[str] = Query(None),
    skill: Optional[str] = Query(None),
    enabled_only: bool = Query(True)
):
    """获取 Vocabulary Skills 明细列表。"""
    rows = vocabulary_skills_service.get_skills(
        grade=grade,
        topic=topic,
        skill=skill,
        enabled_only=enabled_only
    )
    return {"skills": rows, "total": len(rows)}


@router.get("/skills/tree")
async def get_vocabulary_skill_tree(enabled_only: bool = Query(True)):
    """获取 Vocabulary Skills Grade -> Topic -> Skill -> Detail 树。"""
    return vocabulary_skills_service.get_skill_tree(enabled_only=enabled_only)


@router.post("/generate", response_model=VocabularySkillsGenerateResponse)
async def generate_vocabulary_practice(request: VocabularySkillsGenerateRequest):
    """按 Grade / Topic / Skill 生成 Vocabulary Skills 练习题。"""
    result = await vocabulary_skills_service.generate_practice(request)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/evaluate", response_model=VocabularySkillsEvaluationResponse)
async def evaluate_vocabulary_practice(request: VocabularySkillsEvaluateRequest):
    """批改 Vocabulary Skills 答案并写入 Daily Reports。"""
    return await vocabulary_skills_service.evaluate_practice(request)
