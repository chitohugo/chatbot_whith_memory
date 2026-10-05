from uuid import UUID

from config import settings
from memory import OpenAIEmbeddingService


_embedding_service = OpenAIEmbeddingService(
    api_key=settings.openrouter.api_key,
    base_url=settings.openrouter.base_url,
    model=settings.openrouter.embedding_model,
)


def search_memories(db, user_id: UUID, query: str, limit: int):
    embedding = _embedding_service.generate_embedding(query)
    vector = str(embedding)

    with db.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, memory_text, created_at
            FROM agent_memories
            WHERE user_id = %s
              AND embedding IS NOT NULL
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """,
            (str(user_id), vector, limit),
        )
        return cursor.fetchall()


def create_memory(db, user_id: UUID, memory_text: str):
    embedding = _embedding_service.generate_embedding(memory_text)

    with db.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO agent_memories (user_id, memory_text, embedding)
            VALUES (%s, %s, %s::vector)
            RETURNING id, memory_text, created_at
            """,
            (str(user_id), memory_text, str(embedding)),
        )
        memory = cursor.fetchone()

    db.commit()
    return memory
