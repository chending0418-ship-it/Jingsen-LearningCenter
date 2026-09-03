"""Public homepage API and authenticated homepage administration."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse

from models.schemas import HomepageSettingsUpdate
from services.admin_session_service import require_admin_session
from services.homepage_service import get_homepage_service


public_router = APIRouter(prefix="/api/site", tags=["Homepage"])
admin_router = APIRouter(
    prefix="/api/admin/homepage",
    tags=["Homepage Admin"],
    dependencies=[Depends(require_admin_session)],
)


@public_router.get("/homepage")
async def get_homepage_settings():
    return get_homepage_service().get_settings()


@public_router.get("/homepage/hero")
async def get_homepage_hero():
    path = get_homepage_service().hero_path()
    return FileResponse(path, headers={"Cache-Control": "public, max-age=3600"})


@admin_router.get("")
async def get_homepage_admin_settings():
    return get_homepage_service().get_settings()


@admin_router.put("")
async def update_homepage_settings(request: HomepageSettingsUpdate):
    return get_homepage_service().update_settings(request.model_dump(mode="json"))


@admin_router.put("/hero")
async def upload_homepage_hero(request: Request):
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > get_homepage_service().MAX_HERO_BYTES:
                raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="图片不能超过 10MB")
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Content-Length 无效")
    try:
        return get_homepage_service().save_hero(
            await request.body(),
            request.headers.get("content-type", ""),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@admin_router.post("/hero/reset")
async def reset_homepage_hero():
    return get_homepage_service().reset_hero()
