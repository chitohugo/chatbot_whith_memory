import json
from datetime import timedelta
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from api.auth.dependencies import get_current_user_id
from api.conversations.service import get_conversation
from api.database import get_db_session
from api.models import ChatMessage, ChatRun, ToolAction, ToolExecution, utcnow
from api.chat.service import stream_run, user_files
from config import settings

router = APIRouter(prefix="/conversations", tags=["Chat"])
UserID = Annotated[UUID, Depends(get_current_user_id)]


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    content: str = Field(min_length=1, max_length=16_000)
    request_id: UUID


@router.post("/{conversation_id}/chat")
def chat(conversation_id: UUID, data: ChatRequest, current_user_id: UserID, db=Depends(get_db_session)):
    conversation = get_conversation(db, conversation_id, current_user_id, lock=True)
    if conversation is None:
        raise HTTPException(404, "Conversation not found")
    existing = db.scalar(select(ChatRun).where(ChatRun.request_id == data.request_id))
    if existing:
        # Nunca devuelve datos de un run que pertenezca a otra conversación.
        raise HTTPException(409, "Este pedido ya fue recibido; consulta el historial antes de repetirlo.")
    active = db.scalar(select(ChatRun).where(ChatRun.conversation_id == conversation_id, ChatRun.status == "running"))
    if active:
        created = active.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=utcnow().tzinfo)
        if utcnow() - created < timedelta(seconds=settings.agent.max_seconds + settings.openrouter.timeout + 30):
            raise HTTPException(409, "Esta conversación ya está generando una respuesta")
        active.status = "interrupted"
    if len(data.content.encode()) > settings.agent.context_tokens - settings.agent.output_tokens - 5000:
        raise HTTPException(422, "El mensaje supera el límite de contexto configurado")
    conversation.title = conversation.title or " ".join(data.content.split())[:120]
    conversation.updated_at = utcnow()
    run = ChatRun(conversation_id=conversation_id, request_id=data.request_id)
    db.add(run)
    db.add(ChatMessage(conversation_id=conversation_id, session_id=conversation.legacy_session_id or str(conversation_id), role="user", content=data.content))
    db.commit()

    def events():
        for event in stream_run(run.id, current_user_id, data.content):
            yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/{conversation_id}/tools")
def tool_history(conversation_id: UUID, current_user_id: UserID, db=Depends(get_db_session)):
    if get_conversation(db, conversation_id, current_user_id) is None:
        raise HTTPException(404, "Conversation not found")
    records = db.scalars(select(ToolExecution).join(ChatRun).where(ChatRun.conversation_id == conversation_id).order_by(ToolExecution.id.desc()).limit(50)).all()
    return [{"id": record.id, "name": record.name, "status": record.status, "duration_ms": record.duration_ms, "arguments": record.arguments, "created_at": record.created_at} for record in records]


@router.get("/{conversation_id}/actions")
def actions(conversation_id: UUID, current_user_id: UserID, db=Depends(get_db_session)):
    if get_conversation(db, conversation_id, current_user_id) is None:
        raise HTTPException(404, "Conversation not found")
    records = db.scalars(select(ToolAction).where(ToolAction.conversation_id == conversation_id, ToolAction.status == "pending").order_by(ToolAction.created_at).limit(20)).all()
    return [{"id": action.id, "name": action.name, "arguments": action.arguments, "preview": action.preview} for action in records]


@router.post("/{conversation_id}/actions/{action_id}/{decision}")
def decide_action(conversation_id: UUID, action_id: UUID, decision: str, current_user_id: UserID, db=Depends(get_db_session)):
    if decision not in ("approve", "reject"):
        raise HTTPException(422, "Decisión inválida")
    if get_conversation(db, conversation_id, current_user_id, lock=True) is None:
        raise HTTPException(404, "Conversation not found")
    action = db.scalar(select(ToolAction).where(ToolAction.id == action_id, ToolAction.conversation_id == conversation_id).with_for_update())
    if action is None:
        raise HTTPException(404, "Action not found")
    if action.status != "pending":
        raise HTTPException(409, "Esta propuesta ya fue procesada")
    if decision == "reject":
        action.status = "rejected"
        action.result = {"success": True, "message": "Propuesta descartada"}
    else:
        try:
            files = user_files(current_user_id)
        except (OSError, ValueError) as error:
            raise HTTPException(503, "No se pudo cargar la configuración de acceso a archivos") from error
        # Confirma el estado antes del efecto para impedir una segunda ejecución
        # si el proceso se interrumpe entre el cambio de archivo y el commit.
        action.status = "applying"
        db.commit()
        action.result = getattr(files, action.name)(**action.arguments, expected_revision=action.preview["revision"])
        action.status = "failed" if "error" in action.result else "applied"
    db.commit()
    from api.conversations.service import create_message
    summary = f"{'✅' if action.status == 'applied' else '⚠️'} Propuesta {action.status}: {action.preview['path']}. {action.result.get('message', action.result.get('error', ''))}"
    create_message(db, conversation_id, current_user_id, "assistant", summary)
    return {"status": action.status, **action.result}
