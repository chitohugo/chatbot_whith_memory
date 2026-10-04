-- Habilitar extensión de vectores
CREATE EXTENSION IF NOT EXISTS vector;

-- Tabla para Historial Conversacional
CREATE TABLE IF NOT EXISTS chat_messages (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(100) NOT NULL,
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabla para Memoria Semántica (Vectores)
CREATE TABLE IF NOT EXISTS agent_memories (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(100) NOT NULL,
    memory_text TEXT NOT NULL,
    embedding vector(1536),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);