"""
后台管理 API 路由
"""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from models.schemas import (
    LibraryListResponse,
    LibraryAdminItem,
    LibraryCreateRequest,
    LibraryUpdateRequest,
    LibraryStatusRequest,
    LibraryItemsUpdateRequest,
    LibraryDetailResponse
)
from services.library_admin_service import get_library_admin_service

router = APIRouter(prefix="/api/admin", tags=["Admin"])
library_admin_service = get_library_admin_service()


def _error_status_by_message(message: str) -> int:
    return 404 if "不存在" in message else 400


@router.get("/libraries", response_model=LibraryListResponse)
async def list_libraries(
    subject: Optional[str] = Query(None, description="学科过滤: english/chinese"),
    include_disabled: bool = Query(True, description="是否包含未启用词库")
):
    libraries = library_admin_service.list_libraries(subject=subject, include_disabled=include_disabled)
    return {"libraries": libraries, "total": len(libraries)}


@router.get("/libraries/{library_id}", response_model=LibraryDetailResponse)
async def get_library(library_id: str):
    try:
        return library_admin_service.get_library(library_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/libraries", response_model=LibraryAdminItem)
async def create_library(request: LibraryCreateRequest):
    try:
        return library_admin_service.create_library(
            subject=request.subject,
            name=request.name,
            items=request.items,
            enabled=request.enabled,
            library_type=request.library_type
        )
    except ValueError as e:
        raise HTTPException(status_code=_error_status_by_message(str(e)), detail=str(e))


@router.put("/libraries/{library_id}", response_model=LibraryAdminItem)
async def update_library(library_id: str, request: LibraryUpdateRequest):
    try:
        return library_admin_service.update_library(
            library_id=library_id,
            name=request.name,
            library_type=request.library_type
        )
    except ValueError as e:
        raise HTTPException(status_code=_error_status_by_message(str(e)), detail=str(e))


@router.patch("/libraries/{library_id}/status", response_model=LibraryAdminItem)
async def update_library_status(library_id: str, request: LibraryStatusRequest):
    try:
        return library_admin_service.set_library_enabled(library_id, request.enabled)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/libraries/{library_id}/items", response_model=LibraryDetailResponse)
async def update_library_items(library_id: str, request: LibraryItemsUpdateRequest):
    try:
        return library_admin_service.replace_library_items(library_id, request.items)
    except ValueError as e:
        raise HTTPException(status_code=_error_status_by_message(str(e)), detail=str(e))
