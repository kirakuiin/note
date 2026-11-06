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
        self.war.Turn, self.war.ActualTurn, self.war.Cmds = 0, 1, []
        self.war.wait_cmd = lambda: None
        self.war.ProcessFunc, self.war.PlayerTurn = self.war.wait_cmd, 1
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

    def test_types_and_preset_args(self):
        problems = runner.validate({"name": "a", "mocks": [{"name": "m", "patch": "x.y", "value": 1},
                                                          {"name": "n", "install": "", "restore": "True"}],
                                    "steps": [{"wait_for": {"preset": "war_turn"}},
                                              {"wait_for": {"preset": ["war_in"]}},
                                              {"wait_for": {"expr": "1", "timeout": "5", "args": []}},
                                              {"exec": "1", "save_as": 3},
                                              {"exec_check": {"cases": "x", "files": [1]}}]})
        text = "；".join(problems)
        for word in ("value 必须是非空字符串", "install、restore", "缺少参数 ['n']", "未知预设 ['war_in']",
                     "timeout 必须是非负秒数", "args 必须是对象", "save_as 必须是非空字符串", "files 必须是相对路径"):
            self.assertIn(word, text)
        self.assertEqual(runner.validate({"name": "a", "mocks": {}, "steps": [{"exec": "1"}]}), ["mocks 必须是列表"])


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

    def test_overhead_is_two_calls_per_case(self):
        report = self.run_case({"name": "o", "mocks": [{"name": "a", "patch": "fake_target.value", "value": "2"},
                                                       {"name": "b", "patch": "fake_target.Holder.attr", "value": "3"}],
                                "steps": [{"exec": "1"}]})
        self.assertEqual(report["status"], "passed", report)
        labels = [item.get("label") for item in report["executed"][1:]]
        self.assertEqual(len(labels), 3)  # 开始、步骤、收尾
        self.assertTrue(labels[0].startswith("开始") and labels[2].startswith("收尾"))

    def test_mixed_mocks_restore_custom_then_patch(self):
        case = {"name": "mix", "mocks": [
            {"name": "c", "install": "__import__('fake_target').__dict__.update(x=1)",
             "restore": "(lambda m: (m.__dict__.pop('x'), 'x' not in vars(m))[1])(__import__('fake_target'))"},
            {"name": "p", "patch": "fake_target.value", "value": "7"}],
            "steps": [{"assert": "__import__('fake_target').x == 1 and __import__('fake_target').value == 7"}]}
        report = self.run_case(case)
        self.assertEqual((report["status"], report["restoration"]), ("passed", "restored"), report)
        self.assertNotIn("x", vars(self.target))
        self.assertEqual(self.target.value, 1)

    def test_wait_for_preset_and_timeout(self):
        self.war.Turn = 2
        self.war.ActualTurn = 2
        report = self.run_case({"name": "w", "steps": [
            {"wait_for": {"preset": "war_turn", "args": {"n": 2}}},
            {"wait_for": {"preset": "war_out", "timeout": 0}}]})
        steps = report["results"][0]["steps"]
        self.assertEqual(steps[0]["polls"], 1)
        self.assertIn("等待超时", report["results"][0]["failure"])
        self.assertEqual(report["restoration"], "not_needed")
        waits = [item for item in report["executed"] if item.get("label", "").startswith("等待")]
        self.assertEqual(len(waits), 2)

    def test_war_presets_need_waiting_state(self):
        self.war.Turn, self.war.ActualTurn = 1, 3  # 已在战斗中，ActualTurn 残留上一场的值
        for state in ({"PlayerTurn": 0}, {"Cmds": ["war.start"]}, {"ProcessFunc": None}):
            for key, value in state.items():
                setattr(self.war, key, value)
            report = self.run_case({"name": "w", "steps": [{"wait_for": {"preset": "war_turn", "args": {"n": 2},
                                                                         "timeout": 0}}]})
            self.assertIn("等待超时", report["results"][0]["failure"], state)
            self.war.PlayerTurn, self.war.Cmds, self.war.ProcessFunc = 1, [], self.war.wait_cmd

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

    def test_ignore_errors_keeps_text_but_passes(self):
        code = ("(lambda l: (l.error('图标 NSRank 的size不对'), l.error('真的出错')))"
                "(__import__('logging').getLogger('MHXY'))")
        report = self.run_case({"name": "i", "ignore_errors": ["NSRank 的size不对"], "steps": [{"exec": code}]})
        result = report["results"][0]
        self.assertEqual(report["status"], "failed")  # 没被声明的报错仍判失败
        self.assertEqual(len(result["ignored_errors"]), 1)
        self.assertTrue(all("NSRank" not in text for text in report["errors"]))
        report = self.run_case({"name": "j", "ignore_errors": ["NSRank"], "steps": [
            {"exec": "__import__('logging').getLogger('MHXY').error('图标 NSRank 的size不对')"}]})
        self.assertEqual(report["status"], "passed", report)
        self.assertTrue(any("ignore_errors" in text for text in report["unverified"]))

    def test_ignore_errors_validated(self):
        self.assertIn("ignore_errors 必须是正则表达式字符串列表",
                      runner.validate({"name": "a", "ignore_errors": "x", "steps": [{"exec": "1"}]}))
        self.assertTrue(any("无效" in p for p in runner.validate({"name": "a", "ignore_errors": ["("],
                                                                    "steps": [{"exec": "1"}]})))

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

    def test_skipped_files_fail_and_warnings_reported(self):
        fake = types.ModuleType("diff_lines")
        fake.collect = lambda root, rels: {"files": {}, "total": 0, "skipped": {"bad.py": "语法错误"},
                                           "warnings": ["本机不是 3.11"]}
        with patch.dict(sys.modules, {"diff_lines": fake}):
            report = self.run_case({"name": "ec", "steps": [{"exec_check": {"cases": "CASES = []", "files": ["bad.py"]}}]})
        self.assertIn("无法计算目标行", report["results"][0]["failure"])
        self.assertTrue(any("3.11" in text for text in report["unverified"]))

    def test_unexpected_error_still_reports(self):
        with patch.object(runner, "run_step", side_effect=TypeError("bug")):
            report = self.run_case({"name": "u", "mocks": [{"name": "v", "patch": "fake_target.value", "value": "5"}],
                                    "steps": [{"exec": "1"}]})
        self.assertIn("执行器内部错误", report["results"][0]["failure"])
        self.assertEqual(self.target.value, 1)


class Warrior:
    """假的战斗单位，只有 _case_war_act 用到的属性。"""

    def __init__(self, wid, allied, place, owner=0, name=None):
        self.type, self.id, self.allied, self.place, self.owner = "WARRIOR", wid, allied, place, owner
        self.name, self.sid = name or f"u{wid}", 1000 + wid

    def get_member(self, key):
        return 100


class WarBase(Base):
    """在 Base 之上加一场假战斗：人物 1、召唤兽 2、友方 3、敌方 11/12（站位倒序，验证按站位排序）。"""

    def setUp(self):
        super().setUp()
        self.sent = []
        self.war.Turn, self.war.RoleID, self.war.WarriorCmdOkSet = 1, 1, set()
        units = [Warrior(1, 1, 0), Warrior(2, 1, 5, owner=1), Warrior(3, 1, 1), Warrior(11, 0, 3), Warrior(12, 0, 2)]
        world = types.ModuleType("world")
        world.Objects = {unit.id: unit for unit in units}
        self.war.summon_find_list = lambda wid: [u.id for u in units if u.owner == wid]

        def recorder(name):
            def send(*args):
                self.sent.append((name, args))
            send.__name__ = name
            return send
        netwar = types.ModuleType("netwar")
        for name in ("c_war_attack", "c_war_perform", "c_war_guard", "c_war_protect", "c_war_item",
                     "c_war_summ_attack", "c_war_summ_perform", "c_war_summ_guard", "c_war_summ_protect", "c_war_summ_item"):
            setattr(netwar, name, recorder(name))
        netskill = types.ModuleType("netskill")
        netskill.c_sp_perform = recorder("c_sp_perform")
        netfabao = types.ModuleType("netfabao")
        netfabao.C_USE_FIGHT = recorder("C_USE_FIGHT")
        dlgfabao = types.ModuleType("dlgfabao")
        dlgfabao.FABAO_INFO = {4: 6023}
        dlgitem = types.ModuleType("dlgitem")
        item = types.SimpleNamespace(nOID=777)
        dlgitem.item_find_by_name = lambda name: item if name == "金创药" else 0
        dlgitem.item_find_by_type = lambda shape: 0
        self.dlgwar = types.ModuleType("dlgwar")
        self.dlgwar.SelfID = 1

        def wait():  # 收起面板；假服务端立即结算本回合
            self.dlgwar.SelfID = None
            self.war.ActualTurn += 1
        self.dlgwar.wait = wait
        modules = {"world": world, "netwar": netwar, "netskill": netskill, "netfabao": netfabao,
                   "dlgfabao": dlgfabao, "dlgitem": dlgitem, "dlgwar": self.dlgwar}
        patcher = patch.dict(sys.modules, modules)
        patcher.start()
        self.addCleanup(patcher.stop)


class WarActTests(WarBase):
    def test_sends_role_and_pet_then_waits_next_turn(self):
        report = self.run_case({"name": "a", "steps": [
            {"war_act": {"role": {"act": "magic", "id": 1073, "target": "e0"}, "pet": {"act": "attack", "target": "e1"}}}]})
        self.assertEqual(report["status"], "passed", report)
        self.assertEqual(self.sent, [("c_war_perform", (12, 1073)), ("c_war_summ_attack", (2, 11))])
        step = report["results"][0]["steps"][0]
        labels = {item["wid"]: item["label"] for item in step["roster"]}
        self.assertEqual(labels, {1: "self", 2: "pet", 3: "f0", 11: "e1", 12: "e0"})
        self.assertEqual(self.war.WarriorCmdOkSet, {1, 2})
        self.assertEqual(self.war.ActualTurn, 2)

    def test_pet_defaults_to_guard_and_item_fabao_resolved(self):
        report = self.run_case({"name": "b", "steps": [{"war_act": {"role": {"act": "item", "item": "金创药"}}},
                                                       {"war_act": {"role": {"act": "fabao", "id": 6023}}}]})
        self.assertEqual(report["status"], "passed", report)
        self.assertEqual(self.sent, [("c_war_item", (1, 777)), ("c_war_summ_guard", (2,)),
                                     ("C_USE_FIGHT", (12, 4)), ("c_war_summ_guard", (2,))])

    def test_bad_target_sends_nothing(self):
        report = self.run_case({"name": "c", "steps": [
            {"war_act": {"role": {"act": "attack", "target": "e0"}, "pet": {"act": "attack", "target": "e5"}}}]})
        self.assertIn("下指令失败", report["results"][0]["failure"])
        self.assertIn("e5", report["results"][0]["failure"])
        self.assertEqual(self.sent, [])

    def test_sent_names_do_not_rely_on_function_name(self):
        for name in ("c_war_perform", "c_war_summ_guard"):  # 真实客户端的发包函数被装饰器包成 wrapper
            getattr(sys.modules["netwar"], name).__name__ = "wrapper"
        report = self.run_case({"name": "n", "steps": [{"war_act": {"role": {"act": "magic", "id": 7}}}]})
        self.assertEqual(report["results"][0]["steps"][0]["sent"], ["c_war_perform(12, 7)", "c_war_summ_guard(2,)"])

    def test_unknown_wid_sends_nothing(self):
        report = self.run_case({"name": "w", "steps": [{"war_act": {"role": {"act": "item", "item": "金创药", "target": 99}}}]})
        self.assertIn("wid 99 不在场上", report["results"][0]["failure"])
        self.assertEqual(self.sent, [])

    def test_not_waiting_state_fails(self):
        self.war.Cmds = ["cmd"]
        report = self.run_case({"name": "d", "steps": [{"war_act": {"role": {"act": "guard"}}}]})
        self.assertIn("不在等待下指令阶段", report["results"][0]["failure"])
        self.assertEqual(self.sent, [])

    def test_pending_units_fail(self):
        self.dlgwar.wait = lambda: None  # 还有身外化身等单位要下指令：wait 提前返回，SelfID 不清
        report = self.run_case({"name": "e", "steps": [{"war_act": {"role": {"act": "guard"}, "wait": False}}]})
        self.assertIn("还有单位等指令", report["results"][0]["failure"])

    def test_validation(self):
        problems = "；".join(runner.validate({"name": "v", "steps": [
            {"war_act": {"pet": {"act": "guard"}}},
            {"war_act": {"role": {"act": "fly"}}},
            {"war_act": {"role": {"act": "magic", "target": "x1"}, "wait": 1}},
            {"war_act": {"role": {"act": "protect"}, "pet": {"act": "item"}}}]}))
        for word in ("必须有 role", "act 只能是", "magic 需要 id", "target 写 e0", "wait 必须是", "protect 必须写 target",
                     "item 需要 item"):
            self.assertIn(word, problems)


class PumpTests(WarBase):
    """pump：假的 war2021_net／netwar 只记录构造顺序；manage_cmd 记录调用；队列由哨兵命令驱动执行完。"""

    def setUp(self):
        super().setUp()
        self.queued, self.managed = [], []
        war = self.war
        war.Turn, war.AccTurn = 0, 3  # 真实的下指令阶段 Turn 为 0
        sys.modules["utils3"].is_in_war = lambda: True

        class CCmd:
            def __init__(cmd):
                cmd.state, cmd.Func = 0, None
                war.Cmds.append(cmd)
        war.CCmd = CCmd
        war.action_end = lambda: None

        def next_cmd():
            while war.Cmds and war.Cmds[0].state:
                war.Cmds.pop(0)
        war.next_cmd = next_cmd
        net2021 = types.ModuleType("war2021_net")
        net2021.LastCmd = "stale"

        def maker(name):
            def build(*args):
                if self.fail_on == name:
                    raise RuntimeError("构造失败")
                cmd = CCmd()
                cmd.name = name
                self.queued.append((name, args))
            return build
        for name in ("AttackCmd", "WstateCmd", "WstateSplitCmd", "StatusCmd", "AddonCmd"):
            setattr(net2021, name, maker(name))

        def manage_cmd(turn):
            self.managed.append((turn, net2021.LastCmd))
            self.play()  # 假客户端：下一帧起把队列播完
        net2021.manage_cmd = manage_cmd
        self.net2021, self.fail_on = net2021, None
        sys.modules["netwar"].DO_S_WAR_PERFORM = maker("PerformCmd")
        patcher = patch.dict(sys.modules, {"war2021_net": net2021})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(lambda: sys.__dict__.pop("_mhxy_case_pump", None))

    def play(self):
        while self.war.Cmds:
            cmd = self.war.Cmds[0]
            if callable(cmd.Func) and cmd.Func is not self.war.action_end:
                cmd.Func()  # 哨兵自己置 state 并调用 next_cmd
            if self.war.Cmds and self.war.Cmds[0] is cmd:
                self.war.Cmds.pop(0)

    def test_perform_shorthand_expands_and_restores_turn(self):
        report = self.run_case({"name": "p", "steps": [{"pump": {"perform": {
            "magic_id": 1073, "victims": ["e0", "e1"], "hp_chg": 50, "hits": 2, "status": 80,
            "addons": [{"target": "e0", "pid": 9}]}}}]})
        self.assertEqual(report["status"], "passed", report)
        self.assertEqual([name for name, _ in self.queued], [
            "PerformCmd", "WstateCmd", "WstateSplitCmd", "WstateCmd", "WstateCmd", "WstateSplitCmd", "WstateCmd",
            "StatusCmd", "StatusCmd", "AddonCmd"])
        self.assertEqual(self.queued[0][1][:3], (1, [12, 11], 1073))
        self.assertEqual(self.queued[1][1][0], 12)
        self.assertEqual(self.managed, [(3, None)])  # LastCmd 先清空，再按 AccTurn 挂父子
        self.assertEqual(self.war.Turn, 0)  # 哨兵把临时加的 1 减回
        self.assertNotIn("_mhxy_case_pump", sys.__dict__)

    def test_raw_events_and_unsupported_op(self):
        report = self.run_case({"name": "e", "steps": [{"pump": {"events": [
            {"op": "attack", "data": {"attacker_id": "self", "victim_id": "e0"}},
            {"op": "wstate", "data": {"victim_id": "e0", "hp_chg": 30}},
            {"op": "action_end"}]}}]})
        self.assertEqual(report["status"], "passed", report)
        self.assertEqual([name for name, _ in self.queued], ["AttackCmd", "WstateCmd"])
        problems = "；".join(runner.validate({"name": "v", "steps": [
            {"pump": {"events": [{"op": "delete", "data": {}}]}},
            {"pump": {"perform": {"victims": ["e0"]}}},
            {"pump": {"perform": {"magic_id": 1}, "events": []}}]}))
        for word in ("op 只能是", "magic_id", "perform 和 events 二选一"):
            self.assertIn(word, problems)

    def test_validation_never_raises_and_checks_types(self):
        problems = "；".join(runner.validate({"name": "v", "steps": [
            {"pump": {"perform": {"magic_id": 1, "addons": None}}},
            {"pump": {"events": [{"op": []}, {"op": "wstate", "data": {"victim_id": "e0", "hp_chg": "100"}}]}},
            {"pump": {"perform": {"magic_id": True, "victims": "e0", "status": 120}}}]}))
        for word in ("addons 必须是列表", "op 只能是", "hp_chg 必须是整数", "magic_id 必须是整数",
                     "victims 必须是单位列表", "status 必须是0～100"):
            self.assertIn(word, problems)
        problems = "；".join(runner.validate({"name": "u", "steps": [
            {"pump": {"perform": {"magic_id": 1, "victims": []}}},
            {"pump": {"events": [{"op": "wstate", "data": {"victim_id": "pet0"}}, {"op": "wstate", "data": {"victim_id": "e00"}},
                                 {"op": "wstate", "data": {"victim_id": -1}}]}},
            {"war_act": {"role": {"act": "attack", "target": "pet0"}}}]}))
        for word in ("victims 不能为空", "victim_id 必须是单位，实际 'pet0'", "实际 'e00'", "实际 -1", "war_act.role.target"):
            self.assertIn(word, problems)
        self.assertEqual(runner.validate({"name": "ok", "steps": [{"pump": {"events": [
            {"op": "perform", "data": {"attacker_id": "self", "victims": [], "magic_id": 1}},
            {"op": "addon", "data": {"wid": "pet1", "pid": 1, "args": ""}}]}}]}), [])
        report = self.run_case({"name": "b", "steps": [{"pump": {"perform": {"magic_id": 1, "addons": None}}}]})
        self.assertEqual(report["status"], "blocked")

    def test_timeout_records_state_and_expr_error_is_not_timeout(self):
        self.net2021.manage_cmd = lambda turn: None  # 队列不播放
        report = self.run_case({"name": "t", "steps": [{"pump": {"perform": {"magic_id": 1}, "timeout": 0}}]})
        step = report["results"][0]["steps"][0]
        self.assertIn("手动 $at kill", report["results"][0]["failure"])
        self.assertIn("哨兵未执行", report["results"][0]["failure"])
        self.assertEqual(step["queue"]["turn"], 1)  # 哨兵没执行，Turn 仍多 1

        def run_then_server_turn(turn):  # 哨兵播完后，服务端回合命令排进队列
            self.play()
            self.war.Cmds.append(types.SimpleNamespace(state=0, Func=None))
        self.war.Cmds.clear()
        self.war.Turn = 0
        self.net2021.manage_cmd = run_then_server_turn
        report = self.run_case({"name": "s", "steps": [{"pump": {"perform": {"magic_id": 1}, "timeout": 0}}]})
        self.assertIn("哨兵已执行", report["results"][0]["failure"])
        self.assertEqual(self.war.Turn, 0)

        real = self.game

        def probe_error(name, arguments, **kwargs):
            if name == "execute_code" and "'marker'" in arguments["code"]:
                return {"result": {"ret": None, "error": "NameError: boom", "loginfo": ""}}
            return real(name, arguments)
        self.war.Cmds.clear()
        self.net2021.manage_cmd = lambda turn: None
        with patch.object(mcp_http, "call", probe_error):
            report = self.run_case({"name": "q", "steps": [{"pump": {"perform": {"magic_id": 1}, "timeout": 0}}]})
        self.assertIn("读取失败", report["results"][0]["steps"][0]["queue"])
        self.assertIn("状态未知", report["results"][0]["failure"])
        self.war.Cmds.clear()
        self.war.Turn = 0
        with patch.object(runner, "wait_for", side_effect=runner.StepFailed("等待条件报错（第 1 次轮询）")):
            report = self.run_case({"name": "x", "steps": [{"pump": {"perform": {"magic_id": 1}}}]})
        self.assertIn("等待条件报错", report["results"][0]["failure"])
        self.assertNotIn("queue", report["results"][0]["steps"][0])

    def test_construction_failure_rolls_back(self):
        self.fail_on = "StatusCmd"
        report = self.run_case({"name": "f", "steps": [{"pump": {"perform": {"magic_id": 1, "status": 50}}}]})
        self.assertIn("构造失败", report["results"][0]["failure"])
        self.assertEqual(self.war.Cmds, [])
        self.assertEqual(self.war.Turn, 0)
        self.assertEqual(self.managed, [])

    def test_not_idle_fails_and_timeout_reports_queue(self):
        self.war.Cmds.append(types.SimpleNamespace(state=0, Func=None))
        report = self.run_case({"name": "i", "steps": [{"pump": {"perform": {"magic_id": 1}}}]})
        self.assertIn("不在等待下指令阶段", report["results"][0]["failure"])
        self.war.Cmds.clear()
        self.net2021.manage_cmd = lambda turn: None  # 队列不播放
        report = self.run_case({"name": "t", "steps": [{"pump": {"perform": {"magic_id": 1}, "timeout": 0}}]})
        step = report["results"][0]["steps"][0]
        self.assertIn("pump 超时", report["results"][0]["failure"])
        self.assertTrue(step["queue"])


class SetupTests(WarBase):
    def setUp(self):
        super().setUp()
        sdata = types.ModuleType("sdata")
        sdata.hero = types.SimpleNamespace(Prop={"nSchool": 1, "nSect": 1})
        patcher = patch.dict(sys.modules, {"sdata": sdata})
        patcher.start()
        self.addCleanup(patcher.stop)

    def commands(self):
        return [args["command"] for name, args in self.game.calls if name == "execute_command"]

    def test_school_change_needs_allow_destructive(self):
        report = self.run_case({"name": "s", "setup": {"school": [2, 1]}, "steps": [{"exec": "1"}]})
        self.assertIn("allow_destructive", report["results"][0]["failure"])
        self.assertEqual(self.commands(), [])
        self.assertEqual(report["results"][0]["steps"], [])

    def test_skips_satisfied_and_sends_rest(self):
        report = self.run_case({"name": "s", "setup": {"school": [1, 1], "teji": "琴音三叠", "items": ["金创药", "佛光舍利子"],
                                                      "gm": ["$at full"]}, "steps": [{"exec": "1"}]})
        self.assertEqual(report["status"], "passed", report)
        self.assertEqual(self.commands(), ["$at teji 1 琴音三叠", "$at cloneobj 佛光舍利子", "$at full"])
        report = self.run_case({"name": "t", "setup": {"school": [3, 2], "allow_destructive": True}, "steps": [{"exec": "1"}]})
        self.assertEqual(self.commands()[-1], "$at cs 3 2")

    def test_validation(self):
        problems = "；".join(runner.validate({"name": "v", "setup": {"school": [1], "items": [], "x": 1},
                                              "steps": [{"exec": "1"}]}))
        for word in ("未知字段", "school 写成", "items 必须是非空字符串列表"):
            self.assertIn(word, problems)


class MediaTests(WarBase):
    def setUp(self):
        super().setUp()
        self.war.Turn = 0  # 用例开始时不在战斗中
        battle = types.SimpleNamespace(turns=[])
        collector = types.SimpleNamespace(_battle=None, _last_battle=None, _cur_turn=None, _enabled=False)
        collector._notify_export_done = lambda path: self.popups.append(path)
        self.popups, self.battle, self.collector = [], battle, collector
        fc = types.ModuleType("frame_collector")
        fc.g_collector = collector
        fc.get_instance = lambda: collector

        def start_collect():
            collector._enabled = True
        def stop_collect():
            collector._enabled = False
        fc.start_collect, fc.stop_collect = start_collect, stop_collect
        self.recording = None
        app = types.ModuleType("C_app")

        def start_record_screen(path, mouse=1, audio=1):
            self.recording = path
        def stop_record_screen():
            Path(self.recording).write_bytes(b"mp4")
            self.recording = None
        app.start_record_screen, app.stop_record_screen = start_record_screen, stop_record_screen
        app.is_record_screen = lambda: int(self.recording is not None)
        utils = types.ModuleType("utils")
        utils.screenshot = lambda callback, params, path: Path(path).write_bytes(b"png")
        sdata = types.ModuleType("sdata")
        sdata.env = types.SimpleNamespace(SCREENW=1024, SCREENH=768)
        patcher = patch.dict(sys.modules, {"frame_collector": fc, "C_app": app, "utils": utils, "sdata": sdata})
        patcher.start()
        self.addCleanup(patcher.stop)

    def finish_war(self):
        """假战斗：一次 magic_id 1073 的出手播完、战斗结束（导出时会弹窗）。"""
        action = types.SimpleNamespace(magic_id=1073, end_frame=10)
        self.battle.turns.append(types.SimpleNamespace(actions=[action]))
        self.collector._last_battle = self.battle
        self.collector._notify_export_done("frame.json")

    def test_record_frames_and_screenshot(self):
        self.target.finish = self.finish_war
        with patch("dataclasses.asdict", lambda data: {"turns": len(data.turns)}):  # 假 battle 不是 dataclass
            report = self.run_case({"name": "m", "record": True, "frames": True, "steps": [
                {"exec": "__import__('fake_target').finish()"},
                {"wait_for": {"preset": "war_action", "args": {"magic_id": 1073, "n": 1}, "timeout": 0}},
                {"screenshot": "出手后"}]})
        self.assertEqual(report["status"], "passed", report)
        media = report["results"][0]["media"]
        self.assertTrue(media["video"].endswith("case1.mp4") and Path(media["video"]).exists())
        self.assertEqual(json.loads(Path(media["frames"]).read_text(encoding="utf-8")), {"turns": 1})
        self.assertEqual(media["frame_actions"], 1)
        self.assertEqual(media["screenshots"][0]["label"], "出手后")
        self.assertEqual(self.popups, [])  # 导出弹窗被内部 Mock 挡住
        self.collector._notify_export_done("x")  # 已还原为原函数：再调用会记录弹窗
        self.assertEqual(self.popups, ["x"])
        self.assertIsNone(self.recording)
        self.assertEqual(report["restoration"], "restored")

    def test_frames_in_war_fails_and_preset_needs_frames(self):
        self.war.Turn = 1
        report = self.run_case({"name": "f", "frames": True, "steps": [{"exec": "1"}]})
        self.assertIn("帧采集要在进入战斗前开启", report["results"][0]["failure"])
        self.assertTrue(any("frames: true" in p for p in runner.validate(
            {"name": "g", "steps": [{"wait_for": {"preset": "war_action", "args": {"magic_id": 1, "n": 1}}}]})))

    def test_war_action_ignores_previous_battle(self):
        self.finish_war()  # 用例开始前的上一场已有 1073 的出手
        report = self.run_case({"name": "p", "frames": True, "steps": [
            {"wait_for": {"preset": "war_action", "args": {"magic_id": 1073, "n": 1}, "timeout": 0}}]})
        self.assertIn("等待超时", report["results"][0]["failure"])

    def test_begin_call_failure_still_stops_media(self):
        real = self.game

        def flaky(name, arguments, **kwargs):
            result = real(name, arguments)
            if name == "execute_code" and "_case_media_start" in arguments["code"]:
                raise OSError("timeout")  # 客户端已执行完开始阶段，回包丢失
            return result
        with patch.object(mcp_http, "call", flaky):
            report = self.run_case({"name": "b", "record": True, "frames": True, "steps": [{"exec": "1"}]})
        self.assertIn("timeout", report["results"][0]["failure"])
        self.assertIsNone(self.recording)
        self.assertFalse(self.collector._enabled)

    def test_missing_video_is_unverified_not_failure(self):
        sys.modules["C_app"].stop_record_screen = lambda: None
        with patch.object(runner, "VIDEO_WAIT", 0):
            report = self.run_case({"name": "v", "record": True, "steps": [{"exec": "1"}]})
        self.assertEqual(report["status"], "passed", report)
        self.assertTrue(any("mp4" in text for text in report["unverified"]))


class SearchTests(unittest.TestCase):
    def test_templates_are_valid(self):
        templates = runner.load_templates()
        self.assertGreaterEqual(len(templates), 3)
        for item in templates:
            self.assertEqual(runner.validate(item["case"]), [], item["path"])

    def test_template_match_and_skill_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp) / "data"
            data.mkdir()
            (data / "infoskillperform2021.py").write_text(
                '# -*- coding: utf-8 -*-\nPerformInfo = {\n1073 : ( "龙卷雨击", 1073, "x"),\n11949 : ( "龙卷雨击", 1073, "x"),\n}\n',
                encoding="utf-8")
            (data / "infosp.py").write_text('# -*- coding: utf-8 -*-\nSPInfo = {\n2010:( "琴音三叠", "x"),\n}\n',
                                            encoding="utf-8")
            self.assertTrue(runner.search(temp, ["战斗", "普攻"])["templates"])
            result = runner.search(temp, ["琴音三叠"])
            self.assertEqual(result["skills"], [{"name": "琴音三叠", "kind": "sp", "id": 2010, "magic_id": 5010}])
            self.assertEqual(runner.validate(result["skeletons"][0]), [])
            result = runner.search(temp, ["龙卷雨击", "不存在的词"])
            self.assertEqual([s["id"] for s in result["skills"]], [1073])


class FakeCtrl:
    def __init__(self, shown=True):
        self.shown = shown

    def is_real_hide(self):
        return not self.shown


class FakeHandle:
    def __init__(self, shown=True):
        self.ctrl = FakeCtrl(shown)

    def get_hide(self):
        return not self.ctrl.shown

    def hide(self, flag):
        self.ctrl.shown = not flag


class CleanUiTests(Base):
    """开局整理：按清单逐项关闭，每项单独捕获异常；前后可见窗口对比。"""

    def setUp(self):
        super().setUp()
        uisln = types.ModuleType("uisln")
        uisln.Single = type("Single", (FakeHandle,), {})
        self.checkin = type("CControl", (FakeHandle,), {"__module__": "checkin2018_msg"})()
        public_ui = types.ModuleType("public_ui")
        public_ui.CtrlObjsDict = {type(self.checkin): lambda: self.checkin}
        spirit = type("PalSpiritBtn", (uisln.Single,), {"__module__": "newbie2022_msg"})
        spirit.Instance = spirit()  # 常驻 UI：不在清单里，整理后仍可见
        hidden = type("Hidden", (uisln.Single,), {"__module__": "x"})
        hidden.Instance = hidden(False)
        self.classes = [spirit, hidden]  # __subclasses__ 是弱引用，留住类
        guide = types.ModuleType("ww_zlp22_chess_guide")
        names = ["hide_dlg_heroitem", "hide_dlg_status", "hide_dlg_dup", "hide_dlg_task", "hide_dlg_summon",
                 "hide_dlg_shop", "hide_dlg_friend", "hide_dlg_chat", "hide_dlg_factionunion", "hide_dlg_team",
                 "hide_dlg_rili", "hide_dlg_checkin", "hide_small_map", "hide_dlg_fairy", "hide_dlg_pet",
                 "hide_dlg_achieve"]
        self.called = []
        for name in names:
            setattr(guide, name, lambda name=name: self.called.append(name))
        guide.hide_dlg_checkin = lambda: (self.called.append("hide_dlg_checkin"), self.checkin.hide(1))

        def broken():
            raise RuntimeError("shop boom")
        guide.hide_dlg_shop = broken
        interface = types.ModuleType("checkin2018_interface")
        interface.show_checkin_dlg = lambda: None
        utils = types.ModuleType("utils")
        self.unscheduled = []
        utils.UnSchedule = self.unscheduled.append
        new_content = types.ModuleType("ww_2022checkin_msg")
        self.content = FakeHandle()
        new_content.PalNewContent = types.SimpleNamespace(get_ins=lambda: self.content)
        dlgnpc = types.ModuleType("dlgnpc")
        dlgnpc.hide_dlgnpc = lambda: self.called.append("npc")
        self.interface = interface
        patcher = patch.dict(sys.modules, {"uisln": uisln, "public_ui": public_ui, "ww_zlp22_chess_guide": guide,
                                           "checkin2018_interface": interface, "utils": utils,
                                           "ww_2022checkin_msg": new_content, "dlgnpc": dlgnpc})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_closes_listed_windows_and_isolates_failures(self):
        report = self.run_case({"name": "c", "steps": [{"exec": "1"}]})
        result = report["results"][0]
        self.assertEqual(report["status"], "passed", report)  # 整理失败只记 unverified
        cleaned = result["clean_ui"]
        self.assertEqual(cleaned["closed"], ["checkin2018_msg.CControl"])
        self.assertEqual(cleaned["visible"], ["newbie2022_msg.PalSpiritBtn"])
        self.assertEqual(sorted(cleaned["errors"]), ["hide_dlg_shop"])
        self.assertIn("shop boom", cleaned["errors"]["hide_dlg_shop"])
        self.assertIn("hide_dlg_achieve", self.called)  # 商城失败后后面的照常执行
        self.assertIn("npc", self.called)
        self.assertEqual(self.unscheduled, [self.interface.show_checkin_dlg])
        self.assertTrue(self.content.get_hide())
        self.assertTrue(any("开局整理" in text for text in result["unverified"]))

    def test_can_be_disabled(self):
        report = self.run_case({"name": "c", "clean_ui": False, "steps": [{"exec": "1"}]})
        self.assertNotIn("clean_ui", report["results"][0])
        self.assertEqual(self.called, [])
        self.assertFalse(self.checkin.get_hide())


class FinallyTests(Base):
    def test_runs_after_failure_and_reports_separately(self):
        report = self.run_case({"name": "f", "mocks": [{"name": "v", "patch": "fake_target.value", "value": "5"}],
                                "steps": [{"exec": "1/0"}, {"exec": "never()"}],
                                "finally": [{"exec": "__import__('fake_target').value", "save_as": "seen"},
                                            {"gm": "$at kill"}]})
        result = report["results"][0]
        self.assertEqual(report["status"], "failed")
        self.assertIn("客户端报错", result["failure"])
        self.assertNotIn("finally_failure", result)
        self.assertEqual([item["index"] for item in result["finally"]], ["F1", "F2"])
        self.assertEqual(result["finally"][0]["ret"], 5)  # 在还原 Mock 之前执行
        self.assertIn(("execute_command", {"devid": "dev", "command": "$at kill"}), self.game.calls)
        self.assertEqual(self.target.value, 1)

    def test_finally_failure_fails_case(self):
        report = self.run_case({"name": "f", "steps": [{"exec": "1"}],
                                "finally": [{"assert": "False", "message": "退战失败"}, {"gm": "$at kill"}]})
        result = report["results"][0]
        self.assertEqual(report["status"], "failed")
        self.assertNotIn("failure", result)
        self.assertIn("退战失败", result["finally_failure"])
        self.assertEqual(len(result["finally"]), 1)  # finally 内失败即停
        self.assertIn("finally 失败", report["cases"][0])

    def test_validation(self):
        problems = "；".join(runner.validate({"name": "a", "steps": [{"exec": "1"}], "clean_ui": 1,
                                              "finally": [{"nope": 1}]}))
        self.assertIn("clean_ui 必须是 true 或 false", problems)
        self.assertIn("finally[1]：必须恰好有一个步骤类型", problems)
        self.assertIn("finally 必须是步骤列表",
                      runner.validate({"name": "a", "steps": [{"exec": "1"}], "finally": {}}))


class LongValueTests(Base):
    def test_long_return_saved_to_file_and_report_stays_json(self):
        report = self.run_case({"name": "l", "steps": [{"exec": "[{'wid': i, 'name': 'x' * 20} for i in range(200)]"}]})
        ret = report["results"][0]["steps"][0]["ret"]
        self.assertEqual(set(ret), {"clipped", "length", "file"})
        self.assertEqual(len(ret["clipped"]), runner.TEXT_LIMIT)
        full = json.loads(Path(ret["file"]).read_text(encoding="utf-8"))
        self.assertEqual(len(full), 200)
        self.assertTrue(Path(ret["file"]).name.endswith("_step1_ret.json"))
        json.loads(json.dumps(report, ensure_ascii=False))

    def test_clip_is_structured(self):
        self.assertEqual(runner.clip("abc"), "abc")
        clipped = runner.clip("x" * 5000)
        self.assertEqual(clipped["length"], 5002)  # 含 JSON 引号
        self.assertEqual(len(clipped["clipped"]), runner.TEXT_LIMIT)


class Proxy:
    """模拟 sdata.huodong 这类代理：属性存在内层对象上，不在自己的 __dict__ 和类上。"""

    def __init__(self, inner, writable=True):
        object.__setattr__(self, "_inner", inner)
        object.__setattr__(self, "_writable", writable)

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def __setattr__(self, name, value):
        if self._writable:
            setattr(self._inner, name, value)


class ProxyMockTests(Base):
    def test_proxy_attribute_written_back(self):
        inner = types.SimpleNamespace(flag=0)
        self.target.proxy = Proxy(inner)
        report = self.run_case({"name": "p", "mocks": [{"name": "f", "patch": "fake_target.proxy.flag", "value": "1"}],
                                "steps": [{"assert": "__import__('fake_target').proxy.flag == 1"}]})
        self.assertEqual((report["status"], report["restoration"]), ("passed", "restored"), report)
        self.assertEqual(inner.flag, 0)
        self.assertEqual(report["results"][0]["mocks"][0]["install"]["mode"], "proxy")

    def test_proxy_ignoring_assignment_fails_install_and_restores(self):
        inner = types.SimpleNamespace(flag=0)
        self.target.proxy = Proxy(inner, writable=False)
        report = self.run_case({"name": "p", "mocks": [{"name": "f", "patch": "fake_target.proxy.flag", "value": "1"}],
                                "steps": [{"exec": "1"}]})
        self.assertEqual(report["status"], "failed")
        self.assertIn("install/restore", json.dumps(report["results"][0]["mocks"], ensure_ascii=False))
        self.assertEqual(report["restoration"], "restored")
        self.assertNotIn("_mhxy_case_mocks", sys.__dict__)

    def test_sdata_like_cache_and_descriptor(self):
        """仿 sdata_imp：普通值第一次读取时缓存进实例 __dict__；Property 是挂在类上的数据描述符。"""
        store = {"prop": 10}

        class Prop:
            def __get__(self, inst, owner):
                return store["prop"] if inst is not None else self

            def __set__(self, inst, value):
                store["prop"] = value

        module = types.SimpleNamespace(flag=False)

        class ModData:
            prop = Prop()

            def __getattr__(self, name):
                value = getattr(module, name)
                self.__dict__[name] = value  # 缓存，同 sdata_imp._ModData.__getattr__
                return value

        self.target.huodong = ModData()
        case = {"name": "s", "mocks": [{"name": "f", "patch": "fake_target.huodong.flag", "value": "True"},
                                       {"name": "p", "patch": "fake_target.huodong.prop", "value": "99"}],
                "steps": [{"assert": "__import__('fake_target').huodong.flag is True"},
                          {"assert": "__import__('fake_target').huodong.prop == 99"}]}
        report = self.run_case(case)
        self.assertEqual((report["status"], report["restoration"]), ("passed", "restored"), report)
        modes = [item["install"]["mode"] for item in report["results"][0]["mocks"]]
        self.assertEqual(modes, ["proxy", "descriptor"])
        self.assertIs(self.target.huodong.flag, False)
        self.assertEqual(store["prop"], 10)

    def test_absent_attribute_removed(self):
        report = self.run_case({"name": "a", "mocks": [{"name": "n", "patch": "fake_target.brand_new", "value": "3"}],
                                "steps": [{"assert": "__import__('fake_target').brand_new == 3"}]})
        self.assertEqual((report["status"], report["restoration"]), ("passed", "restored"), report)
        self.assertFalse(hasattr(self.target, "brand_new"))


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
