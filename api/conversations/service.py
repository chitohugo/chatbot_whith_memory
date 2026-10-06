from uuid import UUID
from sqlalchemy import select
from api.models import ChatMessage, Conversation, utcnow


def create_conversation(db, user_id: UUID):
    conversation = Conversation(user_id=user_id)
    db.add(conversation)
    db.commit()
    return conversation


def list_conversations(db, user_id: UUID, limit=50, offset=0, archived=False):
    return db.scalars(select(Conversation).where(Conversation.user_id == user_id, Conversation.archived == archived).order_by(Conversation.updated_at.desc(), Conversation.id.desc()).offset(offset).limit(limit)).all()


def get_conversation(db, conversation_id: UUID, user_id: UUID, lock=False):
    statement = select(Conversation).where(Conversation.id == conversation_id, Conversation.user_id == user_id)
    if lock:
        statement = statement.with_for_update()
    return db.scalar(statement)


def list_messages(db, conversation_id: UUID, user_id: UUID, limit=50, before_id=None):
    statement = select(ChatMessage).join(Conversation).where(ChatMessage.conversation_id == conversation_id, Conversation.user_id == user_id)
    if before_id is not None:
        statement = statement.where(ChatMessage.id < before_id)
    return list(reversed(db.scalars(statement.order_by(ChatMessage.id.desc()).limit(limit)).all()))


def create_message(db, conversation_id: UUID, user_id: UUID, role: str, content: str):
    conversation = get_conversation(db, conversation_id, user_id)
    if conversation is None:
        return None
    message = ChatMessage(conversation_id=conversation.id, session_id=conversation.legacy_session_id or str(conversation.id), role=role, content=content)
    if role == "user" and not conversation.title:
        conversation.title = " ".join(content.split())[:120]
    conversation.updated_at = utcnow()
    db.add(message)
    db.commit()
    return message


def update_conversation(db, conversation_id, user_id, changes):
    conversation = get_conversation(db, conversation_id, user_id)
    if conversation is not None:
        for name, value in changes.items():
            setattr(conversation, name, value)
        db.commit()
    return conversation


def delete_conversation(db, conversation_id: UUID, user_id: UUID) -> bool:
    conversation = get_conversation(db, conversation_id, user_id)
    if conversation is None:
        return False
    db.delete(conversation)
    db.commit()
    return True
