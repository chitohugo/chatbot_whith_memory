from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class MemorySearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=4000)
    limit: int = Field(default=3, ge=1, le=50)


class MemoryCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    memory_text: str = Field(min_length=1, max_length=4000)


class MemoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    memory_text: str
    created_at: datetime
