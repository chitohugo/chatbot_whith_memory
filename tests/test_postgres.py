"""Pruebas en PostgreSQL dedicado; nunca apuntar TEST_DATABASE_URL a datos reales."""
import os
import unittest
from pathlib import Path
from uuid import uuid4
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session


@unittest.skipUnless(os.getenv("TEST_DATABASE_URL"), "TEST_DATABASE_URL no está configurada")
class PostgreSQLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(make_url(os.environ["TEST_DATABASE_URL"]).set(drivername="postgresql+psycopg2"))
        cls.config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        cls.config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
        with cls.engine.connect() as connection:
            cls.config.attributes["connection"] = connection
            command.upgrade(cls.config, "head")
        cls.config.attributes.pop("connection", None)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def test_migrations_and_vector_search_use_orm(self):
        from unittest.mock import patch
        from api.models import AgentMemory, User
        from api.conversations.service import create_conversation, create_message, list_messages
        from api.memories.service import search_memories
        with Session(self.engine, expire_on_commit=False) as db:
            user = User(email=f"{uuid4()}@example.com", name="Test", password_hash="test")
            db.add(user)
            db.commit()
            conversation = create_conversation(db, user.id)
            create_message(db, conversation.id, user.id, "user", "Hello")
            self.assertEqual(list_messages(db, conversation.id, user.id)[0].content, "Hello")
            self.assertIsNotNone(conversation.created_at.tzinfo)
            vector = [1.0] + [0.0]*1535
            db.add(AgentMemory(user_id=str(user.id), memory_text="visible", embedding=vector))
            db.add(AgentMemory(user_id="default_user", memory_text="legacy", embedding=vector))
            db.commit()
            with patch("api.memories.service.generate_embedding", return_value=vector):
                self.assertEqual([record.memory_text for record in search_memories(db, user.id, "query", 5)], ["visible"])

    def test_upgrade_down_and_back_preserves_existing_messages(self):
        # Solo revierte la revisión nueva en la base temporal dedicada.
        with self.engine.connect() as connection:
            self.config.attributes["connection"] = connection
            command.downgrade(self.config, "0002_conversations")
            command.upgrade(self.config, "head")
        self.config.attributes.pop("connection", None)
        from api.models import Conversation
        with Session(self.engine) as db:
            for conversation in db.scalars(select(Conversation)):
                self.assertEqual(conversation.title, "Hello")
                self.assertIsNotNone(conversation.updated_at.tzinfo)


if __name__ == "__main__":
    unittest.main()
