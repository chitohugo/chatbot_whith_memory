"""Componentes de navegación y gestión; no ejecutan modelos ni herramientas."""
import streamlit as st
from conversation_ui import conversation_date, conversation_group, conversation_title
from config import settings


def clear_session():
    for key in list(st.session_state):
        del st.session_state[key]


def open_conversation(conversation_id):
    st.session_state.conversation_id = conversation_id
    st.session_state.pop("chat_prompt", None)
    st.session_state.pop("message_cache", None)


def navigation(client):
    if not st.session_state.get("conversation_id"):
        open_conversation(client.create_conversation()["id"])
    with st.sidebar:
        with st.container(key="sidebar_brand"):
            st.subheader("💬 Nexo")
            st.caption("Tu espacio para conversar y trabajar")
        if st.button("Nueva conversación", icon="➕", type="primary", key="new_chat", use_container_width=True):
            open_conversation(client.create_conversation()["id"])
            st.session_state.pop("conversation_search", None)
            st.session_state.pop("archived_chats", None)
            st.rerun()
        search = st.text_input("Buscar conversaciones", placeholder="Buscar en el historial…", key="conversation_search", label_visibility="collapsed")
        archived = st.toggle("Mostrar archivadas", key="archived_chats", on_change=lambda: st.session_state.update(history_pages=1))
        pages = st.session_state.get("history_pages", 1)
        records = []
        last_page = []
        for page in range(pages):
            last_page = client.list_conversations(limit=50, offset=page * 50, archived=archived)
            records.extend(last_page)
        records = list({record["id"]: record for record in records}.values())
        visible = [record for record in records if search.strip().casefold() in conversation_title(record).casefold()]
        st.caption("ARCHIVADAS" if archived else "HISTORIAL")
        if not visible:
            st.info("No hay conversaciones que coincidan con tu búsqueda." if search else "Aquí aparecerán tus conversaciones.")
        with st.container(height=340, border=False, key="history"):
            grouped = {"Hoy": [], "Ayer": [], "Anteriores": []}
            empty = []
            for record in visible:
                if not record.get("title") and record["id"] != st.session_state.conversation_id:
                    empty.append(record)
                else:
                    grouped[conversation_group(record["updated_at"], settings.ui.timezone)].append(record)

            def render(record):
                title = conversation_title(record)
                active = record["id"] == st.session_state.conversation_id
                date = conversation_date(record["updated_at"], settings.ui.timezone)
                st.button(title if len(title) <= 48 else title[:47] + "…", icon="💬", key=f"conversation_{record['id']}", help=f"{'Conversación abierta · ' if active else ''}{date}\n\n{title}", type="primary" if active else "secondary", use_container_width=True, on_click=open_conversation, args=(record["id"],))

            for group, items in grouped.items():
                if items:
                    st.caption(group)
                    for record in items:
                        render(record)
            if empty:
                with st.expander(f"Chats sin mensajes ({len(empty)})"):
                    for record in empty:
                        render(record)
        if len(last_page) == 50 and pages < 20 and st.button("Cargar más conversaciones"):
            st.session_state.history_pages = pages + 1
            st.rerun()
        st.divider()
    return client.conversation(st.session_state.conversation_id)


def memory_panel(client):
    with st.sidebar:
        with st.expander("🧠 Tus recuerdos"):
            st.caption("Consulta y gestiona la información que quieres recordar.")
            query = st.text_input("Buscar recuerdos")
            if st.button("Buscar memoria") and query:
                results = client.search_memories(query)
                for memory in results:
                    st.info(memory["memory_text"])
                if not results:
                    st.caption("No se encontraron recuerdos relevantes.")
            with st.form("new_memory"):
                fact = st.text_area("Nuevo recuerdo", max_chars=4000)
                if st.form_submit_button("Guardar recuerdo") and fact.strip():
                    client.save_memory(fact.strip())
                    st.success("Recuerdo guardado")
            if st.checkbox("Gestionar recuerdos guardados"):
                memories = client.list_memories()
                if memories:
                    labels = {memory["id"]: memory["memory_text"] for memory in memories}
                    selected = st.selectbox("Recuerdo", options=list(labels), format_func=lambda key: labels[key][:80])
                    edited = st.text_area("Editar recuerdo", value=labels[selected], key=f"memory_{selected}", max_chars=4000)
                    if st.button("Actualizar recuerdo") and edited.strip():
                        client.update_memory(selected, edited.strip())
                        st.rerun()
                    confirm = st.checkbox("Confirmar eliminación del recuerdo")
                    if st.button("Eliminar recuerdo", disabled=not confirm):
                        client.delete_memory(selected)
                        st.rerun()
                else:
                    st.caption("Todavía no guardaste recuerdos.")
        user = st.session_state.user
        with st.expander(f"👤 {user.get('name') or user.get('email') or 'Tu cuenta'}"):
            st.text(user.get("email", ""))
            st.button("Cerrar sesión", key="sign_out", on_click=clear_session, use_container_width=True)


def conversation_controls(client, conversation):
    conversation_id = conversation["id"]
    with st.popover("Opciones de conversación"):
        title = st.text_input("Nombre", value=conversation_title(conversation), max_chars=120, key=f"rename_{conversation_id}")
        if st.button("Guardar nombre") and title.strip():
            client.update_conversation(conversation_id, title=title.strip())
            st.rerun()
        if st.button("Restaurar conversación" if conversation.get("archived") else "Archivar conversación"):
            client.update_conversation(conversation_id, archived=not conversation.get("archived", False))
            st.rerun()
        if st.button("Preparar exportación"):
            st.session_state[f"export_{conversation_id}"] = client.export_conversation(conversation_id)
        if f"export_{conversation_id}" in st.session_state:
            st.download_button("Descargar conversación", st.session_state[f"export_{conversation_id}"], file_name=f"chat-{conversation_id}.txt")
        confirm = st.checkbox("Eliminar esta conversación y sus mensajes", key=f"delete_{conversation_id}")
        if st.button("Eliminar conversación", disabled=not confirm):
            client.delete_conversation(conversation_id)
            open_conversation(client.create_conversation()["id"])
            st.rerun()


def history(client, conversation_id):
    cache = st.session_state.get("message_cache")
    if not cache or cache["conversation_id"] != conversation_id:
        records = client.get_messages(conversation_id, limit=50)
        cache = {"conversation_id": conversation_id, "messages": records, "has_more": len(records) == 50}
        st.session_state.message_cache = cache
    if cache["has_more"] and st.button("Cargar mensajes anteriores"):
        older = client.get_messages(conversation_id, limit=50, before_id=cache["messages"][0]["id"])
        cache["messages"] = older + cache["messages"]
        cache["has_more"] = len(older) == 50
        st.rerun()
    return cache["messages"]


def pending_actions(client, conversation_id):
    for action in client.actions(conversation_id):
        preview = action["preview"]
        with st.expander(f"Revisar propuesta: {preview['operation']} {preview['path']}", expanded=True):
            st.caption("El cambio se aplicará únicamente si lo confirmas.")
            if "diff" in preview:
                st.code(preview["diff"][:12000] or "Sin cambios de contenido", language="diff")
                if len(preview["diff"]) > 12000:
                    st.download_button("Descargar vista previa completa", preview["diff"], file_name="cambio.diff", key=f"diff_{action['id']}")
            if "files" in preview:
                st.write(f"Elementos afectados: {len(preview['files'])}")
                st.code("\n".join(preview["files"][:100]))
            left, right = st.columns(2)
            if left.button("Confirmar cambio", key=f"approve_{action['id']}", type="primary"):
                result = client.decide_action(conversation_id, action["id"], "approve")
                st.session_state.flash = ("error" if "error" in result else "success", result.get("error", result.get("message", "Cambio procesado")))
                st.session_state.pop("message_cache", None)
                st.rerun()
            if right.button("Descartar", key=f"reject_{action['id']}"):
                client.decide_action(conversation_id, action["id"], "reject")
                st.session_state.pop("message_cache", None)
                st.rerun()


def activity(client, conversation_id):
    with st.expander("Actividad de herramientas"):
        if st.checkbox("Ver actividad", key=f"activity_{conversation_id}"):
            records = client.tool_history(conversation_id)
            if not records:
                st.caption("No se han usado herramientas en esta conversación.")
            for record in records:
                st.write(f"{record['name']} · {record['status']} · {record['duration_ms']} ms")
                st.json(record["arguments"])
