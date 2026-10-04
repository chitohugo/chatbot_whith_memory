import uuid
import streamlit as st
from containers import setup_container

st.set_page_config(
    page_title="Chatbot con Memoria",
    page_icon="🧠",
    layout="wide"
)


@st.cache_resource
def get_container():
    return setup_container()


container = get_container()
user_id = "hugogonzalez"

# Initialize session state for session tracking
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())


# Helper function to load/instantiate the agent for a given session
def get_agent_for_session(session_id: str):
    memory = container.memory_service(
        session_id=session_id,
        user_id=user_id
    )
    # Carga los mensajes guardados en PostgreSQL para esta sesión
    recent_messages = memory.load_recent_messages(limit=50)
    agent_instance = container.agent(memory=memory)
    agent_instance.messages = recent_messages
    return agent_instance


# Configurar agente activo en session_state
if "agent" not in st.session_state or st.session_state.get("active_session_id") != st.session_state.session_id:
    st.session_state.agent = get_agent_for_session(st.session_state.session_id)
    st.session_state.active_session_id = st.session_state.session_id

agent = st.session_state.agent
llm_client = container.embedding_service().client

# ==========================================
# SIDEBAR: Historial de Chats y Memoria Semántica
# ==========================================
with st.sidebar:
    st.title("💬 Sesiones de Chat")

    # 1. Botón para crear un Chat Limpio
    if st.button("➕ Nuevo Chat", use_container_width=True):
        new_session_id = str(uuid.uuid4())
        st.session_state.session_id = new_session_id
        st.session_state.agent = get_agent_for_session(new_session_id)
        st.session_state.active_session_id = new_session_id
        st.rerun()

    st.divider()

    # 2. Selector de Chats Anteriores desde PostgreSQL
    st.subheader("📜 Historial de Conversaciones")
    try:
        past_sessions = agent.memory.list_user_sessions(limit=15)
    except AttributeError:
        # Fallback en caso de que list_user_sessions no esté en la interfaz
        past_sessions = []

    if past_sessions:
        session_options = {
            s["session_id"]: f"Chat {s['session_id'][:8]}... ({s['last_activity'].strftime('%d/%m %H:%M')})"
            for s in past_sessions
        }

        # Asegurar que la sesión actual figure en las opciones
        if st.session_state.session_id not in session_options:
            session_options[st.session_state.session_id] = "🟢 Chat Actual (Nuevo)"


        def on_session_change():
            selected_id = st.session_state.selected_session_key
            st.session_state.session_id = selected_id
            st.session_state.agent = get_agent_for_session(selected_id)
            st.session_state.active_session_id = selected_id


        # Selector
        st.selectbox(
            "Seleccionar conversación:",
            options=list(session_options.keys()),
            format_func=lambda x: session_options[x],
            key="selected_session_key",
            index=list(session_options.keys()).index(st.session_state.session_id),
            on_change=on_session_change
        )
    else:
        st.caption("No hay chats previos guardados.")

    st.divider()

    # 3. Panel de Memoria Semántica (pgvector)
    st.title("🧠 Inspección de Memoria")
    st.markdown("Consulta en tiempo real la **memoria a largo plazo**.")

    query_search = st.text_input("Buscar recuerdos por relevancia semántica:", placeholder="Ej: ¿Qué prefiero tomar?")
    if st.button("Buscar en pgvector", use_container_width=True):
        if query_search:
            results = agent.memory.search_memories(query_search, limit=5)
            if results:
                st.subheader("Resultados:")
                for r in results:
                    st.info(f"• {r}")
            else:
                st.warning("No se encontraron recuerdos relevantes.")

    st.divider()

    st.subheader("Guardar Recuerdo Manual")
    new_fact = st.text_input("Añadir dato relevante:", placeholder="Ej: Le gusta el café sin azúcar")
    if st.button("Guardar dato", use_container_width=True):
        if new_fact:
            if agent.memory.save_memory(new_fact):
                st.success("¡Recuerdo guardado con éxito!")
            else:
                st.error("Error al guardar el recuerdo.")

# ==========================================
# CHAT PRINCIPAL
# ==========================================
st.title("💬 Chatbot con Memoria Postgres")
st.caption(f"Sesión activa: `{st.session_state.session_id[:8]}...`")

# Renderizar únicamente los mensajes de la sesión activa
for msg in agent.messages:
    if isinstance(msg, dict):
        role = msg.get("role")
        content = msg.get("content")
    else:
        role = getattr(msg, "role", None)
        content = getattr(msg, "content", None)

    if role in ["user", "assistant"] and content:
        with st.chat_message(role):
            st.markdown(content)

# Entrada del usuario
if user_input := st.chat_input("Escribe tu mensaje aquí..."):
    # 1. Mostrar mensaje del usuario
    with st.chat_message("user"):
        st.markdown(user_input)

    # 2. Guardar mensaje en memoria y en la lista local del agente
    agent.memory.save_message("user", user_input)
    agent.messages.append({"role": "user", "content": user_input})

    # 3. Preparar System Prompt consultando la memoria semántica
    agent.prepare_system_prompt(user_input)

    # 4. Bucle de streaming con st.status
    with st.chat_message("assistant"):
        status = st.status("El agente está procesando...", expanded=True)
        status.write("🔍 Consultando memoria semántica en pgvector...")

        message_placeholder = st.empty()
        accumulated_text = ""

        while True:
            # Petición con stream=True habilitado
            stream_response = llm_client.chat.completions.create(
                model="openrouter/free",
                messages=agent.messages,
                tools=agent.tools,
                stream=True
            )

            requires_continuation = False

            # Consumir el generador del agente
            for event in agent.process_stream_response(stream_response):
                if event["type"] == "content":
                    accumulated_text += event["value"]
                    message_placeholder.markdown(accumulated_text + "▌")

                elif event["type"] == "tool_executing":
                    status.write(f"⚙️ **Ejecutando herramienta:** `{event['name']}` con argumentos: `{event['args']}`")

                elif event["type"] == "requires_continuation":
                    requires_continuation = True

            if not requires_continuation:
                break

        # Limpiar el cursor final y actualizar estado
        message_placeholder.markdown(accumulated_text)
        status.update(label="Respuesta completada", state="complete", expanded=False)

        # Guardar la respuesta final del asistente
        agent.memory.save_message("assistant", accumulated_text)