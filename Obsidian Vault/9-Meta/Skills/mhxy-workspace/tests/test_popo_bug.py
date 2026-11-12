"""popo_bug.py（提单平台）的隔离测试；不访问网络，用假的 Client。"""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import eros_auth  # noqa: E402
import popo_bug as p  # noqa: E402

TASK = {"_id": "t1", "task_name": "#834463 奇袭", "parentid": "834463", "popo_group_num": ["8854601"],
        "related_person": ["caoyuxuan01", "wangzhuowei"], "related_redmine": {"wangzhuowei": 834466, "ylyn3265": 834468},
        "qa": "yuanyanliang"}
PEOPLE = {"wangzhuowei": {"name": "W王卓为", "mail": "wangzhuowei@corp.netease.com"},
          "ylyn3265": {"name": "Y杨某", "mail": "yangmou@corp.netease.com"}}
ROW = {"_id": "b1", "readable_id": 297291, "taskid": "t1", "subject": "返回键歪了", "status": "新建",
       "origin_subject": "mark @王卓为|梦幻2|191  返回键歪了 ", "author": "yuanyanliang", "followqa": "yuanyanliang",
       "popo_group_num": "8854601"}


class FakeClient:
    def __init__(self, rows=(), markdown="", judge=None):
        self.rows = list(rows)
        self.markdowns = [markdown] if isinstance(markdown, str) else list(markdown)
        self.judge = judge or {"success": True}
        self.posts = []

    def tasks(self, account):
        return [TASK, {**TASK, "_id": "t2", "popo_group_num": ["999"]}]

    def people(self):
        return PEOPLE

    def type_prefix(self):
        return {"bug": "BUG", "mark": "备忘", "sug": "建议"}

    def issues(self, task_id, keyword="", length=200):
        self.keyword = keyword
        return self.rows

    def issue(self, task_id, bug_id):
        value = self.markdowns.pop(0) if len(self.markdowns) > 1 else self.markdowns[0]
        return {"_id": bug_id, "markdown": value, "followqa": "yuanyanliang"}

    def post_json(self, path, body):
        self.posts.append((path, body))
        return self.judge if path.endswith("judge_change_status") else {"success": True}

    def post_form(self, path, fields):
        self.posts.append((path, fields))
        self.rows = [{**ROW, "_id": "new", "readable_id": 300001, "subject": fields["subject"]}]
        return {"success": True}


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = p.main([str(a) for a in argv])
    return code, json.loads(out.getvalue() or "null"), json.loads(err.getvalue() or "null")


class PopoBugTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {"MHXY_NO_PM_WRITE": ""})
        env.start()
        self.addCleanup(env.stop)

    def test_login_allows_qkit_relay(self):
        handler = eros_auth._redirects(p.SITE, eros_auth.QKIT_AUTH_HOST)()
        request = eros_auth.Request(p.SITE + "/auth/login")
        handler.redirect_request(request, None, 302, "", {}, "http://auth2.qkit.nie.netease.com/openid/login")
        with self.assertRaises(eros_auth.LoginError):
            eros_auth._redirects(p.SITE)().redirect_request(request, None, 302, "", {},
                                                            "http://auth2.qkit.nie.netease.com/openid/login")

    def test_tasks_filtered_by_group_with_member_union(self):
        tasks = p.find_tasks(FakeClient(), "wangzhuowei", "8854601")
        self.assertEqual([t["id"] for t in tasks], ["t1"])
        self.assertEqual(tasks[0]["members"], ["caoyuxuan01", "wangzhuowei", "ylyn3265"])
        self.assertEqual(tasks[0]["member_mails"], ["wangzhuowei@corp.netease.com", "yangmou@corp.netease.com"])
        self.assertEqual((tasks[0]["planner_id"], tasks[0]["subtickets"]["wangzhuowei"]), ("834463", "834466"))

    def test_find_normalizes_whitespace(self):
        client = FakeClient([{**ROW, "_id": "other", "origin_subject": "别的"}, ROW])
        bug = p.find_bug(client, "t1", "mark @王卓为|梦幻2|191 返回键歪了")
        self.assertEqual((bug["id"], bug["readable_id"]), ("b1", "297291"))
        self.assertTrue(client.keyword)
        self.assertIsNone(p.find_bug(client, "t1", "mark @王卓为|梦幻2|191 返回键歪"))

    def test_find_matches_reported_bugs_only_while_open_and_takes_newest(self):
        made = {**ROW, "origin_subject": "", "subject": "【群里报告】Y杨某\n奇袭按钮  点不动"}
        client = FakeClient([{**made, "_id": "old", "readable_id": 1}, {**made, "_id": "new", "readable_id": 9},
                             {**made, "_id": "done", "readable_id": 20, "status": "已完成"},
                             {**ROW, "_id": "x", "origin_subject": "", "subject": "奇袭按钮 点不动"}])
        self.assertEqual(p.find_bug(client, "t1", "奇袭按钮 点不动")["id"], "new")
        self.assertIsNone(p.find_bug(FakeClient([{**ROW, "status": "关闭"}]), "t1", "mark @王卓为|梦幻2|191 返回键歪了"))

    def test_create_takes_exact_subject_not_substring(self):
        client = FakeClient()
        client.post_form = lambda path, fields: (setattr(client, "rows", [
            {**ROW, "_id": "older", "readable_id": 5, "subject": fields["subject"] + " 打不开"},
            {**ROW, "_id": "new", "readable_id": 7, "subject": fields["subject"]}]) or {"success": True})
        self.assertEqual(p.create_bug(client, "wangzhuowei", "t1", "卡住", "Y杨某")["id"], "new")

    def test_images_fill_placeholders_and_failures_do_not_stop(self):
        self.assertEqual(p.fill_images("a[图片]b[图片]", ["1.png"]), "a[图片 1.png]b[图片]")
        self.assertEqual(p.fill_images("a", ["1.png", "2.png"]), "a\n\n[图片 1.png]\n[图片 2.png]")
        text = p.render({"readable_id": 1, "subject": "看图[图片]", "way_text": "", "way_img": ["u"]}, {},
                        {"img": ["D:/a.png"], "way_img": ["下载失败，原链接 u"]})
        self.assertIn("看图[图片 D:/a.png]", text)
        self.assertIn("## 重现步骤\n\n[图片 下载失败，原链接 u]", text)     # 只有图没有文字也保留这一段

    def test_create_marks_reporter_and_finds_new_issue(self):
        client = FakeClient()
        bug = p.create_bug(client, "wangzhuowei", "t1", "  奇袭按钮  点不动 ", "YangMou@corp.netease.com")
        path, fields = client.posts[0]
        self.assertEqual(path, "/mgr/task/save_issue")
        self.assertTrue(fields["subject"].startswith("【群里报告】Y杨某\n"))
        self.assertEqual((fields["ctype"], fields["assignee"], fields["issue_type"]), ("0", "wangzhuowei", "BUG"))
        self.assertEqual(bug["readable_id"], "300001")
        self.assertEqual(p.display_name(client, "wangzhuowei"), "W王卓为")
        self.assertEqual(p.display_name(client, "Y袁延亮"), "Y袁延亮")
        p.create_bug(client, "wangzhuowei", "t1", "加个按钮", "Y杨某", issue_type="建议")
        self.assertEqual(client.posts[-1][1]["issue_type"], "建议")
        with self.assertRaises(p.PopoBugError):
            p.create_bug(client, "wangzhuowei", "t1", "x", "y", issue_type="乱写")

    def test_task_result_includes_platform_prefixes(self):
        out = p.task_result(FakeClient(), "wangzhuowei", "8854601")
        self.assertEqual(out["type_prefix"]["mark"], "备忘")
        self.assertEqual([t["id"] for t in out["tasks"]], ["t1"])

    def test_note_appends_without_name_and_rejects_long_text(self):
        client = FakeClient(markdown="杨某: 已复现")
        out = p.append_note(client, "t1", "b1", "已修复", "返回键改用原按钮坐标")
        self.assertEqual(out["markdown"], "杨某: 已复现\n已修复：返回键改用原按钮坐标")
        self.assertEqual(client.posts[-1], ("/mgr/task/update_issue",
                                            {"_id": "b1", "taskid": "t1", "markdown": out["markdown"]}))
        with self.assertRaises(p.PopoBugError):
            p.append_note(FakeClient(), "t1", "b1", "已修复", "一" * 21)
        with self.assertRaises(p.PopoBugError):
            p.append_note(FakeClient(), "t1", "b1", "随便", "x")
        self.assertEqual(p.append_note(FakeClient(), "t1", "b1", "未处理", "缺少复现步骤")["markdown"], "未处理：缺少复现步骤")

    def test_note_rebuilds_when_changed_between_reads(self):
        client = FakeClient(markdown=["A", "A\nB", "A\nB", "A\nB"])
        out = p.append_note(client, "t1", "b1", "未处理", "缺少复现步骤")
        self.assertEqual(out["markdown"], "A\nB\n未处理：缺少复现步骤")

    def test_status_done_and_followqa_fallback(self):
        client = FakeClient()
        self.assertEqual(p.set_done(client, "t1", "b1"), {"status": "已完成", "followqa": None})
        client = FakeClient(judge={"success": False, "ret_code": 2})
        self.assertEqual(p.set_done(client, "t1", "b1")["followqa"], "yuanyanliang")
        self.assertEqual(client.posts[-1][1], {"_id": "b1", "status": "已完成", "taskid": "t1", "followqa": "yuanyanliang"})
        with self.assertRaises(p.PopoBugError) as error:
            p.set_done(FakeClient(judge={"success": False, "ret_code": 1, "retmsg": "非QA同学不允许关闭单"}), "t1", "b1")
        self.assertIn("ret_code 1", str(error.exception))

    def test_writes_refused_without_approval(self):
        with patch.dict(os.environ, {"MHXY_NO_PM_WRITE": "1"}):
            for argv in (("note", "--task", "t1", "--id", "b1", "--prefix", "已修复", "--text", "x"),
                         ("status", "--task", "t1", "--id", "b1", "--to", "已完成"),
                         ("create", "--task", "t1", "--text", "x", "--reporter", "y")):
                with patch.object(p, "connect", side_effect=AssertionError("不应登录")):
                    code, _, error = run(*argv)
                self.assertEqual(code, 1)
                self.assertIn("MHXY_NO_PM_WRITE", error["error"])
            with self.assertRaises(p.PopoBugError):
                p.append_note(FakeClient(), "t1", "b1", "已修复", "x")

    def test_arguments_checked_before_login(self):
        with patch.object(p, "connect", side_effect=AssertionError("不应登录")):
            self.assertEqual(run("find", "--task", "t1")[0], 1)
            self.assertEqual(run("status", "--task", "t1", "--id", "b1", "--to", "关闭")[0], 1)
            self.assertEqual(run("note", "--task", "t1", "--id", "b1", "--prefix", "已修复", "--text", "一" * 21)[0], 1)

    def test_render_issue_markdown(self):
        text = p.render({"readable_id": 297291, "subject": "返回键\n歪了", "type": "BUG", "status": "新建",
                         "author": "yuanyanliang", "author_name": "Y袁延亮", "way_text": "进奇袭", "markdown": "已复现"},
                        {"name": "#834463 奇袭", "planner_id": "834463"})
        for part in ("# popo-297291 返回键 歪了", "提单：Y袁延亮（yuanyanliang）", "策划单号：834463", "## 重现步骤",
                     "## 已有备注"):
            self.assertIn(part, text)


if __name__ == "__main__":
    unittest.main()
