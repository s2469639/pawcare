"""요청 본문 검증 모델."""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

RecordType = Literal["식사", "배변", "활동", "행동", "특이사항", "기타"]
Priority = Literal["high", "normal", "low"]


def _strip(v):
    return v.strip() if isinstance(v, str) else v


class RecordCreate(BaseModel):
    dog_id: int
    record_type: RecordType
    structured_value: Optional[str] = Field(default=None, max_length=60)
    content: str = Field(default="", max_length=1000)
    observed_at: Optional[str] = None
    author_id: Optional[int] = None

    _s = field_validator("structured_value", "content", mode="before")(_strip)

    @field_validator("observed_at")
    @classmethod
    def _iso(cls, v):
        if v in (None, ""):
            return None
        try:
            return datetime.fromisoformat(v).replace(tzinfo=None, microsecond=0).isoformat()
        except ValueError:
            raise ValueError("기록 시각 형식이 올바르지 않습니다.")


class ApprovalBody(BaseModel):
    action: Literal["approve", "revoke"]
    parent_text: Optional[str] = Field(default=None, max_length=500)

    _s = field_validator("parent_text", mode="before")(_strip)


class TaskCreate(BaseModel):
    dog_id: int
    source_record_id: Optional[int] = None
    title: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=500)
    assignee_id: Optional[int] = None
    priority: Priority = "normal"
    ai_suggested: bool = False

    _s = field_validator("title", "description", mode="before")(_strip)


class TaskPatch(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=80)
    description: Optional[str] = Field(default=None, max_length=500)
    assignee_id: Optional[int] = None
    priority: Optional[Priority] = None

    _s = field_validator("title", "description", mode="before")(_strip)


class ActionCreate(BaseModel):
    action_type: Literal["acknowledge", "start", "complete", "comment"]
    note: Optional[str] = Field(default=None, max_length=500)

    _s = field_validator("note", mode="before")(_strip)


class DogPatch(BaseModel):
    breed: Optional[str] = Field(default=None, min_length=1, max_length=40)
    birth_date: Optional[str] = None
    owner_name: Optional[str] = Field(default=None, min_length=1, max_length=40)
    attending: Optional[bool] = None
    care_context: Optional[dict[str, str]] = None

    @field_validator("birth_date")
    @classmethod
    def _date(cls, v):
        if v is None:
            return v
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("생년월일은 YYYY-MM-DD 형식이어야 합니다.")
        return v

    @field_validator("care_context")
    @classmethod
    def _ctx(cls, v):
        if v is None:
            return v
        allowed = {"meal", "sensitivity", "behavior", "owner_request", "other"}
        if set(v) - allowed:
            raise ValueError("허용되지 않는 돌봄 정보 항목입니다.")
        if any(len(x) > 300 for x in v.values()):
            raise ValueError("각 항목은 300자 이내여야 합니다.")
        return {k: x.strip() for k, x in v.items()}


class SuggestRequest(BaseModel):
    record_id: int
