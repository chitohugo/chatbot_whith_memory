from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from api.auth.dependencies import get_current_user_id
from api.database import get_db_connection
from api.memories.schemas import (
    MemoryCreateRequest,
    MemoryResponse,
    MemorySearchRequest,
)
from api.memories.service import create_memory, search_memories


router = APIRouter(
    prefix="/memories",
    tags=["Memories"],
)


def _memory_response(row) -> MemoryResponse:
    return MemoryResponse(
        id=row[0],
        memory_text=row[1],
        created_at=row[2],
    )


@router.post(
    "/search",
    response_model=list[MemoryResponse],
)
def post_memory_search(
    data: MemorySearchRequest,
    current_user_id: Annotated[
        UUID,
        Depends(get_current_user_id),
    ],
    db=Depends(get_db_connection),
):
    try:
        memories = search_memories(
            db,
            current_user_id,
            data.query,
            data.limit,
        )
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Memory search unavailable",
        ) from exc

    return [_memory_response(row) for row in memories]


@router.post(
    "",
    response_model=MemoryResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_memory(
    data: MemoryCreateRequest,
    current_user_id: Annotated[
        UUID,
        Depends(get_current_user_id),
    ],
    db=Depends(get_db_connection),
):
    try:
        memory = create_memory(db, current_user_id, data.memory_text)
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Memory storage unavailable",
        ) from exc

    return _memory_response(memory)
