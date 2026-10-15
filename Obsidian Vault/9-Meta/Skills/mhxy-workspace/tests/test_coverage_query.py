"""Offline coverage contract tests; fixtures do not stand in for authenticated QA."""
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import sys
import types
import http.cookiejar
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import corp_login  # noqa: E402

spec = importlib.util.spec_from_file_location("coverage_query", Path(__file__).resolve().parents[1] / "scripts/coverage_query.py")
q = importlib.util.module_from_spec(spec)
spec.loader.exec_module(q)


class FixtureClient:
    """Serve explicit payloads for the documented website endpoints."""

    def __init__(self):
        self.missing = False
        self.ignored = []
        self.confirmers = {}
        self.required = [10, 11]
        self.version = 123
        self.history_version = 123
        self.branch = "branchs/dev/test"
        self.date = "2026-09-28T10:00:00+08:00"
        self.history_branch = "branchs/dev/test"
        self.calls = []

    def get(self, path, **params):
        self.calls.append((path, params))
        if path == "/api/tasks/test":
            return {"task_id": "test", "cur_branch": self.branch, "cur_ver": self.version}
        if "/coverage/rates/" in path:
            return {"total_rate": 100, "rates": {"module.py": 100}}
        if path.endswith("/coverage/confirmers"):
            return self.confirmers
        if path.endswith("/commits/history"):
            return {"items": [{"task_id": "test", "date": self.date, "branch": self.history_branch, "revision": self.history_version}]}
        if "/coverage/require/" in path:
            return self.required
        if "/coverage/specific/" in path:
            return {"lines": {"10": [0]}, "ids": ["evidence"]}
        if "/coverage/history/" in path:
            return {"lines": {} if self.missing else {"11": [0]}, "ids": ["history"]}
        if "/ignore/" in path:
            return self.ignored
        raise AssertionError(path)


class QueryTests(unittest.TestCase):
    def test_cli_uses_config_password_and_derived_coder_without_output(self):
        secret = "synthetic-config-secret"
        config = {"openid_username": "developer@corp.netease.com", "openid_password": secret, "coder_name": "developer"}
        workspace = types.SimpleNamespace(WorkspaceError=ValueError, load_config=lambda *args: dict(config),
                                          svn_branch=lambda root: None)
        auth = types.SimpleNamespace(AuthError=ValueError)
        from unittest.mock import Mock
        auth.login = Mock(return_value=http.cookiejar.CookieJar())
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        global_config = Path(directory.name) / "config.json"
        global_config.write_text(json.dumps({key: config[key] for key in ("openid_username", "openid_password")}), encoding="utf-8")
        argv = ["coverage_query.py", "--task-name", "test", "--branch", "branchs/dev/test", "--global-config", str(global_config)]
        # 指定其他账号（大小写不同的同一账号仍复用）时不使用已存密码，改为交互输入。
        for extra, expected_password in (([], secret), (["--openid-user", "Developer"], secret),
                                         (["--openid-user", "other"], "synthetic-typed")):
            output = io.StringIO()
            with patch.dict(sys.modules, {"workspace": workspace, "coverage_auth": auth}), \
                 patch.object(sys, "argv", argv + extra), patch.object(sys, "stdout", output), \
                 patch.object(corp_login, "interactive_terminal", return_value=True), \
                 patch.object(corp_login.getpass, "getpass", return_value="synthetic-typed"), \
                 patch.dict(q.os.environ, {"MHXY_COVERAGE_AUTH_FILE": ""}), patch.object(q, "query", return_value={"status": "passed"}) as run:
                self.assertEqual(q.main(), 0)
                self.assertEqual(auth.login.call_args.kwargs["password"], expected_password)
                self.assertEqual(run.call_args.args[4], "developer")
                self.assertNotIn(secret, output.getvalue())

    def test_cli_without_terminal_reports_auth_required_instead_of_prompting(self):
        config = {"openid_username": "developer@corp.netease.com", "coder_name": "developer"}
        workspace = types.SimpleNamespace(WorkspaceError=ValueError, load_config=lambda *args: dict(config),
                                          svn_branch=lambda root: None)
        auth = types.SimpleNamespace(AuthError=corp_login.LoginError, login=lambda *a, **k: self.fail("must not log in"))
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        global_config = Path(directory.name) / "config.json"
        global_config.write_text(json.dumps({"openid_username": config["openid_username"], "openid_password": ""}), encoding="utf-8")
        output = io.StringIO()
        with patch.dict(sys.modules, {"workspace": workspace, "coverage_auth": auth}), \
             patch.object(sys, "argv", ["coverage_query.py", "--task-name", "test", "--branch", "b", "--global-config", str(global_config)]), \
             patch.object(sys, "stdout", output), patch.object(corp_login.sys.stdin, "isatty", return_value=True), \
             patch.object(corp_login.sys.stderr, "isatty", return_value=False), \
             patch.object(corp_login.getpass, "getpass", side_effect=AssertionError("must not prompt")), \
             patch.dict(q.os.environ, {"MHXY_COVERAGE_AUTH_FILE": ""}):
            self.assertEqual(q.main(), 3)
        self.assertEqual(json.loads(output.getvalue())["status"], "auth_required")

    def test_cli_infers_branch_path_or_reports_input_error(self):
        config = {"coder_name": "developer"}
        argv = ["coverage_query.py", "--task-name", "test", "--auth-file", "unused.json"]
        for inferred, code in (({"path": "branchs/dev/test"}, 0), (None, 3)):
            workspace = types.SimpleNamespace(WorkspaceError=ValueError, load_config=lambda *args: dict(config),
                                              svn_branch=lambda root, inferred=inferred: inferred)
            output = io.StringIO()
            with patch.dict(sys.modules, {"workspace": workspace}), patch.object(sys, "argv", argv), \
                 patch.object(sys, "stdout", output), patch.object(q, "Client"), \
                 patch.object(q, "query", return_value={"status": "passed"}) as run:
                self.assertEqual(q.main(), code)
            if inferred:
                self.assertEqual(run.call_args.args[2], "branchs/dev/test")
            else:
                run.assert_not_called()
                self.assertIn("input_error", output.getvalue())

    def query(self, client, after="2026-09-28T09:59:00+08:00"):
        return q.query(client, "test", "branchs/dev/test", 123, "developer", after)

    def test_complete_and_history_union(self):
        client = FixtureClient()
        result = self.query(client)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["executed_count"], 2)
        paths = [p for p, _ in client.calls]
        self.assertIn("/api/tasks/test/coverage/rates/branchs%252Fdev%252Ftest", paths)
        self.assertIn("/api/tasks/test/coverage/require/branchs%25252Fdev%25252Ftest/module.py", paths)

    def test_rounded_percentage_is_not_success(self):
        client = FixtureClient()
        client.missing = True
        result = self.query(client)
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["files"][0]["missing_lines"], [11])

    def test_manual_adjustments_and_empty_scope_block(self):
        for attribute, value in (("ignored", [11]), ("confirmers", {"module.py": ["developer"]}), ("required", [])):
            client = FixtureClient()
            setattr(client, attribute, value)
            self.assertEqual(self.query(client)["status"], "blocked")

    def test_freshness_and_scope(self):
        client = FixtureClient()
        self.assertIn("freshness_not_checked", self.query(client, None)["blockers"])
        self.assertIn("submission_not_visible", self.query(client, "2026-09-28T10:01:00+08:00")["blockers"])
        self.assertIn("submission_not_visible", self.query(client, client.date)["blockers"])
        client.date = "invalid-date"
        self.assertIn("freshness_unknown", self.query(client)["blockers"])
        client.history_branch = "other"
        self.assertIn("submission_scope_unverified", self.query(client)["blockers"])
        client.branch = "other"
        with self.assertRaisesRegex(q.QueryError, "'other'.*'branchs/dev/test'"):
            self.query(client)

    def test_website_revision_replaces_legacy_argument(self):
        for legacy in (None, 123):
            client = FixtureClient()
            client.version = "456"
            client.history_version = 456
            result = q.query(client, "test", client.branch, legacy, "developer",
                             "2026-09-28T09:59:00+08:00")
            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["revision"], "456")
            self.assertTrue(all(params["revision"] == 456 for _, params in client.calls if "revision" in params))

    def test_invalid_website_revision_is_not_guessed(self):
        for value in (None, True, 0, -1, "bad", "", 1.5):
            client = FixtureClient()
            client.version = value
            with self.assertRaisesRegex(q.QueryError, "cur_ver"):
                self.query(client)

    def test_submission_still_belongs_to_website_record(self):
        client = FixtureClient()
        client.history_version = 122
        self.assertIn("submission_scope_unverified", self.query(client)["blockers"])

    def test_empty_scope_explains_baseline_without_mutation(self):
        client = FixtureClient()
        client.required = []
        result = self.query(client)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("基准", result["hints"][0])

    def test_live_naive_server_time_is_utc(self):
        self.assertEqual(q.timestamp("2026-09-23T02:40:18.974000", server=True),
                         q.timestamp("2026-09-23T10:40:18.974000+08:00"))
        with self.assertRaises(q.QueryError):
            q.timestamp("2026-09-23T02:40:18.974000")

    def test_invalid_line_payload_is_not_empty_success(self):
        for value in ({}, {"lines": None}, {"lines": {"bad": []}}):
            with self.assertRaises(q.QueryError):
                q.covered_lines(value)

    def test_auth_failure_does_not_expose_body_or_credentials(self):
        client = q.Client()
        error = HTTPError("https://example.invalid", 401, "Unauthorized", {}, io.BytesIO(b"secret-body"))
        with patch.object(client.opener, "open", side_effect=error):
            with self.assertRaises(q.QueryError) as result:
                client.get("/api/tasks/test")
        self.assertEqual(result.exception.status, "auth_required")
        self.assertNotIn("secret", str(result.exception))
        self.assertIsNone(q.NoRedirect().redirect_request(None, None, 302, None, None, "https://other.invalid"))

    def test_auth_file_allowlist(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "auth.json"
            path.write_text(json.dumps({"Host": "other.invalid"}))
            with self.assertRaises(q.QueryError):
                q.Client(path)


if __name__ == "__main__":
    unittest.main()
