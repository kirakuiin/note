"""提交前自检的隔离测试；svn 调用全部替换为假数据。"""
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
