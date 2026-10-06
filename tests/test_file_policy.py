import ntpath
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from config import FileSettings, settings
from file_policy import FileAccessPolicy, PathRule
from file_service import FileSystemTools


class FilePolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "Documents").mkdir()
        (self.root / "Documents" / "note.txt").write_text("before", encoding="utf-8")

    def test_default_home_and_explicit_root(self):
        with patch.dict(os.environ, {}, clear=True), patch("config.Path.home", return_value=self.root):
            config = FileSettings(_env_file=None)
            self.assertEqual(config.root, self.root)
            self.assertEqual(config.scope, "shared")
            explicit = FileSettings(_env_file=None, root=self.root / "custom")
            self.assertEqual(explicit.root, self.root / "custom")

    def test_shared_root_is_not_suffixed_with_account_id(self):
        from api.chat.service import user_files
        with patch.object(settings.files, "root", self.root), patch.object(settings.files, "scope", "shared"), patch.object(settings.files, "rules_file", None):
            self.assertEqual(user_files(uuid4()).root, self.root.resolve())

    def test_read_only_default(self):
        (self.root / ".bashrc").write_text("hidden")
        (self.root / ".config").mkdir()
        (self.root / "Documents" / ".hidden.txt").write_text("hidden")
        files = FileSystemTools(self.root)
        listing = files.list_files()
        self.assertEqual(listing["files"], ["Documents"])
        self.assertEqual([entry["name"] for entry in listing["entries"]], ["Documents"])
        self.assertEqual(files.list_files("Documents")["files"], ["note.txt"])
        self.assertEqual(files.read_file("Documents/note.txt")["content"], "before")
        self.assertIn("error", files.preview_edit(file_path="Documents/new.txt", new_text="new"))
        self.assertIn("error", files.edit_file("Documents/note.txt", "before", "after"))
        self.assertIn("error", files.delete_file("Documents/note.txt"))
        self.assertEqual((self.root / "Documents/note.txt").read_text(), "before")

    def test_inherited_permissions_and_deny_precedence(self):
        policy = FileAccessPolicy(rules=[
            PathRule(path="Documents/private", deny=["list", "read", "edit", "delete"]),
            PathRule(path="Documents", allow=["create", "edit", "delete"]),
            PathRule(path="Documents/private", allow=["read", "edit"]),
        ])
        private = self.root / "Documents/private"
        private.mkdir()
        (private / "secret.txt").write_text("secret")
        files = FileSystemTools(self.root, policy=policy)
        self.assertNotIn("private", files.list_files("Documents")["files"])
        self.assertIn("error", files.list_files("Documents/private"))
        self.assertIn("error", files.read_file("Documents/private/secret.txt"))
        self.assertIn("error", files.edit_file("Documents/private/secret.txt", "secret", "changed"))
        self.assertTrue(files.edit_file("Documents/new.txt", new_text="new")["success"])
        self.assertTrue(files.edit_file("Documents/note.txt", "before", "after")["success"])
        self.assertTrue(files.delete_file("Documents/new.txt")["success"])
        self.assertFalse(policy.allows("DocumentsElsewhere/file.txt", "create"))
        self.assertIn("error", files.delete_file("Documents", recursive=True))
        self.assertEqual((private / "secret.txt").read_text(), "secret")

    def test_protected_files_and_external_paths_cannot_be_granted(self):
        policy = FileAccessPolicy(default_allow=["list", "read", "create", "edit", "delete"])
        rules_file = self.root / "rules.json"
        rules_file.write_text("{}")
        files = FileSystemTools(self.root, policy=policy, rules_file=rules_file)
        (self.root / ".env").write_text("private")
        for path in ("../outside.txt", ".env", "rules.json"):
            self.assertIn("error", files.read_file(path))
            self.assertIn("error", files.edit_file(path, new_text="changed"))
            self.assertIn("error", files.delete_file(path))
        self.assertNotIn("rules.json", files.list_files()["files"])
        self.assertIn("error", files.delete_file("."))

    def test_symlinks_cannot_bypass_rules(self):
        linked = self.root / "alias"
        try:
            linked.symlink_to(self.root / "Documents", target_is_directory=True)
        except OSError:
            self.skipTest("El sistema no permite crear enlaces simbólicos con este usuario")
        files = FileSystemTools(self.root)
        self.assertNotIn("alias", files.list_files()["files"])
        self.assertIn("error", files.read_file("alias/note.txt"))

    @unittest.skipUnless(os.name == "nt", "Solo Windows tiene junctions")
    def test_windows_junctions_are_rejected(self):
        import subprocess
        junction = self.root / "junction"
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(self.root / "Documents")], capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.addCleanup(junction.rmdir)
        files = FileSystemTools(self.root)
        self.assertNotIn("junction", files.list_files()["files"])
        self.assertIn("error", files.read_file("junction/note.txt"))

    def test_missing_invalid_or_unknown_rules_fail_closed(self):
        rules_file = self.root / "rules.json"
        with self.assertRaises(OSError):
            FileAccessPolicy.load(rules_file)
        for data in ("broken JSON", '{"default_allow":["execute"]}', '{"rules":[{"path":"../outside"}]}', '{"rules":[{"path":"C:/Users"}]}', '{"rules":[{"path":"/etc"}]}', '{"unknown":true}'):
            rules_file.write_text(data)
            with self.subTest(data=data), self.assertRaises(ValueError):
                FileAccessPolicy.load(rules_file)

    def test_windows_rule_matching_uses_case_insensitive_paths(self):
        policy = FileAccessPolicy(rules=[PathRule(path="Documents/private", deny=["read"])])
        with patch("file_policy.os.path.normcase", side_effect=ntpath.normcase):
            self.assertFalse(policy.allows("DOCUMENTS/PRIVATE/note.txt", "read"))
            self.assertTrue(policy.allows("DocumentsElsewhere/note.txt", "read"))

    @unittest.skipUnless(os.name == "nt", "Solo Windows tiene flujos alternativos")
    def test_windows_alternate_streams_and_protected_suffixes_are_rejected(self):
        files = FileSystemTools(self.root)
        self.assertTrue(files._protected("certificate.pem. "))
        self.assertIn("error", files.read_file("Documents/note.txt:stream"))

    def test_create_edit_delete_use_native_lock_and_backups(self):
        policy = FileAccessPolicy(default_allow=["list", "read", "create", "edit", "delete"])
        files = FileSystemTools(self.root, policy=policy)
        self.assertTrue(files.edit_file("Documents/new.txt", new_text="á\ntext")["success"])
        self.assertEqual(files.read_file("Documents/new.txt")["content"], "á\ntext")
        updated = files.edit_file("Documents/new.txt", "text", "updated")
        self.assertTrue(updated["success"])
        self.assertEqual((self.root / ".history" / updated["backup"]).read_text(encoding="utf-8"), "á\ntext")
        self.assertTrue(files.delete_file("Documents/new.txt")["success"])


if __name__ == "__main__":
    unittest.main()
