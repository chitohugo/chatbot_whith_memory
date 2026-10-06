from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ConversationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    user_id: UUID | None
    legacy_session_id: str | None
    created_at: datetime
    updated_at: datetime
    title: str | None = None
    archived: bool = False


class ConversationUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str | None = Field(default=None, min_length=1, max_length=120)
    archived: bool | None = None


class MessageCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user"]
    content: str = Field(min_length=1, max_length=16_000)


class InternalMessageCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["assistant", "system", "tool"]
    content: str = Field(min_length=1, max_length=16_000)


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    conversation_id: UUID
    role: str
    content: str
    created_at: datetime
