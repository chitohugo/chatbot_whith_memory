from functools import lru_cache
from uuid import UUID
from sqlalchemy import func, select
from api.models import AgentMemory
from config import settings
from memory import OpenAIEmbeddingService


@lru_cache(maxsize=1)
def embedding_service():
    return OpenAIEmbeddingService(settings.openrouter.api_key.get_secret_value(), settings.openrouter.base_url, settings.openrouter.embedding_model)


def generate_embedding(text):
    vector = embedding_service().generate_embedding(text)
    if len(vector) != 1536:
        raise ValueError("El modelo de embeddings debe producir 1536 dimensiones")
    return vector


def search_memories(db, user_id: UUID, query: str, limit: int):
    vector = generate_embedding(query)
    if db.bind.dialect.name == "sqlite":
        import json
        distance = func.cosine_distance(AgentMemory.embedding, json.dumps(vector))
    else:
        distance = AgentMemory.embedding.op("<=>")(vector)
    return db.scalars(select(AgentMemory).where(AgentMemory.user_id == str(user_id), AgentMemory.embedding.is_not(None), distance <= 1 - settings.agent.memory_similarity).order_by(distance).limit(limit)).all()


def create_memory(db, user_id: UUID, memory_text: str):
    existing = db.scalar(select(AgentMemory).where(AgentMemory.user_id == str(user_id), AgentMemory.memory_text == memory_text))
    if existing:
        return existing
    memory = AgentMemory(user_id=str(user_id), memory_text=memory_text, embedding=generate_embedding(memory_text))
    db.add(memory)
    db.commit()
    return memory


def list_memories(db, user_id, limit=50, offset=0):
    return db.scalars(select(AgentMemory).where(AgentMemory.user_id == str(user_id)).order_by(AgentMemory.id.desc()).offset(offset).limit(limit)).all()


def update_memory(db, user_id, memory_id, content):
    memory = db.scalar(select(AgentMemory).where(AgentMemory.user_id == str(user_id), AgentMemory.id == memory_id))
    if memory:
        vector = generate_embedding(content)
        memory.memory_text, memory.embedding = content, vector
        db.commit()
    return memory


def delete_memory(db, user_id, memory_id):
    memory = db.scalar(select(AgentMemory).where(AgentMemory.user_id == str(user_id), AgentMemory.id == memory_id))
    if memory is None:
        return False
    db.delete(memory)
    db.commit()
    return True
