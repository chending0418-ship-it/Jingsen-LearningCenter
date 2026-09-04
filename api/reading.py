"""Public guided-reading APIs and authenticated parent administration."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse

from config import config
from models.reading_schemas import (
    ReadingAnswerRequest,
    ReadingBookStatusUpdate,
    ReadingBookUpdate,
    ReadingChaptersUpdate,
    ReadingFinishRequest,
    ReadingSessionCreate,
)
from services.admin_session_service import require_admin_session
from services.reading_service import get_reading_service


public_router = APIRouter(prefix="/api/reading", tags=["Book Reading"])
admin_router = APIRouter(
    prefix="/api/admin/reading",
    tags=["Book Reading Admin"],
    dependencies=[Depends(require_admin_session)],
)


def _raise_reading_error(exc: Exception) -> None:
    message = str(exc)
    if "不存在" in message or "尚未发布" in message:
        code = status.HTTP_404_NOT_FOUND
    elif "已经上传过" in message:
        code = status.HTTP_409_CONFLICT
    elif isinstance(exc, ValueError):
        code = status.HTTP_400_BAD_REQUEST
    else:
        code = status.HTTP_502_BAD_GATEWAY
        message = "阅读助手暂时没有响应，请稍后重试"
    raise HTTPException(status_code=code, detail=message) from exc


def _check_length(request: Request, maximum: int, label: str) -> None:
    content_length = request.headers.get("content-length")
    if not content_length:
        return
    try:
        if int(content_length) > maximum:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"{label}文件过大",
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Content-Length 无效") from exc


@public_router.get("/books")
async def list_public_books():
    books = get_reading_service().list_public_books()
    return {"books": books, "total": len(books)}


@public_router.get("/books/{book_id}/cover")
async def get_public_cover(book_id: str):
    try:
        path = get_reading_service().cover_path(book_id, public_only=True)
    except ValueError as exc:
        _raise_reading_error(exc)
    return FileResponse(path, headers={"Cache-Control": "public, max-age=86400"})


@public_router.post("/sessions", status_code=status.HTTP_201_CREATED)
async def start_reading_session(payload: ReadingSessionCreate):
    try:
        return await get_reading_service().start_session(
            payload.book_id, payload.chapter_ids, payload.question_count, payload.question_focus
        )
    except Exception as exc:
        _raise_reading_error(exc)


@public_router.get("/sessions/{session_id}")
async def get_reading_session(session_id: str, access_token: str = Query(..., min_length=20, max_length=200)):
    try:
        return get_reading_service().get_public_session(session_id, access_token)
    except Exception as exc:
        _raise_reading_error(exc)


@public_router.post("/sessions/{session_id}/answers")
async def answer_reading_question(session_id: str, payload: ReadingAnswerRequest):
    try:
        return await get_reading_service().answer_question(
            session_id, payload.access_token, payload.question_id, payload.answer,
            payload.input_mode, payload.is_follow_up,
        )
    except Exception as exc:
        _raise_reading_error(exc)


@public_router.post("/sessions/{session_id}/finish")
async def finish_reading_session(session_id: str, payload: ReadingFinishRequest):
    try:
        return await get_reading_service().finish_session(session_id, payload.access_token)
    except Exception as exc:
        _raise_reading_error(exc)


@admin_router.get("/books")
async def list_admin_books():
    books = get_reading_service().list_admin_books()
    return {"books": books, "total": len(books)}


@admin_router.post("/books", status_code=status.HTTP_201_CREATED)
async def upload_book(
    request: Request,
    title: str = Query(..., min_length=1, max_length=160),
    author: str = Query("", max_length=120),
    description: str = Query("", max_length=1200),
    age_level: str = Query("", max_length=80),
    language: str = Query("English", min_length=1, max_length=40),
):
    _check_length(request, config.READING_MAX_PDF_BYTES, "PDF")
    try:
        return await get_reading_service().create_book(
            await request.body(), request.headers.get("content-type", ""),
            title=title, author=author, description=description,
            age_level=age_level, language=language,
        )
    except Exception as exc:
        _raise_reading_error(exc)


@admin_router.get("/books/{book_id}")
async def get_admin_book(book_id: str):
    try:
        return get_reading_service().get_admin_book(book_id)
    except Exception as exc:
        _raise_reading_error(exc)


@admin_router.put("/books/{book_id}")
async def update_book(book_id: str, payload: ReadingBookUpdate):
    try:
        return get_reading_service().update_book(book_id, payload.model_dump())
    except Exception as exc:
        _raise_reading_error(exc)


@admin_router.put("/books/{book_id}/status")
async def update_book_status(book_id: str, payload: ReadingBookStatusUpdate):
    try:
        return get_reading_service().set_status(book_id, payload.status)
    except Exception as exc:
        _raise_reading_error(exc)


@admin_router.put("/books/{book_id}/chapters")
async def update_book_chapters(book_id: str, payload: ReadingChaptersUpdate):
    try:
        return get_reading_service().replace_chapters(
            book_id, [chapter.model_dump() for chapter in payload.chapters]
        )
    except Exception as exc:
        _raise_reading_error(exc)


@admin_router.post("/books/{book_id}/redetect-chapters")
async def redetect_book_chapters(book_id: str):
    try:
        return await get_reading_service().redetect_chapters(book_id)
    except Exception as exc:
        _raise_reading_error(exc)


@admin_router.post("/books/{book_id}/cover")
async def upload_book_cover(book_id: str, request: Request):
    _check_length(request, 8 * 1024 * 1024, "封面")
    try:
        return get_reading_service().upload_cover(
            book_id, await request.body(), request.headers.get("content-type", "")
        )
    except Exception as exc:
        _raise_reading_error(exc)


@admin_router.get("/books/{book_id}/cover")
async def get_admin_cover(book_id: str):
    try:
        path = get_reading_service().cover_path(book_id, public_only=False)
    except ValueError as exc:
        _raise_reading_error(exc)
    return FileResponse(path, headers={"Cache-Control": "private, max-age=3600"})


@admin_router.get("/sessions")
async def list_admin_sessions():
    sessions = get_reading_service().list_admin_sessions()
    return {"sessions": sessions, "total": len(sessions)}


@admin_router.get("/sessions/{session_id}")
async def get_admin_session(session_id: str):
    try:
        return get_reading_service().get_admin_session(session_id)
    except Exception as exc:
        _raise_reading_error(exc)
