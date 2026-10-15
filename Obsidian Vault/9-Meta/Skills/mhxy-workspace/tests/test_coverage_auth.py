"""Check the login boundary without using real passwords or external services."""
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("coverage_auth", Path(__file__).resolve().parents[1] / "scripts/coverage_auth.py")
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


class Response(io.BytesIO):
    def __init__(self, url, body):
        super().__init__(body.encode())
        self.url = url


class LoginTests(unittest.TestCase):
    def test_unsupported_origin_and_account_rejected(self):
        for url in ("http://login.netease.com/", "https://unrelated.invalid/", "https://login.netease.com@unrelated.invalid/"):
            with self.assertRaises(a.AuthError):
                a.LoginRedirects().redirect_request(None, None, 302, None, {}, url)
        with self.assertRaises(a.AuthError):
            a.login("test@example.invalid")

    def test_form_defaults_are_collected(self):
        parser = a.LoginForms()
        parser.feed('<form><input name="authm" value="corp"><input name="corpid"><input name="corppw" type="password"></form>')
        self.assertEqual(parser.forms, [{"authm": "corp", "corpid": "", "corppw": ""}])

    def test_callback_exchange_and_identity(self):
        html = '<form><input name="authm" value="corp"><input name="corpid"><input name="corppw" type="password"></form>'
        def responses(name):
            return [Response(a.SITE, '{"assoc_handle":"test"}'),
                    Response(a.LOGIN + "/accounts/login/", html),
                    Response(a.SITE + "/consume?openid.mode=id_res", ""),
                    Response(a.SITE + "/api/auth/login", "{}"),
                    Response(a.SITE + "/api/auth/info", json.dumps({"name": name}))]

        with patch.object(a, "build_opener") as build, patch.object(a.sys.stdin, "isatty", return_value=True), \
             patch.object(a.sys.stderr, "isatty", return_value=True), \
             patch.object(a.getpass, "getpass", return_value="synthetic-test-input"), \
             patch.object(a.corp_login, "encode_password", return_value="synthetic-encoded-value"):
            build.return_value.open.side_effect = responses("test")
            jar = a.login("test@corp.netease.com")
            self.assertIsInstance(jar, a.http.cookiejar.CookieJar)
            calls = build.return_value.open.call_args_list
            self.assertEqual(calls[3].args[0].full_url, a.SITE + "/api/auth/login?openid.mode=id_res")
            self.assertNotIn(b"synthetic-test-input", calls[2].args[0].data)
            build.return_value.open.side_effect = responses("test")
            with patch.object(a.sys.stdin, "isatty", return_value=False), patch.object(a.getpass, "getpass", side_effect=AssertionError("must use config password")):
                a.login("test", password="synthetic-config-password")
            build.return_value.open.side_effect = responses("someone_else")
            with self.assertRaisesRegex(a.AuthError, "不一致"):
                a.login("test")

    def test_missing_password_without_terminal_does_not_prompt(self):
        """Agent 命令工具：stdin 是 NUL（isatty 为 True），stderr 是管道；不得调用 getpass。"""
        html = '<form><input name="corpid"><input name="corppw" type="password"></form>'
        for password in (None, ""):
            with patch.object(a, "build_opener") as build, patch.object(a.sys.stdin, "isatty", return_value=True), \
                 patch.object(a.sys.stderr, "isatty", return_value=False), \
                 patch.object(a.getpass, "getpass", side_effect=AssertionError("must not prompt")):
                build.return_value.open.side_effect = [Response(a.SITE, '{"assoc_handle":"test"}'),
                                                       Response(a.LOGIN + "/accounts/login/", html)]
                with self.assertRaisesRegex(a.AuthError, "没有已配置密码"):
                    a.login("test", password=password)

    def test_encoding_change_does_not_submit_plaintext(self):
        with self.assertRaises(a.AuthError):
            a.encode_password("synthetic-test-input", "no encoding fields")


if __name__ == "__main__":
    unittest.main()
