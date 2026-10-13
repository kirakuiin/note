"""定向提交的范围、失败语义和临时 SVN 仓库集成测试，不连接业务仓库。"""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import svn_commit as commit  # noqa: E402

MESSAGE = "finish #844233 【全部服务器放出】指挥系统设置界面描述优化：保留字体并调整留白"
URL = "svn://example.test/products/wzimage/trunk"
REPOSITORY = "svn://example.test"
PREFIX = "/products/wzimage/trunk/"


class CommitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="svn commit ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.message_file = self.root / "message.txt"
        self.message_file.write_text(MESSAGE, encoding="utf-8")
        (self.root / "a.py").write_text("x = 1", encoding="utf-8")
        (self.root / "new.txt").write_text("说明", encoding="utf-8")
        (self.root / "unrelated.py").write_text("x = 2", encoding="utf-8")
        self.statuses = {"a.py": {"item": "modified", "props": "none"},
                         "new.txt": {"item": "unversioned", "props": "none"}}
        self.calls = []
        self.failed_commit = False
        self.bad_log = False
        self.extra_log_path = False
        self.foreign = False
        self.commit_message_bytes = None
        self.last_targets = []

    def fake_svn(self, root, *args):
        self.calls.append(args)
        command = args[0]
        if command == "info":
            target = args[-1].removesuffix("@").removeprefix("./")
            tree = ET.Element("info")
            entry = ET.SubElement(tree, "entry", kind="dir" if target == "." else "file")
            ET.SubElement(entry, "url").text = URL if target == "." else URL + "/" + target
            repository = ET.SubElement(entry, "repository")
            ET.SubElement(repository, "root").text = REPOSITORY
            wc_info = ET.SubElement(entry, "wc-info")
            ET.SubElement(wc_info, "wcroot-abspath").text = str(self.root / "external") if self.foreign and target != "." else str(self.root)
        elif command == "status":
            target = args[-1].removesuffix("@").removeprefix("./")
            tree = ET.Element("status")
            entry = ET.SubElement(ET.SubElement(tree, "target", path=target), "entry", path=target)
            ET.SubElement(entry, "wc-status", **self.statuses[target])
        elif command == "add":
            return b"Added new.txt"
        elif command == "commit":
            if self.failed_commit:
                raise commit.precommit.PrecheckError("connection lost")
            self.commit_message_bytes = Path(args[args.index("-F") + 1]).read_bytes()
            self.last_targets = [target.removesuffix("@").removeprefix("./") for target in args[args.index("-F") + 2:]]
            return b"Committed revision 42."
        elif command == "log":
            tree = ET.Element("log")
            entry = ET.SubElement(tree, "logentry", revision="42")
            ET.SubElement(entry, "msg").text = "wrong message" if self.bad_log else MESSAGE
            paths = ET.SubElement(entry, "paths")
            for target in self.last_targets + (["unrelated.py"] if self.extra_log_path else []):
                ET.SubElement(paths, "path").text = PREFIX + target
        else:
            raise AssertionError(args)
        return ET.tostring(tree, encoding="utf-8")

    def submit(self, paths=None, apply=False):
        with patch.object(commit, "run_svn", side_effect=self.fake_svn):
            return commit.submit(self.root, paths or ["a.py", "new.txt"], self.message_file, apply)

    def test_known_formal_branch_names_and_dates(self):
        self.assertEqual(commit.branch_kind(URL), "trunk")
        for name in commit.workspace.PERIODIC_TYPES:
            for suffix in (name, name + "_2026_10_13"):
                with self.subTest(name=suffix):
                    self.assertEqual(commit.branch_kind("svn://example.test/wzimage/branchs/2026_ship/" + suffix), "周期分支")
        for path in ("branchs/2026_dev/test", "branchs/2026_ship/test_bugfix", "branchs/2026_ship/research"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                commit.branch_kind("svn://example.test/wzimage/" + path)

    def test_preview_is_read_only_and_reports_exact_selection(self):
        result = self.submit()
        self.assertNotIn("error", result)
        self.assertEqual(result["changed_count"], 2)
        self.assertEqual(result["will_add"], ["new.txt"])
        self.assertEqual([entry["path"] for entry in result["entries"]], ["a.py", "new.txt"])
        self.assertFalse(result["committed"])
        self.assertTrue(all(call[0] in ("info", "status") for call in self.calls))

    def test_apply_adds_only_selected_files_and_preserves_utf8_message(self):
        result = self.submit(apply=True)
        self.assertNotIn("error", result)
        self.assertTrue(result["committed"])
        self.assertTrue(result["verified"])
        self.assertEqual(result["revision"], 42)
        self.assertEqual(self.commit_message_bytes, MESSAGE.encode("utf-8"))
        self.assertEqual([call for call in self.calls if call[0] == "add"], [("add", "--depth", "empty", "./new.txt@")])
        self.assertEqual(self.last_targets, ["a.py", "new.txt"])

    def test_rejects_unsafe_or_unrelated_paths_without_writes(self):
        for path in (".", "../outside.py", str(self.root / "a.py"), "AGENTS.md", ".mhxy-workspace/cache.json", "data/table.py"):
            with self.subTest(path=path):
                self.calls.clear()
                result = self.submit([path], apply=True)
                self.assertIn("error", result)
                self.assertFalse(result["committed"])
                self.assertTrue(all(call[0] in ("info", "status") for call in self.calls))
        result = self.submit(["a.py", "./a.py"], apply=True)
        self.assertIn("重复", result["error"])

    def test_rejects_invalid_messages_without_any_svn_call(self):
        for message in ("", "#844233 title", "finish #844233", "refs #844233 title", "finish #844233 auto commit: title"):
            with self.subTest(message=message):
                self.message_file.write_text(message, encoding="utf-8")
                result = self.submit(apply=True)
                self.assertIn("error", result)
                self.assertFalse(self.calls)

    def test_rejects_conflicts_missing_ignored_and_unchanged_files(self):
        for item in ("conflicted", "missing", "obstructed", "ignored", "normal"):
            with self.subTest(item=item):
                self.statuses["a.py"]["item"] = item
                self.calls.clear()
                result = self.submit(["a.py"], apply=True)
                self.assertIn("error", result)
                self.assertFalse(result["committed"])
                self.assertTrue(all(call[0] in ("info", "status") for call in self.calls))

    def test_rejects_external_workcopy_and_switched_file(self):
        self.foreign = True
        self.assertIn("error", self.submit(["a.py"], apply=True))
        self.foreign = False
        self.statuses["a.py"]["switched"] = "true"
        self.assertIn("error", self.submit(["a.py"], apply=True))

    def test_commit_failure_is_unknown_and_never_retried(self):
        self.failed_commit = True
        result = self.submit(["a.py"], apply=True)
        self.assertIsNone(result["committed"])
        self.assertFalse(result["verified"])
        self.assertEqual(sum(call[0] == "commit" for call in self.calls), 1)

    def test_log_failure_preserves_committed_revision_without_retry(self):
        for mode in ("bad_log", "extra_log_path"):
            with self.subTest(mode=mode):
                self.calls.clear()
                setattr(self, mode, True)
                result = self.submit(["a.py"], apply=True)
                self.assertTrue(result["committed"])
                self.assertEqual(result["revision"], 42)
                self.assertFalse(result["verified"])
                self.assertIn("error", result)
                self.assertEqual(sum(call[0] == "commit" for call in self.calls), 1)
                setattr(self, mode, False)


@unittest.skipUnless(shutil.which("svn") and shutil.which("svnadmin"), "需要本机 svn 和 svnadmin")
class LocalRepositoryTests(unittest.TestCase):
    def test_real_preview_commit_delete_and_unselected_changes(self):
        with tempfile.TemporaryDirectory(prefix="svn commit integration ") as directory:
            base = Path(directory).resolve()
            repository = base / "repository"
            root = base / "working copy"
            subprocess.run(["svnadmin", "create", str(repository)], check=True, capture_output=True)
            url = repository.as_uri() + "/wzimage/trunk"
            subprocess.run(["svn", "mkdir", "--parents", url, "-m", "setup", "--non-interactive"], check=True, capture_output=True)
            subprocess.run(["svn", "checkout", url, str(root), "--non-interactive"], check=True, capture_output=True)
            message_file = base / "message.txt"
            message_file.write_text(MESSAGE, encoding="utf-8")
            names = ["-a@名字.py", "unrelated.py", "deleted.py"]
            for name in names:
                (root / name).write_text("x = 1", encoding="utf-8")
            seeded = commit.submit(root, names, message_file, apply=True)
            self.assertNotIn("error", seeded, seeded)
            self.assertTrue(seeded["verified"])
            for name in names[:2]:
                (root / name).write_text("x = 2", encoding="utf-8")
            (root / "new.txt").write_text("中文说明", encoding="utf-8")
            subprocess.run(["svn", "delete", "./deleted.py@", "--non-interactive"], cwd=root, check=True, capture_output=True)
            selected = [names[0], "new.txt", "deleted.py"]
            preview = commit.submit(root, selected, message_file)
            self.assertNotIn("error", preview, preview)
            before = subprocess.run(["svn", "status", "--xml", "--non-interactive"], cwd=root, check=True, capture_output=True).stdout
            self.assertEqual(ET.fromstring(before).find(".//entry[@path='new.txt']/wc-status").get("item"), "unversioned")
            result = commit.submit(root, selected, message_file, apply=True)
            self.assertNotIn("error", result, result)
            self.assertTrue(result["verified"])
            self.assertEqual(result["revision"], seeded["revision"] + 1)
            after = ET.fromstring(subprocess.run(["svn", "status", "--xml", "--non-interactive"], cwd=root, check=True, capture_output=True).stdout)
            self.assertEqual([entry.get("path") for entry in after.findall(".//entry")], ["unrelated.py"])


if __name__ == "__main__":
    unittest.main()
