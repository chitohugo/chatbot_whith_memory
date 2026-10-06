import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from agent import Agent
from tool_executor import ToolExecutor
from tools import tools


def stream_call(call_id, name="list_files", args=None, content=None, index=0):
    call = SimpleNamespace(
        index=index, id=call_id,
        function=SimpleNamespace(name=name, arguments=json.dumps(args or {})),
    )
    return [SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=content, tool_calls=[call]))])]


class AgentToolTests(unittest.TestCase):
    def setUp(self):
        self.memory = Mock()
        self.memory.load_recent_messages.return_value = []
        self.memory.search_memories.return_value = []
        self.executor = ToolExecutor()
        self.list_files = Mock(return_value={"files": ["main.py"]})
        self.executor.register_tool("list_files", self.list_files)
        self.agent = Agent(self.memory, self.executor, tools)
        self.agent.prepare_system_prompt("Lista el directorio")

    def test_duplicate_read_across_continuations_executes_once_with_matching_replies(self):
        list(self.agent.process_stream_response(stream_call("first")))
        events = list(self.agent.process_stream_response(stream_call("second", args={"directory": "."})))
        self.list_files.assert_called_once_with(directory=".")
        self.assertIn("tool_reused", [event["type"] for event in events])
        self.assertNotIn("tool_executing", [event["type"] for event in events])
        replies = [message for message in self.agent.messages if message["role"] == "tool"]
        self.assertEqual([message["tool_call_id"] for message in replies], ["first", "second"])
        self.assertEqual(replies[0]["content"], replies[1]["content"])

    def test_duplicate_calls_in_one_response_execute_once(self):
        stream = stream_call("first") + stream_call("second", index=1)
        events = list(self.agent.process_stream_response(stream))
        self.assertEqual(self.list_files.call_count, 1)
        self.assertEqual(sum(event["type"] == "tool_executing" for event in events), 1)

    def test_new_user_request_reads_again(self):
        list(self.agent.process_stream_response(stream_call("first")))
        self.list_files.return_value = {"files": ["main.py", "new.py"]}
        self.agent.prepare_system_prompt("Lista de nuevo")
        list(self.agent.process_stream_response(stream_call("second")))
        self.assertEqual(self.list_files.call_count, 2)
        self.assertIn("new.py", self.agent.messages[-1]["content"])

    def test_other_directories_are_not_reused(self):
        list(self.agent.process_stream_response(stream_call("first", args={"directory": "one"})))
        list(self.agent.process_stream_response(stream_call("second", args={"directory": "two"})))
        self.assertEqual(self.list_files.call_count, 2)

    def test_edit_and_delete_invalidate_previous_reads(self):
        for tool in ("edit_file", "delete_file"):
            with self.subTest(tool=tool):
                self.agent.prepare_system_prompt("Actualiza los archivos")
                self.list_files.reset_mock()
                self.executor.register_tool(tool, Mock(return_value={"success": True}))
                list(self.agent.process_stream_response(stream_call("before")))
                list(self.agent.process_stream_response(stream_call("write", tool, {"file_path": "new.py"})))
                list(self.agent.process_stream_response(stream_call("after")))
                self.assertEqual(self.list_files.call_count, 2)

    def test_errors_can_be_retried(self):
        self.list_files.side_effect = [{"error": "Temporary failure"}, {"files": ["main.py"]}]
        list(self.agent.process_stream_response(stream_call("first")))
        list(self.agent.process_stream_response(stream_call("retry")))
        self.assertEqual(self.list_files.call_count, 2)

    def test_read_file_reuses_identical_arguments_with_different_json_formatting(self):
        read_file = Mock(return_value={"content": "hello"})
        self.executor.register_tool("read_file", read_file)
        list(self.agent.process_stream_response(stream_call("first", "read_file", {"file_path": "main.py"})))
        second = stream_call("second", "read_file", {"file_path": "main.py"})
        second[0].choices[0].delta.tool_calls[0].function.arguments = ' { "file_path" : "main.py" } '
        list(self.agent.process_stream_response(second))
        self.assertEqual(read_file.call_count, 1)

    def test_text_before_tool_call_is_added_once(self):
        list(self.agent.process_stream_response(stream_call("first", content="Voy a listar los archivos.")))
        assistants = [message for message in self.agent.messages if message["role"] == "assistant"]
        self.assertEqual(len(assistants), 1)
        self.assertEqual(assistants[0]["tool_calls"][0]["id"], "first")
        self.memory.save_message.assert_called_once_with("assistant", "Voy a listar los archivos.")

    def test_tool_metadata_can_arrive_after_first_chunk(self):
        first = SimpleNamespace(index=0, id=None, function=None)
        last = SimpleNamespace(index=0, id="later", function=SimpleNamespace(name="list_files", arguments="{}"))
        stream = [SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=None, tool_calls=[call]))]) for call in (first, last)]
        list(self.agent.process_stream_response(stream))
        self.list_files.assert_called_once_with(directory=".")
        self.assertEqual(self.agent.messages[-1]["tool_call_id"], "later")


if __name__ == "__main__":
    unittest.main()
