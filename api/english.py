"""
英语学科 API 路由
"""
from fastapi import APIRouter, BackgroundTasks, Query, HTTPException
from services.english_service import EnglishService
from models.schemas import GenerateRequest, GenerationJobResponse, QuestionsResponse, ErrorResponse, LibraryInfo, SubmitRequest, GradeResponse
from services.generation_job_service import GenerationJobNotFound, get_generation_job_service
from typing import List, Optional

router = APIRouter(prefix="/api/english", tags=["English"])

# 初始化服务
english_service = EnglishService()
generation_job_service = get_generation_job_service()


@router.post("/generation-jobs", response_model=GenerationJobResponse, status_code=202)
async def create_english_generation_job(request: GenerateRequest, background_tasks: BackgroundTasks):
    """创建 Daily Word 分批生成任务；Passage Cloze 继续使用原完整生成接口。"""
    if request.mode == "passage_cloze":
        raise HTTPException(status_code=400, detail="Passage Cloze 是完整文章，请使用 /api/english/generate")
    try:
        plan = english_service.prepare_generation_job(request.count, request.library, request.mode or "cloze")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    job = generation_job_service.create_job(
        kind="daily_word",
        requested_count=len(plan["selected_words"]),
        request=request.model_dump(mode="json"),
        plan=plan,
        metadata={
            "subject": "english",
            "mode": request.mode,
            "library": plan["library_name"],
        },
    )
    background_tasks.add_task(english_service.run_generation_job, job["job_id"])
    return job


@router.get("/generation-jobs/{job_id}", response_model=GenerationJobResponse)
async def get_english_generation_job(job_id: str, after: int = Query(0, ge=0)):
    try:
        return generation_job_service.get_job(job_id, kind="daily_word", after=after)
    except GenerationJobNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/generation-jobs/{job_id}", response_model=GenerationJobResponse)
async def cancel_english_generation_job(job_id: str):
    try:
        return generation_job_service.cancel_job(job_id, kind="daily_word")
    except GenerationJobNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/generate", response_model=QuestionsResponse)
async def generate_english_exam(
    count: int = Query(10, ge=1, le=50, description="题目数量"),
    library: Optional[str] = Query(None, description="词库名称，不传则自动选择已启用词库"),
    mode: str = Query("cloze", description="题型模式: cloze(完形填空)、match(匹配题) 或 passage_cloze(短文填空)")
):
    if mode not in ["cloze", "match", "passage_cloze"]:
        raise HTTPException(status_code=400, detail=f"不支持的题型: {mode}，仅支持 cloze/match/passage_cloze")
    """
    生成英语考题
    
    - **count**: 题目数量 (1-50)
    - **library**: 词库名称（可选，不传自动使用已启用词库）
    - **mode**: 题型模式 (cloze/match/passage_cloze)
    """
    result = await english_service.generate_exam(count, library, mode)
    
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    questions = result.get("questions", [])
    if not questions:
        raise HTTPException(status_code=400, detail="未能生成题目，请检查词库内容后重试")

    return {
        "questions": questions,
        "total": len(questions),
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
async def get_libraries(
    mode: Optional[str] = Query(None, description="题型模式: cloze/match/passage_cloze")
):
    """
    获取可用且已启用的词库列表
    """
    if mode and mode not in ["cloze", "match", "passage_cloze"]:
        raise HTTPException(status_code=400, detail=f"不支持的题型: {mode}，仅支持 cloze/match/passage_cloze")
    return await english_service.get_library_list(mode)


@router.get("/library/{library_name}", response_model=LibraryInfo)
async def get_library_info(library_name: str):
    """
    获取指定词库的详细信息
    
    - **library_name**: 词库名称
    """
    return await english_service.get_library_info(library_name)
