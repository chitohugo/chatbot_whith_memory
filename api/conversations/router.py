from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from api.auth.dependencies import get_current_user_id
from api.database import get_db_session
from api.conversations.schemas import ConversationCreateRequest, ConversationResponse, ConversationUpdateRequest, MessageResponse
from api.conversations import service

router = APIRouter(prefix="/conversations", tags=["Conversations"])
UserID = Annotated[UUID, Depends(get_current_user_id)]


@router.post("", response_model=ConversationResponse, status_code=201)
def post_conversation(current_user_id: UserID, data: ConversationCreateRequest | None = None, db=Depends(get_db_session)):
    return service.create_conversation(db, current_user_id)


@router.get("", response_model=list[ConversationResponse])
def get_conversations(current_user_id: UserID, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), archived: bool = False, db=Depends(get_db_session)):
    return service.list_conversations(db, current_user_id, limit, offset, archived)


@router.patch("/{conversation_id}", response_model=ConversationResponse)
def patch_conversation(conversation_id: UUID, data: ConversationUpdateRequest, current_user_id: UserID, db=Depends(get_db_session)):
    changes = data.model_dump(exclude_unset=True)
    if any(value is None for value in changes.values()):
        raise HTTPException(422, "Los campos no pueden ser nulos")
    conversation = service.update_conversation(db, conversation_id, current_user_id, changes)
    if conversation is None:
        raise HTTPException(404, "Conversation not found")
    return conversation


@router.get("/{conversation_id}", response_model=ConversationResponse)
def get_one_conversation(conversation_id: UUID, current_user_id: UserID, db=Depends(get_db_session)):
    conversation = service.get_conversation(db, conversation_id, current_user_id)
    if conversation is None:
        raise HTTPException(404, "Conversation not found")
    return conversation


@router.get("/{conversation_id}/messages", response_model=list[MessageResponse])
def get_messages(conversation_id: UUID, current_user_id: UserID, limit: int = Query(50, ge=1, le=100), before_id: int | None = Query(None, ge=1), db=Depends(get_db_session)):
    if not service.get_conversation(db, conversation_id, current_user_id):
        raise HTTPException(404, "Conversation not found")
    return service.list_messages(db, conversation_id, current_user_id, limit, before_id)


@router.get("/{conversation_id}/export")
def export_conversation(conversation_id: UUID, current_user_id: UserID, db=Depends(get_db_session)):
    from sqlalchemy import select
    from api.models import ChatMessage
    conversation = service.get_conversation(db, conversation_id, current_user_id)
    if conversation is None:
        raise HTTPException(404, "Conversation not found")
    messages = db.scalars(select(ChatMessage).where(ChatMessage.conversation_id == conversation_id).order_by(ChatMessage.id)).all()
    document = (conversation.title or "Nueva conversación") + "\n\n"
    document += "\n\n".join(f"{'Tú' if message.role == 'user' else 'Asistente'}:\n{message.content}" for message in messages if message.role in ("user", "assistant"))
    return Response(document, media_type="text/plain", headers={"Content-Disposition": f'attachment; filename="chat-{conversation_id}.txt"'})


@router.delete("/{conversation_id}", status_code=204)
def remove_conversation(conversation_id: UUID, current_user_id: UserID, db=Depends(get_db_session)):
    if not service.delete_conversation(db, conversation_id, current_user_id):
        raise HTTPException(404, "Conversation not found")
