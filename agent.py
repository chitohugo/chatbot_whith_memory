# agent.py
import json
from typing import Any, Generator, Dict, List
from memory import MemoryService
from tool_executor import ToolExecutor


class Agent:

    def __init__(
        self,
        memory: MemoryService,
        tool_executor: ToolExecutor,
        tools_schema: List[Dict[str, Any]],
    ):
        self.memory = memory
        self.tool_executor = tool_executor
        self.tools = tools_schema
        self.messages: List[Dict[str, Any]] = (
            self.memory.load_recent_messages(limit=10)
        )

    def prepare_system_prompt(self, user_query: str) -> None:
        relevant_memories = self.memory.search_memories(user_query, limit=3)

        memories_str = (
            "\n".join([f"- {m}" for m in relevant_memories])
            if relevant_memories
            else "Sin recuerdos previos."
        )

        system_content = f"""You are a helpful assistant.

### MEMORIA Y CONTEXTO RELEVANTE DEL USUARIO:
{memories_str}

Instrucciones: Usa la memoria anterior para personalizar tus respuestas. Si el usuario te pide recordar una preferencia o dato relevante, usa la función `save_memory`."""

        if self.messages and self._get_role(self.messages[0]) == "system":
            self._set_content(self.messages[0], system_content)
        else:
            self.messages.insert(
                0, {"role": "system", "content": system_content}
            )

    def process_stream_response(
        self, stream_response: Any
    ) -> Generator[Dict[str, Any], None, None]:
        """Procesa el flujo streaming devuelto por OpenAI."""
        full_content = ""
        tool_calls_buffer: Dict[int, Dict[str, Any]] = {}

        for chunk in stream_response:
            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta

            # 1. Acumular y emitir tokens de texto
            if delta.content:
                full_content += delta.content
                yield {"type": "content", "value": delta.content}

            # 2. Reconstruir llamadas a herramientas (tool_calls)
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in tool_calls_buffer:
                        tool_calls_buffer[idx] = {
                            "id": tc.id,
                            "name": tc.function.name,
                            "arguments": "",
                        }
                    if tc.function.arguments:
                        tool_calls_buffer[idx][
                            "arguments"
                        ] += tc.function.arguments

        # Guardar en memoria si hubo respuesta de texto
        if full_content:
            self.messages.append(
                {"role": "assistant", "content": full_content}
            )
            self.memory.save_message("assistant", full_content)

        # Ejecutar herramientas solicitadas
        if tool_calls_buffer:
            assistant_msg = {
                "role": "assistant",
                "content": full_content or None,
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": tc["arguments"],
                        },
                    }
                    for tc in tool_calls_buffer.values()
                ],
            }
            self.messages.append(assistant_msg)

            for tc in tool_calls_buffer.values():
                fn_name = tc["name"]
                args_json = tc["arguments"]

                yield {"type": "tool_executing", "name": fn_name, "args": args_json}

                result = self.tool_executor.execute(fn_name, args_json)

                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": json.dumps(result),
                    }
                )

            yield {"type": "requires_continuation"}

    @staticmethod
    def _get_role(msg: Any) -> str:
        return (
            msg.get("role")
            if isinstance(msg, dict)
            else getattr(msg, "role", "")
        )

    @staticmethod
    def _set_content(msg: Any, content: str) -> None:
        if isinstance(msg, dict):
            msg["content"] = content
        else:
            setattr(msg, "content", content)