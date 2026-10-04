from typing import Protocol, List, Any, Dict

class EmbeddingService(Protocol):
    def generate_embedding(self, text: str) -> List[float]: ...


class MemoryService(Protocol):
    def load_recent_messages(self, limit: int = 10) -> List[dict]:
        ...
    def save_message(self, role: str, content: str) -> None:
        ...
    def search_memories(self, query: str, limit: int = 3) -> List[str]:
        ...
    def save_memory(self, fact: str) -> bool:
        ...


class OpenAIEmbeddingService:
    def __init__(self, api_key: str, base_url: str, model: str = "text-embedding-3-small"):
        from openai import OpenAI
        self.model = model
        self.client = OpenAI(base_url=base_url, api_key=api_key)

    def generate_embedding(self, text: str) -> List[float]:
        res = self.client.embeddings.create(input=text, model=self.model)
        return res.data[0].embedding


class DatabaseMemory(MemoryService):
    def __init__(
        self,
        db_connection: Any,
        embedding_service: EmbeddingService,
        session_id: str = "default_session",
        user_id: str = "default_user",
    ):
        self.conn = db_connection
        self.embedding_service = embedding_service
        self.session_id = session_id
        self.user_id = user_id

    def load_recent_messages(self, limit: int = 10) -> List[dict]:
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT role, content
                    FROM (
                        SELECT id, role, content
                        FROM chat_messages
                        WHERE session_id = %s
                        ORDER BY id DESC 
                        LIMIT %s
                    ) sub
                    ORDER BY id ASC
                    """,
                    (self.session_id, limit),
                )
                rows = cur.fetchall()
                return [{"role": r[0], "content": r[1]} for r in rows]
        except Exception as e:
            print(f"[Memory Error] Error al cargar historial: {e}")
            self.conn.rollback()
            return []

    def save_message(self, role: str, content: str) -> None:
        if not content:
            return
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO chat_messages (session_id, role, content) VALUES (%s, %s, %s)",
                    (self.session_id, role, content),
                )
            self.conn.commit()
        except Exception as e:
            print(f"[Memory Error] Error al guardar mensaje: {e}")
            self.conn.rollback()

    def search_memories(self, query: str, limit: int = 3) -> List[str]:
        try:
            embedding = self.embedding_service.generate_embedding(query)
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT memory_text
                    FROM agent_memories
                    WHERE user_id = %s
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (self.user_id, str(embedding), limit),
                )
                return [r[0] for r in cur.fetchall()]
        except Exception as e:
            print(f"[Memory Error] No se pudo buscar en la memoria: {e}")
            self.conn.rollback()
            return []

    def save_memory(self, fact: str) -> bool:
        try:
            embedding = self.embedding_service.generate_embedding(fact)
            with self.conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO agent_memories (user_id, memory_text, embedding) VALUES (%s, %s, %s::vector)",
                    (self.user_id, fact, str(embedding)),
                )
            self.conn.commit()
            return True
        except Exception as e:
            print(f"[Memory Error] No se pudo guardar la memoria: {e}")
            self.conn.rollback()
            return False

    def list_user_sessions(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Obtiene los IDs de sesión únicos del usuario y la fecha de su último mensaje."""
        query = """
                SELECT session_id, MAX(created_at) as last_activity
                FROM chat_messages
                WHERE user_id = %s
                GROUP BY session_id
                ORDER BY last_activity DESC
                    LIMIT %s; \
                """
        with self.db_conn.cursor() as cursor:
            cursor.execute(query, (self.user_id, limit))
            rows = cursor.fetchall()

        return [
            {"session_id": row[0], "last_activity": row[1]}
            for row in rows
        ]