import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from api_client import APIError
from conversation_ui import conversation_date, conversation_group, conversation_title


class ConversationFormattingTests(unittest.TestCase):
    def test_titles(self):
        self.assertEqual(conversation_title({"title": " Revisar\n archivos "}), "Revisar archivos")
        self.assertEqual(conversation_title({"title": None}), "Nueva conversación")

    def test_local_dates(self):
        now = datetime(2026, 10, 6, 17, tzinfo=timezone.utc)
        zone = "America/Argentina/Buenos_Aires"
        self.assertEqual(conversation_date("2026-10-06T16:35:00Z", zone, now), "Hoy, 13:35")
        self.assertEqual(conversation_group("2026-10-06T01:35:00Z", zone, now), "Ayer")
        self.assertEqual(conversation_group("2026-10-01T16:35:00Z", zone, now), "Anteriores")


class ConversationSidebarTests(unittest.TestCase):
    def setUp(self):
        self.conversations = [
            {"id": "first", "title": "Revisar archivos", "updated_at": "2026-10-06T16:35:00Z"},
            {"id": "second", "title": "Configurar Docker", "updated_at": "2026-10-05T16:35:00Z"},
        ]
        self.messages = {"first": [{"id": 1, "role": "user", "content": "Revisar archivos"}], "second": [{"id": 2, "role": "user", "content": "Configurar Docker"}]}
        self.created_count = 0
        self.fail_creation = False
        self.stream_count = 0
        test = self

        class LocalClient:
            def __init__(self, *args, **kwargs):
                self.token = kwargs.get("token")

            def login(self, email, password):
                self.token = "new-login-token"

            def me(self):
                return {"id": "user", "email": "user@example.com", "name": "Usuario de prueba"}

            def list_conversations(self, limit=50, offset=0, archived=False):
                return [record for record in test.conversations if record.get("archived", False) == archived][offset:offset + limit]

            def conversation(self, conversation_id):
                return next(record for record in test.conversations if record["id"] == conversation_id)

            def create_conversation(self):
                if test.fail_creation:
                    raise APIError(503, "No se pudo crear la conversación")
                test.created_count += 1
                conversation_id = "new" if test.created_count == 1 else f"new-{test.created_count}"
                conversation = {"id": conversation_id, "title": None, "updated_at": "2026-10-06T17:00:00Z"}
                test.conversations.insert(0, conversation)
                test.messages[conversation_id] = []
                return conversation

            def get_messages(self, conversation_id, limit=50, before_id=None):
                records = test.messages.get(conversation_id, [])
                if before_id is not None:
                    records = [record for record in records if record["id"] < before_id]
                return records[-limit:]

            def actions(self, conversation_id):
                return []

            def stream_chat(self, conversation_id, prompt):
                test.stream_count += 1
                test.messages[conversation_id].extend([{"id": 1000, "role": "user", "content": prompt}, {"id": 1001, "role": "assistant", "content": "📁 main.py"}])
                yield {"type": "content", "value": "📁 main.py"}
                yield {"type": "done"}

            def update_conversation(self, conversation_id, **changes):
                self.conversation(conversation_id).update(changes)

            def tool_history(self, conversation_id):
                return []

        config = ModuleType("config")
        config.settings = SimpleNamespace(api=SimpleNamespace(base_url="http://unused", timeout=150), ui=SimpleNamespace(timezone="America/Argentina/Buenos_Aires"))
        self.config_patch = patch.dict(sys.modules, {"config": config})
        self.client_patch = patch("api_client.APIClient", LocalClient)
        self.config_patch.start()
        self.client_patch.start()
        self.addCleanup(self.config_patch.stop)
        self.addCleanup(self.client_patch.stop)
        self.app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"))
        self.app.session_state["token"] = "test-token"
        self.app.session_state["conversation_id"] = "first"
        self.app.session_state["user"] = {"name": "Usuario de prueba"}
        self.app.run()
        self.assertEqual(len(self.app.exception), 0)

    def sign_in(self):
        self.app.button(key="sign_out").click().run()
        self.app.text_input[0].set_value("user@example.com")
        self.app.text_input[1].set_value("password")
        next(button for button in self.app.button if button.label == "Iniciar sesión").click().run()

    def test_switching_conversations(self):
        self.app.button(key="conversation_second").click().run()
        self.assertEqual(len(self.app.exception), 0)
        self.assertEqual(self.app.session_state["conversation_id"], "second")
        self.assertIn("Configurar Docker", [element.value for element in self.app.text])

    def test_search_does_not_switch_active_chat(self):
        self.app.text_input(key="conversation_search").set_value("DOCKER").run()
        self.assertEqual([button.label for button in self.app.button if (button.key or "").startswith("conversation_")], ["Configurar Docker"])
        self.app.text_input(key="conversation_search").set_value("inexistente").run()
        self.assertEqual(self.app.session_state["conversation_id"], "first")

    def test_each_login_opens_a_new_chat(self):
        self.sign_in()
        self.assertEqual(len(self.app.exception), 0)
        self.assertEqual(self.app.session_state["conversation_id"], "new")
        self.app.run()
        self.assertEqual(self.created_count, 1)
        self.sign_in()
        self.assertEqual(self.app.session_state["conversation_id"], "new-2")

    def test_failed_creation_stays_on_login(self):
        self.fail_creation = True
        self.sign_in()
        self.assertEqual(len(self.app.exception), 0)
        self.assertIsNone(self.app.session_state["token"])
        self.assertIn("No se pudo crear la conversación", self.app.error[0].value)

    def test_suggestion_is_not_sent_automatically(self):
        self.app.button(key="new_chat").click().run()
        self.app.button(key="suggestion_📁").click().run()
        self.assertEqual(len(self.app.exception), 0)
        self.assertEqual(self.stream_count, 0)
        self.assertIn("espacio de trabajo", self.app.chat_input[0].proto.value)

    def test_submit_is_not_repeated_on_rerun(self):
        self.app.chat_input[0].set_value("Lista los archivos").run()
        self.assertEqual(len(self.app.exception), 0)
        self.app.run()
        self.assertEqual(self.stream_count, 1)
        self.assertIn("📁 main.py", [element.value for element in self.app.markdown])

    def test_older_messages_can_be_loaded(self):
        self.messages["first"] = [{"id": index, "role": "user", "content": f"Mensaje {index}"} for index in range(1, 81)]
        del self.app.session_state["message_cache"]
        self.app.run()
        self.assertEqual(len(self.app.chat_message), 50)
        next(button for button in self.app.button if button.label == "Cargar mensajes anteriores").click().run()
        self.assertEqual(len(self.app.exception), 0)
        self.assertEqual(len(self.app.chat_message), 80)

    def test_archived_filter_retains_current_chat(self):
        self.conversations[1]["archived"] = True
        self.app.toggle(key="archived_chats").set_value(True).run()
        self.assertEqual(len(self.app.exception), 0)
        self.assertEqual(self.app.session_state["conversation_id"], "first")
        self.assertEqual(self.app.button(key="conversation_second").label, "Configurar Docker")


if __name__ == "__main__":
    unittest.main()
