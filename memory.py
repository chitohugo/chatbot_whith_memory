from typing import Protocol


class MemoryService(Protocol):
    def load_recent_messages(self, limit: int = 10) -> list[dict]: ...
    def save_message(self, role: str, content: str) -> None: ...
    def search_memories(self, query: str, limit: int = 3) -> list[str]: ...
    def save_memory(self, fact: str) -> bool: ...


class OpenAIEmbeddingService:
    def __init__(self, api_key: str, base_url: str, model: str = "text-embedding-3-small"):
        from openai import OpenAI
        self.model = model
        self.client = OpenAI(base_url=base_url, api_key=api_key, timeout=10, max_retries=1)

    def generate_embedding(self, text: str) -> list[float]:
        result = self.client.embeddings.create(input=text, model=self.model)
        return result.data[0].embedding


class ORMMemory:
    """Memoria del agente; solo se construye dentro de la API autenticada."""
    def __init__(self, db, user_id, conversation_id):
        self.db, self.user_id, self.conversation_id = db, user_id, conversation_id

    def load_recent_messages(self, limit=10):
        from sqlalchemy import select
        from api.models import ChatRun
        from api.conversations.service import list_messages
        previous = self.db.scalar(select(ChatRun).where(ChatRun.conversation_id == self.conversation_id, ChatRun.status == "complete").order_by(ChatRun.created_at.desc()).limit(1))
        if previous and previous.transcript:
            from api.models import ChatMessage
            db_statement = select(ChatMessage).where(ChatMessage.conversation_id == self.conversation_id, ChatMessage.created_at > previous.finished_at).order_by(ChatMessage.id)
            later = self.db.scalars(db_statement).all() if previous.finished_at else []
            return list(previous.transcript) + [{"role": message.role, "content": message.content} for message in later]
        return [{"role": message.role, "content": message.content} for message in list_messages(self.db, self.conversation_id, self.user_id, limit)]

    def save_message(self, role, content):
        from api.conversations.service import create_message
        if content:
            create_message(self.db, self.conversation_id, self.user_id, role, content)

    def search_memories(self, query, limit=3):
        from api.memories.service import search_memories
        return [memory.memory_text for memory in search_memories(self.db, self.user_id, query, limit)]

    def save_memory(self, fact):
        from api.memories.service import create_memory
        create_memory(self.db, self.user_id, fact)
        return True
