from pathlib import Path

import streamlit as st

from api_client import APIClient, APIError, SessionExpired
from config import settings
from conversation_ui import conversation_title
from tools import TOOL_ICONS
from ui_components import activity, clear_session, conversation_controls, history, memory_panel, navigation, \
    pending_actions

st.set_page_config(page_title="Nexo", page_icon="🧠", layout="wide")
st.html(Path(__file__).with_name("ui.css"))
st.session_state.setdefault("token", None)
st.session_state.setdefault("user", None)
st.session_state.setdefault("conversation_id", None)


def render_login():
    if "flash" in st.session_state:
        kind, message = st.session_state.pop("flash")
        getattr(st, kind)(message)
    st.title("🔐 Iniciar sesión en Nexo")
    st.caption("Empieza una conversación nueva y conserva tu historial.")
    with st.form("login_form"):
        email = st.text_input("Email")
        password = st.text_input("Contraseña", type="password")
        submitted = st.form_submit_button("Iniciar sesión", type="primary", use_container_width=True)
    if not submitted:
        return
    if not email or not password:
        st.error("Indica tu email y contraseña.")
        return
    client = APIClient(settings.api.base_url, timeout=settings.api.timeout)
    try:
        with st.spinner("Iniciando sesión…"):
            client.login(email, password)
            user = client.me()
            conversation = client.create_conversation()
    except APIError as error:
        st.error("Credenciales inválidas." if error.status_code == 401 else f"No se pudo iniciar sesión: {error.detail}")
        return
    st.session_state.token = client.token
    st.session_state.user = user
    st.session_state.conversation_id = conversation["id"]
    st.session_state.pop("conversation_search", None)
    st.session_state.pop("message_cache", None)
    st.rerun()


def render_chat(client):
    conversation = navigation(client)
    memory_panel(client)
    conversation_id = conversation["id"]
    messages = history(client, conversation_id)
    if not messages:
        with st.container(key="welcome"):
            name = (st.session_state.user.get("name") or "").split()
            st.caption("NUEVA CONVERSACIÓN")
            st.title(f"Hola, {name[0]}" if name else "Hola")
            st.header("¿En qué te ayudo hoy?")
            st.write("Escribe tu mensaje o elige una idea para empezar.")
        with st.container(key="suggestions"):
            suggestions = (("Explorar archivos", "📁", "Muéstrame los archivos de mi espacio de trabajo."), ("Revisar código", "🐍", "Ayúdame a revisar el código de "), ("Guardar un recuerdo", "🧠", "Recuerda que "))
            for column, (label, icon, prompt) in zip(st.columns(3), suggestions):
                if column.button(label, icon=icon, key=f"suggestion_{icon}", use_container_width=True):
                    st.session_state.chat_prompt = prompt
            st.caption("La idea se copia en el mensaje. Puedes editarla antes de enviarla.")
    else:
        st.caption("CONVERSACIÓN ABIERTA")
        st.text(conversation_title(conversation))
    conversation_controls(client, conversation)
    if "flash" in st.session_state:
        kind, message = st.session_state.pop("flash")
        getattr(st, kind)(message)
    for message in messages:
        if message["role"] in ("user", "assistant"):
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
    pending_actions(client, conversation_id)
    activity(client, conversation_id)
    if prompt := st.chat_input("Escribe un mensaje para empezar…" if not messages else "Escribe tu siguiente mensaje…", key="chat_prompt", max_chars=16_000):
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            status = st.status("Preparando respuesta…", expanded=True)
            placeholder = st.empty()
            content = ""
            error_message = None
            try:
                for event in client.stream_chat(conversation_id, prompt):
                    if event["type"] == "content":
                        content += event["value"]
                        placeholder.markdown(content + "▌")
                    elif event["type"] == "tool_executing":
                        status.write(f"{TOOL_ICONS.get(event['name'], '⚙️')} Ejecutando `{event['name']}`")
                    elif event["type"] == "tool_reused":
                        status.write(f"♻️ Usando el resultado ya obtenido de `{event['name']}`")
                    elif event["type"] == "warning":
                        status.write(event["value"])
                    elif event["type"] == "error":
                        error_message = event["value"]
            except SessionExpired:
                raise
            except APIError as error:
                error_message = error.detail
            placeholder.markdown(content)
            status.update(label="Respuesta interrumpida" if error_message else "Respuesta completada", state="error" if error_message else "complete", expanded=bool(error_message))
            if error_message:
                st.session_state.flash = ("error", error_message)
        st.session_state.pop("message_cache", None)
        st.session_state.pop(f"export_{conversation_id}", None)
        st.rerun()


if not st.session_state.token:
    render_login()
    st.stop()

client = APIClient(settings.api.base_url, token=st.session_state.token, timeout=settings.api.timeout)
try:
    render_chat(client)
except SessionExpired:
    clear_session()
    st.session_state.flash = ("warning", "Tu sesión venció. Inicia sesión nuevamente.")
    st.rerun()
except APIError as error:
    st.error(error.detail)
    if st.button("Reintentar conexión"):
        st.rerun()
