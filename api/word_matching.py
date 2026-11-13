"""Word Matching practice and administrator word banks."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from database import database_for_data_root
from services.admin_session_service import require_admin_session
from services.word_matching_service import MAX_PAIRS, WordMatchingService


router = APIRouter(prefix="/api/english/word-matching", tags=["Word Matching"])
admin_router = APIRouter(
    prefix="/api/admin/word-matching",
    tags=["Word Matching Admin"],
    dependencies=[Depends(require_admin_session)],
)


class WordBankInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    pairs_text: str = Field(min_length=1, max_length=25_000)
    show_word_bank: bool | None = None


class StartAttemptInput(BaseModel):
    bank_id: str = Field(min_length=1, max_length=32)


class GradeAttemptInput(BaseModel):
    answers: dict[str, Annotated[str, Field(max_length=100)]] = Field(max_length=MAX_PAIRS)


def _service() -> WordMatchingService:
    return WordMatchingService(database_for_data_root())


@router.get("/banks")
@admin_router.get("/banks")
def list_banks():
    return {"banks": _service().list_banks()}


@admin_router.get("/banks/{bank_id}")
def get_bank(bank_id: str):
    try:
        return _service().get_bank(bank_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _save_bank(request: WordBankInput, bank_id: str | None = None):
    try:
        return _service().save_bank(
            request.name, request.pairs_text, bank_id, show_word_bank=request.show_word_bank
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@admin_router.post("/banks", status_code=201)
def create_bank(request: WordBankInput):
    return _save_bank(request)


@admin_router.put("/banks/{bank_id}")
def update_bank(bank_id: str, request: WordBankInput):
    return _save_bank(request, bank_id)


@router.post("/attempts", status_code=201)
def start_attempt(request: StartAttemptInput):
    try:
        return _service().start_attempt(request.bank_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/attempts/{attempt_id}/grade")
def grade_attempt(attempt_id: str, request: GradeAttemptInput):
    try:
        return _service().grade_attempt(attempt_id, request.answers)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
