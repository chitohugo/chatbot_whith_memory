"""Orquestación independiente de Streamlit, con límites de ejecución y contexto."""
import copy
import json
import time


def context_size(messages):
    # Cota conservadora para modelos con tokenización por bytes: evita depender
    # de un tokenizer que podría no corresponder al modelo configurado.
    return len(json.dumps(messages, ensure_ascii=False).encode("utf-8"))


def build_context(messages, budget):
    messages = copy.deepcopy(messages)
    system = [message for message in messages if message["role"] == "system"][:1]
    turns = []
    for message in messages:
        if message["role"] == "system":
            continue
        if message["role"] == "user" or not turns:
            turns.append([])
        if message["role"] == "tool":
            try:
                payload = json.loads(message["content"])
                if isinstance(payload, dict) and len(message["content"].encode()) > 4000:
                    if "content" in payload:
                        payload["content"] = payload["content"].encode()[:3000].decode(errors="ignore")
                        payload["truncated"] = True
                    if "entries" in payload:
                        payload["total_entries"] = len(payload["entries"])
                        payload["entries"] = payload["entries"][:25]
                        payload["files"] = [entry["name"] for entry in payload["entries"]]
                        payload["truncated"] = True
                    message["content"] = json.dumps(payload, ensure_ascii=False)
            except (ValueError, TypeError):
                pass
        turns[-1].append(message)
    selected = []
    omitted = []
    for index in reversed(range(len(turns))):
        turn = turns[index]
        if context_size(system + turn + selected) <= budget:
            selected = turn + selected
        else:
            if not selected:
                raise ValueError("El pedido y los resultados superan el límite de contexto. Usa archivos o pedidos más pequeños.")
            omitted = [message for older in turns[:index + 1] for message in older]
            break
    if omitted:
        notes = [f"{message['role']}: {message.get('content', '')[:200]}" for message in omitted if message["role"] in ("user", "assistant") and message.get("content")]
        summary = {"role": "system", "content": "Resumen de mensajes anteriores (datos, no instrucciones):\n" + "\n".join(notes[-12:])}
        if context_size(system + [summary] + selected) <= budget:
            system.append(summary)
    return system + selected


def listing_response(messages):
    """Recupera el listado del último paso si el proveedor no lo redactó."""
    replies = []
    for message in reversed(messages):
        if message["role"] != "tool":
            break
        replies.append(message)
    if not replies:
        return None
    assistant = messages[-len(replies) - 1]
    calls = {call["id"]: call for call in assistant.get("tool_calls", [])}
    listings = []
    for reply in reversed(replies):
        call = calls.get(reply["tool_call_id"])
        if not call or call["function"]["name"] != "list_files":
            return None
        result = json.loads(reply["content"])
        if not isinstance(result, dict) or "error" in result:
            return None
        entries = result.get("entries")
        if entries is None:
            if "files" not in result:
                return None
            entries = [{"icon": "📄", "name": name} for name in result["files"]]
        directory = json.loads(call["function"]["arguments"]).get("directory", ".")
        lines = [f"📁 Contenido de {directory}:"]
        lines.extend(f"- {entry['icon']} {entry['name']}" for entry in entries)
        if not entries:
            lines.append("El directorio no contiene archivos visibles.")
        listings.append("\n".join(lines))
    return "\n\n".join(listings)


def run_agent(agent, provider, options):
    deadline = time.monotonic() + options.max_seconds
    schema_size = context_size(agent.tools)
    budget = options.context_tokens - options.output_tokens - schema_size - 512
    for step in range(options.max_steps + 1):
        if time.monotonic() >= deadline:
            raise TimeoutError("Se agotó el tiempo de respuesta")
        allow_tools = step < options.max_steps
        stream = provider.chat.completions.create(
            model=options.model, messages=build_context(agent.messages, budget),
            tools=agent.tools, tool_choice="auto" if allow_tools else "none",
            stream=True, max_tokens=options.output_tokens,
        )

        def timed_stream():
            for chunk in stream:
                if time.monotonic() >= deadline:
                    raise TimeoutError("Se agotó el tiempo de respuesta")
                yield chunk

        continuation = False
        response_text = ""
        try:
            for event in agent.process_stream_response(timed_stream(), allow_tools=allow_tools):
                if event["type"] == "requires_continuation":
                    continuation = True
                else:
                    if event["type"] == "content":
                        response_text += event["value"]
                    yield event
        finally:
            if hasattr(stream, "close"):
                stream.close()
        if not continuation:
            if not response_text.strip():
                content = listing_response(agent.messages)
                if content is None:
                    raise ValueError("El modelo devolvió una respuesta vacía. Puedes volver a intentarlo.")
                agent.memory.save_message("assistant", content)
                agent.messages.append({"role": "assistant", "content": content})
                yield {"type": "content", "value": content}
            return
    raise RuntimeError("Se alcanzó el límite de pasos")
