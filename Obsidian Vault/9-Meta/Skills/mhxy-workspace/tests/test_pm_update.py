"""隔离验证工单状态修改和工时登记；用假服务器，不访问真实账号或网络。"""
import argparse
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import pm_update as u

PERCENTS = "新建,10%,20%,30%,40%,50%,60%,70%,80%,90%"
STATUSES = [{"id": 1, "name": "新建", "disabled": False}, {"id": 55, "name": "80%", "disabled": False},
            {"id": 42, "name": "测试中", "disabled": False}, {"id": 5, "name": "代码审查", "disabled": False},
            {"id": 3, "name": "关闭", "disabled": True}]
ACTIVITIES = [{"id": 9, "name": "程序开发-制作", "role_ids": [], "active": True},
              {"id": 8, "name": "策划设计", "role_ids": [6], "active": True},
              {"id": 99, "name": "已停用", "role_ids": [], "active": False}]


class Server:
    """模拟易协作：保存一张工单的状态和工时，记录收到的写请求。"""

    def __init__(self, status_id=1, entries=None):
        self.status_id = status_id
        self.entries = list(entries or [])
        self.lock_version = 2
        self.writes = []
        self.fail = {}  # 路径片段 -> 要抛出的错误；用于模拟写入或读回失败。
        self.drop_writes = False  # 为真时写请求返回成功但不生效。
        self.can_edit = True

    def request(self, client, method, path, body=None):
        for fragment, error in self.fail.items():
            if fragment in path and (method != "GET" or fragment.startswith("GET ")):
                raise error
        if method == "GET" and path == "/issues/864519.json":
            status = next(item for item in STATUSES if item["id"] == self.status_id)
            return {"issue": {"id": 864519, "subject": "【全部服务器放出】特效迭代", "tracker": {"id": 26, "name": "[客户端]程序开发"},
                              "status": {"id": status["id"], "name": status["name"], "is_closed": False},
                              "fixed_version": {"id": 1076, "name": "2026-11-17维护内容"}}}
        if path == "/api/v6/issue_form/form":
            return {"res_code": 1, "data": {
                "issue": {"id": 864519, "status_id": self.status_id, "lock_version": self.lock_version,
                          "last_journal_id": 7, "project_id": 16},
                "fields": {"left": [{"id": "status_id", "possible_values": copy.deepcopy(STATUSES)}]}}}
        if method == "GET" and path.endswith("/time_entries/new_options.json"):
            return {"res_code": 1, "data": {"options": {
                "activities": copy.deepcopy(ACTIVITIES), "users": [{"id": 986, "role_ids": [7]}],
                "can_edit": self.can_edit,
                "list": {"current": {"currentIssueTimeEntry": copy.deepcopy(self.entries)}}}}}
        if method == "POST" and path == "/api/v6/java_proxy/time_entries/save.json":
            self.writes.append(("time", body))
            if not self.drop_writes:
                entry = dict(body["time_entry"][0], id=1000 + len(self.entries), user_id=str(body["time_entry"][0]["user_id"]))
                self.entries.append(entry)
            return {"res_code": 1, "data": []}
        if method == "PUT" and path == "/issues/864519.json":
            self.writes.append(("status", body))
            if not self.drop_writes:
                self.status_id = body["issue"]["status_id"]
                self.lock_version += 1
            return None
        raise AssertionError(f"未预期的请求：{method} {path}")


def arguments(**values):
    defaults = {"issue_id": "864519", "status": None, "status_from": None, "hours": None, "activity": None,
                "spent_on": "2026-11-11", "comments": "", "apply": False}
    defaults.update(values)
    return argparse.Namespace(**defaults)


class UpdateTests(unittest.TestCase):
    def run_update(self, server, **values):
        with patch.object(u, "request", server.request):
            return u.run(object(), 986, arguments(**values))

    def test_summary_only_reads(self):
        server = Server(entries=[{"id": 1, "user_id": "986", "hours": 0.1}, {"id": 2, "user_id": "12", "hours": 1.0}])
        output, code = self.run_update(server)
        self.assertEqual(code, 0)
        self.assertEqual(output["issue"]["target_version"], "2026-11-17维护内容")
        self.assertEqual(output["issue"]["status"], "新建")
        self.assertEqual(output["issue"]["time_entries"], {"count": 2, "hours": 1.1, "mine_count": 1, "mine_hours": 0.1})
        self.assertNotIn("status", output)
        self.assertEqual(server.writes, [])

    def test_preview_plans_without_writing(self):
        server = Server()
        output, code = self.run_update(server, status="代码审查", status_from=PERCENTS, hours="0.2", activity="程序开发-制作")
        self.assertEqual((code, output["applied"]), (0, False))
        self.assertEqual(output["status"]["action"], "change")
        self.assertEqual(output["time_entry"]["action"], "add")
        self.assertNotIn("entry", output["time_entry"])
        self.assertEqual(server.writes, [])

    def test_apply_logs_time_then_changes_status(self):
        server = Server()
        output, code = self.run_update(server, status="代码审查", status_from=PERCENTS, hours="0.2",
                                       activity="程序开发-制作", apply=True)
        self.assertEqual(code, 0)
        self.assertEqual([kind for kind, _ in server.writes], ["time", "status"])
        self.assertEqual(server.writes[0][1], {"time_entry": [{
            "issue_id": 864519, "project_id": 16, "activity_id": 9, "hours": 0.2, "spent_on": "2026-11-11",
            "user_id": 986, "comments": ""}]})
        self.assertEqual(server.writes[1][1], {"id": 864519, "issue": {"status_id": 5, "lock_version": 2},
                                               "last_journal_id": 7, "project_id": 16})
        self.assertTrue(output["status"]["done"] and output["time_entry"]["done"])
        self.assertEqual(output["time_entry"]["id"], 1000)
        self.assertEqual(output["errors"], [])

    def test_already_in_review_only_appends_time(self):
        server = Server(status_id=5, entries=[{"id": 1, "user_id": "986", "hours": 0.1, "activity_id": 9,
                                               "spent_on": "2026-11-11"}])
        output, code = self.run_update(server, status="代码审查", status_from=PERCENTS, hours="0.1",
                                       activity="程序开发-制作", apply=True)
        self.assertEqual(code, 0)
        self.assertEqual([kind for kind, _ in server.writes], ["time"])
        self.assertEqual((output["status"]["action"], output["status"]["done"]), ("skip", False))
        self.assertEqual(len(server.entries), 2)

    def test_status_outside_sources_is_skipped(self):
        server = Server(status_id=42)
        output, code = self.run_update(server, status="代码审查", status_from=PERCENTS, apply=True)
        self.assertEqual((code, output["status"]["action"]), (0, "skip"))
        self.assertIn("测试中", output["status"]["reason"])
        self.assertEqual(server.writes, [])

    def test_percent_status_moves_to_review(self):
        server = Server(status_id=55)
        output, code = self.run_update(server, status="代码审查", status_from=PERCENTS, apply=True)
        self.assertEqual((code, server.status_id), (0, 5))

    def test_invalid_inputs_are_rejected_before_any_write(self):
        cases = [
            {"status": "不存在"},
            {"status": "关闭"},
            {"hours": "0.2", "activity": "没有这个活动"},
            {"hours": "0.2", "activity": "策划设计"},
            {"hours": "0.2", "activity": "已停用"},
            {"status": "代码审查", "hours": "0.2", "activity": "没有这个活动"},
        ]
        for values in cases:
            server = Server()
            with self.subTest(values=values), self.assertRaises(u.UpdateError):
                self.run_update(server, apply=True, **values)
            self.assertEqual(server.writes, [])
        server = Server()
        server.can_edit = False
        with self.assertRaises(u.UpdateError):
            self.run_update(server, hours="0.2", activity="程序开发-制作", apply=True)

    def test_hours_and_date_validation(self):
        for text in ("0", "-1", "0.125", "1000", "abc", "nan", "inf"):
            with self.subTest(text=text), self.assertRaises(u.UpdateError):
                u.parse_hours(text)
        self.assertEqual(float(u.parse_hours("0.5")), 0.5)
        self.assertEqual(float(u.parse_hours("999.99")), 999.99)
        with self.assertRaises(u.UpdateError):
            u.parse_date("2026/11/11")
        with self.assertRaises(u.UpdateError):
            u.split_names("新建,,10%")
        self.assertEqual(u.split_names("新建， 10%"), ["新建", "10%"])

    def test_time_failure_stops_before_status(self):
        server = Server()
        server.fail["time_entries/save.json"] = u.UpdateError("接口返回 HTTP 422：工时不合法")
        output, code = self.run_update(server, status="代码审查", hours="0.2", activity="程序开发-制作", apply=True)
        self.assertEqual(code, 1)
        self.assertEqual(server.status_id, 1)
        self.assertIn("HTTP 422", output["errors"][0])
        self.assertFalse(output["time_entry"]["done"])

    def test_write_error_but_server_applied_counts_as_done(self):
        server = Server()
        real = server.request

        def flaky(client, method, path, body=None):
            value = real(client, method, path, body)
            if method == "POST" and path.endswith("save.json"):
                raise u.UpdateError("网络请求失败，结果不明")
            return value

        with patch.object(u, "request", flaky):
            output, code = u.run(object(), 986, arguments(hours="0.2", activity="程序开发-制作", apply=True))
        self.assertEqual((code, output["time_entry"]["done"]), (0, True))

    def test_status_failure_after_time_is_partial(self):
        server = Server()
        server.fail["/issues/864519.json"] = u.UpdateError("接口返回 HTTP 422：缺少必填字段")
        output, code = self.run_update(server, status="代码审查", hours="0.2", activity="程序开发-制作", apply=True)
        self.assertEqual(code, 2)
        self.assertTrue(output["time_entry"]["done"])
        self.assertFalse(output["status"]["done"])
        self.assertIn("缺少必填字段", output["errors"][0])

    def test_silently_ignored_writes_are_reported(self):
        server = Server()
        server.drop_writes = True
        output, code = self.run_update(server, status="代码审查", apply=True)
        self.assertEqual(code, 1)
        self.assertIn("读回状态仍是", output["errors"][0])
        output, code = self.run_update(server, hours="0.2", activity="程序开发-制作", apply=True)
        self.assertEqual(code, 1)
        self.assertIn("没有找到新记录", output["errors"][0])

    def test_readback_failure_is_unknown_not_clean(self):
        server = Server()
        real = server.request
        state = {"posted": False}

        def broken(client, method, path, body=None):
            if state["posted"] and method == "GET":
                raise u.UpdateError("网络请求失败，结果不明")
            value = real(client, method, path, body)
            if method == "POST" and path.endswith("save.json"):
                state["posted"] = True
            return value

        with patch.object(u, "request", broken):
            output, code = u.run(object(), 986, arguments(hours="0.2", activity="程序开发-制作", apply=True))
        self.assertEqual(code, 2)
        self.assertIn("结果不明", output["errors"][0])

    def test_form_read_failure_before_put_is_not_a_write(self):
        server = Server()
        real = server.request
        calls = {"form": 0}

        def broken(client, method, path, body=None):
            if path == "/api/v6/issue_form/form":
                calls["form"] += 1
                if calls["form"] == 2:
                    raise u.UpdateError("网络请求失败，结果不明")
            return real(client, method, path, body)

        with patch.object(u, "request", broken):
            output, code = u.run(object(), 986, arguments(status="代码审查", apply=True))
        self.assertEqual((code, server.writes), (1, []))
        self.assertIn("尚未发出", output["errors"][0])

    def test_argument_combinations(self):
        for argv in (["--issue-id", "864519", "--hours", "0.2"],
                     ["--issue-id", "864519", "--activity", "程序开发-制作"],
                     ["--issue-id", "864519", "--status-from", "新建"],
                     ["--issue-id", "864519", "--comments", "x"],
                     ["--issue-id", "864519", "--apply"],
                     ["--issue-id", "abc", "--status", "代码审查"],
                     ["--issue-id", "864519", "--hours", "9999", "--activity", "程序开发-制作"]):
            with self.subTest(argv=argv), patch.object(u.corp_login, "load_credentials") as load, \
                    patch("sys.stderr"):
                self.assertEqual(u.main(argv), 1)
                load.assert_not_called()

    def test_server_message(self):
        self.assertEqual(u.server_message(b'{"errors": ["a", "b"]}'), '["a", "b"]')
        self.assertEqual(u.server_message(b'{"res_code": 0, "res_msg": "no"}'), "no")
        self.assertEqual(u.server_message(b"<html>"), "")


if __name__ == "__main__":
    unittest.main()
