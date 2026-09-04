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
    question_count: int = Field(5, ge=3, le=6)

    @field_validator("chapter_ids")
    @classmethod
    def unique_chapters(cls, value: List[str]) -> List[str]:
        if len(set(value)) != len(value):
            raise ValueError("章节不能重复选择")
        return value


class ReadingAnswerRequest(BaseModel):
    access_token: str = Field(..., min_length=20, max_length=200)
    question_id: str = Field(..., min_length=1, max_length=64)
    answer: str = Field(..., min_length=1, max_length=5000)
    input_mode: Literal["text", "voice"] = "text"
    is_follow_up: bool = False


class ReadingFinishRequest(BaseModel):
    access_token: str = Field(..., min_length=20, max_length=200)
