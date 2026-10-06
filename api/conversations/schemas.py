from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ConversationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConversationResponse(BaseModel):
    id: UUID
    user_id: UUID | None
    legacy_session_id: str | None
    created_at: datetime
    updated_at: datetime


class MessageCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user"]
    content: str = Field(min_length=1)


class InternalMessageCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["assistant", "system", "tool"]
    content: str = Field(min_length=1)


class MessageResponse(BaseModel):
    id: int
    conversation_id: UUID
    role: str
    content: str
    created_at: datetime
