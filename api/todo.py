"""Learning Todo 公共端、Admin 管理端和 Admin 会话 API。"""

from datetime import date, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from models.todo_schemas import (
    AdminLoginRequest,
    BackupRestoreRequest,
    CopyDayRequest,
    CopyWeekRequest,
    EditScope,
    PointsSpendRequest,
    ReportCommentRequest,
    SettingsUpdateRequest,
    SubjectCreateRequest,
    SubjectUpdateRequest,
    TaskCreateRequest,
    TaskUpdateRequest,
)
from services.admin_session_service import (
    clear_admin_session,
    create_admin_session,
    is_admin_authenticated,
    require_admin_session,
    verify_admin_password,
)
from services.learning_todo_service import TodoDataError, get_learning_todo_service


public_router = APIRouter(prefix="/api/todo", tags=["Learning Todo"])
admin_router = APIRouter(
    prefix="/api/admin/todo",
    tags=["Learning Todo Admin"],
    dependencies=[Depends(require_admin_session)],
)
admin_session_router = APIRouter(prefix="/api/admin", tags=["Admin Session"])


def _service():
    return get_learning_todo_service()


def _raise_todo_error(error: TodoDataError) -> None:
    message = str(error)
    code = status.HTTP_404_NOT_FOUND if "不存在" in message else status.HTTP_400_BAD_REQUEST
    raise HTTPException(status_code=code, detail=message)


def _model_json(model, *, exclude_unset: bool = False) -> dict:
    return model.model_dump(mode="json", exclude_unset=exclude_unset)


def _public_task(payload: dict) -> dict:
    payload = dict(payload)
    for private_key in (
        "parent_note",
        "history",
        "template_id",
        "occurrence_key",
        "voided_at",
        "voided_local_date",
        "cancelled_at",
        "cancelled_local_date",
    ):
        payload.pop(private_key, None)
    return payload


@admin_session_router.post("/session")
async def login_admin(request: AdminLoginRequest, response: Response):
    if not verify_admin_password(request.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="密码错误")
    expires_at = create_admin_session(response)
    return {"authenticated": True, "expires_at": expires_at}


@admin_session_router.get("/session")
async def get_admin_session(request: Request):
    return {"authenticated": is_admin_authenticated(request)}


@admin_session_router.delete("/session")
async def logout_admin(response: Response):
    clear_admin_session(response)
    return {"authenticated": False}


@public_router.get("/today")
async def get_today_tasks():
    return _service().today_payload()


@public_router.get("/reward")
async def get_reward_summary():
    return _service().reward_summary()


@public_router.post("/tasks/{task_id}/complete")
async def complete_public_task(task_id: str):
    try:
        return _public_task(_service().complete_task(task_id))
    except TodoDataError as error:
        _raise_todo_error(error)


@public_router.post("/tasks/{task_id}/undo-completion")
async def undo_public_task_completion(task_id: str):
    try:
        return _public_task(_service().undo_completion(task_id))
    except TodoDataError as error:
        _raise_todo_error(error)


@admin_router.get("/overview")
async def get_overview():
    return _service().overview()


@admin_router.get("/points")
async def get_points_account():
    return _service().points_account()


@admin_router.post("/points/spend", status_code=status.HTTP_201_CREATED)
async def spend_points(request: PointsSpendRequest):
    try:
        return _service().spend_points(request.points, request.purpose)
    except TodoDataError as error:
        _raise_todo_error(error)


@admin_router.get("/subjects")
async def list_subjects(include_disabled: bool = True):
    return {"subjects": _service().list_subjects(include_disabled=include_disabled)}


@admin_router.post("/subjects", status_code=status.HTTP_201_CREATED)
async def create_subject(request: SubjectCreateRequest):
    try:
        return _service().create_subject(request.name, request.color, request.sort_order)
    except TodoDataError as error:
        _raise_todo_error(error)


@admin_router.put("/subjects/{subject_id}")
async def update_subject(subject_id: str, request: SubjectUpdateRequest):
    try:
        return _service().update_subject(subject_id, _model_json(request, exclude_unset=True))
    except TodoDataError as error:
        _raise_todo_error(error)


@admin_router.get("/tasks")
async def list_tasks(
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    subject_id: Optional[str] = None,
    task_status: Optional[str] = Query(default=None, alias="status"),
    include_inactive: bool = False,
):
    try:
        tasks = _service().list_tasks(
            from_date=from_date.isoformat() if from_date else None,
            to_date=to_date.isoformat() if to_date else None,
            subject_id=subject_id,
            status=task_status,
            include_inactive=include_inactive,
        )
        return {"tasks": tasks, "total": len(tasks)}
    except TodoDataError as error:
        _raise_todo_error(error)


@admin_router.post("/tasks", status_code=status.HTTP_201_CREATED)
async def create_task(request: TaskCreateRequest):
    try:
        return _service().create_task(_model_json(request))
    except TodoDataError as error:
        _raise_todo_error(error)


@admin_router.get("/tasks/{task_id}")
async def get_task(task_id: str):
    try:
        return _service().get_task(task_id)
    except TodoDataError as error:
        _raise_todo_error(error)


@admin_router.put("/tasks/{task_id}")
async def update_task(task_id: str, request: TaskUpdateRequest, scope: EditScope = "this"):
    try:
        return _service().update_task(task_id, _model_json(request, exclude_unset=True), scope=scope)
    except TodoDataError as error:
        _raise_todo_error(error)


@admin_router.delete("/tasks/{task_id}")
async def delete_task(task_id: str, scope: EditScope = "this"):
    try:
        return _service().void_task(task_id, scope=scope, lifecycle="voided")
    except TodoDataError as error:
        _raise_todo_error(error)


@admin_router.post("/tasks/{task_id}/void")
async def void_task(task_id: str, scope: EditScope = "this"):
    try:
        return _service().void_task(task_id, scope=scope, lifecycle="voided")
    except TodoDataError as error:
        _raise_todo_error(error)


@admin_router.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str, scope: EditScope = "this"):
    try:
        return _service().void_task(task_id, scope=scope, lifecycle="cancelled")
    except TodoDataError as error:
        _raise_todo_error(error)


@admin_router.post("/tasks/{task_id}/complete")
async def complete_admin_task(task_id: str):
    try:
        return _service().complete_task(task_id)
    except TodoDataError as error:
        _raise_todo_error(error)


@admin_router.post("/tasks/{task_id}/undo-completion")
async def undo_admin_task_completion(task_id: str):
    try:
        return _service().undo_completion(task_id)
    except TodoDataError as error:
        _raise_todo_error(error)


@admin_router.post("/tasks/{task_id}/reward/confirm")
async def confirm_admin_task_reward(task_id: str):
    try:
        return _service().grant_task_reward(task_id)
    except TodoDataError as error:
        _raise_todo_error(error)


@admin_router.get("/tasks/{task_id}/history")
async def get_task_history(task_id: str):
    try:
        return _service().task_history(task_id)
    except TodoDataError as error:
        _raise_todo_error(error)


@admin_router.post("/copy-day")
async def copy_day(request: CopyDayRequest):
    try:
        tasks = _service().copy_day(request.source_date.isoformat(), request.target_date.isoformat())
        return {"tasks": tasks, "copied": len(tasks)}
    except TodoDataError as error:
        _raise_todo_error(error)


@admin_router.post("/copy-last-week")
async def copy_last_week(request: CopyWeekRequest):
    try:
        tasks = _service().copy_last_week(request.target_week_start.isoformat())
        return {"tasks": tasks, "copied": len(tasks)}
    except TodoDataError as error:
        _raise_todo_error(error)


@admin_router.get("/templates")
async def list_templates(include_inactive: bool = False):
    return {"templates": _service().list_templates(include_inactive=include_inactive)}


@admin_router.post("/templates", status_code=status.HTTP_201_CREATED)
async def create_template(request: TaskCreateRequest):
    if request.repeat == "once":
        raise HTTPException(status_code=400, detail="重复任务模板不能使用“不重复”")
    try:
        return _service().create_task(_model_json(request))
    except TodoDataError as error:
        _raise_todo_error(error)


@admin_router.put("/templates/{template_id}")
async def update_template(template_id: str, request: TaskUpdateRequest):
    try:
        return _service().update_template(template_id, _model_json(request, exclude_unset=True))
    except TodoDataError as error:
        _raise_todo_error(error)


@admin_router.delete("/templates/{template_id}")
async def delete_template(template_id: str):
    try:
        return _service().deactivate_template(template_id)
    except TodoDataError as error:
        _raise_todo_error(error)


@admin_router.get("/day")
async def get_day_view(day: date):
    try:
        return _service().day_view(day.isoformat())
    except TodoDataError as error:
        _raise_todo_error(error)


@admin_router.get("/week")
async def get_week_view(
    week_start: Optional[date] = None,
):
    service_today = date.fromisoformat(_service().today())
    start = week_start or (service_today - timedelta(days=service_today.weekday()))
    try:
        return _service().week_view(start.isoformat())
    except TodoDataError as error:
        _raise_todo_error(error)


@admin_router.get("/month")
async def get_month_view(month: Optional[str] = None):
    target = month or _service().today()[:7]
    try:
        return _service().month_view(target)
    except TodoDataError as error:
        _raise_todo_error(error)


@admin_router.get("/stats/week")
async def get_week_stats(week_start: date):
    try:
        return _service().week_stats(week_start.isoformat())
    except TodoDataError as error:
        _raise_todo_error(error)


@admin_router.get("/stats/month")
async def get_month_stats(month: str):
    try:
        return _service().month_stats(month)
    except TodoDataError as error:
        _raise_todo_error(error)


@admin_router.get("/reports/{period_type}/{period_key}")
async def get_report(period_type: Literal["week", "month"], period_key: str):
    try:
        return _service().get_report(period_type, period_key)
    except TodoDataError as error:
        _raise_todo_error(error)


@admin_router.put("/reports/{period_type}/{period_key}")
async def save_report(period_type: Literal["week", "month"], period_key: str, request: ReportCommentRequest):
    try:
        return _service().save_report(period_type, period_key, request.comment)
    except TodoDataError as error:
        _raise_todo_error(error)


@admin_router.get("/settings")
async def get_settings():
    return _service().get_settings()


@admin_router.put("/settings")
async def update_settings(request: SettingsUpdateRequest):
    return _service().update_settings(_model_json(request, exclude_unset=True))


@admin_router.get("/backups")
async def list_backups():
    return {"backups": _service().list_backups()}


@admin_router.post("/backups", status_code=status.HTTP_201_CREATED)
async def create_backup():
    return _service().create_backup("manual")


@admin_router.post("/backups/{backup_name}/restore")
async def restore_backup(backup_name: str, request: BackupRestoreRequest):
    if not request.confirm:
        raise HTTPException(status_code=400, detail="恢复备份需要明确确认")
    try:
        return _service().restore_backup(backup_name)
    except TodoDataError as error:
        _raise_todo_error(error)


@admin_router.get("/storage/validate")
async def validate_storage():
    return _service().validate_storage()
