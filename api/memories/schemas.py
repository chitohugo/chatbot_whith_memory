from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class MemorySearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1)
    limit: int = Field(default=3, ge=1, le=50)


class MemoryCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_text: str = Field(min_length=1)


class MemoryResponse(BaseModel):
    id: int
    memory_text: str
    created_at: datetime
