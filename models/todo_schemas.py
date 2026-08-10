"""Learning Todo API 请求模型。"""

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


RepeatKind = Literal["once", "daily", "weekly", "monthly"]
EditScope = Literal["this", "future", "series"]


class AdminLoginRequest(BaseModel):
    password: str = Field(min_length=1, max_length=256)


class SubjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    color: str = Field(default="#6B7280", pattern=r"^#[0-9A-Fa-f]{6}$")
    sort_order: Optional[int] = Field(default=None, ge=0, le=100000)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("科目名称不能为空")
        return value


class SubjectUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=40)
    color: Optional[str] = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    sort_order: Optional[int] = Field(default=None, ge=0, le=100000)
    enabled: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def clean_optional_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("科目名称不能为空")
        return value


class TaskCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    subject_id: str = Field(min_length=1, max_length=80)
    planned_date: date
    description: str = Field(default="", max_length=2000)
    parent_note: str = Field(default="", max_length=2000)
    reward_goal: str = Field(default="", max_length=500)
    reward_points: int = Field(default=0, ge=0, le=100000)
    repeat: RepeatKind = "once"
    repeat_weekdays: list[int] = Field(default_factory=list)
    end_date: Optional[date] = None
    repeat_month_day: Optional[int | Literal["last"]] = None

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("任务名称不能为空")
        return value

    @field_validator("repeat_weekdays")
    @classmethod
    def validate_weekdays(cls, value: list[int]) -> list[int]:
        if any(day < 0 or day > 6 for day in value):
            raise ValueError("重复星期必须在 0（周日）到 6（周六）之间")
        return sorted(set(value))


class TaskUpdateRequest(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=160)
    subject_id: Optional[str] = Field(default=None, min_length=1, max_length=80)
    planned_date: Optional[date] = None
    description: Optional[str] = Field(default=None, max_length=2000)
    parent_note: Optional[str] = Field(default=None, max_length=2000)
    reward_goal: Optional[str] = Field(default=None, max_length=500)
    reward_points: Optional[int] = Field(default=None, ge=0, le=100000)
    repeat: Optional[RepeatKind] = None
    repeat_weekdays: Optional[list[int]] = None
    end_date: Optional[date] = None
    repeat_month_day: Optional[int | Literal["last"]] = None

    @field_validator("title")
    @classmethod
    def clean_optional_title(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("任务名称不能为空")
        return value

    @field_validator("repeat_weekdays")
    @classmethod
    def validate_optional_weekdays(cls, value: Optional[list[int]]) -> Optional[list[int]]:
        if value is None:
            return value
        if any(day < 0 or day > 6 for day in value):
            raise ValueError("重复星期必须在 0（周日）到 6（周六）之间")
        return sorted(set(value))


class CopyDayRequest(BaseModel):
    source_date: date
    target_date: date


class CopyWeekRequest(BaseModel):
    target_week_start: date


class ReportCommentRequest(BaseModel):
    comment: str = Field(default="", max_length=5000)


class SettingsUpdateRequest(BaseModel):
    recurrence_horizon_days: Optional[int] = Field(default=None, ge=30, le=1095)
    backup_retention: Optional[int] = Field(default=None, ge=5, le=200)


class BackupRestoreRequest(BaseModel):
    confirm: bool = False
