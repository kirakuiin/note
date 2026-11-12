"""patch.py 的隔离测试：假打包服务、假 svn info，不访问网络和真实工作副本。"""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import patch  # noqa: E402
import workspace  # noqa: E402

SCRIPT = "svn://svn-xyq.gz.netease.com/svn/products/xy1/develop/client/wzimage/branchs/2026_dev/wzw_2026_11_10_hancu_effect"
RES = "svn://svn-xyq.gz.netease.com/svn/products/xy1/share/patch/branchs/2026_dev/wzw_2026_11_10_hancu_effect/_test"
BLOCK = ("<!-- mhxy-workspace:begin -->\n### 管理元数据\n```json\n"
         '{"skill": "mhxy-workspace", "applied_version": "0.3.42", "schema_version": 2}\n'
         "```\n<!-- mhxy-workspace:end -->\n")
WRITE_TOOLS = {"pack_issue", "start_patching"}


def template_info(name="寒促特效", script=SCRIPT, res=RES, packed=True):
    info = {"status": "packed" if packed else "not_packed", "matched_name": name,
            "template": {"name": name, "scriptpath": script, "respath": res, "description": ""}}
    if packed:
        info["package"] = {"upload_time": "2026-11-11 10:00:00", "packer_username": "wangzhuowei",
                           "script_url": "s3://script", "res_url": "s3://res", "patch_info": {}}
    return info


class FakeRemote:
    """按工具名返回预设载荷，记录调用顺序；载荷可以是函数（按调用次数变化）。"""

    def __init__(self, **responses):
        self.responses = responses
        self.calls = []

    def call(self, name, arguments=None):
        self.calls.append((name, arguments))
        value = self.responses[name]
        if isinstance(value, Exception):
            raise value
        return value(len([c for c in self.calls if c[0] == name])) if callable(value) else value

    def tools(self):
        return [name for name, _ in self.calls]


class PatchTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.root = base / "branch" / "mhimage"
        self.root.mkdir(parents=True)
        (self.root.parent / "_test").mkdir()
        (self.root / "AGENTS.md").write_text(BLOCK, encoding="utf-8")
        self.config = base / "global.json"
        self.config.write_text(json.dumps({"patch_token": "token"}), encoding="utf-8")
        self.urls = {self.root.resolve(): SCRIPT, (self.root.parent / "_test").resolve(): RES}
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        self.addCleanup(self.temp.cleanup)
        stack.enter_context(mock.patch.object(patch, "workspace_config", lambda: str(self.config)))
        stack.enter_context(mock.patch.object(patch.branch, "svn_info",
                                              lambda target, item=None, cwd=None: self.urls.get(Path(target).resolve())))

    def run_main(self, remote, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = patch.main([*argv, "--root", str(self.root)] if argv[0] not in ("tables", "status")
                              else list(argv), remote=remote)
        return code, json.loads(out.getvalue())

    def recorded(self):
        return workspace.load_config(str(self.root), str(self.config))["patch_template"]

    def set_recorded(self, name):
        workspace.configure_local(str(self.root), str(self.config), [f"patch_template={name}"], apply=True)

    # 分支识别

    def test_rejects_non_dev_branch(self):
        self.urls[self.root.resolve()] = "svn://svn-xyq.gz.netease.com/svn/products/xy1/develop/client/wzimage/branchs/2026_ship/release_2026_11_12"
        remote = FakeRemote()
        code, result = self.run_main(remote, "prepare", "--name", "寒促特效")
        self.assertEqual(code, 1)
        self.assertIn("外放分支请走单独流程", result["errors"][0])
        self.assertEqual(remote.calls, [])

    def test_rejects_resource_of_other_branch(self):
        self.urls[(self.root.parent / "_test").resolve()] = RES.replace("hancu_effect", "other")
        code, result = self.run_main(FakeRemote(), "prepare", "--name", "寒促特效")
        self.assertEqual(code, 1)
        self.assertIn("不是同一个开发分支", result["errors"][0])

    def test_missing_resource_working_copy(self):
        del self.urls[(self.root.parent / "_test").resolve()]
        code, result = self.run_main(FakeRemote(), "prepare", "--name", "寒促特效")
        self.assertEqual(code, 1)
        self.assertIn("资源工作副本", result["errors"][0])

    # prepare

    def test_prepare_without_name_lists_matching_candidates(self):
        remote = FakeRemote(query_patch_template={"matches": [
            {"name": "寒促特效", "data": {"patch": SCRIPT + "/"}},
            {"name": "别的", "data": {"patch": SCRIPT.replace("hancu_effect", "x")}}]})
        code, result = self.run_main(remote, "prepare")
        self.assertEqual(code, 0)
        self.assertEqual(result["next"], "name")
        self.assertEqual(result["candidates"], ["寒促特效"])
        self.assertEqual(remote.calls, [("query_patch_template", {"keyword": "wzw_2026_11_10_hancu_effect"})])

    def test_prepare_uses_recorded_name_and_suggests_start(self):
        self.set_recorded("寒促特效")
        remote = FakeRemote(query_patch_by_template=template_info())
        code, result = self.run_main(remote, "prepare")
        self.assertEqual(code, 0)
        self.assertEqual(result["next"], "start")
        self.assertTrue(result["template"]["matches_branch"])
        self.assertEqual(result["package"]["packer_username"], "wangzhuowei")

    def test_prepare_missing_template_suggests_create(self):
        remote = FakeRemote(query_patch_by_template={"status": "no_template", "candidates": []})
        code, result = self.run_main(remote, "prepare", "--name", "寒促特效")
        self.assertEqual((code, result["next"]), (0, "create"))
        self.assertFalse(result["template"]["exists"])

    def test_prepare_template_of_other_branch_stops(self):
        remote = FakeRemote(query_patch_by_template=template_info(script=SCRIPT.replace("hancu_effect", "x")))
        code, result = self.run_main(remote, "prepare", "--name", "寒促特效")
        self.assertEqual((code, result["next"]), (1, "stop"))

    def test_prepare_rejects_invalid_name(self):
        code, result = self.run_main(FakeRemote(), "prepare", "--name", "带\"引号")
        self.assertEqual(code, 1)

    # create

    def test_create_preview_does_not_write(self):
        remote = FakeRemote(query_patch_by_template={"status": "no_template"})
        code, result = self.run_main(remote, "create", "--name", "寒促特效", "--issue-id", "860053")
        self.assertEqual((code, result["next"]), (0, "confirm"))
        self.assertEqual(result["job"]["arguments"], {
            "subject": "寒促特效", "script_svn": SCRIPT, "res_svn": RES, "issue_id": 860053,
            "tableinfo": [], "auto_start": False})
        self.assertFalse(WRITE_TOOLS & set(remote.tools()))
        self.assertIsNone(self.recorded())

    def test_create_apply_reads_back_and_records(self):
        remote = FakeRemote(
            query_patch_by_template=lambda n: {"status": "no_template"} if n == 1 else template_info(packed=False),
            pack_issue={"success": True, "template_name": "寒促特效", "tableinfo": ["3"], "tableinfo_source": "manual"})
        code, result = self.run_main(remote, "create", "--name", "寒促特效", "--table", "3", "--apply")
        self.assertEqual(code, 0, result)
        self.assertEqual(remote.tools(), ["query_patch_by_template", "pack_issue", "query_patch_by_template"])
        self.assertEqual(remote.calls[1][1]["tableinfo"], ["3"])
        self.assertEqual(self.recorded(), "寒促特效")
        self.assertEqual(result["next"], "start")

    def test_create_refuses_existing_template(self):
        remote = FakeRemote(query_patch_by_template=template_info())
        code, result = self.run_main(remote, "create", "--name", "寒促特效", "--apply")
        self.assertEqual(code, 1)
        self.assertNotIn("pack_issue", remote.tools())

    def test_create_readback_mismatch_exits_2(self):
        remote = FakeRemote(
            query_patch_by_template=lambda n: {"status": "no_template"} if n == 1 else template_info(res=RES[:-6]),
            pack_issue={"success": True, "template_name": "寒促特效"})
        code, result = self.run_main(remote, "create", "--name", "寒促特效", "--apply")
        self.assertEqual(code, 2)
        self.assertIn("已建", result["errors"][0])
        self.assertIsNone(self.recorded())

    def test_rejects_non_numeric_table(self):
        code, result = self.run_main(FakeRemote(), "create", "--name", "寒促特效", "--table", "a")
        self.assertEqual(code, 1)

    # start

    def test_start_preview_and_apply(self):
        remote = FakeRemote(query_patch_by_template=template_info(),
                            start_patching={"started": True, "job_id": "j1", "batch_id": "b1", "message": "ok"})
        code, result = self.run_main(remote, "start", "--name", "寒促特效")
        self.assertEqual((code, result["next"]), (0, "confirm"))
        self.assertNotIn("start_patching", remote.tools())
        code, result = self.run_main(remote, "start", "--name", "寒促特效", "--apply")
        self.assertEqual(code, 0, result)
        self.assertEqual(result["job"]["result"]["job_id"], "j1")
        self.assertEqual(self.recorded(), "寒促特效")

    def test_start_refuses_other_branch_and_fuzzy_name(self):
        remote = FakeRemote(query_patch_by_template=template_info(script=SCRIPT.replace("hancu_effect", "x")))
        self.assertEqual(self.run_main(remote, "start", "--name", "寒促特效", "--apply")[0], 1)
        remote = FakeRemote(query_patch_by_template=template_info(name="寒促特效2"))
        code, result = self.run_main(remote, "start", "--name", "寒促特效", "--apply")
        self.assertEqual(code, 1)
        self.assertNotIn("start_patching", remote.tools())

    def test_start_without_name(self):
        code, result = self.run_main(FakeRemote(), "start")
        self.assertEqual(code, 1)
        self.assertIn("没有模板名", result["errors"][0])

    # status、tables

    def test_status_hides_raw_error_by_default(self):
        job = {"found": True, "job_id": "j1", "status": "failed", "error": "e", "raw_error": "long"}
        code, result = self.run_main(FakeRemote(query_pack_job_status=dict(job)), "status", "--job-id", "j1")
        self.assertEqual(code, 0)
        self.assertNotIn("raw_error", result["job"])
        self.assertIsNone(result["next"])
        code, result = self.run_main(FakeRemote(query_pack_job_status=dict(job)), "status", "--job-id", "j1", "--raw")
        self.assertEqual(result["job"]["raw_error"], "long")

    def test_tables(self):
        remote = FakeRemote(query_ca_table_options={"success": True, "issue_id": "1", "tables": ["a"], "options": [{"index": "0"}]})
        code, result = self.run_main(remote, "tables", "--issue-id", "1")
        self.assertEqual(code, 0)
        self.assertEqual(result["tables"]["options"], [{"index": "0"}])

    def test_apply_only_for_write_actions(self):
        self.assertEqual(self.run_main(FakeRemote(), "prepare", "--apply")[0], 1)


class RemoteTest(unittest.TestCase):
    """Remote 的会话和错误处理：替换 urlopen。"""

    def response(self, body, session=None):
        resp = mock.MagicMock()
        resp.__enter__.return_value = resp
        resp.read.return_value = body.encode("utf-8")
        resp.headers = {"mcp-session-id": session} if session else {}
        return resp

    def sse(self, request_id, result):
        return "event: message\ndata: " + json.dumps({"jsonrpc": "2.0", "id": request_id, "result": result}) + "\n\n"

    def test_session_header_and_token_error(self):
        requests = []
        bodies = [self.response(self.sse(1, {}), "sid"), self.response(""),
                  self.response(self.sse(2, {"isError": True, "content": [{"type": "text", "text": "v2_token 无效或已过期"}]}))]

        def fake(request, timeout):
            requests.append(request)
            return bodies.pop(0)
        with mock.patch.object(patch, "urlopen", fake):
            remote = patch.Remote("tok")
            with self.assertRaises(patch.PatchError) as caught:
                remote.call("get_user_valid")
        self.assertIn("令牌无效或已过期", str(caught.exception))
        self.assertEqual(requests[0].get_header("X-access-token"), "tok")
        self.assertIsNone(requests[0].get_header("Mcp-session-id"))
        self.assertEqual(requests[2].get_header("Mcp-session-id"), "sid")

    def test_structured_and_text_payload(self):
        bodies = [self.response(self.sse(1, {}), "sid"), self.response(""),
                  self.response(self.sse(2, {"structuredContent": {"result": {"a": 1}}, "content": []})),
                  self.response(self.sse(3, {"content": [{"type": "text", "text": "{\"b\": 2}"}]}))]
        with mock.patch.object(patch, "urlopen", lambda request, timeout: bodies.pop(0)):
            remote = patch.Remote("tok")
            self.assertEqual(remote.call("x"), {"a": 1})
            self.assertEqual(remote.call("y"), {"b": 2})

    def test_missing_token(self):
        with self.assertRaises(patch.PatchError):
            patch.Remote(None)


class ConfigTest(unittest.TestCase):
    def test_token_and_template_rules(self):
        defaults = json.loads((Path(__file__).resolve().parents[1] / "config/defaults.json").read_text(encoding="utf-8"))
        workspace.validate_config({"patch_token": "abc", "patch_template": "寒促特效"}, defaults, "x")
        for bad in ({"patch_template": "a\nb"}, {"patch_template": ""}, {"patch_template": "x" * 65},
                    {"patch_token": ""}):
            with self.assertRaises(workspace.WorkspaceError):
                workspace.validate_config(bad, defaults, "x")
        with self.assertRaises(workspace.WorkspaceError):
            workspace.apply_settings({}, ["patch_token=abc"], "--set-global")
        with self.assertRaises(workspace.WorkspaceError):
            workspace.effective_values({}, {"patch_token": "abc"})
        self.assertEqual(workspace.masked_config({"patch_token": "abc"}), {"patch_token": "***"})


if __name__ == "__main__":
    unittest.main()
