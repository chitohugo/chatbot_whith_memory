import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from file_service import FileSystemTools
from tool_executor import ToolExecutor
from agent_runtime import build_context, run_agent
from config import Settings
from file_policy import FileAccessPolicy


class FileSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "owned"
        self.files = FileSystemTools(self.root, max_bytes=1024, policy=FileAccessPolicy(default_allow=["list", "read", "create", "edit", "delete"]))

    def test_external_paths_and_symlinks_are_rejected(self):
        external = Path(self.temp.name) / "outside.txt"
        external.write_text("private")
        for value in (str(external), "../outside.txt"):
            self.assertIn("error", self.files.read_file(value))
            self.assertIn("error", self.files.edit_file(value, "private", "changed"))
            self.assertIn("error", self.files.delete_file(value))
        (self.root / "linked.txt").symlink_to(external)
        self.assertIn("error", self.files.read_file("linked.txt"))
        self.assertEqual(external.read_text(), "private")

    def test_sensitive_files_are_hidden_and_large_files_rejected(self):
        (self.root / ".env").write_text("secret")
        (self.root / "visible.txt").write_text("ok")
        (self.root / "large.txt").write_text("x"*1025)
        self.assertNotIn(".env", self.files.list_files()["files"])
        self.assertIn("error", self.files.read_file(".env"))
        self.assertIn("error", self.files.read_file("large.txt"))

    def test_preview_and_revision_protect_edits(self):
        path = self.root / "main.py"
        path.write_text("before\n")
        preview = self.files.preview_edit(file_path="main.py", prev_text="before", new_text="after")
        self.assertEqual(path.read_text(), "before\n")
        self.assertIn("+after", preview["diff"])
        path.write_text("changed elsewhere\n")
        self.assertIn("error", self.files.edit_file("main.py", "before", "after", preview["revision"]))
        self.assertEqual(path.read_text(), "changed elsewhere\n")
        preview = self.files.preview_edit(file_path="main.py", prev_text="changed elsewhere", new_text="after")
        result = self.files.edit_file("main.py", "changed elsewhere", "after", preview["revision"])
        self.assertTrue(result["success"])
        self.assertEqual(path.read_text(), "after\n")
        self.assertEqual((self.root / ".history" / result["backup"]).read_text(), "changed elsewhere\n")

    def test_delete_is_reviewed_and_backed_up(self):
        path = self.root / "file.txt"
        path.write_text("original")
        preview = self.files.preview_delete("file.txt")
        result = self.files.delete_file("file.txt", expected_revision=preview["revision"])
        self.assertTrue(result["success"])
        self.assertFalse(path.exists())
        self.assertEqual((self.root / ".history" / result["backup"]).read_text(), "original")
        self.assertIn("error", self.files.delete_file("."))

    def test_recursive_deletion_revision_includes_children(self):
        folder = self.root / "folder"
        folder.mkdir()
        (folder / "child.txt").write_text("old")
        preview = self.files.preview_delete("folder", recursive=True)
        (folder / "child.txt").write_text("new")
        self.assertIn("error", self.files.delete_file("folder", True, preview["revision"]))
        self.assertTrue(folder.exists())


class ConfigurationTests(unittest.TestCase):
    def test_nested_settings_load_dotenv_and_aliases(self):
        original = Path.cwd()
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {}, clear=True):
            os.chdir(temporary)
            try:
                Path(".env").write_text("OPENROUTER_API_KEY=dummy\nJWT_SECRET_KEY=abcdefghijklmnopqrstuvwxyz0123456789\nOPENROUTER_BASE_URL=https://example.invalid\nOPENROUTER_EMBEDDING_MODEL=embedding-test\n")
                config = Settings()
                self.assertEqual(config.openrouter.base_url, "https://example.invalid")
                self.assertEqual(config.openrouter.embedding_model, "embedding-test")
                self.assertEqual(config.openrouter.api_key.get_secret_value(), "dummy")
                self.assertNotIn("abcdefghijklmnopqrstuvwxyz", repr(config))
            finally:
                os.chdir(original)

    def test_ui_can_start_without_api_credentials(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings(_env_file=None, openrouter={"api_key": ""}, auth={"secret_key": ""})
            self.assertFalse(bool(settings.auth.secret_key.get_secret_value()), "La configuración explícita vacía no debe cargar credenciales")


class RuntimeTests(unittest.TestCase):
    def test_context_preserves_complete_tool_pairs(self):
        messages = [{"role": "system", "content": "rules"}, {"role": "user", "content": "old"*300}, {"role": "assistant", "content": "old answer"}, {"role": "user", "content": "current"}, {"role": "assistant", "content": None, "tool_calls": [{"id": "one"}]}, {"role": "tool", "tool_call_id": "one", "content": "result"}]
        bounded = build_context(messages, 500)
        self.assertEqual(bounded[-1]["tool_call_id"], bounded[-2]["tool_calls"][0]["id"])
        self.assertEqual(messages[1]["content"], "old"*300)

    def test_runtime_forces_final_response_after_tool_limit(self):
        from test_agent_tools import stream_call
        from agent import Agent
        from tools import tools
        memory = Mock()
        memory.load_recent_messages.return_value = []
        executor = ToolExecutor()
        executor.register_tool("list_files", lambda directory=".": {"files": []})
        agent = Agent(memory, executor, tools)
        agent.messages = [{"role": "user", "content": "List"}]
        provider = Mock()
        final = SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="Done", tool_calls=None))])
        provider.chat.completions.create.side_effect = [stream_call("one"), [final]]
        options = SimpleNamespace(max_seconds=10, context_tokens=16_000, output_tokens=1000, max_steps=1, model="test")
        events = list(run_agent(agent, provider, options))
        self.assertEqual(provider.chat.completions.create.call_args.kwargs["tool_choice"], "none")
        self.assertEqual(events[-1]["value"], "Done")

    def test_invalid_recursive_flag_never_reaches_tool(self):
        executor = ToolExecutor()
        tool = Mock()
        executor.register_tool("delete_file", tool)
        result = executor.execute("delete_file", '{"file_path":"folder","recursive":"false"}')
        self.assertIn("error", result)
        tool.assert_not_called()


if __name__ == "__main__":
    unittest.main()
