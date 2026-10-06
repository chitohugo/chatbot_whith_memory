import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID, uuid4
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from api.main import app
from api.database import get_db_session
from api.models import AgentMemory, Base, ChatRun, ToolExecution, User, utcnow
from api.auth.service import create_access_token, hash_password
from config import settings


class APITests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        @event.listens_for(self.engine, "connect")
        def sqlite_setup(connection, record):
            connection.execute("PRAGMA foreign_keys=ON")
            def distance(left, right):
                import math
                a, b = json.loads(left), json.loads(right)
                return 1 - sum(x*y for x,y in zip(a,b)) / (math.sqrt(sum(x*x for x in a))*math.sqrt(sum(x*x for x in b)))
            connection.create_function("cosine_distance", 2, distance)
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)
        def override():
            with self.sessions() as db:
                yield db
        app.dependency_overrides[get_db_session] = override
        self.addCleanup(app.dependency_overrides.clear)
        self.addCleanup(self.engine.dispose)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root_patch = patch.object(settings.files, "root", Path(self.temp.name))
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        self.scope_patch = patch.object(settings.files, "scope", "per_user")
        self.scope_patch.start()
        self.addCleanup(self.scope_patch.stop)
        rules_path = Path(self.temp.name) / "rules.json"
        rules_path.write_text(json.dumps({"default_allow": ["list", "read", "create", "edit", "delete"], "rules": []}))
        self.rules_patch = patch.object(settings.files, "rules_file", rules_path)
        self.rules_patch.start()
        self.addCleanup(self.rules_patch.stop)
        self.client = TestClient(app)
        self.first, self.second = uuid4(), uuid4()
        with self.sessions() as db:
            db.add_all([User(id=self.first, email="first@example.com", name="First", password_hash=hash_password("password123")), User(id=self.second, email="second@example.com", name="Second", password_hash=hash_password("password123"))])
            db.commit()
        self.headers = {"Authorization": "Bearer " + create_access_token(self.first)}
        self.other = {"Authorization": "Bearer " + create_access_token(self.second)}

    def new_chat(self):
        response = self.client.post("/conversations", headers=self.headers, json={})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["id"]

    def test_ownership_and_management(self):
        chat = self.new_chat()
        self.assertEqual(self.client.get(f"/conversations/{chat}", headers=self.other).status_code, 404)
        self.assertEqual(self.client.get(f"/conversations/{chat}/messages", headers=self.other).status_code, 404)
        self.assertEqual(self.client.delete(f"/conversations/{chat}", headers=self.other).status_code, 404)
        response = self.client.patch(f"/conversations/{chat}", headers=self.headers, json={"title": "Nuevo título", "archived": True})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/conversations", headers=self.headers).json(), [])
        self.assertEqual(self.client.get("/conversations?archived=true", headers=self.headers).json()[0]["title"], "Nuevo título")
        self.assertEqual(self.client.delete(f"/conversations/{chat}", headers=self.headers).status_code, 204)

    def test_invalid_and_expired_tokens(self):
        import jwt
        token = jwt.encode({"sub": str(self.first), "exp": utcnow() - timedelta(minutes=1)}, settings.auth.secret_key.get_secret_value(), algorithm="HS256")
        self.assertEqual(self.client.get("/conversations", headers={"Authorization": "Bearer " + token}).status_code, 401)
        self.assertEqual(self.client.get("/conversations", headers={"Authorization": "Bearer invalid"}).status_code, 401)
        self.assertEqual(self.client.get("/conversations").status_code, 401)

    def test_login_rate_limit_and_duplicate_registration(self):
        with patch.object(settings.auth, "login_attempts", 2):
            for _ in range(2):
                self.assertEqual(self.client.post("/auth/login", json={"email": "first@example.com", "password": "wrong"}).status_code, 401)
            self.assertEqual(self.client.post("/auth/login", json={"email": "first@example.com", "password": "password123"}).status_code, 429)
        response = self.client.post("/auth/register", json={"email": "first@example.com", "password": "password123", "name": "Duplicate"})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.client.post("/auth/register", json={"email": "new@example.com", "password": "password123", "name": "  "}).status_code, 422)

    def test_memory_crud_and_legacy_isolation(self):
        vector = [1.0] + [0.0]*1535
        with self.sessions() as db:
            db.add(AgentMemory(user_id="default_user", memory_text="legacy", embedding=vector))
            db.commit()
        with patch("api.memories.service.generate_embedding", return_value=vector):
            created = self.client.post("/memories", headers=self.headers, json={"memory_text": "Me gusta el café"})
            self.assertEqual(created.status_code, 201, created.text)
            memory_id = created.json()["id"]
            self.assertEqual(self.client.get("/memories", headers=self.other).json(), [])
            self.assertEqual(self.client.patch(f"/memories/{memory_id}", headers=self.other, json={"memory_text": "Otro"}).status_code, 404)
            self.assertEqual(self.client.patch(f"/memories/{memory_id}", headers=self.headers, json={"memory_text": "Prefiero té"}).status_code, 200)
            results = self.client.post("/memories/search", headers=self.headers, json={"query": "bebidas"}).json()
            self.assertEqual([item["memory_text"] for item in results], ["Prefiero té"])
            self.assertEqual(self.client.delete(f"/memories/{memory_id}", headers=self.headers).status_code, 204)

    def test_stream_duplicate_reads_and_idempotent_request(self):
        from test_agent_tools import stream_call
        chat = self.new_chat()
        request_id = str(uuid4())
        final = SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="Listado terminado", tool_calls=None))])
        provider = unittest.mock.Mock()
        provider.chat.completions.create.side_effect = [stream_call("first"), stream_call("second", args={"directory": "."}), [final]]
        with patch("api.chat.service.database_session", self.sessions), patch("api.chat.service.model_client", return_value=provider), patch("memory.ORMMemory.search_memories", side_effect=RuntimeError("offline")), patch("file_service.FileSystemTools.list_files", return_value={"files": ["main.py"]}) as listing:
            response = self.client.post(f"/conversations/{chat}/chat", headers=self.headers, json={"content": "Lista archivos", "request_id": request_id})
            self.assertEqual(response.status_code, 200, response.text)
            events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
            self.assertIn("warning", [event["type"] for event in events])
            self.assertEqual(events[-1]["type"], "done", events)
            self.assertEqual(listing.call_count, 1)
        self.assertEqual(self.client.post(f"/conversations/{chat}/chat", headers=self.headers, json={"content": "Lista archivos", "request_id": request_id}).status_code, 409)
        with self.sessions() as db:
            run = db.scalar(select(ChatRun))
            self.assertEqual(run.status, "complete")
            self.assertEqual(len(db.scalars(select(ToolExecution)).all()), 2)
        self.assertIn("Listado terminado", self.client.get(f"/conversations/{chat}/export", headers=self.headers).text)

    def test_reviewed_changes_cannot_be_applied_twice(self):
        from api.chat.service import propose_action, user_files
        chat = self.new_chat()
        from uuid import UUID
        with self.sessions() as db:
            run = ChatRun(conversation_id=UUID(chat), request_id=uuid4())
            db.add(run)
            db.commit()
            proposal = propose_action(db, run, user_files(self.first), "edit_file", {"file_path": "main.py", "new_text": "print('hello')", "prev_text": None})
        path = Path(self.temp.name) / str(self.first) / "main.py"
        self.assertFalse(path.exists())
        action_id = proposal["action_id"]
        self.assertEqual(self.client.post(f"/conversations/{chat}/actions/{action_id}/approve", headers=self.other).status_code, 404)
        self.assertEqual(self.client.post(f"/conversations/{chat}/actions/{action_id}/approve", headers=self.headers).json()["status"], "applied")
        self.assertEqual(path.read_text(), "print('hello')")
        self.assertEqual(self.client.post(f"/conversations/{chat}/actions/{action_id}/approve", headers=self.headers).status_code, 409)

    def test_empty_model_response_after_listing_returns_and_persists_results(self):
        from test_agent_tools import stream_call
        for populated in (False, True):
            with self.subTest(populated=populated):
                chat = self.new_chat()
                root = Path(self.temp.name) / str(self.first)
                root.mkdir(exist_ok=True)
                if populated:
                    (root / "main.py").write_text("print('hello')")
                    (root / "docs").mkdir()
                empty = SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=" \n", tool_calls=None))])
                provider = unittest.mock.Mock()
                provider.chat.completions.create.side_effect = [stream_call("listing"), [empty]]
                with patch("api.chat.service.database_session", self.sessions), patch("api.chat.service.model_client", return_value=provider), patch("memory.ORMMemory.search_memories", return_value=[]):
                    response = self.client.post(f"/conversations/{chat}/chat", headers=self.headers, json={"content": "Lista mi directorio", "request_id": str(uuid4())})
                events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
                self.assertEqual(events[-1]["type"], "done", events)
                content = "".join(event["value"] for event in events if event["type"] == "content").strip()
                if populated:
                    self.assertIn("- 📁 docs", content)
                    self.assertIn("- 🐍 main.py", content)
                    self.assertNotIn("`", content)
                else:
                    self.assertIn("no contiene archivos visibles", content)
                messages = self.client.get(f"/conversations/{chat}/messages", headers=self.headers).json()
                self.assertEqual(messages[-1]["content"], content)
                with self.sessions() as db:
                    run = db.scalar(select(ChatRun).where(ChatRun.conversation_id == UUID(chat)))
                    self.assertEqual(run.status, "complete")
                    self.assertEqual(run.transcript[-1]["content"], content)

    def test_empty_model_response_without_listing_returns_error(self):
        chat = self.new_chat()
        provider = unittest.mock.Mock()
        provider.chat.completions.create.return_value = []
        with patch("api.chat.service.database_session", self.sessions), patch("api.chat.service.model_client", return_value=provider), patch("memory.ORMMemory.search_memories", return_value=[]):
            response = self.client.post(f"/conversations/{chat}/chat", headers=self.headers, json={"content": "Hola", "request_id": str(uuid4())})
        self.assertIn("respuesta vacía", response.text)
        self.assertNotIn('"type": "done"', response.text)
        with self.sessions() as db:
            self.assertEqual(db.scalar(select(ChatRun)).status, "error")

    def test_model_failure_marks_run_and_returns_stream_error(self):
        chat = self.new_chat()
        with patch("api.chat.service.database_session", self.sessions), patch("api.chat.service.model_client", side_effect=RuntimeError("offline")), patch("memory.ORMMemory.search_memories", return_value=[]):
            result = self.client.post(f"/conversations/{chat}/chat", headers=self.headers, json={"content": "Hola", "request_id": str(uuid4())})
            self.assertIn('"type": "error"', result.text)
        with self.sessions() as db:
            self.assertEqual(db.scalar(select(ChatRun)).status, "error")

    def test_changed_rules_block_previously_approved_write(self):
        from api.chat.service import propose_action, user_files
        chat = self.new_chat()
        with self.sessions() as db:
            run = ChatRun(conversation_id=UUID(chat), request_id=uuid4())
            db.add(run)
            db.commit()
            proposal = propose_action(db, run, user_files(self.first), "edit_file", {"file_path": "new.txt", "new_text": "hello", "prev_text": None})
        settings.files.rules_file.write_text('{"default_allow":["list","read"],"rules":[]}')
        response = self.client.post(f"/conversations/{chat}/actions/{proposal['action_id']}/approve", headers=self.headers)
        self.assertEqual(response.json()["status"], "failed", response.text)
        self.assertIn("reglas", response.json()["error"])
        self.assertFalse((Path(self.temp.name) / str(self.first) / "new.txt").exists())

    def test_invalid_rules_return_stream_error_and_finish_run(self):
        chat = self.new_chat()
        settings.files.rules_file.write_text("invalid")
        with patch("api.chat.service.database_session", self.sessions):
            response = self.client.post(f"/conversations/{chat}/chat", headers=self.headers, json={"content": "Lista archivos", "request_id": str(uuid4())})
        self.assertIn('"type": "error"', response.text)
        with self.sessions() as db:
            self.assertEqual(db.scalar(select(ChatRun)).status, "error")


if __name__ == "__main__":
    unittest.main()
