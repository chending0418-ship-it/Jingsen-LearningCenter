"""Request models for the guided Book Reading feature."""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class ReadingBookUpdate(BaseModel):
    title: str = Field(..., min_length=1, max_length=160)
    author: str = Field("", max_length=120)
    description: str = Field("", max_length=1200)
    age_level: str = Field("", max_length=80)
    language: str = Field("English", min_length=1, max_length=40)


class ReadingBookStatusUpdate(BaseModel):
    status: Literal["draft", "published", "archived"]


class ReadingChapterInput(BaseModel):
    id: Optional[str] = None
    title: str = Field(..., min_length=1, max_length=180)
    start_page: int = Field(..., ge=1)
    end_page: int = Field(..., ge=1)


class ReadingChaptersUpdate(BaseModel):
    chapters: List[ReadingChapterInput] = Field(..., min_length=1, max_length=300)


class ReadingSessionCreate(BaseModel):
    book_id: str = Field(..., min_length=1, max_length=64)
    chapter_ids: List[str] = Field(..., min_length=1, max_length=3)
    question_count: int = Field(4, ge=3, le=5)
    question_focus: Literal["main_idea", "detail", "mixed"] = "mixed"

    @field_validator("chapter_ids")
    @classmethod
    def unique_chapters(cls, value: List[str]) -> List[str]:
        if len(set(value)) != len(value):
            raise ValueError("章节不能重复选择")
        return value


class ReadingAnswerRequest(BaseModel):
    access_token: str = Field(..., min_length=20, max_length=200)
    question_id: str = Field(..., min_length=1, max_length=64)
    answer: str = Field(..., min_length=1, max_length=1500)
    input_mode: Literal["text"] = "text"
    is_follow_up: bool = False


class ReadingFinishRequest(BaseModel):
    access_token: str = Field(..., min_length=20, max_length=200)


class ReadingPreparationCreate(BaseModel):
    book_id: str = Field(..., min_length=1, max_length=64)
    lesson_id: str = Field(..., min_length=1, max_length=64)


class ReadingPreparationDraft(ReadingFinishRequest):
    answers: dict[str, str] = Field(default_factory=dict, max_length=10)
    revision: int = Field(..., ge=0)

    @field_validator("answers")
    @classmethod
    def limit_answers(cls, values):
        if any(len(k) > 64 or len(v) > 1500 for k, v in values.items()):
            raise ValueError("每题回答不能超过1500字")
        return values


class ReadingPreparationSubmit(ReadingFinishRequest):
    revision: int = Field(..., ge=0)


class ReadingPreparationAnswer(ReadingPreparationSubmit):
    question_id: str = Field(..., min_length=1, max_length=64)
    answer: str = Field(..., min_length=1, max_length=1500)
