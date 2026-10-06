from typing import Annotated
from uuid import UUID
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from api.auth.dependencies import get_current_user_id
from api.database import get_db_session
from api.memories.schemas import MemoryCreateRequest, MemoryResponse, MemorySearchRequest
from api.memories import service

router = APIRouter(prefix="/memories", tags=["Memories"])
UserID = Annotated[UUID, Depends(get_current_user_id)]
logger = logging.getLogger(__name__)


def embedding_operation(operation):
    try:
        return operation()
    except Exception as error:
        logger.warning("memory_unavailable", extra={"error_type": type(error).__name__})
        raise HTTPException(502, "El servicio de recuerdos no está disponible") from error


@router.get("", response_model=list[MemoryResponse])
def get_memories(current_user_id: UserID, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), db=Depends(get_db_session)):
    return service.list_memories(db, current_user_id, limit, offset)


@router.post("/search", response_model=list[MemoryResponse])
def post_memory_search(data: MemorySearchRequest, current_user_id: UserID, db=Depends(get_db_session)):
    return embedding_operation(lambda: service.search_memories(db, current_user_id, data.query, data.limit))


@router.post("", response_model=MemoryResponse, status_code=201)
def post_memory(data: MemoryCreateRequest, current_user_id: UserID, db=Depends(get_db_session)):
    return embedding_operation(lambda: service.create_memory(db, current_user_id, data.memory_text))


@router.patch("/{memory_id}", response_model=MemoryResponse)
def patch_memory(memory_id: int, data: MemoryCreateRequest, current_user_id: UserID, db=Depends(get_db_session)):
    result = embedding_operation(lambda: service.update_memory(db, current_user_id, memory_id, data.memory_text))
    if result is None:
        raise HTTPException(404, "Memory not found")
    return result


@router.delete("/{memory_id}", status_code=204)
def remove_memory(memory_id: int, current_user_id: UserID, db=Depends(get_db_session)):
    if not service.delete_memory(db, current_user_id, memory_id):
        raise HTTPException(404, "Memory not found")
