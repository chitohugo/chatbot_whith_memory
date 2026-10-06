import hashlib
import json
import logging
import time
from functools import lru_cache
from types import SimpleNamespace
from uuid import UUID
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from openai import OpenAI
from agent import Agent
from agent_runtime import build_context, run_agent
from api.database import database_session
from api.models import ChatRun, ToolAction, ToolExecution, utcnow
from config import settings
from file_service import FileSystemTools
from file_policy import FileAccessPolicy
from memory import ORMMemory
from tool_executor import ToolExecutor
from tools import tools

logger = logging.getLogger(__name__)


def user_files(user_id):
    root = settings.files.root.expanduser()
    if settings.files.scope == "per_user":
        root = root / str(user_id)
    return FileSystemTools(root, settings.files.max_bytes,
                           policy=FileAccessPolicy.load(settings.files.rules_file),
                           rules_file=settings.files.rules_file)


@lru_cache(maxsize=1)
def model_client():
    return OpenAI(api_key=settings.openrouter.api_key.get_secret_value(), base_url=settings.openrouter.base_url, timeout=settings.openrouter.timeout, max_retries=1)


def propose_action(db, run, files, name, arguments):
    preview = files.preview_edit(**arguments) if name == "edit_file" else files.preview_delete(**arguments)
    if "error" in preview:
        return preview
    fingerprint = hashlib.sha256(json.dumps([name, arguments, preview["revision"]], sort_keys=True).encode()).hexdigest()
    action = db.scalar(select(ToolAction).where(ToolAction.run_id == run.id, ToolAction.fingerprint == fingerprint))
    if not action:
        action = ToolAction(conversation_id=run.conversation_id, run_id=run.id, name=name, arguments=arguments, preview=preview, fingerprint=fingerprint)
        db.add(action)
        db.commit()
    return {"approval_required": True, "action_id": str(action.id), "operation": preview["operation"], "path": preview["path"], "message": "Propuesta preparada. El usuario debe confirmarla en la interfaz."}


def stream_run(run_id, user_id, prompt):
    started = time.monotonic()
    with database_session() as db:
        run = db.get(ChatRun, run_id)
        memory = ORMMemory(db, user_id, run.conversation_id)
        def observe(stage, call, result, duration):
            record = db.scalar(select(ToolExecution).where(ToolExecution.run_id == run.id, ToolExecution.call_id == call["id"]))
            if not record:
                try:
                    args = json.loads(call["arguments"])
                except ValueError:
                    args = {"invalid_json": True}
                record = ToolExecution(run_id=run.id, call_id=call["id"], name=call["name"], arguments=args if isinstance(args, dict) else {"invalid_arguments": True})
                db.add(record)
            record.status = stage if result is None else "error" if "error" in result else "pending" if result.get("approval_required") else stage
            record.result = result or {}
            record.duration_ms = duration
            db.commit()
            logger.info("tool_event", extra={"run_id": str(run.id), "tool": record.name, "status": record.status, "duration_ms": duration})

        agent = None
        run_status = "error"
        output = ""
        pending_output = ""
        try:
            files = user_files(user_id)
            executor = ToolExecutor()
            executor.register_tool("list_files", files.list_files)
            executor.register_tool("read_file", files.read_file)
            executor.register_tool("save_memory", memory.save_memory)
            for name in ("edit_file", "delete_file"):
                executor.register_tool(name, lambda _name=name, **args: propose_action(db, run, files, _name, args))
            agent = Agent(memory, executor, tools, observer=observe, workspace_root=str(files.root))
            # La petición actual ya fue persistida al crear el run; elimina su
            # duplicado si el fallback al historial la incluyó.
            if agent.messages and agent.messages[-1].get("role") == "user" and agent.messages[-1].get("content") == prompt:
                agent.messages.pop()
            agent.messages.append({"role": "user", "content": prompt})
            agent.prepare_system_prompt(prompt)
            for warning in agent.warnings:
                yield {"type": "warning", "value": warning}
            options = SimpleNamespace(**settings.agent.model_dump(), model=settings.openrouter.model)
            for event in run_agent(agent, model_client(), options):
                if event["type"] == "content":
                    output += event["value"]
                    pending_output += event["value"]
                elif event["type"] == "tool_completed":
                    pending_output = ""
                yield event
            run_status = "complete"
            pending_output = ""
            yield {"type": "done", "run_id": str(run.id)}
        except GeneratorExit:
            run_status = "interrupted"
            raise
        except Exception as error:
            db.rollback()
            logger.warning("chat_failed", extra={"run_id": str(run_id), "error_type": type(error).__name__})
            message = str(error) if isinstance(error, (TimeoutError, ValueError)) else "No se pudo completar la respuesta. Puedes volver a intentarlo."
            yield {"type": "error", "value": message, "run_id": str(run_id)}
        finally:
            # Un fallo nunca deja una conversación bloqueada como running.
            run = db.get(ChatRun, run_id)
            if pending_output and run_status != "complete":
                memory.save_message("assistant", pending_output + "\n\n⚠️ Respuesta interrumpida.")
            if agent is not None:
                try:
                    run.transcript = build_context(agent.messages, settings.agent.context_tokens - settings.agent.output_tokens - 4096)
                except ValueError:
                    run.transcript = []
            run.status = run_status
            run.finished_at = utcnow()
            run.metrics = {"duration_ms": int((time.monotonic() - started) * 1000), "output_characters": len(output), "tool_calls": db.scalar(select(func.count()).select_from(ToolExecution).where(ToolExecution.run_id == run.id))}
            db.commit()
            logger.info("chat_finished", extra={"run_id": str(run.id), "status": run.status, **run.metrics})
