"""真机用例执行器的隔离测试：execute_code 在本进程内模拟执行，不连接真实服务。"""
import ast
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
DIRECTORY = Path(__file__).resolve().parents[1] / "scripts" / "game-debugging"
sys.path.insert(0, str(DIRECTORY))


def load(name):
    spec = importlib.util.spec_from_file_location(name, DIRECTORY / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = load("case_runner")
mcp_http = runner.mcp_http


def execute(code):
    """模拟客户端 execute_code：分开的 globals／locals，最后一行裸表达式为返回值。"""
    tree = ast.parse(code)
    last = tree.body.pop() if tree.body and isinstance(tree.body[-1], ast.Expr) else None
    g, l = {}, {}
    try:
        exec(compile(tree, "<client>", "exec"), g, l)
        ret = eval(compile(ast.Expression(last.value), "<client>", "eval"), g, l) if last else None
        return {"result": {"ret": ret, "error": None, "loginfo": ""}}
    except Exception as error:  # 客户端把异常放在 error 里返回
        return {"result": {"ret": None, "error": f"{type(error).__name__}: {error}", "loginfo": ""}}


class FakeGame:
    """假的 mh-game-mcp：execute_code 本地执行，其他工具记录调用。"""

    def __init__(self):
        self.calls = []

    def __call__(self, name, arguments, timeout=None, handshake=True):
        self.calls.append((name, arguments))
        if name == "execute_code":
            return json.loads(json.dumps(execute(arguments["code"]), default=repr))
        return {"ok": True}


class Base(unittest.TestCase):
    def setUp(self):
        self.game = FakeGame()
        for patcher in (patch.object(mcp_http, "call", self.game), patch.object(mcp_http, "initialize"),
                        patch.object(runner.time, "sleep")):
            patcher.start()
            self.addCleanup(patcher.stop)
        # 假的客户端模块
        self.target = types.ModuleType("fake_target")
        self.target.value = 1
        self.target.Holder = type("Holder", (), {"attr": "base"})
        self.war = types.ModuleType("war")
        self.war.Turn, self.war.Cmds = 0, []
        utils3 = types.ModuleType("utils3")
        utils3.is_in_war = lambda: self.war.Turn > 0
        event = types.ModuleType("event")
        event.E1 = types.SimpleNamespace(listeners=[])
        modules = {"fake_target": self.target, "war": self.war, "utils3": utils3, "event": event}
        patcher = patch.dict(sys.modules, modules)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(lambda: sys.__dict__.pop("_mhxy_case_mocks", None))
        self.temp = Path(tempfile.mkdtemp())

    def run_case(self, case, **kwargs):
        path = self.temp / "case.json"
        path.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
        return runner.run(self.temp, "dev", [str(path)], **kwargs)


class ValidateTests(unittest.TestCase):
    def test_good_case(self):
        case = {"name": "a", "mocks": [{"name": "m", "patch": "x.y", "value": "1"}],
                "steps": [{"exec": "1", "save_as": "v"}, {"wait_for": {"preset": "war_turn", "args": {"n": 1}}},
                          {"mcp": "get_game_status", "args": {"devid": "{devid}"}}, {"assert": "True"}]}
        self.assertEqual(runner.validate(case), [])

    def test_problems(self):
        problems = runner.validate({"steps": [{"exec": "1", "gm": "x"}, {"wait_for": {"preset": "nope"}},
                                              {"assert": "1", "save_as": "x"}], "extra": 1,
                                    "mocks": [{"name": "m", "patch": "x"}]})
        text = "；".join(problems)
        for word in ("未知字段", "缺少 name", "恰好有一个步骤类型", "未知预设", "不支持选项", "name+patch+value"):
            self.assertIn(word, text)


class RenderTests(unittest.TestCase):
    def test_placeholders(self):
        context = {"devid": "d1", "root": "R", "vars": {"wid": "a'b"}, "args": {}}
        self.assertEqual(runner.render("f({vars.wid}, {devid}) or {'k': 1}", context, code=True),
                         "f(\"a'b\", d1) or {'k': 1}")
        self.assertEqual(runner.render("$at give {vars.wid}", context, code=False), "$at give a'b")
        with self.assertRaises(KeyError):
            runner.render("{vars.nope}", context, code=True)


class SpecTests(unittest.TestCase):
    def test_reads_only_test_case_section(self):
        text = "\n".join(["# 标题", "```json", '{"name": "不要"}', "```", "## 测试用例", "说明",
                          "```json", '{"name": "a", "steps": []}', "```", "### 子节", "```json",
                          '[{"name": "b"}]', "```", "## 变更记录", "```json", '{"name": "也不要"}', "```"])
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "spec.md"
            path.write_text(text, encoding="utf-8")
            names = [case["name"] for _, case in runner.load_cases(path)]
        self.assertEqual(names, ["a", "b"])

    def test_missing_section(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "spec.md"
            path.write_text("# 无", encoding="utf-8")
            with self.assertRaises(runner.CaseError):
                runner.load_cases(path)


class RunTests(Base):
    def test_pass_with_patch_mock_restored(self):
        case = {"name": "patch", "mocks": [
            {"name": "v", "patch": "fake_target.value", "value": "orig + 41"},
            {"name": "new", "patch": "fake_target.Holder.attr", "value": "'mock'"}],
            "steps": [{"exec": "__import__('fake_target').value", "save_as": "v"},
                      {"assert": "{vars.v} == 42 and __import__('fake_target').Holder.attr == 'mock'"}]}
        report = self.run_case(case)
        self.assertEqual(report["status"], "passed", report)
        self.assertEqual(report["restoration"], "restored")
        self.assertEqual(self.target.value, 1)
        self.assertEqual(self.target.Holder.__dict__["attr"], "base")
        self.assertNotIn("_mhxy_case_mocks", sys.__dict__)
        self.assertEqual(self.game.calls[0], ("init_client", {"devid": "dev"}))
        self.assertEqual(report["executed"][0]["tool"], "init_client")
        self.assertIn("<error_watch.py 全文>", report["executed"][1]["arguments"]["code"])

    def test_inherited_attribute_is_deleted_not_shadowed(self):
        sub = type("Sub", (self.target.Holder,), {})
        self.target.Sub = sub
        report = self.run_case({"name": "inh", "mocks": [{"name": "s", "patch": "fake_target.Sub.attr", "value": "2"}],
                                "steps": [{"assert": "__import__('fake_target').Sub.attr == 2"}]})
        self.assertEqual(report["status"], "passed", report)
        self.assertNotIn("attr", vars(sub))

    def test_failed_step_still_restores_and_stops(self):
        case = {"name": "fail", "mocks": [{"name": "v", "patch": "fake_target.value", "value": "9"}],
                "steps": [{"exec": "1/0"}, {"exec": "never()"}]}
        report = self.run_case(case)
        result = report["results"][0]
        self.assertEqual(report["status"], "failed")
        self.assertEqual(len(result["steps"]), 1)
        self.assertIn("ZeroDivisionError", result["steps"][0]["error"])
        self.assertEqual(report["restoration"], "restored")
        self.assertEqual(self.target.value, 1)

    def test_custom_mock_needs_true(self):
        case = {"name": "c", "mocks": [{"name": "m", "install": "__import__('fake_target').__dict__.update(x=1)",
                                        "restore": "__import__('fake_target').__dict__.pop('x')"}],
                "steps": [{"exec": "1"}]}
        report = self.run_case(case)
        self.assertEqual(report["restoration"], "unknown")  # restore 没返回 True，无法确认
        self.assertEqual(report["status"], "failed")

    def test_install_failure_before_register_needs_no_restore(self):
        report = self.run_case({"name": "bad", "mocks": [{"name": "m", "patch": "no_such_mod.x", "value": "1"}],
                                "steps": [{"exec": "1"}]})
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["restoration"], "restored")
        self.assertEqual(report["results"][0]["steps"], [])

    def test_wait_for_preset_and_timeout(self):
        self.war.Turn = 2
        report = self.run_case({"name": "w", "steps": [
            {"wait_for": {"preset": "war_turn", "args": {"n": 2}}},
            {"wait_for": {"preset": "war_out", "timeout": 0}}]})
        steps = report["results"][0]["steps"]
        self.assertEqual(steps[0]["polls"], 1)
        self.assertIn("等待超时", report["results"][0]["failure"])
        self.assertEqual(report["restoration"], "not_needed")
        waits = [item for item in report["executed"] if item.get("label", "").startswith("等待")]
        self.assertEqual(len(waits), 2)

    def test_gm_and_mcp_render(self):
        report = self.run_case({"name": "g", "steps": [{"gm": "$at fightN 2"},
                                                       {"mcp": "get_game_status", "args": {"devid": "{devid}"}}]})
        self.assertEqual(report["status"], "passed", report)
        self.assertIn(("execute_command", {"devid": "dev", "command": "$at fightN 2"}), self.game.calls)
        self.assertIn(("get_game_status", {"devid": "dev"}), self.game.calls)

    def test_collected_errors_fail_case(self):
        report = self.run_case({"name": "e", "steps": [
            {"exec": "__import__('logging').getLogger('MHXY').error('boom')"}]})
        self.assertEqual(report["status"], "failed")
        self.assertTrue(any("boom" in text for text in report["errors"]))

    def test_invalid_case_blocks_without_connecting(self):
        report = self.run_case({"name": "x", "steps": []})
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(self.game.calls, [])

    def test_init_failure_blocks(self):
        def broken(name, arguments, **kwargs):
            raise mcp_http.McpError("offline")
        with patch.object(mcp_http, "call", broken):
            report = self.run_case({"name": "x", "steps": [{"exec": "1"}]})
        self.assertEqual(report["status"], "blocked")
        self.assertIn("offline", report["errors"][0])

    def test_network_error_mid_case_still_finishes(self):
        real = self.game

        def flaky(name, arguments, **kwargs):
            if name == "execute_code" and arguments["code"] == "boom":
                raise OSError("timeout")
            return real(name, arguments)
        with patch.object(mcp_http, "call", flaky):
            report = self.run_case({"name": "n", "mocks": [{"name": "v", "patch": "fake_target.value", "value": "3"}],
                                    "steps": [{"exec": "boom"}]})
        self.assertIn("timeout", report["results"][0]["failure"])
        self.assertEqual(self.target.value, 1)
        self.assertEqual(report["restoration"], "restored")


class ExecCheckTests(Base):
    def test_runs_cases_and_reports_missing(self):
        target = self.temp / "mod_x.py"
        target.write_text("def f(a):\n\tif a:\n\t\treturn 1\n\treturn 2\n", encoding="utf-8")
        fake = types.ModuleType("diff_lines")
        fake.changed_py_files = lambda root: ["mod_x.py"]
        fake.collect = lambda root, rels: {"files": {"mod_x.py": [2, 3, 4]}, "total": 3, "skipped": {}, "warnings": []}
        cases = ("def _case():\n\timport importlib.util\n"
                 f"\tspec = importlib.util.spec_from_file_location('mod_x', {str(target)!r})\n"
                 "\tm = importlib.util.module_from_spec(spec)\n\tspec.loader.exec_module(m)\n\tassert m.f(1) == 1\n"
                 "CASES = [('f', _case)]")
        with patch.dict(sys.modules, {"diff_lines": fake}):
            report = self.run_case({"name": "ec", "steps": [{"exec_check": {"cases": cases}}]})
        self.assertEqual(report["status"], "passed", report)
        self.assertEqual(report["results"][0]["steps"][0]["missing"], {"mod_x.py": [4]})
        self.assertTrue(any("[4]" in text for text in report["unverified"]))


class MainTests(Base):
    def test_saves_report_and_exit_code(self):
        path = self.temp / "c.json"
        path.write_text(json.dumps({"name": "m", "steps": [{"exec": "1"}]}), encoding="utf-8")
        with patch("sys.stdout"):
            code = runner.main(["run", "--root", str(self.temp), "--devid", "dev", str(path)])
        self.assertEqual(code, 0)
        reports = list((self.temp / runner.REPORT_DIR).glob("*.json"))
        self.assertEqual(len(reports), 1)


if __name__ == "__main__":
    unittest.main()
