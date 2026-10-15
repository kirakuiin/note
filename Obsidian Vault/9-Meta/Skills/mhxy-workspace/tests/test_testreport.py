"""提测脚本与 eros 登录的隔离测试；不访问网络。"""
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import eros_auth  # noqa: E402
import testreport as t  # noqa: E402

INFO = {"_id": 838745, "root_id": 838743, "subject": "【外测】战斗指挥", "svrCoder": [], "cliCoder": ["dev@corp.netease.com"],
        "cehua": "plan@corp.netease.com", "qa": ["qa@corp.netease.com"], "output_type": "部分服务器外测"}
EXISTING = {"_id": "1790135449544", "redmineId": "838743", "sysName": "旧名", "svrCoder": ["svr@corp.netease.com"],
            "cliCoder": ["dev@corp.netease.com"], "dutyDesign": ["plan@corp.netease.com"], "dutyQA": ["qa@corp.netease.com"],
            "testPort": "刘斯明-dev", "axCrossServer": "0", "patch": "旧模板", "pcSrc": "旧模板", "selfTest": "16",
            "coverPath": "服务端链接", "MOScoverPath": "无", "CLIcoverPath": "https://cov/old", "cli_checked": "false",
            "attition": "<p>旧重点</p>", "at_content": "指令", "pro_content": "概率", "htEngineVer": ""}


class TestReportTests(unittest.TestCase):
    def test_refresh_mapping_matches_web_page(self):
        fields = t.refreshed_fields({**INFO, "cover": "c", "pycover": {"url": "https://cli", "tag": "client"}})
        self.assertEqual((fields["dutyDesign"], fields["coverPath"], fields["CLIcoverPath"], fields["MOScoverPath"]),
                         (["plan@corp.netease.com"], "c", "https://cli", ""))
        self.assertEqual(t.refreshed_fields({**INFO, "pycover": {"url": "https://mos", "tag": "mhxy"}})["MOScoverPath"], "https://mos")

    def test_new_request_defaults(self):
        fields = t.build_fields("838743", INFO, None, "模板A", "https://cov/new", "<p>重点</p>")
        self.assertEqual(fields["testRequestID"], "")
        self.assertEqual((fields["patch"], fields["pcSrc"]), ("模板A", "模板A"))
        self.assertEqual(fields["CliCheckListPath"], t.CHECKLIST)
        self.assertEqual((fields["coverPath"], fields["MOScoverPath"]), (t.SERVER_PLACEHOLDER, t.SERVER_PLACEHOLDER))
        self.assertEqual((fields["testPort"], fields["selfTest"], fields["cli_checked"], fields["at_content"]), ("", "0", "", ""))
        self.assertEqual(fields["cliCoder"], '["dev@corp.netease.com"]')
        self.assertEqual(fields["testRequestName"], fields["sysName"])

    def test_update_keeps_server_fields_and_overrides_client_fields(self):
        fields = t.build_fields("838743", INFO, EXISTING, "新模板", "https://cov/new", "<p>新重点</p>")
        self.assertEqual(fields["testRequestID"], "1790135449544")
        for key in ("testPort", "coverPath", "MOScoverPath", "selfTest", "at_content", "pro_content"):
            self.assertEqual(fields[key], EXISTING[key], key)
        self.assertEqual((fields["patch"], fields["CLIcoverPath"], fields["attition"]), ("新模板", "https://cov/new", "<p>新重点</p>"))
        self.assertEqual(fields["sysName"], "旧名")
        kept = t.build_fields("838743", INFO, EXISTING, None, None, "")
        self.assertEqual((kept["patch"], kept["CLIcoverPath"], kept["attition"]), ("旧模板", "https://cov/old", "<p>旧重点</p>"))

    def test_missing_required_fields(self):
        with self.assertRaises(t.TestReportError) as error:
            t.build_fields("838743", {**INFO, "cehua": "", "qa": []}, None, "", "", "")
        for label in ("策划", "QA", "Patch 模板", "客户端覆盖率地址", "测试需特别注意"):
            self.assertIn(label, str(error.exception))
        with self.assertRaises(t.TestReportError):
            t.build_fields("abc", INFO, None, "模板", "x", "y")

    def test_my_requests_parsing_and_save_result(self):
        client = t.Client(MagicMock())
        html = ("<table><tr class='a'><th><a href='http://xyq.pm.netease.com/v6/issues/828900'>828900</a></th>"
                "<th><a href=\"/testreport/preViewTestRequest?testRequestID=111\">x</a>"
                "<a href=\"/testreport/preViewTestRequest?testRequestID=111&re=1\">y</a></th></tr>"
                "<tr><th>表头</th></tr><tr><th><a href='/v6/issues/838743'>8</a></th>"
                "<th><a href='?testRequestID=222'>z</a></th></tr></table>")
        client._read = MagicMock(return_value=html)
        self.assertEqual(client.my_requests(), [{"redmineId": "828900", "testRequestID": "111"},
                                                {"redmineId": "838743", "testRequestID": "222"}])
        client._read = MagicMock(return_value='"1790135449544"')
        self.assertEqual(client.save({}), "1790135449544")
        client._read = MagicMock(return_value="<html>error</html>")
        with self.assertRaises(t.TestReportError):
            client.save({})

    def test_prepare_uses_root_issue_and_existing_records(self):
        client = MagicMock()
        client.redmine_info.side_effect = lambda issue: {**INFO, "subject": f"单{issue}"}
        client.my_requests.return_value = [{"redmineId": "838743", "testRequestID": "222"},
                                           {"redmineId": "838743", "testRequestID": "222"},
                                           {"redmineId": "1", "testRequestID": "333"}]
        client.get_request.return_value = EXISTING
        result = t.prepare(client, "838745")
        self.assertEqual(result["redmineId"], "838743")
        self.assertEqual(result["refreshed"]["sysName"], "单838743")
        self.assertEqual([e["testRequestID"] for e in result["existing"]], ["222"])
        self.assertEqual(result["existing"][0]["link"], t.preview_link("222"))

    def run_main(self, argv, client=None):
        """运行命令行；connect 被替换，返回 (退出码, 标准输出 JSON, 标准错误 JSON, connect mock)。"""
        out, err = io.StringIO(), io.StringIO()
        with patch.object(t, "connect", return_value=client) as connect, \
             patch.object(sys, "stdout", out), patch.object(sys, "stderr", err):
            code = t.main(argv)
        return (code, json.loads(out.getvalue()) if out.getvalue() else None,
                json.loads(err.getvalue()) if err.getvalue() else None, connect)

    def test_cli_validates_arguments_and_files_before_login(self):
        with tempfile.TemporaryDirectory() as directory:
            gbk = Path(directory) / "attention.html"
            gbk.write_bytes("<p>重点</p>".encode("gbk"))
            for argv, message in ((["prepare"], "--issue-id"), (["prepare", "--issue-id", "abc"], "--issue-id"),
                                  (["save"], "--redmine-id"), (["save", "--redmine-id", "8387a"], "--redmine-id"),
                                  (["save", "--redmine-id", "838743", "--test-request-id", "x"], "--test-request-id"),
                                  (["save", "--redmine-id", "838743", "--attention-file", str(gbk)], "UTF-8")):
                code, _, error, connect = self.run_main(argv)
                self.assertEqual(code, 1, argv)
                self.assertIn(message, error["error"])
                connect.assert_not_called()

    def test_update_requires_matching_request_and_never_falls_back_to_new(self):
        client = MagicMock()
        client.redmine_info.return_value = INFO
        argv = ["save", "--redmine-id", "838743", "--test-request-id", "1790135449544", "--patch", "模板"]
        for record in ({**EXISTING, "_id": "999"}, {**EXISTING, "redmineId": "1"}, {}):
            client.get_request.return_value = record
            code, _, error, _ = self.run_main(argv, client)
            self.assertEqual(code, 1)
            self.assertIn("1790135449544", error["error"])
        client.get_request.return_value = EXISTING
        code, result, _, _ = self.run_main(argv, client)
        self.assertEqual(code, 0)
        self.assertEqual((result["mode"], result["fields"]["testRequestID"]), ("更新", "1790135449544"))
        client.save.assert_not_called()
        api = t.Client(MagicMock())
        api._read = MagicMock(return_value="null")
        with self.assertRaises(t.TestReportError):
            api.get_request("1")

    def test_attention_html_check(self):
        self.assertEqual(t.attention_issues("<p>回归慧根<br/>测一下<strong>蓝耗</strong></p><ul><li>a</li></ul>"), [])
        issues = t.attention_issues("<p>x</p></parameter><script>1</script>**重点** ``` {{x}} <!-- c -->")
        self.assertEqual(issues[:2], ["不允许的标签 <parameter>", "不允许的标签 <script>"])
        for label in ("代码块", "粗体", "占位符", "注释"):
            self.assertTrue(any(label in issue for issue in issues), label)

    def test_eros_redirect_whitelist(self):
        handler = eros_auth._redirects(t.SITE)()
        for url in ("http://auth.eros.nie.netease.com/oid_login", "https://login.netease.com/accounts/login/",
                    t.SITE + "/auth/after_login"):
            handler.redirect_request(MagicMock(get_method=lambda: "GET", headers={}, unredirected_hdrs={},
                                               get_full_url=lambda: url, data=None, origin_req_host="x",
                                               unverifiable=False), None, 302, "Found", {}, url)
        for url in ("http://newtestreport.eros.nie.netease.com/", "https://evil.example.com/",
                    "http://login.netease.com/", "https://user@login.netease.com/"):
            with self.assertRaises(eros_auth.LoginError):
                handler.redirect_request(None, None, 302, "Found", {}, url)


if __name__ == "__main__":
    unittest.main()
