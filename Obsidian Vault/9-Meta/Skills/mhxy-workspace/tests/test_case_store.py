"""工作区用例的扫描、归属校验、通过记录和检索（case_store.py）。"""
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("case_store_under_test", SCRIPTS / "case_store.py")
store = importlib.util.module_from_spec(spec)
spec.loader.exec_module(store)

META = {"issue": "860053", "spec": None, "targets": ["war/dlgwar.py"], "keywords": ["成语", "弹窗"]}


def case(name, **meta):
    return {"name": name, **{**META, **meta}, "steps": [{"exec": "1"}]}


class StoreBase(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp()).resolve()

    def write(self, rel, value):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False), encoding="utf-8")
        return path


class MetaTests(StoreBase):
    def test_required_only_for_workspace_cases(self):
        bare = {"name": "x", "steps": []}
        self.assertEqual(store.meta_problems(bare, False), [])
        self.assertIn("归属字段", store.meta_problems(bare, True)[0])
        self.assertEqual(store.meta_problems(case("x"), True), [])
        self.assertEqual(store.meta_problems(case("x", issue=None, spec="spec/a.md", keywords=[]), True), [])
        placeholder = case("x", targets=["<被测文件或模块>"])  # 模板里的占位：模板本身合法，工作区用例要换掉
        self.assertEqual(store.meta_problems(placeholder, False), [])
        self.assertIn("模板占位", store.meta_problems(placeholder, True)[0])
        for wrong in ({"issue": 860053}, {"issue": "abc"}, {"spec": ""}, {"targets": []}, {"targets": ["a", 1]},
                      {"keywords": "成语"}):
            self.assertTrue(store.meta_problems(case("x", **wrong), False), wrong)

    def test_location(self):
        self.assertEqual(store.area(self.root, self.root / ".mhxy-workspace/cases/1/a.json"), "cases")
        self.assertEqual(store.area(self.root, self.root / ".mhxy-workspace/coverage/t/a.json"), "coverage")
        self.assertIsNone(store.area(self.root, self.root / "spec/a.md"))
        self.assertIsNone(store.area(self.root, Path(tempfile.gettempdir()) / "a.json"))
        self.assertIn("<工单号或功能名>", store.location_problems(self.root, self.root / ".mhxy-workspace/cases/a.json")[0])
        self.assertTrue(store.location_problems(self.root, self.root / ".mhxy-workspace/cases/reports/a.json"))
        self.assertEqual(store.location_problems(self.root, self.root / ".mhxy-workspace/cases/x/a.json"), [])
        self.assertIn("单个路径段", store.location_problems(self.root, self.root / ".mhxy-workspace/cases/x/y/a.json")[0])
        self.assertIn("保留名", store.location_problems(self.root, self.root / ".mhxy-workspace/cases/runs.json/a.json")[0])

    def test_digest_ignores_key_order(self):
        self.assertEqual(store.digest({"a": 1, "b": [1, "中"]}), store.digest({"b": [1, "中"], "a": 1}))
        self.assertNotEqual(store.digest({"a": 1}), store.digest({"a": 2}))


class ScanTests(StoreBase):
    def test_scan_collects_cases_and_reports_problems(self):
        self.write(".mhxy-workspace/cases/860053/popup.json", [case("弹窗"), case("关闭")])
        self.write(".mhxy-workspace/cases/flat.json", case("平铺"))
        self.write(".mhxy-workspace/cases/860053/bad.json", "{")
        self.write(".mhxy-workspace/cases/860053/nometa.json", {"name": "缺归属", "steps": []})
        self.write(".mhxy-workspace/cases/reports/20261111.json", {"status": "passed"})
        self.write(".mhxy-workspace/cases/runs.json", {"cases": {}})
        self.write(".mhxy-workspace/coverage/task/cover.json", case("覆盖率", issue="849400"))
        self.write(".mhxy-workspace/coverage/task/query.json", {"status": "passed"})  # 不是用例，跳过
        self.write(".mhxy-workspace/coverage/task/broken.json", "{")  # 读不了的不静默跳过
        self.write(".mhxy-workspace/cases/1/dup.json", [case("同名"), case("同名")])
        entries, problems = store.scan(self.root)
        self.assertEqual(sorted((item["path"], item["name"]) for item in entries), [
            (".mhxy-workspace/cases/860053/popup.json", "关闭"), (".mhxy-workspace/cases/860053/popup.json", "弹窗"),
            (".mhxy-workspace/coverage/task/cover.json", "覆盖率")])
        self.assertEqual(sorted(item["path"] for item in problems), [
            ".mhxy-workspace/cases/1/dup.json", ".mhxy-workspace/cases/860053/bad.json",
            ".mhxy-workspace/cases/860053/nometa.json", ".mhxy-workspace/cases/flat.json",
            ".mhxy-workspace/coverage/task/broken.json"])

    def test_spec_blocks(self):
        path = self.write("spec/a.md", "# A\n## 测试用例\n```json\n" + json.dumps(case("s")) + "\n```\n## 其他\n"
                          "```json\n{}\n```\n")
        self.assertEqual([item["name"] for _, item in store.load_cases(path)], ["s"])


class RunsTests(StoreBase):
    def result(self, path, name, status, value):
        return {"source": str(path), "name": name, "status": status, "case_hash": store.digest(value)}

    def test_record_keeps_last_pass_and_flags_changes(self):
        value = case("弹窗")
        path = self.write(".mhxy-workspace/cases/860053/popup.json", value)
        first = datetime(2026, 11, 11, 10, 0, tzinfo=timezone.utc)
        self.assertEqual(store.record_runs(self.root, [self.result(path, "弹窗", "passed", value)], "r1.json", first), [])
        later = datetime(2026, 11, 11, 11, 0, tzinfo=timezone.utc)
        self.assertEqual(store.record_runs(self.root, [self.result(path, "弹窗", "failed", value)], "r2.json", later), [])
        run = store.read_runs(self.root)[".mhxy-workspace/cases/860053/popup.json#弹窗"]
        self.assertEqual((run["last_status"], run["last_passed"], run["report"]),
                         ("failed", first.isoformat(timespec="seconds"), "r2.json"))
        found = store.find(self.root, issue="860053")["cases"][0]
        self.assertEqual((found["last_status"], found["changed_since_pass"]), ("failed", False))
        self.write(".mhxy-workspace/cases/860053/popup.json", case("弹窗", keywords=["改过"]))
        self.assertTrue(store.find(self.root, issue="860053")["cases"][0]["changed_since_pass"])

    def test_sources_outside_root_are_skipped(self):
        outside = Path(tempfile.mkdtemp()) / "a.json"
        self.assertEqual(store.record_runs(self.root, [self.result(outside, "x", "passed", {})], "r"), [])
        self.assertFalse(store.runs_path(self.root).exists())

    def test_busy_and_stale_lock(self):
        path = self.write(".mhxy-workspace/cases/1/a.json", case("a"))
        lock = self.write(".mhxy-workspace/cases/runs.json.lock", "")
        with patch.object(store, "LOCK_WAIT", 0.2):
            problems = store.record_runs(self.root, [self.result(path, "a", "passed", {})], "r")
        self.assertIn("被占用", problems[0])
        old = time.time() - store.LOCK_STALE - 5
        import os
        os.utime(lock, (old, old))
        self.assertEqual(store.record_runs(self.root, [self.result(path, "a", "passed", {})], "r"), [])
        self.assertFalse(lock.exists())

    def test_corrupt_runs_is_reported(self):
        path = self.write(".mhxy-workspace/cases/1/a.json", case("a"))
        self.write(".mhxy-workspace/cases/runs.json", "[")
        problems = store.record_runs(self.root, [self.result(path, "a", "passed", {})], "r")
        self.assertIn("通过记录", problems[0])
        with self.assertRaises(store.CaseError):
            store.find(self.root, issue="1")


class FindTests(StoreBase):
    def setUp(self):
        super().setUp()
        self.write(".mhxy-workspace/cases/860053/popup.json",
                   [case("弹窗", targets=["war/dlgwar.py", "westworld/ui_msg/"]), case("模块", targets=["netwar"])])
        self.write(".mhxy-workspace/cases/sign/checkin.json",
                   case("签到", issue=None, targets=["westworld/checkin2018_interface.py"], keywords=["签到"]))

    def names(self, **kwargs):
        return sorted(item["name"] for item in store.find(self.root, **kwargs)["cases"])

    def test_target_matching(self):
        self.assertTrue(store.target_matches("war/dlgwar.py", "war/dlgwar.py"))
        self.assertTrue(store.target_matches("dlgwar.py", "war/dlgwar.py"))
        self.assertTrue(store.target_matches("./war/dlgwar.py", "D:/x/mhimage/war/dlgwar.py"))
        self.assertTrue(store.target_matches("dlgwar", "war/dlgwar.py"))
        self.assertTrue(store.target_matches("war\\", "war/dlgwar.py"))
        self.assertTrue(store.target_matches("ui_msg/", "westworld/ui_msg/a.py"))
        self.assertFalse(store.target_matches("war", "war/dlgwar.py"))  # 模块名只比文件名
        self.assertFalse(store.target_matches("dlgwar.py", "war/xdlgwar.py"))
        self.assertFalse(store.target_matches("war/", "warx/a.py"))

    def test_conditions(self):
        self.assertEqual(self.names(issue="860053"), ["弹窗", "模块"])
        self.assertEqual(self.names(files=["war/dlgwar.py"]), ["弹窗"])
        self.assertEqual(self.names(files=["gameplay/netwar.py"]), ["模块"])
        self.assertEqual(self.names(terms=["签到"]), ["签到"])
        self.assertEqual(self.names(terms=["860053", "netwar"]), ["模块"])  # 关键词也查工单号和目标
        self.assertEqual(self.names(changed=["westworld/ui_msg/x.py", "westworld/checkin2018_interface.py"]),
                         ["弹窗", "签到"])
        self.assertEqual(self.names(changed=[]), [])
        self.assertEqual(self.names(issue="860053", terms=["签到"]), [])

    def test_context_summary(self):
        value = json.loads((self.root / ".mhxy-workspace/cases/860053/popup.json").read_text(encoding="utf-8"))[0]
        store.record_runs(self.root, [{"source": str(self.root / ".mhxy-workspace/cases/860053/popup.json"),
                                       "name": "弹窗", "status": "passed", "case_hash": store.digest(value)}], "r")
        self.write(".mhxy-workspace/cases/flat.json", case("平铺"))
        summary = store.context_summary(self.root, ["860053", "849400"])
        self.assertEqual((summary["total"], summary["problem_files"]), (3, 1))
        self.assertEqual(len(summary["tracked"]), 1)
        item = summary["tracked"][0]
        self.assertEqual((item["issue_id"], item["count"], item["passed"]), ("860053", 2, 1))
        self.assertEqual(item["files"], [".mhxy-workspace/cases/860053/popup.json"])
        self.assertTrue(item["last_passed"])
        self.assertNotIn("steps", json.dumps(summary))


if __name__ == "__main__":
    unittest.main()
