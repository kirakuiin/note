"""隔离验证工单保存、图片链接、追踪和清理；不访问真实账号或网络。"""
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.request import Request, HTTPCookieProcessor

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import pm_issues as p
import workspace as w


PNG = b"\x89PNG\r\n\x1a\nsynthetic-image"


class IssueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.root = self.base / "工作区"
        self.root.mkdir()
        self.config = self.base / "global.json"
        self.personal = self.root / w.DIRECTORY
        self.client = Mock()
        self.client.image.return_value = (PNG, ".png")
        self.query = {"title_tags": ["放出release2客户端（新）"]}

    def tearDown(self):
        self.temp.cleanup()

    def save(self, rows):
        return p.save_issues(self.client, rows, self.root, self.config, self.query)

    def test_full_tags_are_exact_without_aliases(self):
        for tag in ("放出release2客户端（新）", "部分服务器外测", "全部服务器放出"):
            self.assertTrue(p.matches_title_tags("【" + tag + "】任务", p.normalize_title_tags([tag]), "or"))
        self.assertFalse(p.matches_title_tags("【放出release2客户端（新）】任务", {"release2"}, "or"))
        self.assertEqual(p.normalize_title_tags(["【外测】"]), {"外测"})
        self.assertFalse(p.matches_title_tags("部分服务器外测任务", {"部分服务器外测"}, "or"))

    def test_target_version_name_id_and_unrestricted(self):
        issue = {"fixed_version": {"value": "项目研发内容", "id": 14}}
        self.assertTrue(p.matches_target_version(issue, "项目研发内容"))
        self.assertTrue(p.matches_target_version(issue, "14"))
        self.assertFalse(p.matches_target_version(issue, "项目研发"))
        self.assertFalse(p.matches_target_version(issue, "程序研发内容"))
        self.assertTrue(p.matches_target_version({}, None))
        self.assertFalse(p.matches_target_version({"fixed_version": None}, "项目研发内容"))
        for row in ({}, {"fixed_version": "项目研发内容"}, {"fixed_version": {"name": "项目研发内容"}}):
            with self.assertRaises(p.QueryError):
                p.matches_target_version(row, "项目研发内容")

    def test_target_filter_keeps_pagination_and_combines_title_filter(self):
        def row(issue_id, version, title):
            return {"id": issue_id, "is_closed": False, "assigned_to": {"id": 7},
                    "tracker": p.DEFAULT_TRACKER, "subject": title,
                    "fixed_version": {"value": version, "id": 14 if version == "项目研发内容" else 16}}

        pages = [
            {"list": [row(1, "程序研发内容", "【标签】跳过"), row(2, "项目研发内容", "无标签")], "total_count": 3, "page": 1},
            {"list": [row(3, "项目研发内容", "【标签】保留")], "total_count": 3, "page": 2},
        ]

        def api(path, params, post=False):
            if path == "/issues":
                self.assertIn("fixed_version", params["c[]"])
                return pages[params["page"] - 1]
            self.assertEqual(path, "/issue_show/base")
            self.assertEqual(params, {"id": 3})
            return {"base": {"id": 3, "is_closed": False, "description": "正文"}}

        self.client.api.side_effect = api
        rows = p.query_rows(self.client, "mhxy", 7, p.DEFAULT_TRACKER, page_size=2,
                            target_version="项目研发内容", title_tags=["标签"])
        self.assertEqual(rows, [["#3", "【标签】保留", "正文"]])
        self.assertEqual(self.client.api.call_count, 3)

    def test_issue_base_reads_closed_issue_and_parent(self):
        self.client.api.return_value = {"base": {"id": 835520, "subject": "标题", "parent_id": 835517,
                                                 "is_closed": True, "status": "关闭", "tracker": "程序",
                                                 "created_on": "2026-09-22T17:10:05+08:00"}}
        info = p.issue_base(self.client, "835520")
        self.client.api.assert_called_once_with("/issue_show/base", {"id": 835520}, post=True)
        self.assertEqual(info["parent_id"], "835517")
        self.assertTrue(info["is_closed"])
        self.client.api.return_value = {"base": {"id": 835517, "subject": "总单", "parent_id": None}}
        self.assertIsNone(p.issue_base(self.client, "835517")["parent_id"])
        for base in ({"id": 1, "subject": "标题"}, {"id": 835517, "subject": ""},
                     {"id": 835517, "subject": "标题", "parent_id": "x"}):
            self.client.api.return_value = {"base": base}
            with self.assertRaises(p.QueryError):
                p.issue_base(self.client, "835517")
        with self.assertRaises(w.WorkspaceError):
            p.issue_base(self.client, "../1")
        for detail in ({"base": None}, {"base": []}, []):
            self.client.api.return_value = detail
            with self.assertRaisesRegex(p.QueryError, "格式已变化"):
                p.issue_base(self.client, "835517")

    def test_unassigned_or_malformed_rows_are_readable_errors(self):
        for row in ({"id": 1, "is_closed": False, "assigned_to": None}, "not-a-row"):
            self.client.api.return_value = {"list": [row], "total_count": 1, "page": 1}
            with self.assertRaises(p.QueryError):
                p.list_open_issues(self.client, "mhxy", 7, "*")

    def test_cli_reports_unexpected_shapes_without_traceback(self):
        err = io.StringIO()
        with patch.object(p, "credentials", return_value=("test", "synthetic-password")), \
             patch.object(p, "Client", return_value=self.client), \
             patch.object(p, "issue_base", side_effect=AttributeError("x")), patch.object(sys, "stderr", err):
            code = p.main(["--root", str(self.root), "--config", str(self.config), "--show", "1"])
        self.assertEqual(code, 1)
        self.assertIn("数据结构已变化", err.getvalue())

    def test_missing_password_needs_both_stdin_and_stderr_terminal(self):
        """Agent 命令工具：stdin 是 NUL（isatty 为 True），stderr 是管道；不得调用 getpass。"""
        self.config.write_text(json.dumps({"openid_username": "test@corp.netease.com", "openid_password": ""}),
                               encoding="utf-8")
        with patch.object(p.corp_login.sys.stdin, "isatty", return_value=True), \
             patch.object(p.corp_login.sys.stderr, "isatty", return_value=False), \
             patch.object(p.corp_login.getpass, "getpass", side_effect=AssertionError("must not prompt")):
            with self.assertRaisesRegex(p.corp_login.LoginError, "未配置密码"):
                p.credentials(self.config)
        with patch.object(p.corp_login.sys.stdin, "isatty", return_value=True), \
             patch.object(p.corp_login.sys.stderr, "isatty", return_value=True), \
             patch.object(p.corp_login.getpass, "getpass", return_value="synthetic-typed") as prompt:
            self.assertEqual(p.credentials(self.config), ("test@corp.netease.com", "synthetic-typed"))
            prompt.assert_called_once()

    def test_cli_show_outputs_issue_without_saving(self):
        self.client.login.return_value = {"id": 7}
        out = io.StringIO()
        with patch.object(p, "credentials", return_value=("test", "synthetic-password")), \
             patch.object(p, "Client", return_value=self.client), \
             patch.object(p, "issue_base", return_value={"issue_id": "1", "parent_id": "2"}) as show, \
             patch.object(sys, "stdout", out):
            code = p.main(["--root", str(self.root), "--config", str(self.config), "--show", "1"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue())["parent_id"], "2")
        self.assertEqual(show.call_args.args[1], "1")
        self.assertFalse(self.personal.exists())

    def test_html_images_and_image_links_are_local_same_directory(self):
        result = self.save([["#123", "标题", '<p>说明<img src="/pic/1" alt="设计图"></p><a href="/pic/1">原图</a><a href="/issues/456">另一工单</a>'],
                            ["#456", "标题二", "普通正文"]])
        folder = self.personal / "tasks/123"
        images = list(folder.glob("*.png"))
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0].read_bytes(), PNG)
        body = (folder / "issue.md").read_text(encoding="utf-8")
        self.assertIn(f"![设计图](<{images[0].name}>)", body)
        self.assertIn(f"[原图](<{images[0].name}>)", body)
        self.assertIn("[另一工单](<../456/issue.md>)", body)
        self.assertNotIn("/pic/1", body)
        self.assertEqual(result["status"], "saved")
        index = json.loads((self.personal / "tasks/index.json").read_text(encoding="utf-8"))
        self.assertEqual(index["query"], self.query)
        self.assertFalse((self.root / "AGENTS.md").exists())

    def test_markdown_image_and_full_image_link(self):
        url = p.SITE + "/pic/1"
        self.save([["#123", "标题", f'![设计图]({url})\n[原图]({url})\n[相对原图](/pic/1)\n![重复](/pic/1 "说明")']])
        folder = self.personal / "tasks/123"
        name = next(folder.glob("*.png")).name
        body = (folder / "issue.md").read_text(encoding="utf-8")
        self.assertIn("![设计图](<" + name + ">)", body)
        self.assertIn("[原图](<" + name + ">)", body)
        self.assertIn("[相对原图](<" + name + ">)", body)
        self.assertIn("![重复](<" + name + ">)", body)
        self.client.image.assert_called_once()

    def test_image_failure_is_reported_and_keeps_remote_link(self):
        self.client.image.side_effect = p.QueryError("图片下载失败")
        result = self.save([["#123", "标题", '<img src="/pic/1">']])
        body = (self.personal / "tasks/123/issue.md").read_text(encoding="utf-8")
        self.assertEqual(result["status"], "partial")
        self.assertEqual(len(result["image_failures"]), 1)
        self.assertIn(p.SITE + "/pic/1", body)
        self.assertIn("尚未采集完整", body)

    def test_tracking_append_replace_refresh_coverage_and_clean(self):
        self.save([["#123", "标题", "正文"], ["#456", "标题二", "正文二"]])
        agents = self.root / "AGENTS.md"
        agents.write_text("固定规则", encoding="utf-8")
        w.track_tasks(self.root, self.config, ["123"], apply=True)
        w.track_tasks(self.root, self.config, ["456", "123"], apply=True)
        task = {"task_name": "test", "branch": "trunk", "redmine_id": "123", "coder_name": "dev", "created": True}
        w.record_coverage_task(self.root, self.config, task, True)
        self.save([["#123", "新标题", "新正文"]])
        tracking = w.read_tracking(self.personal)[2]
        self.assertEqual([t["issue_id"] for t in tracking["tracked_tasks"]], ["123", "456"])
        self.assertEqual(tracking["tracked_tasks"][0]["title"], "新标题")
        self.assertEqual(tracking["coverage_tasks"], [task])
        w.track_tasks(self.root, self.config, ["123"], replace=True, apply=True)
        self.assertEqual(len(w.read_tracking(self.personal)[2]["tracked_tasks"]), 1)
        w.track_tasks(self.root, self.config, ["123"], remove=True, apply=True)
        self.assertEqual(w.read_tracking(self.personal)[2]["tracked_tasks"], [])
        self.assertTrue((self.personal / "tasks/123/issue.md").is_file())
        w.clean(self.root, self.config, True)
        self.assertEqual(list(self.personal.iterdir()), [])
        self.assertEqual(agents.read_text(encoding="utf-8"), "固定规则")
        self.save([["#123", "重新获取", "正文"]])
        self.assertFalse((self.personal / "tracking.json").exists())

    def test_empty_refresh_keeps_tracked_tasks_and_existing_files(self):
        self.save([["#123", "标题", "正文"]])
        w.track_tasks(self.root, self.config, ["123"], apply=True)
        previous = (self.personal / "tracking.json").read_bytes()
        result = self.save([])
        self.assertEqual(result["tasks"], [])
        self.assertEqual((self.personal / "tracking.json").read_bytes(), previous)
        self.assertTrue((self.personal / "tasks/123/issue.md").exists())

    def test_track_preview_does_not_create_state(self):
        self.save([["#123", "标题", "正文"]])
        result = w.track_tasks(self.root, self.config, ["123"])
        self.assertFalse(result["applied"])
        self.assertFalse((self.personal / "tracking.json").exists())

    def test_cli_saves_with_exact_tag_and_reports_partial_images(self):
        self.client.login.return_value = {"id": 7}
        self.client.image.side_effect = p.QueryError("图片失败")
        out = io.StringIO()
        with patch.object(p, "credentials", return_value=("test", "synthetic-password")), \
             patch.object(p, "Client", return_value=self.client), \
             patch.object(p, "query_rows", return_value=[["#123", "标题", '<img src="/pic/1">']]) as query, \
             patch.object(sys, "stdout", out):
            code = p.main(["--root", str(self.root), "--config", str(self.config),
                           "--title-tags", "放出release2客户端（新）", "--target-version", "项目研发内容"])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out.getvalue())["status"], "partial")
        self.assertEqual(query.call_args.kwargs["title_tags"], ["放出release2客户端（新）"])
        self.assertEqual(query.call_args.kwargs["target_version"], "项目研发内容")
        self.assertEqual(json.loads(out.getvalue())["query"]["target_version"], "项目研发内容")
        self.assertNotIn("synthetic-password", out.getvalue())

    def test_invalid_id_and_unavailable_selection_cannot_write(self):
        for issue_id in ("../outside", "0", "1/2"):
            with self.assertRaises(w.WorkspaceError):
                self.save([["#" + issue_id, "标题", "正文"]])
        self.assertFalse(self.personal.exists())
        self.save([["#123", "标题", "正文"]])
        with self.assertRaises(w.WorkspaceError):
            w.track_tasks(self.root, self.config, ["456"], apply=True)
        self.assertFalse((self.personal / "tracking.json").exists())

    def test_write_failure_rolls_back_previous_documents(self):
        self.save([["#123", "标题", "旧正文"]])
        before = {path: path.read_bytes() for path in self.personal.rglob("*") if path.is_file()}
        original = w.atomic_write

        def fail_index(path, data):
            if path.name == "index.json":
                raise OSError("simulated disk error")
            return original(path, data)

        with patch.object(w, "atomic_write", side_effect=fail_index):
            with self.assertRaises(w.WorkspaceError):
                self.save([["#123", "新标题", "新正文"]])
        self.assertEqual(before, {path: path.read_bytes() for path in self.personal.rglob("*") if path.is_file()})

    def test_image_download_auth_boundary_and_html_rejection(self):
        client = p.Client()
        for url, authenticated in ((p.SITE + "/pic/1", True), ("https://images.example.test/pic", False)):
            response = io.BytesIO(PNG)
            opener = Mock()
            opener.open.return_value = response
            with patch.object(p, "build_opener", return_value=opener) as build:
                self.assertEqual(client.image(url), (PNG, ".png"))
                handlers = build.call_args.args
                self.assertEqual(any(isinstance(h, HTTPCookieProcessor) for h in handlers), authenticated)
                with self.assertRaises(p.QueryError):
                    handlers[0].redirect_request(Request(url), None, 302, "redirect", {}, "https://other.example.test/pic")
        opener.open.return_value = io.BytesIO(b"<html>login</html>")
        with patch.object(p, "build_opener", return_value=opener):
            with self.assertRaises(p.QueryError):
                client.image(p.SITE + "/pic")


if __name__ == "__main__":
    unittest.main()
