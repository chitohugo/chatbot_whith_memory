import psycopg2
from dependency_injector import containers, providers

from config import settings
from memory import OpenAIEmbeddingService, DatabaseMemory
from file_service import FileSystemTools
from tool_executor import ToolExecutor
from agent import Agent
from tools import tools as tools_schema


class ApplicationContainer(containers.DeclarativeContainer):
    # 1. Inyectar directamente la instancia congelada de configuración
    config = providers.Configuration()

    # 2. Conexión a la base de datos (se crea una vez como Resource)
    db_connection = providers.Resource(
        psycopg2.connect,
        dsn=config.db.url,
    )

    # 3. Servicios de Infraestructura
    embedding_service = providers.Singleton(
        OpenAIEmbeddingService,
        api_key=config.openrouter.api_key,
        base_url=config.openrouter.base_url,
        model=config.openrouter.embedding_model,
    )

    file_service = providers.Singleton(FileSystemTools)

    # 4. Servicio de Memoria (Factory para poder re-crear con diferentes sesiones/usuarios)
    memory_service = providers.Factory(
        DatabaseMemory,
        db_connection=db_connection,
        embedding_service=embedding_service,
        session_id=config.session.id,
        user_id=config.session.user_id,
    )

    # 5. Ejecutor de Herramientas
    tool_executor = providers.Singleton(ToolExecutor)

    # 6. Agente Principal
    agent = providers.Factory(
        Agent,
        memory=memory_service,
        tool_executor=tool_executor,
        tools_schema=tools_schema,
    )


def setup_container() -> ApplicationContainer:
    """Instancia y configura el contenedor con los valores de config.py."""
    container = ApplicationContainer()

    # Cargar los valores de Pydantic directamente al objeto config del contenedor
    container.config.from_pydantic(settings)

    # Inicializar recursos gestionados (como la conexión DB)
    container.init_resources()

    # Registrar funciones concretas dentro del ejecutor
    executor = container.tool_executor()
    file_tools = container.file_service()
    memory = container.memory_service()

    executor.register_tool("save_memory", memory.save_memory)
    executor.register_tool("list_files", file_tools.list_files)
    executor.register_tool("read_file", file_tools.read_file)
    executor.register_tool("edit_file", file_tools.edit_file)
    executor.register_tool("delete_file", file_tools.delete_file)

    return container