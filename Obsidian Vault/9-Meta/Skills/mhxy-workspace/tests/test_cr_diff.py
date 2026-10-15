"""隔离验证 CR diff 的提交筛选、diff 切分、表单字段、插件配置读取和 Jenkins 流程；不访问 svn 或网络。"""
from datetime import date
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import cr_diff as c
import workspace as w

BRANCH = "/products/client/wzimage/branchs/2026_dev/demo"
URL = "svn://svn.example.test/svn" + BRANCH
ISSUE = {"issue_id": "835520", "title": "【维护转制作】山河快捷购买", "parent_id": "835517",
         "tracker": "[客户端]程序开发", "status": "关闭", "created_on": "2026-09-22T17:10:05+08:00"}


def log(*entries):
    """entries: (revision, author, msg, [(action, kind, path, copyfrom)])"""
    body = ""
    for revision, author, msg, paths in entries:
        nodes = ""
        for action, kind, path, copyfrom in paths:
            source = f' copyfrom-path="{copyfrom}"' if copyfrom else ""
            nodes += f'<path action="{action}" kind="{kind}"{source}>{BRANCH}/{path}</path>'
        body += (f'<logentry revision="{revision}"><author>{author}</author><date>2026-09-28T00:00:00Z</date>'
                 f"<paths>{nodes}</paths><msg>{msg}</msg></logentry>")
    return f'<?xml version="1.0" encoding="UTF-8"?><log>{body}</log>'.encode("utf-8")


def chunk(path, encoding="utf-8"):
    return (b"Index: " + path.encode(encoding) + b"\r\n" + b"=" * 67 + b"\r\n--- a\r\n+++ b\r\n@@ -1 +1 @@\n-old\n+new\n")


class CommitTests(unittest.TestCase):
    def test_own_commits_match_issue_author_and_skip_prefix_numbers(self):
        data = log((3, "dev", "#835520 工单：改动", [("M", "file", "gameplay/a.py", None)]),
                   (1, "dev", "finish #835520 工单", [("A", "file", "data/x.py", None)]),
                   (4, "other", "#835520 别人", [("M", "file", "gameplay/b.py", None)]),
                   (5, "dev", "#8355201 另一工单", [("M", "file", "gameplay/c.py", None)]),
                   (6, "DEV", "#835520 复制目录", [("A", "dir", "gameplay/copied", "/x/y")]))
        revisions, files, dirs = c.own_commits(data, "835520", "dev", BRANCH)
        self.assertEqual(revisions, [1, 3, 6])
        self.assertEqual(set(files), {"gameplay/a.py", "data/x.py"})
        self.assertEqual(dirs, {"gameplay/copied"})

    def test_split_and_select_keep_bytes_and_decode_gbk_paths(self):
        diff = chunk("spec/快捷购买.md", "gbk") + chunk("gameplay/a.py") + chunk("gameplay/copied/n.py") + chunk("other.py")
        chunks = c.split_chunks(diff)
        self.assertEqual([p for p, _ in chunks], ["spec/快捷购买.md", "gameplay/a.py", "gameplay/copied/n.py", "other.py"])
        self.assertEqual(b"".join(b for _, b in chunks), diff)
        selected = c.select_chunks(chunks, {"spec/快捷购买.md": {"A"}, "gameplay/a.py": {"M"}}, {"gameplay/copied"})
        self.assertEqual([p for p, _ in selected], ["spec/快捷购买.md", "gameplay/a.py", "gameplay/copied/n.py"])

    def test_collect_excludes_data_and_reports_others(self):
        own = log((10, "dev", "#835520 一", [("M", "file", "gameplay/a.py", None), ("M", "file", "data/t.py", None)]),
                  (12, "dev", "#835520 二", [("M", "file", "gameplay/b.py", None)]))
        rng = log((10, "dev", "#835520 一", []), (11, "other", "别的", [("M", "file", "gameplay/a.py", None)]),
                  (12, "dev", "#835520 二", []))
        diff = chunk("gameplay/a.py") + chunk("data/t.py") + chunk("gameplay/b.py") + chunk("gameplay/z.py")
        info = f'<info><entry><url>{URL}</url><relative-url>^{BRANCH}</relative-url></entry></info>'.encode()
        calls = []

        def svn(root, *args):
            calls.append(args)
            if args[0] == "info":
                return info
            if args[0] == "diff":
                return diff
            return own if "--search" in args else rng

        with patch.object(c.precommit, "run_svn", side_effect=svn):
            result = c.collect(Path("."), ISSUE, "dev")
        self.assertEqual(result["revisions"], [10, 12])
        self.assertEqual(result["range"], "9:12")
        self.assertEqual(result["files"], ["gameplay/a.py", "gameplay/b.py"])
        self.assertEqual(result["excluded_data"], ["data/t.py"])
        self.assertEqual(result["others_in_range"], [{"revision": 11, "author": "other", "files": ["gameplay/a.py"]}])
        self.assertEqual(result["diff"], chunk("gameplay/a.py") + chunk("gameplay/b.py"))
        search = next(args for args in calls if "--search" in args)
        self.assertIn("{2026-09-21}:HEAD", search)
        self.assertIn("--stop-on-copy", search)
        self.assertIn(("diff", "--internal-diff", "-r", "9:12", URL), calls)

    def test_branch_info_decodes_relative_url(self):
        info = (f'<info><entry><url>{URL}/%E4%B8%AD%20x</url>'
                f'<relative-url>^{BRANCH}/%E4%B8%AD%20x/</relative-url></entry></info>').encode()
        with patch.object(c.precommit, "run_svn", return_value=info):
            branch = c.branch_info(Path("."))
        self.assertEqual(branch["path"], BRANCH + "/中 x")
        self.assertEqual(branch["url"], URL + "/%E4%B8%AD%20x")
        self.assertEqual(c.branch_relative(BRANCH + "/中 x/gameplay/a.py", branch["path"]), "gameplay/a.py")

    def test_collect_without_commits_fails(self):
        info = f'<info><entry><url>{URL}</url><relative-url>^{BRANCH}</relative-url></entry></info>'.encode()
        with patch.object(c.precommit, "run_svn", side_effect=lambda root, *a: info if a[0] == "info" else log()):
            with self.assertRaises(c.CrError):
                c.collect(Path("."), ISSUE, "dev")


class FieldTests(unittest.TestCase):
    manifest = {"issue": ISSUE, "branch": URL, "real_user": "dev"}

    def test_fields_use_tomorrow_parent_and_default_title(self):
        fields = c.form_fields(self.manifest, " 1. 改动\n2. 改动 ", today=date(2026, 10, 10))
        self.assertEqual(fields, {"from_url": URL, "review_title": "#835520 【维护转制作】山河快捷购买",
                                  "time_request": "2026-10-11|2026-10-11|2026-10-11", "testing_done": "835517",
                                  "real_user": "dev", "review_desc": "1. 改动\n2. 改动"})

    def test_desc_limit_and_missing_parent(self):
        c.form_fields(self.manifest, "字" * c.DESC_LIMIT)
        for desc in ("", "  ", "字" * (c.DESC_LIMIT + 1)):
            with self.assertRaises(c.CrError):
                c.form_fields(self.manifest, desc)
        orphan = {**self.manifest, "issue": {**ISSUE, "parent_id": None}}
        self.assertIsNone(c.base_fields(orphan)["testing_done"])
        with self.assertRaises(c.CrError):
            c.form_fields(orphan, "描述")
        self.assertEqual(c.form_fields(orphan, "描述", testing_done="123")["testing_done"], "123")


class PluginTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def plugin(self, version, url, token="tok"):
        path = self.base / f"mhxy2.mhcoder-{version}" / c.PLUGIN_FILE
        path.parent.mkdir(parents=True)
        path.write_text(f"const url = '{url}';\nconst token = '{token}';\n", encoding="utf-8")

    def test_reads_latest_plugin_and_splits_credentials(self):
        self.plugin("0.5.9", "http://u:old@ci.example.test/job/a/buildWithParameters", "old")
        self.plugin("0.5.43", "http://u:p%40ss@ci.example.test/job/server/job/post/buildWithParameters")
        endpoint = c.plugin_endpoint([self.base])
        self.assertEqual(endpoint, {"job": "http://ci.example.test/job/server/job/post", "user": "u",
                                    "password": "p@ss", "token": "tok"})

    def test_missing_or_changed_plugin_fails(self):
        with self.assertRaises(c.CrError):
            c.plugin_endpoint([self.base])
        self.plugin("1.0.0", "http://ci.example.test/job/a/buildWithParameters")
        with self.assertRaises(c.CrError):
            c.plugin_endpoint([self.base])


class Response:
    def __init__(self, body=b"", headers=None):
        self.body, self.headers = body, headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, limit=-1):
        return self.body


class FakeOpener:
    def __init__(self, responses):
        self.responses, self.requests = responses, []

    def open(self, request, timeout=None):
        self.requests.append(request)
        return self.responses.pop(0)


class JenkinsTests(unittest.TestCase):
    endpoint = {"job": "http://ci.example.test/job/post", "user": "u", "password": "p", "token": "tok"}

    def test_trigger_matches_plugin_request_and_follows_own_build(self):
        build = "http://ci.example.test/job/post/7/"
        opener = FakeOpener([
            Response(headers={"Location": "http://ci.example.test/queue/item/5/"}),
            Response(json.dumps({}).encode()),
            Response(json.dumps({"executable": {"url": build}}).encode()),
            Response(json.dumps({"building": False, "result": "SUCCESS"}).encode()),
            Response(b"posted http://reviewboard.mhxy.netease.com/r/123/ done"),
        ])
        jenkins = c.Jenkins(self.endpoint, opener=opener)
        fields = {"from_url": URL, "review_title": "#1 标题", "review_desc": "1. 改动"}
        queue = jenkins.trigger("tok", fields, b"DIFF")
        result = jenkins.follow(queue, sleep=lambda s: None)
        post = opener.requests[0]
        query = parse_qs(urlsplit(post.full_url).query)
        self.assertTrue(post.full_url.startswith("http://ci.example.test/job/post/buildWithParameters?"))
        self.assertEqual(query["token"], ["tok"])
        self.assertEqual(query["review_title"], ["#1 标题"])
        self.assertEqual(post.get_header("Authorization"), "Basic dTpw")
        self.assertIn(b'name="client_diff.dat"; filename="crDiff.diff"', post.data)
        self.assertIn(b"\r\n\r\nDIFF\r\n", post.data)
        self.assertEqual(result["build_url"], build)
        self.assertEqual(result["result"], "SUCCESS")
        self.assertEqual(result["review_url"], "http://reviewboard.mhxy.netease.com/r/123/")

    def test_follow_timeout_and_errors_keep_urls_and_console_tail(self):
        queue, build = "http://ci.example.test/queue/item/5/", "http://ci.example.test/job/post/7/"
        lines = "\n".join(f"line {n}" for n in range(20)).encode()
        clock = iter([0, 0, 1000])  # deadline、第一次构建检查、第二次构建检查时超时
        with patch.object(c.time, "monotonic", side_effect=lambda: next(clock)):
            jenkins = c.Jenkins(self.endpoint, opener=FakeOpener([
                Response(json.dumps({"executable": {"url": build}}).encode()),
                Response(json.dumps({"building": True}).encode()),
                Response(json.dumps({"building": True}).encode()),
                Response(lines)]))
            result = jenkins.follow(queue, wait=10, sleep=lambda s: None)
        self.assertEqual((result["queue_url"], result["build_url"], result["result"]), (queue, build, None))
        self.assertEqual(result["console_tail"], [f"line {n}" for n in range(5, 20)])
        self.assertNotIn("error", result)
        jenkins = c.Jenkins(self.endpoint, opener=FakeOpener([
            Response(json.dumps({"executable": {"url": build}}).encode()), Response(b"<html>")]))
        result = jenkins.follow(queue, sleep=lambda s: None)
        self.assertEqual((result["queue_url"], result["build_url"], result["result"]), (queue, build, None))
        self.assertIn("已上传、结果未确认", result["error"])

    def test_rejects_foreign_hosts_and_missing_queue(self):
        jenkins = c.Jenkins(self.endpoint, opener=FakeOpener([Response()]))
        with self.assertRaises(c.CrError):
            jenkins.trigger("tok", {}, b"")
        with self.assertRaises(c.CrError):
            jenkins.open("http://elsewhere.example.test/x")


class FlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.root = self.base / "工作区"
        self.root.mkdir()
        self.config = self.base / "global.json"
        self.config.write_text(json.dumps({"openid_username": "dev@corp.netease.com"}), encoding="utf-8")
        self.diff = chunk("gameplay/a.py")
        collected = {"branch": URL, "revisions": [10], "range": "9:10", "files": ["gameplay/a.py"],
                     "excluded_data": [], "not_in_diff": [], "others_in_range": [], "diff": self.diff}
        self.patches = [patch.object(c, "collect", side_effect=lambda *a: dict(collected)),
                        patch.object(c, "branch_info", return_value={"url": URL, "path": BRANCH})]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in self.patches:
            item.stop()
        self.temp.cleanup()

    def test_prepare_writes_personal_files_then_upload_previews_and_applies(self):
        result = c.prepare(self.root, self.config, "835520", lookup=lambda config, issue_id: ISSUE)
        folder = self.root / w.DIRECTORY / c.OUTPUT_DIRECTORY / "835520"
        self.assertEqual((folder / c.DIFF_FILE).read_bytes(), self.diff)
        self.assertEqual(result["diff_path"], ".mhxy-workspace/code-review/835520/crDiff.diff")
        self.assertEqual(result["real_user"], "dev")
        self.assertEqual(result["fields"]["testing_done"], "835517")
        preview = c.upload(self.root, self.config, "835520", "1. 改动")
        self.assertFalse(preview["applied"])
        self.assertNotIn("build", preview)

        class FakeJenkins:
            def trigger(self, token, fields, diff):
                self.sent = (token, fields, diff)
                return "http://ci.example.test/queue/item/1/"

            def follow(self, queue, wait):
                return {"result": "SUCCESS", "build_url": "b", "review_url": None}

        fake = FakeJenkins()
        applied = c.upload(self.root, self.config, "835520", "1. 改动", apply=True,
                           endpoint={"token": "tok"}, jenkins=fake)
        self.assertEqual(fake.sent[0], "tok")
        self.assertEqual(fake.sent[2], self.diff)
        self.assertEqual(applied["build"]["result"], "SUCCESS")

    def test_preview_lists_exclusions_and_apply_records_upload_against_duplicates(self):
        extra = {"excluded_data": ["data/t.py"], "not_in_diff": ["gameplay/gone.py"],
                 "others_in_range": [{"revision": 9, "author": "other", "files": ["gameplay/a.py"]}]}
        with patch.object(c, "collect", side_effect=lambda *a: {"branch": URL, "revisions": [10], "range": "9:10",
                                                                 "files": ["gameplay/a.py"], **extra, "diff": self.diff}):
            c.prepare(self.root, self.config, "835520", lookup=lambda config, issue_id: ISSUE)
        preview = c.upload(self.root, self.config, "835520", "1. 改动")
        for key, value in extra.items():
            self.assertEqual(preview[key], value)
        self.assertEqual(preview["previous_uploads"], [])

        class FailingJenkins:
            triggered = 0

            def trigger(self, token, fields, diff):
                self.triggered += 1
                return "http://ci.example.test/queue/item/1/"

            def follow(self, queue, wait):
                raise RuntimeError("boom")

        fake, notified = FailingJenkins(), []
        applied = c.upload(self.root, self.config, "835520", "1. 改动", apply=True, endpoint={"token": "tok"},
                           jenkins=fake, notify=notified.append)
        self.assertEqual(notified, ["http://ci.example.test/queue/item/1/"])
        self.assertEqual(applied["build"]["queue_url"], "http://ci.example.test/queue/item/1/")
        self.assertIsNone(applied["build"]["result"])
        self.assertIn("已上传、结果未确认", applied["build"]["error"])
        marker = self.root / w.DIRECTORY / c.OUTPUT_DIRECTORY / "835520" / c.APPLIED_FILE
        self.assertEqual(json.loads(marker.read_text(encoding="utf-8"))["uploads"][0]["queue_url"],
                         "http://ci.example.test/queue/item/1/")
        with self.assertRaisesRegex(c.CrError, "--force"):
            c.upload(self.root, self.config, "835520", "1. 改动", apply=True, endpoint={"token": "tok"},
                     jenkins=fake, notify=notified.append)
        self.assertEqual(fake.triggered, 1)
        self.assertEqual(len(c.upload(self.root, self.config, "835520", "1. 改动")["previous_uploads"]), 1)
        c.upload(self.root, self.config, "835520", "1. 改动", apply=True, endpoint={"token": "tok"},
                 jenkins=fake, notify=notified.append, force=True)
        self.assertEqual(len(json.loads(marker.read_text(encoding="utf-8"))["uploads"]), 2)

    def test_cli_unconfirmed_build_exits_2_and_bad_desc_encoding_is_readable(self):
        c.prepare(self.root, self.config, "835520", lookup=lambda config, issue_id: ISSUE)
        desc = self.base / "desc.txt"
        desc.write_bytes("1. 改动".encode("gbk"))
        argv = ["upload", "--root", str(self.root), "--config", str(self.config), "--issue", "835520",
                "--desc-file", str(desc)]
        err = io.StringIO()
        with patch.object(sys, "stderr", err):
            self.assertEqual(c.main(argv), 1)
        self.assertIn("UTF-8", json.loads(err.getvalue())["error"])
        desc.write_text("﻿1. 改动", encoding="utf-8")
        build = {"queue_url": "q", "build_url": None, "result": None, "review_url": None, "error": "已上传、结果未确认：x"}
        out = io.StringIO()
        with patch.object(c, "upload", return_value={"build": build}) as run, patch.object(sys, "stdout", out):
            self.assertEqual(c.main(argv + ["--apply"]), 2)
        self.assertEqual(run.call_args.args[3], "1. 改动")
        self.assertEqual(run.call_args.kwargs["wait"], c.WAIT_SECONDS)
        self.assertEqual(json.loads(out.getvalue())["build"]["queue_url"], "q")

    def test_upload_rejects_stale_or_missing_prepare(self):
        with self.assertRaises(c.CrError):
            c.upload(self.root, self.config, "835520", "描述")
        c.prepare(self.root, self.config, "835520", lookup=lambda config, issue_id: ISSUE)
        diff = self.root / w.DIRECTORY / c.OUTPUT_DIRECTORY / "835520" / c.DIFF_FILE
        diff.write_bytes(b"edited")
        with self.assertRaises(c.CrError):
            c.upload(self.root, self.config, "835520", "描述")
        c.prepare(self.root, self.config, "835520", lookup=lambda config, issue_id: ISSUE)
        with patch.object(c, "branch_info", return_value={"url": URL + "_other", "path": BRANCH}):
            with self.assertRaises(c.CrError):
                c.upload(self.root, self.config, "835520", "描述")

    def test_cli_reports_errors_as_json_without_secrets(self):
        err = io.StringIO()
        with patch.object(sys, "stderr", err):
            code = c.main(["upload", "--root", str(self.root), "--config", str(self.config), "--issue", "835520"])
        self.assertEqual(code, 1)
        self.assertIn("--desc-file", json.loads(err.getvalue())["error"])


if __name__ == "__main__":
    unittest.main()
