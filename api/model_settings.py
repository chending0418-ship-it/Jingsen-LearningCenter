"""Admin 模型目录和默认模型设置 API。"""

from fastapi import APIRouter, Depends, HTTPException, status

from models.model_settings_schemas import ModelSelectionRequest
from services.admin_session_service import require_admin_session
from services.model_settings_service import (
    ModelSettingsError,
    get_model_settings_service,
)


router = APIRouter(
    prefix="/api/admin",
    tags=["Admin Model Settings"],
    dependencies=[Depends(require_admin_session)],
)


def _service():
    return get_model_settings_service()


def _raise_service_error(error: ModelSettingsError) -> None:
    status_by_kind = {
        "configuration": status.HTTP_503_SERVICE_UNAVAILABLE,
        "upstream": status.HTTP_502_BAD_GATEWAY,
        "storage": status.HTTP_500_INTERNAL_SERVER_ERROR,
        "validation": status.HTTP_400_BAD_REQUEST,
    }
    raise HTTPException(
        status_code=status_by_kind.get(error.kind, status.HTTP_400_BAD_REQUEST),
        detail=str(error),
    )


@router.get("/model-settings")
async def get_model_settings():
    try:
        return _service().get_settings()
    except ModelSettingsError as error:
        _raise_service_error(error)


@router.get("/models")
async def list_available_models():
    try:
        return await _service().fetch_available_models()
    except ModelSettingsError as error:
        _raise_service_error(error)


@router.put("/model-settings")
async def update_model_settings(request: ModelSelectionRequest):
    try:
        catalog = await _service().fetch_available_models()
        available_ids = {item["id"] for item in catalog["models"]}
        if request.model_id not in available_ids:
            raise ModelSettingsError("所选模型不在当前令牌的可用列表中")
        return _service().set_selected_model(request.model_id)
    except ModelSettingsError as error:
        _raise_service_error(error)
