"""Public Gallery feed and authenticated Gallery administration."""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse

from models.schemas import GalleryItemUpdate
from services.admin_session_service import require_admin_session
from services.gallery_service import get_gallery_service


public_router = APIRouter(prefix="/api/site/gallery", tags=["Gallery"])
admin_router = APIRouter(
    prefix="/api/admin/gallery",
    tags=["Gallery Admin"],
    dependencies=[Depends(require_admin_session)],
)


def _raise_gallery_error(exc: ValueError) -> None:
    code = status.HTTP_404_NOT_FOUND if "不存在" in str(exc) else status.HTTP_400_BAD_REQUEST
    raise HTTPException(status_code=code, detail=str(exc)) from exc


@public_router.get("")
async def list_gallery_items():
    items = get_gallery_service().list_items()
    return {"items": items, "total": len(items)}


@public_router.get("/items/{item_id}/image")
async def get_gallery_image(item_id: str):
    try:
        path = get_gallery_service().image_path(item_id)
    except ValueError as exc:
        _raise_gallery_error(exc)
    return FileResponse(path, headers={"Cache-Control": "public, max-age=86400"})


@admin_router.get("")
async def list_gallery_admin_items():
    items = get_gallery_service().list_items()
    return {"items": items, "total": len(items)}


@admin_router.post("/items", status_code=status.HTTP_201_CREATED)
async def upload_gallery_item(
    request: Request,
    title: str = Query(..., min_length=1, max_length=100),
    caption: str = Query("", max_length=600),
    location: str = Query("", max_length=100),
    shot_date: Optional[date] = Query(None),
    alt: str = Query(..., min_length=1, max_length=180),
):
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > get_gallery_service().MAX_IMAGE_BYTES:
                raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="单张图片不能超过 15MB")
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Content-Length 无效")
    try:
        return get_gallery_service().create_item(
            await request.body(),
            request.headers.get("content-type", ""),
            title=title,
            caption=caption,
            location=location,
            shot_date=shot_date.isoformat() if shot_date else None,
            alt=alt,
        )
    except ValueError as exc:
        _raise_gallery_error(exc)


@admin_router.put("/items/{item_id}")
async def update_gallery_item(item_id: str, request: GalleryItemUpdate):
    try:
        return get_gallery_service().update_item(item_id, request.model_dump(mode="json"))
    except ValueError as exc:
        _raise_gallery_error(exc)


@admin_router.delete("/items/{item_id}")
async def remove_gallery_item(item_id: str):
    try:
        return get_gallery_service().remove_item(item_id)
    except ValueError as exc:
        _raise_gallery_error(exc)
