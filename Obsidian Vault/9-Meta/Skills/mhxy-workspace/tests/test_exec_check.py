"""改动执行检查脚本的隔离测试：svn 调用替换为假数据，客户端模板在本机 Python 中运行。"""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / "exec-check" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


d = load("diff_lines")
t = load("exec_trace")

SAMPLE = (b'x = 1\n'
          b'class A:\n'
          b'    y = 2\n'
          b'\n'
          b'    def f(self):\n'
          b'        """doc"""\n'
          b'        # comment\n'
          b'        return [i for i in (1, 2)]\n')

MODULE = '''def ok(v):
    if v:
        return 1
    return 2


def boom():
    raise ValueError("boom")
'''


class DiffLinesTests(unittest.TestCase):
    def test_lone_cr_counts_as_line_break(self):
        # 基线第 1 行以单独的 CR 结尾：Python 计为两行，新增行应是第 3 行而不是按 LF 计的第 2 行
        self.assertEqual(d.changed_line_numbers(b"a\rb\r\nc\n", b"a\rb\r\nX\nc\n"), {3})

    def test_new_file_is_all_changed(self):
        self.assertEqual(d.changed_line_numbers(b"", b"a\nb\n"), {1, 2, 3})

    def test_only_function_bodies_are_executable(self):
        # 模块级、类体、docstring、注释都不算；def 行（RESUME）和函数体算
        self.assertEqual(d.executable_lines(SAMPLE, "sample.py"), {5, 8})

    def test_collect_intersects_changes_with_executable_lines(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "pkg").mkdir()
            (root / "pkg" / "a.py").write_bytes(SAMPLE)
            (root / "pkg" / "bad.py").write_bytes(b"def f(:\n")
            base = SAMPLE.replace(b"return [i for i in (1, 2)]", b"return None").replace(b"y = 2", b"y = 1")
            with patch.object(d, "base_source", side_effect=lambda r, rel: base if rel == "pkg/a.py" else b""):
                result = d.collect(root, ["pkg/a.py", "pkg/bad.py", "pkg/gone.py"])
        self.assertEqual(result["files"], {"pkg/a.py": [8]})  # 第 3 行是类体，不计入
        self.assertEqual(result["total"], 1)
        self.assertIn("无法解析", result["skipped"]["pkg/bad.py"])
        self.assertEqual(result["skipped"]["pkg/gone.py"], "文件不存在")

    def test_changed_py_files_skips_local_and_data(self):
        entries = [{"path": p, "item": i, "props": "none", "tree_conflict": False, "changelist": None} for p, i in (
            ("gameplay/a.py", "modified"), ("gameplay/b.py", "added"), ("gameplay/c.txt", "modified"),
            ("gameplay/d.py", "deleted"), ("gameplay/e.py", "unversioned"), ("gameplay/new", "unversioned"),
            ("data/t.py", "modified"), (".mhxy-workspace/x.py", "added"))]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            # 未纳入版本控制的目录在 svn status 中只有一条，要展开成其中的 .py 文件
            (root / "gameplay" / "new" / "sub").mkdir(parents=True)
            (root / "gameplay" / "new" / "sub" / "m.py").write_bytes(b"")
            (root / "gameplay" / "new" / "readme.txt").write_bytes(b"")
            with patch.object(d.precommit, "svn_status", return_value=entries):
                self.assertEqual(d.changed_py_files(root), ["gameplay/a.py", "gameplay/b.py", "gameplay/e.py",
                                                            "gameplay/new/sub/m.py"])

    def test_bom_file_is_parsed(self):
        source = b"\xef\xbb\xbfdef f():\n    return 1\n"
        self.assertEqual(d.executable_lines(source, "bom.py"), {1, 2})
        self.assertEqual(d.changed_line_numbers(b"\xef\xbb\xbfdef f():\n    return 0\n", source), {2})

    def test_warns_when_not_client_python(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(d, "CLIENT_PYTHON", sys.version_info[:2]):
                self.assertEqual(d.collect(Path(temp), [])["warnings"], [])
            with patch.object(d, "CLIENT_PYTHON", (2, 7)):
                self.assertIn("行号表随版本变化", d.collect(Path(temp), [])["warnings"][0])


class ExecTraceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        path = Path(self.temp.name) / "pkg" / "target_mod.py"
        path.parent.mkdir()
        path.write_text(MODULE, encoding="utf-8")
        spec = importlib.util.spec_from_file_location("target_mod", path)
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)
        self.targets = {"pkg/target_mod.py": sorted(d.executable_lines(path.read_bytes(), str(path)))}
        self.addCleanup(self.temp.cleanup)

    def test_reports_hits_missing_and_case_errors(self):
        self.assertEqual(self.targets["pkg/target_mod.py"], [1, 2, 3, 4, 7, 8])
        result = t.exec_check_start(self.targets, [("ok", lambda: self.mod.ok(True)), ("boom", self.mod.boom)])
        self.assertEqual(result["results"]["ok"], "ok")
        self.assertIn("ValueError: boom", result["results"]["boom"])
        self.assertEqual(result["missing"]["pkg/target_mod.py"], [4])  # 只走了 v 为真的分支
        self.assertEqual(result["covered"]["pkg/target_mod.py"], "5/6")
        self.assertIsNone(sys.gettrace())

    def test_path_suffix_must_start_at_separator(self):
        # et_mod.py 只是 target_mod.py 的字符串后缀，不是路径后缀，不能误配
        result = t.exec_check_start({"et_mod.py": [1, 2]}, [("ok", lambda: self.mod.ok(True))])
        self.assertEqual(result["missing"]["et_mod.py"], [1, 2])
        result = t.exec_check_start({"target_mod.py": [1, 2]}, [("ok", lambda: self.mod.ok(True))])
        self.assertEqual(result["missing"]["target_mod.py"], [])

    def test_aborts_when_another_tracer_is_active(self):
        previous = sys.gettrace()
        sys.settrace(lambda *a: None)
        try:
            self.assertIn("已有追踪器", t.exec_check_start(self.targets, [])["abort"])
        finally:
            sys.settrace(previous)

    def test_templates_run_together_like_execute_code(self):
        # 按 exec-check.md「执行」：error_watch 与 exec_trace 拼接后发送，最后一行同时启动两者；
        # execute_code 用分开的 globals／locals 执行，用例需要的模块在函数内部 import
        sys.modules["target_mod"] = self.mod
        self.addCleanup(sys.modules.pop, "target_mod", None)
        watch = (SCRIPTS / "game-debugging" / "error_watch.py").read_text(encoding="utf-8")
        trace = (SCRIPTS / "exec-check" / "exec_trace.py").read_text(encoding="utf-8")
        cases = ("def case_ok():\n    import target_mod\n    target_mod.ok(False)\n"
                 "def case_log():\n    import logging\n    logging.getLogger('MHXY').error('logged in case')\n")
        call = f"[error_watch_start(), exec_check_start({self.targets!r}, [('ok', case_ok), ('log', case_log)])]"
        watch_result, start = eval_last(f"{watch}\n{trace}\n{cases}\n{call}")
        self.assertTrue(watch_result["started"])
        self.assertEqual(start["results"], {"ok": "ok", "log": "ok"})
        self.assertEqual(start["missing"]["pkg/target_mod.py"], [3, 7, 8])
        finish = eval_last(watch + "\nerror_watch_finish()")
        self.assertEqual([e["text"] for e in finish["errors"]], ["logged in case"])


def eval_last(code):
    """模拟 execute_code：globals 和 locals 分开执行，返回最后一行表达式的值。"""
    *body, last = code.rstrip().splitlines()
    scope_globals, scope_locals = {"__builtins__": __builtins__}, {}
    exec("\n".join(body), scope_globals, scope_locals)
    return eval(last, scope_globals, scope_locals)


if __name__ == "__main__":
    unittest.main()
