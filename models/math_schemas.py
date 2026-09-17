"""The server owns the ten-question plan, solutions and grading."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class MathSessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Optional for clients that explicitly declare the fixed session length.
    question_count: int = Field(10, ge=10, le=10)


class MathAnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question_id: str = Field(..., min_length=1, max_length=64)
    answer: str = Field("", max_length=240)
    scratch: list[Annotated[str, Field(max_length=240)]] = Field(default_factory=list, max_length=6)
    skipped: bool = False


class MathHintRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question_id: str = Field(..., min_length=1, max_length=64)
    level: int = Field(..., ge=1, le=3)
