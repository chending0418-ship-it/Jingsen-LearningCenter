"""Admin 模型选择相关请求模型。"""

from pydantic import BaseModel, Field, field_validator


class ModelSelectionRequest(BaseModel):
    model_id: str = Field(..., min_length=1, max_length=255)

    @field_validator("model_id")
    @classmethod
    def validate_model_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("模型 ID 不能为空")
        if any(character.isspace() or ord(character) < 32 for character in normalized):
            raise ValueError("模型 ID 不能包含空格或控制字符")
        return normalized
