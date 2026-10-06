import streamlit as st
from openai import OpenAI

from agent import Agent
from api_client import APIClient, APIError, SessionExpired
from config import settings
from file_service import FileSystemTools
from memory import APIMemory
from tool_executor import ToolExecutor
from tools import tools as tools_schema


st.set_page_config(
    page_title="Chatbot con Memoria",
    page_icon="🧠",
    layout="wide",
)


for key, default in (
    ("token", None),
    ("user", None),
    ("conversation_id", None),
    ("agent", None),
    ("agent_conversation_id", None),
):
    st.session_state.setdefault(key, default)


def clear_session() -> None:
    st.session_state.token = None
    st.session_state.user = None
    st.session_state.conversation_id = None
    st.session_state.agent = None
    st.session_state.agent_conversation_id = None
    st.session_state.pop("selected_conversation_id", None)


def expire_session() -> None:
    clear_session()
    st.rerun()


def render_login() -> None:
    st.title("🔐 Iniciar sesión")
    st.caption("Accede para consultar tus conversaciones y memoria.")

    with st.form("login_form"):
        email = st.text_input("Email")
        password = st.text_input("Contraseña", type="password")
        submitted = st.form_submit_button("Sign in", use_container_width=True)

    if not submitted:
        return

    if not email or not password:
        st.error("Indica tu email y contraseña.")
        return

    client = APIClient(settings.api.base_url)
    try:
        with st.spinner("Iniciando sesión..."):
            client.login(email, password)
            user = client.me()
    except APIError as error:
        if error.status_code == 401:
            st.error("Credenciales inválidas.")
        else:
            st.error(f"No se pudo iniciar sesión: {error.detail}")
        return

    st.session_state.token = client.token
    st.session_state.user = {
        "id": user["id"],
        "email": user["email"],
        "name": user["name"],
    }
    st.session_state.conversation_id = None
    st.session_state.agent = None
    st.session_state.agent_conversation_id = None
    st.rerun()


if not st.session_state.token:
    render_login()
    st.stop()


client = APIClient(
    settings.api.base_url,
    token=st.session_state.token,
    internal_key=settings.auth.secret_key,
)

with st.sidebar:
    user = st.session_state.user or {}
    st.title("💬 Conversaciones")
    st.caption(user.get("name", user.get("email", "Usuario")))
    if st.button("Sign out", use_container_width=True):
        clear_session()
        st.rerun()

try:
    conversations = client.list_conversations()
    if not conversations:
        conversation = client.create_conversation()
        conversations = [conversation]
except SessionExpired:
    expire_session()
except APIError as error:
    st.error(f"No se pudieron cargar las conversaciones: {error.detail}")
    st.stop()

conversation_ids = [conversation["id"] for conversation in conversations]
if st.session_state.conversation_id not in conversation_ids:
    st.session_state.conversation_id = conversation_ids[0]

conversation_labels = {
    conversation["id"]: (
        f"Chat {conversation['id'][:8]} · "
        f"{conversation['updated_at'].replace('T', ' ')[:16]}"
    )
    for conversation in conversations
}

with st.sidebar:
    if st.button("➕ Nuevo chat", use_container_width=True):
        try:
            new_conversation = client.create_conversation()
        except SessionExpired:
            expire_session()
        except APIError as error:
            st.error(f"No se pudo crear el chat: {error.detail}")
        else:
            st.session_state.conversation_id = new_conversation["id"]
            st.session_state.agent = None
            st.session_state.agent_conversation_id = None
            st.rerun()

    selected_conversation = st.selectbox(
        "Seleccionar conversación",
        options=conversation_ids,
        index=conversation_ids.index(st.session_state.conversation_id),
        format_func=lambda value: conversation_labels[value],
        key="selected_conversation_id",
    )
    if selected_conversation != st.session_state.conversation_id:
        st.session_state.conversation_id = selected_conversation
        st.session_state.agent = None
        st.session_state.agent_conversation_id = None
        st.rerun()


def build_agent(conversation_id: str) -> Agent:
    memory = APIMemory(client, conversation_id)
    executor = ToolExecutor()
    file_service = FileSystemTools()
    executor.register_tool("save_memory", memory.save_memory)
    executor.register_tool("list_files", file_service.list_files)
    executor.register_tool("read_file", file_service.read_file)
    executor.register_tool("edit_file", file_service.edit_file)
    executor.register_tool("delete_file", file_service.delete_file)
    return Agent(
        memory=memory,
        tool_executor=executor,
        tools_schema=tools_schema,
    )


conversation_id = st.session_state.conversation_id
if (
    st.session_state.agent is None
    or st.session_state.agent_conversation_id != conversation_id
):
    try:
        st.session_state.agent = build_agent(conversation_id)
        st.session_state.agent_conversation_id = conversation_id
    except SessionExpired:
        expire_session()
    except APIError as error:
        st.error(f"No se pudo abrir la conversación: {error.detail}")
        st.stop()

agent = st.session_state.agent

with st.sidebar:
    st.divider()
    st.subheader("🧠 Memoria")
    query_search = st.text_input(
        "Buscar recuerdos",
        placeholder="Ej: ¿Qué prefiero tomar?",
    )
    if st.button("Buscar memoria", use_container_width=True):
        if query_search:
            try:
                results = agent.memory.search_memories(query_search, limit=5)
            except SessionExpired:
                expire_session()
            except APIError as error:
                st.error(f"No se pudo buscar memoria: {error.detail}")
            else:
                if results:
                    for result in results:
                        st.info(f"• {result}")
                else:
                    st.warning("No se encontraron recuerdos relevantes.")

    new_fact = st.text_input(
        "Guardar recuerdo",
        placeholder="Ej: Le gusta el café sin azúcar",
    )
    if st.button("Guardar dato", use_container_width=True) and new_fact:
        try:
            agent.memory.save_memory(new_fact)
        except SessionExpired:
            expire_session()
        except APIError as error:
            st.error(f"No se pudo guardar el recuerdo: {error.detail}")
        else:
            st.success("¡Recuerdo guardado con éxito!")


st.title("💬 Chatbot con Memoria")
st.caption(f"Conversación activa: `{conversation_id[:8]}...`")

for message in agent.messages:
    role = message.get("role") if isinstance(message, dict) else getattr(message, "role", None)
    content = message.get("content") if isinstance(message, dict) else getattr(message, "content", None)
    if role in ["user", "assistant"] and content:
        with st.chat_message(role):
            st.markdown(content)


if user_input := st.chat_input("Escribe tu mensaje aquí..."):
    try:
        with st.chat_message("user"):
            st.markdown(user_input)
        agent.memory.save_message("user", user_input)
        agent.messages.append({"role": "user", "content": user_input})
        agent.prepare_system_prompt(user_input)

        with st.chat_message("assistant"):
            status = st.status("El agente está procesando...", expanded=True)
            status.write("🔍 Consultando memoria semántica...")
            message_placeholder = st.empty()
            accumulated_text = ""

            while True:
                stream_response = OpenAI(
                    base_url=settings.openrouter.base_url,
                    api_key=settings.openrouter.api_key,
                ).chat.completions.create(
                    model="openrouter/free",
                    messages=agent.messages,
                    tools=agent.tools,
                    stream=True,
                )

                requires_continuation = False
                for event in agent.process_stream_response(stream_response):
                    if event["type"] == "content":
                        accumulated_text += event["value"]
                        message_placeholder.markdown(accumulated_text + "▌")
                    elif event["type"] == "tool_executing":
                        status.write(
                            f"⚙️ **Ejecutando herramienta:** `{event['name']}`"
                        )
                    elif event["type"] == "requires_continuation":
                        requires_continuation = True

                if not requires_continuation:
                    break

            message_placeholder.markdown(accumulated_text)
            status.update(
                label="Respuesta completada",
                state="complete",
                expanded=False,
            )
    except SessionExpired:
        expire_session()
    except APIError as error:
        st.error(f"No se pudo guardar el mensaje: {error.detail}")
