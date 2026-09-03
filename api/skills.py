"""
Skills 知识点 API
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from services.skills_service import get_skills_service
from services.admin_session_service import require_admin_session

router = APIRouter(prefix="/api/skills", tags=["Skills"])
skills_service = get_skills_service()


class SkillUpdateRequest(BaseModel):
    detail: Optional[str] = None
    difficulty: Optional[str] = None
    question_types: Optional[list[str]] = None
    tags: Optional[list[str]] = None
    enabled: Optional[bool] = None
    sort_order: Optional[int] = Field(None, ge=0)


@router.get("/sections")
async def list_skill_sections():
    """获取 skills 文件入口列表"""
    return {"sections": skills_service.list_sections()}


@router.get("/tree")
async def get_skills_tree(
    module: Optional[str] = Query(None),
    section: Optional[str] = Query(None),
    enabled_only: bool = Query(True)
):
    """获取 Grade -> Topic -> Skill -> Detail 树"""
    return skills_service.get_tree(module=module, section=section, enabled_only=enabled_only)


@router.get("")
async def list_skills(
    module: Optional[str] = Query(None),
    section: Optional[str] = Query(None),
    grade: Optional[str] = Query(None),
    topic: Optional[str] = Query(None),
    skill: Optional[str] = Query(None),
    enabled_only: bool = Query(False)
):
    """按条件查询 skills 明细"""
    rows = skills_service.list_skills(
        module=module,
        section=section,
        grade=grade,
        topic=topic,
        skill=skill,
        enabled_only=enabled_only
    )
    return {"skills": rows, "total": len(rows)}


@router.patch("/{skill_id}", dependencies=[Depends(require_admin_session)])
async def update_skill(skill_id: str, request: SkillUpdateRequest):
    """维护单个 skill 的启用状态或基础字段"""
    try:
        updates = {k: v for k, v in request.model_dump().items() if v is not None}
        return skills_service.update_skill(skill_id, updates)
    except ValueError as e:
        raise HTTPException(status_code=404 if "不存在" in str(e) else 400, detail=str(e))
