from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from api.auth.dependencies import (
    get_current_user_id,
    require_internal_request,
)
from api.conversations.schemas import (
    ConversationCreateRequest,
    ConversationResponse,
    InternalMessageCreateRequest,
    MessageCreateRequest,
    MessageResponse,
)
from api.conversations.service import (
    create_conversation,
    create_message,
    delete_conversation,
    get_conversation,
    list_conversations,
    list_messages,
)
from api.database import get_db_connection


router = APIRouter(
    prefix="/conversations",
    tags=["Conversations"],
)


@router.post(
    "",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_conversation(
    current_user_id: Annotated[
        UUID,
        Depends(get_current_user_id),
    ],
    data: ConversationCreateRequest | None = None,
    db=Depends(get_db_connection),
):
    conversation = create_conversation(db, current_user_id)
    return ConversationResponse(
        id=conversation[0],
        user_id=conversation[1],
        legacy_session_id=conversation[2],
        created_at=conversation[3],
        updated_at=conversation[4],
    )


@router.get(
    "",
    response_model=list[ConversationResponse],
)
def get_conversations(
    current_user_id: Annotated[
        UUID,
        Depends(get_current_user_id),
    ],
    db=Depends(get_db_connection),
):
    return [
        ConversationResponse(
            id=row[0],
            user_id=row[1],
            legacy_session_id=row[2],
            created_at=row[3],
            updated_at=row[4],
        )
        for row in list_conversations(db, current_user_id)
    ]


@router.get(
    "/{conversation_id}/messages",
    response_model=list[MessageResponse],
)
def get_messages(
    conversation_id: UUID,
    current_user_id: Annotated[
        UUID,
        Depends(get_current_user_id),
    ],
    db=Depends(get_db_connection),
):
    if not get_conversation(db, conversation_id, current_user_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    return [
        MessageResponse(
            id=row[0],
            conversation_id=row[1],
            role=row[2],
            content=row[3],
            created_at=row[4],
        )
        for row in list_messages(db, conversation_id, current_user_id)
    ]


@router.post(
    "/{conversation_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_message(
    conversation_id: UUID,
    data: MessageCreateRequest,
    current_user_id: Annotated[
        UUID,
        Depends(get_current_user_id),
    ],
    db=Depends(get_db_connection),
):
    if not get_conversation(db, conversation_id, current_user_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    message = create_message(
        db,
        conversation_id,
        current_user_id,
        data.role,
        data.content,
    )

    return MessageResponse(
        id=message[0],
        conversation_id=message[1],
        role=message[2],
        content=message[3],
        created_at=message[4],
    )


@router.post(
    "/{conversation_id}/messages/internal",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_internal_request)],
)
def post_internal_message(
    conversation_id: UUID,
    data: InternalMessageCreateRequest,
    current_user_id: Annotated[
        UUID,
        Depends(get_current_user_id),
    ],
    db=Depends(get_db_connection),
):
    if not get_conversation(db, conversation_id, current_user_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    message = create_message(
        db,
        conversation_id,
        current_user_id,
        data.role,
        data.content,
    )

    return MessageResponse(
        id=message[0],
        conversation_id=message[1],
        role=message[2],
        content=message[3],
        created_at=message[4],
    )


@router.delete(
    "/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_conversation(
    conversation_id: UUID,
    current_user_id: Annotated[
        UUID,
        Depends(get_current_user_id),
    ],
    db=Depends(get_db_connection),
):
    if not delete_conversation(db, conversation_id, current_user_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
