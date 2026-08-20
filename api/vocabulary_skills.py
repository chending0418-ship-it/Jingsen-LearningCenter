"""
Word Palace Vocabulary Skills API 路由
"""
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from models.schemas import (
    VocabularySkillsEvaluateRequest,
    VocabularySkillsEvaluationResponse,
    VocabularySkillsGenerateRequest,
    VocabularySkillsGenerateResponse,
    GenerationJobResponse,
)
from services.vocabulary_skills_service import get_vocabulary_skills_service
from services.generation_job_service import GenerationJobNotFound, get_generation_job_service

router = APIRouter(prefix="/api/word-palace/vocabulary-skills", tags=["Vocabulary Skills"])

vocabulary_skills_service = get_vocabulary_skills_service()
generation_job_service = get_generation_job_service()


@router.post("/generation-jobs", response_model=GenerationJobResponse, status_code=202)
async def create_vocabulary_generation_job(
    request: VocabularySkillsGenerateRequest,
    background_tasks: BackgroundTasks,
):
    try:
        plan = vocabulary_skills_service.prepare_generation_job(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    topic = request.topic or plan["selected_details"][0].get("topic", "Vocabulary")
    job = generation_job_service.create_job(
        kind="vocabulary_skills",
        requested_count=request.question_count,
        request=request.model_dump(mode="json"),
        plan=plan,
        metadata={
            "test_title": "Vocabulary Skills Practice",
            "grade_level": vocabulary_skills_service._normalize_grade(request.grade_level),
            "topic": topic,
            "skill": request.skill,
            "difficulty": request.difficulty,
        },
    )
    background_tasks.add_task(vocabulary_skills_service.run_generation_job, job["job_id"])
    return job


@router.get("/generation-jobs/{job_id}", response_model=GenerationJobResponse)
async def get_vocabulary_generation_job(job_id: str, after: int = Query(0, ge=0)):
    try:
        return generation_job_service.get_job(job_id, kind="vocabulary_skills", after=after)
    except GenerationJobNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/generation-jobs/{job_id}", response_model=GenerationJobResponse)
async def cancel_vocabulary_generation_job(job_id: str):
    try:
        return generation_job_service.cancel_job(job_id, kind="vocabulary_skills")
    except GenerationJobNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


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
