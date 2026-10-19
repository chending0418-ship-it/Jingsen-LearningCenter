"""Family-meeting pages and capability-scoped, password-gated collection APIs."""

from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from services.admin_session_service import require_admin_session
from services.familymeeting_service import MeetingError, get_familymeeting_service


router = APIRouter(tags=["Family Meeting"])
ASSETS = Path(__file__).resolve().parents[1] / "static/familymeeting"
PRIVATE_HEADERS = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer", "X-Content-Type-Options": "nosniff", "X-Robots-Tag": "noindex, nofollow, noarchive", "X-Frame-Options": "DENY", "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"}


class CreateMeeting(BaseModel):
    title: str = Field(default="棒球家庭会议", max_length=100)
    meeting_date: str = Field(max_length=10)


class SaveAnswers(BaseModel):
    answers: dict
    revision: int = Field(ge=0)
    submit: bool = False


class UnlockMeeting(BaseModel):
    password: str = Field(min_length=1, max_length=128)


class SaveNotes(BaseModel):
    notes: dict
    revision: int = Field(ge=0)


def bearer(authorization):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(403, "请使用自己的会议专属链接。")
    return authorization[7:]


def respond(fn, *args):
    try:
        return JSONResponse(fn(*args), headers=PRIVATE_HEADERS)
    except MeetingError as error:
        return JSONResponse({"detail": error.message}, status_code=error.status, headers=PRIVATE_HEADERS)


def same_origin(request: Request):
    origin = request.headers.get("origin")
    if origin and urlsplit(origin).netloc != request.headers.get("host"):
        raise HTTPException(403, "请从本站操作。")


@router.get("/baseball/familymeeting/query", include_in_schema=False)
@router.get("/baseball/familymeeting/query/", include_in_schema=False)
def page():
    return FileResponse(ASSETS / "index.html", headers=PRIVATE_HEADERS)


@router.get("/baseball/familymeeting/assets/{filename}", include_in_schema=False)
@router.get("/static/familymeeting/{filename}", include_in_schema=False)
def asset(filename: str):
    if filename not in {"app.js", "styles.css", "questions.json"}:
        raise HTTPException(404)
    return FileResponse(ASSETS / filename, headers={**PRIVATE_HEADERS, "Cache-Control": "no-cache"})


@router.get("/api/baseball/familymeeting/meetings", dependencies=[Depends(require_admin_session)])
def list_meetings():
    return respond(get_familymeeting_service().list_meetings)


@router.post("/api/baseball/familymeeting/meetings", dependencies=[Depends(require_admin_session), Depends(same_origin)])
def create_meeting(payload: CreateMeeting):
    return respond(get_familymeeting_service().create, payload.title, payload.meeting_date)


@router.post("/api/baseball/familymeeting/meetings/{meeting_id}/access", dependencies=[Depends(require_admin_session), Depends(same_origin)])
def manage(meeting_id: str):
    return respond(get_familymeeting_service().admin_access, meeting_id)


@router.get("/api/baseball/familymeeting/meetings/{meeting_id}")
def get_state(meeting_id: str, authorization: str = Header(default=""), x_meeting_view: str = Header(default="")):
    return respond(get_familymeeting_service().state, meeting_id, bearer(authorization), x_meeting_view)


@router.put("/api/baseball/familymeeting/meetings/{meeting_id}/answers")
def save_answers(meeting_id: str, payload: SaveAnswers, authorization: str = Header(default="")):
    return respond(get_familymeeting_service().save_answers, meeting_id, bearer(authorization), payload.answers, payload.revision, payload.submit)


@router.post("/api/baseball/familymeeting/meetings/{meeting_id}/unlock")
def unlock(meeting_id: str, payload: UnlockMeeting, authorization: str = Header(default="")):
    return respond(get_familymeeting_service().unlock, meeting_id, bearer(authorization), payload.password)


@router.put("/api/baseball/familymeeting/meetings/{meeting_id}/notes")
def save_notes(meeting_id: str, payload: SaveNotes, authorization: str = Header(default=""), x_meeting_view: str = Header(default="")):
    return respond(get_familymeeting_service().save_notes, meeting_id, bearer(authorization), x_meeting_view, payload.notes, payload.revision)
