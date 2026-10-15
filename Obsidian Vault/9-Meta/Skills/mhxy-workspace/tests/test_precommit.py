"""提交前自检的隔离测试；svn 调用全部替换为假数据。"""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import precommit as p  # noqa: E402

STATUS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<status>
<target path=".">
<entry path=".mhxy-workspace"><wc-status item="unversioned" props="none"/></entry>
<entry path="prot"><wc-status item="external" props="none"/></entry>
<entry path="gameplay\\chat\\a.py"><wc-status item="modified" props="none"/></entry>
<entry path="gameplay\\new.py"><wc-status item="unversioned" props="none"/></entry>
<entry path="gameplay\\gone.py"><wc-status item="missing" props="none"/></entry>
<entry path="gameplay\\c.py"><wc-status item="conflicted" props="none"/></entry>
<entry path="data\\table.py"><wc-status item="modified" props="none"/></entry>
<entry path="lib"><wc-status item="normal" props="modified"/></entry>
<entry path="old.py"><wc-status item="deleted" props="none"/></entry>
</target>
<changelist name="ignore-on-commit">
<entry path="AGENTS.md"><wc-status item="modified" props="none"/></entry>
</changelist>
</status>""".encode("utf-8")


class PrecommitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()

    def tearDown(self):
        self.temp.cleanup()

    def write(self, relative, data):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
        return path

    def test_status_parsing_and_classification(self):
        with patch.object(p, "run_svn", return_value=STATUS_XML):
            entries = p.svn_status(self.root)
        self.assertIn({"path": "AGENTS.md", "item": "modified", "props": "none", "tree_conflict": False,
                       "changelist": "ignore-on-commit"}, entries)
        result = p.classify(entries)
        self.assertEqual(result["commit"], ["gameplay/chat/a.py（modified）", "lib（属性修改）", "old.py（deleted）"])
        self.assertEqual(sorted(result["excluded_local_only"]), [".mhxy-workspace", "AGENTS.md"])
        self.assertEqual(result["excluded_data"], ["data/table.py"])
        self.assertEqual(result["unversioned"], ["gameplay/new.py"])
        self.assertEqual(result["property_changes"], ["lib"])
        self.assertEqual(len(result["blocking"]), 2)
        self.assertTrue(any("gone.py" in item and "missing" in item for item in result["blocking"]))

    def test_builtin_source_checks(self):
        good = self.write("good.py", "# -*- coding: utf-8 -*-\r\nx = '中文'\r\n")
        gbk = self.write("gbk.py", "# -*- coding: gbk -*-\nx = 1\n")
        bad_bytes = self.write("bad.py", "x = '中文'\n".encode("gb18030"))
        syntax = self.write("syntax.py", "def f(:\n")
        mixed = self.write("mixed.py", "a = 1\r\nb = 2\n")
        blocking, warnings, method = p.check_sources(self.root, [good, gbk, bad_bytes, syntax, mixed])
        self.assertIn("内置检查", method)
        self.assertEqual(len(blocking), 3)
        self.assertTrue(any("gbk.py" in item and "编码声明" in item for item in blocking))
        self.assertTrue(any("bad.py" in item and "UTF-8" in item for item in blocking))
        self.assertTrue(any("syntax.py:1" in item for item in blocking))
        self.assertEqual(warnings, ["mixed.py：混用 CRLF 和 LF 换行"])

    def test_project_encoding_tool_is_preferred(self):
        source = self.write("a.py", "x = 1\n")
        self.write(p.ENCODING_TOOL, "import sys\nprint('ERROR\\ta.py\\tbad header')\nprint('OK\\tdone')\nsys.exit(1)\n")
        blocking, warnings, method = p.check_sources(self.root, [source])
        self.assertEqual(method, p.ENCODING_TOOL)
        self.assertEqual(blocking, ["ERROR\ta.py\tbad header"])
        self.write(p.ENCODING_TOOL, "print('WARN\\ta.py\\tmojibake?')\n")
        blocking, warnings, _ = p.check_sources(self.root, [source])
        self.assertEqual((blocking, warnings), ([], ["WARN\ta.py\tmojibake?"]))

    def test_leftovers_from_new_and_modified_files(self):
        self.write("gameplay/new.py", "import pdb\nprint('x')\nDEV = 'mh_at_" + "a" * 32 + "'\n")
        self.write("gameplay/a.py", "value = 1\n")
        diff = "--- a.py\n+++ a.py\n@@\n-old\n+    print('debug')\n+value = 1\n".encode("utf-8")
        entries = [{"path": "gameplay/new.py", "item": "unversioned"}, {"path": "gameplay/a.py", "item": "modified"},
                   {"path": "data/t.py", "item": "modified"}, {"path": "readme.md", "item": "modified"}]
        with patch.object(p, "run_svn", return_value=diff) as run:
            warnings = p.check_leftovers(self.root, entries)
        run.assert_called_once()
        self.assertEqual(len(warnings), 4)
        self.assertTrue(any("调试断点" in w for w in warnings))
        self.assertTrue(any("写死的设备 ID" in w for w in warnings))
        self.assertTrue(any(w.startswith("gameplay/a.py：新增 print") for w in warnings))

    def test_ignore_on_commit_files_are_not_commit_candidates(self):
        entries = [{"path": "gameplay/local.py", "item": "modified", "props": "none", "tree_conflict": False,
                    "changelist": "ignore-on-commit"},
                   {"path": "lib", "item": "normal", "props": "modified", "tree_conflict": False,
                    "changelist": "ignore-on-commit"},
                   {"path": "CLAUDE.md", "item": "modified", "props": "none", "tree_conflict": False,
                    "changelist": "ignore-on-commit"},
                   {"path": "gameplay/b.py", "item": "modified", "props": "none", "tree_conflict": False,
                    "changelist": "feature"}]
        self.write("gameplay/local.py", "print('local')\n")
        result = p.classify(entries)
        self.assertEqual(result["commit"], ["gameplay/b.py（modified）"])
        self.assertEqual(result["ignore_on_commit"], ["gameplay/local.py（modified）", "lib（属性修改）"])
        self.assertEqual(result["excluded_local_only"], ["CLAUDE.md"])
        self.assertEqual(result["property_changes"], [])
        # 不提交的文件也不做编码检查和调试残留扫描。
        self.assertNotIn(self.root / "gameplay" / "local.py", p.source_files(self.root, entries))

    def test_diff_with_mixed_encodings_and_chinese_names(self):
        # svn diff 的文件头用系统代码页（cp936），内容行是文件原始字节（UTF-8）。
        diff = ("Index: 界面/中文.py\n" + "=" * 67 + "\n").encode("gbk")
        diff += "--- 界面/中文.py\t(版本 3)\n+++ 界面/中文.py\t(工作副本)\n".encode("gbk")
        diff += "@@ -1 +1,3 @@\n-旧 = 1\n+名字 = '中文'\n+print('调试')\n+++x\n".encode("utf-8")
        diff += "+gbk_line = '中'\n".encode("gb18030")
        diff += "\nProperty changes on: 界面/中文.py\n___\nAdded: svn:eol-style\n## -0,0 +1 ##\n+native\n".encode("gbk")
        self.assertEqual(p.diff_added_lines(diff), ["名字 = '中文'", "print('调试')", "++x", "gbk_line = '中'"])
        self.write("界面/中文.py", "名字 = '中文'\n")
        entries = [{"path": "界面/中文.py", "item": "modified"}]
        with patch.object(p, "run_svn", return_value=diff):
            warnings = p.check_leftovers(self.root, entries)
        self.assertEqual(warnings, ["界面/中文.py：新增 print：print('调试')"])

    def test_leftovers_scan_sources_inside_unversioned_directories(self):
        self.write("gameplay/newdir/sub/a.py", "breakpoint()\n")
        self.write("gameplay/newdir/b.tmpl", "print('x')\n")
        self.write("gameplay/newdir/readme.txt", "print('x')\n")
        entries = [{"path": "gameplay/newdir", "item": "unversioned"}]
        files = p.source_files(self.root, entries)
        self.assertEqual([path.relative_to(self.root).as_posix() for path in files],
                         ["gameplay/newdir/b.tmpl", "gameplay/newdir/sub/a.py"])
        warnings = p.check_leftovers(self.root, entries)
        self.assertEqual(sorted(warnings), ["gameplay/newdir/b.tmpl：新增 print：print('x')",
                                            "gameplay/newdir/sub/a.py：调试断点：breakpoint()"])

    def test_cli_reports_workspace_errors_and_timeouts_as_json(self):
        for error in (p.workspace.WorkspaceError("文档编码无法处理"),
                      subprocess.TimeoutExpired(["python"], 300),
                      p.SvnTimeout("svn status 超过 120 秒未结束")):
            with self.subTest(error=type(error).__name__):
                stderr = io.StringIO()
                with patch.object(p, "precheck", side_effect=error), patch.object(sys, "argv", ["precommit.py"]), \
                        contextlib.redirect_stderr(stderr):
                    self.assertEqual(p.main(), 1)
                self.assertIn("error", json.loads(stderr.getvalue()))

    def test_svn_timeout_is_distinct_from_unavailable(self):
        with patch.object(p.subprocess, "run", side_effect=subprocess.TimeoutExpired(["svn"], 5)):
            with self.assertRaisesRegex(p.SvnTimeout, "超过 5 秒未结束"):
                p.svn_process(self.root, "status", timeout=5)
        with patch.object(p.subprocess, "run", side_effect=FileNotFoundError("svn")):
            with self.assertRaisesRegex(p.PrecheckError, "svn 不可用") as caught:
                p.svn_process(self.root, "status")
        self.assertNotIsInstance(caught.exception, p.SvnTimeout)

    def test_cli_exit_codes(self):
        script = Path(p.__file__)
        for returncode, stdout, expected in ((1, b"", 1),):
            fake = subprocess.CompletedProcess([], returncode, stdout, b"svn: E155007: not a working copy")
            with patch.object(p.subprocess, "run", return_value=fake):
                with self.assertRaises(p.PrecheckError):
                    p.run_svn(self.root, "status")
        completed = subprocess.run([sys.executable, "-B", str(script), "--root", str(self.root)], capture_output=True)
        self.assertEqual(completed.returncode, 1)
        self.assertIn("error", json.loads(completed.stderr))
        with patch.object(p, "svn_status", return_value=[{"path": "x.py", "item": "conflicted", "props": "none",
                                                          "tree_conflict": False, "changelist": None}]), \
             patch.object(p.workspace, "svn_branch", return_value=None):
            result = p.precheck(self.root)
        self.assertEqual(len(result["blocking"]), 1)


if __name__ == "__main__":
    unittest.main()
