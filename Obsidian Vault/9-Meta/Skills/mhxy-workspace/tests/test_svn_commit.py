"""定向提交的范围、失败语义和临时 SVN 仓库集成测试，不连接业务仓库。"""
import json
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
        self.changelists = {}
        self.kinds = {}
        self.calls = []
        self.commit_failure = None
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
            entry = ET.SubElement(tree, "entry", kind="dir" if target == "." else self.kinds.get(target, "file"))
            ET.SubElement(entry, "url").text = URL if target == "." else URL + "/" + target
            repository = ET.SubElement(entry, "repository")
            ET.SubElement(repository, "root").text = REPOSITORY
            wc_info = ET.SubElement(entry, "wc-info")
            ET.SubElement(wc_info, "wcroot-abspath").text = str(self.root / "external") if self.foreign and target != "." else str(self.root)
        elif command == "status":
            target = args[-1].removesuffix("@").removeprefix("./")
            tree = ET.Element("status")
            parent = ET.SubElement(tree, "target", path=target)
            if target in self.changelists:
                parent = ET.SubElement(tree, "changelist", name=self.changelists[target])
            entry = ET.SubElement(parent, "entry", path=target)
            ET.SubElement(entry, "wc-status", **self.statuses.get(target, {"item": "normal", "props": "none"}))
        elif command == "add":
            return b"Added new.txt"
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

    def fake_commit(self, root, *args):
        self.calls.append(("commit", *args))
        if isinstance(self.commit_failure, Exception):
            raise self.commit_failure
        if self.commit_failure:
            return subprocess.CompletedProcess(args, 1, b"", self.commit_failure.encode("utf-8"))
        self.commit_message_bytes = Path(args[args.index("-F") + 1]).read_bytes()
        self.last_targets = [target.removesuffix("@").removeprefix("./") for target in args[args.index("-F") + 2:]]
        return subprocess.CompletedProcess(args, 0, b"Committed revision 42.", b"")

    def submit(self, paths=None, apply=False):
        with patch.object(commit, "run_svn", side_effect=self.fake_svn), \
                patch.object(commit, "commit_process", side_effect=self.fake_commit):
            return commit.submit(self.root, paths or ["a.py", "new.txt"], self.message_file, apply)

    def test_known_formal_branch_names_and_dates(self):
        self.assertEqual(commit.branch_kind(URL), "trunk")
        for name in commit.workspace.PERIODIC_TYPES:
            with self.subTest(name=name):
                self.assertEqual(commit.branch_kind(f"svn://example.test/wzimage/branchs/2026_ship/{name}_2026_10_13"),
                                 "周期分支")
        # 周期分支一定带日期：_ship 下不带日期的类型名不是周期分支。
        for path in ("branchs/2026_dev/test", "branchs/2026_ship/test_bugfix", "branchs/2026_ship/research",
                     "branchs/2026_ship/test", "branchs/2026_ship/zlp", "branchs/2026_ship/release2"):
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

    def test_commit_removes_committed_files_from_review_mark(self):
        mark = self.root / ".mhxy-workspace" / "review-mark.json"
        mark.parent.mkdir()
        mark.write_text(json.dumps({"marked_at": "t", "files": {"a.py": "x", "new.txt": "y", "b.py": "z"}}),
                        encoding="utf-8")
        result = self.submit(apply=True)
        self.assertTrue(result["committed"] and result["verified"])
        self.assertNotIn("warnings", result)
        self.assertEqual(json.loads(mark.read_text(encoding="utf-8")), {"marked_at": "t", "files": {"b.py": "z"}})
        # 记录损坏只给警告，不影响已提交的结果。
        mark.write_text("[]", encoding="utf-8")
        result = self.submit(apply=True)
        self.assertTrue(result["committed"] and result["verified"])
        self.assertNotIn("error", result)
        self.assertIn("review 记录", result["warnings"][0])

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
        for failure in ("svn: E170013: Unable to connect to a repository\nsvn: E730054: connection reset",
                        "svn: E155011: Commit failed (details follow):\nsvn: E170013: connection lost",
                        "svn: unexpected failure without code",
                        commit.precommit.SvnTimeout("svn commit 超过 3600 秒未结束")):
            with self.subTest(failure=str(failure)):
                self.calls.clear()
                self.commit_failure = failure
                result = self.submit(["a.py"], apply=True)
                self.assertIsNone(result["committed"])
                self.assertFalse(result["verified"])
                self.assertEqual(sum(call[0] == "commit" for call in self.calls), 1)
        self.assertIn("提交超时，结果不明，可能需要 cleanup", result["error"])

    def test_rejected_commit_reports_not_committed(self):
        for failure in ("svn: E155011: Commit failed (details follow):\nsvn: E155011: File 'a.py' is out of date\n"
                        "svn: E160028: File '/trunk/a.py' is out of date",
                        "svn: E165001: Commit failed (details follow):\nsvn: E165001: Commit blocked by pre-commit hook",
                        "svn: E200009: Commit failed (details follow):\nsvn: E200009: 'd' is not known to exist",
                        "svn: E155015: Commit failed (details follow):\nsvn: E155015: Aborting commit: remains in conflict",
                        commit.precommit.PrecheckError("svn 不可用：not found")):
            with self.subTest(failure=str(failure)):
                self.commit_failure = failure
                result = self.submit(["a.py"], apply=True)
                self.assertIs(result["committed"], False)
                self.assertIn("error", result)

    def test_rejects_ignore_on_commit_changelist_and_shows_other_changelists(self):
        self.changelists["a.py"] = "ignore-on-commit"
        result = self.submit(["a.py"], apply=True)
        self.assertIn("ignore-on-commit", result["error"])
        self.assertFalse(any(call[0] in ("add", "commit") for call in self.calls))
        self.changelists["a.py"] = "feature"
        result = self.submit(["a.py"])
        self.assertNotIn("error", result)
        self.assertEqual(result["entries"][0]["changelist"], "feature")

    def test_rejects_files_under_new_unversioned_or_deleted_directories(self):
        (self.root / "dir").mkdir()
        (self.root / "dir" / "f.py").write_text("x = 1", encoding="utf-8")
        self.statuses["dir/f.py"] = {"item": "added", "props": "none"}
        for item, expected in (("added", "尚未提交的新目录"), ("unversioned", "未纳入版本控制的目录"),
                               ("deleted", "目录删除")):
            with self.subTest(item=item):
                self.calls.clear()
                self.statuses["dir"] = {"item": item, "props": "none"}
                result = self.submit(["dir/f.py"], apply=True)
                self.assertIn(expected, result["error"])
                self.assertIs(result["committed"], False)
                self.assertFalse(any(call[0] in ("add", "commit") for call in self.calls))

    def test_deleted_directory_reports_directory_rule(self):
        self.statuses["olddir"] = {"item": "deleted", "props": "none"}
        self.kinds["olddir"] = "dir"
        result = self.submit(["olddir"], apply=True)
        self.assertIn("目录删除由用户自行提交", result["error"])

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

            # 新目录中的文件：预览即拒绝，不再等到 --apply 时 E200009 失败。
            svn = lambda *args: subprocess.run(["svn", *args, "--non-interactive"], cwd=root, check=True, capture_output=True)
            (root / "newdir").mkdir()
            (root / "newdir" / "f.py").write_text("x = 1", encoding="utf-8")
            (root / "plain").mkdir()
            (root / "plain" / "g.py").write_text("x = 1", encoding="utf-8")
            svn("add", "newdir")
            for path, expected in (("newdir/f.py", "尚未提交的新目录"), ("plain/g.py", "未纳入版本控制的目录")):
                with self.subTest(path=path):
                    rejected = commit.submit(root, [path], message_file, apply=True)
                    self.assertIn(expected, rejected["error"])
                    self.assertIs(rejected["committed"], False)

            # ignore-on-commit 中的文件不能被显式路径带进提交。
            svn("changelist", "ignore-on-commit", "unrelated.py")
            rejected = commit.submit(root, ["unrelated.py"], message_file, apply=True)
            self.assertIn("ignore-on-commit", rejected["error"])
            svn("changelist", "--remove", "unrelated.py")

            # 版本过旧：仓库被另一个工作副本推进后，提交被拒绝，committed 为 false。
            other = base / "other copy"
            svn("checkout", url, str(other))
            (other / "unrelated.py").write_text("x = 3", encoding="utf-8")
            pushed = commit.submit(other, ["unrelated.py"], message_file, apply=True)
            self.assertTrue(pushed["verified"], pushed)
            stale = commit.submit(root, ["unrelated.py"], message_file, apply=True)
            self.assertIs(stale["committed"], False, stale)
            self.assertIn("E155011", stale["error"])


if __name__ == "__main__":
    unittest.main()
