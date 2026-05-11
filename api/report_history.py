"""
学习报告历史 API 路由
"""
from typing import Optional

from fastapi import APIRouter, Query

from services.report_history_service import get_report_history_service

router = APIRouter(prefix="/api/reports", tags=["Reports"])

report_history_service = get_report_history_service()


@router.get("/history")
async def get_report_history(
    module: Optional[str] = Query(None, description="模块过滤: word_palace/word_vocabulary_skills/map_language_arts"),
    days: int = Query(30, ge=1, le=365, description="查询最近多少天")
):
    """获取本地每日报告历史"""
    return report_history_service.get_history(module=module, days=days)
