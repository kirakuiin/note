"""开发分支流程的隔离测试；SVN 和 HTTP 均不访问真实服务。"""
from datetime import date
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from urllib.error import HTTPError
from unittest.mock import patch

import sys
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import branch as b  # noqa: E402


NAME = "wzw_2026_10_10_qixi"
SCRIPT_URL = f"{b.SCRIPT_BRANCH_ROOT}/2026_dev/{NAME}"
RES_ROOT = f"{b.RES_BRANCH_ROOT}/2026_dev/{NAME}"
URLS = {"script": SCRIPT_URL,
        "resources": {"_test": f"{RES_ROOT}/_test", "_testhd": f"{RES_ROOT}/_testhd"}}
ROWS = [{"url": SCRIPT_URL, "msg": "ok"}, {"url": URLS["resources"]["_test"], "msg": "ok"},
        {"url": URLS["resources"]["_testhd"], "msg": "ok"}]
CONFIG = {"openid_username": "wangzhuowei@corp.netease.com"}


class BranchNamingTests(unittest.TestCase):
    def test_pinyin_prefixes_and_raw_fallback(self):
        examples = {
            "wangzhuowei": "wzw", "liangxiangcheng01": "lxc", "zhenghaiming01": "zhm",
            "zhangdaolin": "zdl", "jiangnanxi": "jnx", "liucailin": "lcl", "xian": "x",
            "ybn1984": "ybn1984", "cyxn2760": "cyxn2760",
        }
        for value, prefix in examples.items():
            with self.subTest(value=value):
                self.assertEqual(b.infer_prefix(value)["prefix"], prefix)
        self.assertEqual(b.infer_prefix("ybn1984")["basis"], "raw")
        self.assertEqual(b.infer_prefix("wangzhuowei")["basis"], "pinyin")
        self.assertEqual(b.split_pinyin("xian"), ("xian",))
        for value, parts in (("wangrui", ("wang", "rui")), ("lijiakei", ("li", "jia", "kei")),
                             ("zhanglue", ("zhang", "lue")), ("chennue", ("chen", "nue"))):
            with self.subTest(value=value):
                self.assertEqual(b.split_pinyin(value), parts)

    def test_branch_name_and_purpose_validation(self):
        result = b.name_result("qixi", CONFIG, date(2026, 10, 10))
        self.assertEqual(result["branch"], NAME)
        for purpose in ("Qixi", "two words", "七夕", "one_two_three"):
            with self.subTest(purpose=purpose), self.assertRaises(b.BranchError):
                b.validate_purpose(purpose)

    def test_branch_name_rejects_path_traversal_and_separators(self):
        for name in ("../evil_2026_10_10_qixi", "/tmp_2026_10_10_qixi",
                     "C:\\temp_2026_10_10_qixi", "x\\.._2026_10_10_qixi"):
            with self.subTest(name=name), self.assertRaises(b.BranchError):
                b.validate_branch_name(name)


class CreateTests(unittest.TestCase):
    def test_preview_defaults_and_no_resource_parameters(self):
        with patch.object(b, "svn_info", return_value=None), patch.object(b, "http_get") as request:
            preview = b.create_preview("qixi", config=CONFIG, today=date(2026, 10, 10))
            no_res = b.create_preview("qixi", no_res=True, config=CONFIG, today=date(2026, 10, 10))
        self.assertEqual(preview["base"], "release")
        self.assertTrue(preview["create_resources"])
        self.assertEqual(preview["parameters"]["source_name"], NAME)
        self.assertEqual(preview["urls"], URLS)
        self.assertEqual(no_res["parameters"]["source_name"], "")
        self.assertEqual(no_res["urls"]["resources"], {})
        request.assert_not_called()

    def test_preview_rejects_existing_script_url(self):
        with patch.object(b, "svn_info", return_value=SCRIPT_URL):
            with self.assertRaisesRegex(b.BranchError, "已存在"):
                b.create_preview("qixi", config=CONFIG, today=date(2026, 10, 10))

    def test_create_polls_until_second_response_succeeds(self):
        with patch.object(b, "svn_info", return_value=None), \
                patch.object(b, "create_branch_request") as create_request, \
                patch.object(b, "branch_rows", side_effect=[[], [], ROWS]) as rows, \
                patch.object(b.time, "sleep") as sleep:
            result = b.create("qixi", apply=True, config=CONFIG, today=date(2026, 10, 10), expected=NAME)
        self.assertEqual(result["status"], "created")
        self.assertEqual(result["urls"], URLS)
        create_request.assert_called_once()
        self.assertEqual(rows.call_count, 3)  # 请求前取一次快照，之后轮询两次。
        sleep.assert_called_once_with(2)

    def test_create_apply_requires_confirmed_branch_name(self):
        with patch.object(b, "svn_info", return_value=None), \
                patch.object(b, "create_branch_request") as create_request, \
                patch.object(b, "branch_rows", return_value=[]):
            with self.assertRaisesRegex(b.BranchError, "--branch"):
                b.create("qixi", apply=True, config=CONFIG, today=date(2026, 10, 10))
            # 预览在 10 日，确认后跨日才执行：重新计算的名称不同，拒绝创建。
            with self.assertRaisesRegex(b.BranchError, "不一致"):
                b.create("qixi", apply=True, config=CONFIG, today=date(2026, 10, 11), expected=NAME)
        create_request.assert_not_called()

    def test_poll_ignores_failure_records_from_before_the_request(self):
        old_failure = {"url": SCRIPT_URL, "msg": "permission denied"}
        with patch.object(b, "svn_info", return_value=None), \
                patch.object(b, "create_branch_request"), \
                patch.object(b, "branch_rows", side_effect=[[old_failure], [old_failure], [*ROWS, old_failure]]), \
                patch.object(b.time, "sleep"):
            result = b.create("qixi", apply=True, config=CONFIG, today=date(2026, 10, 10), expected=NAME)
        self.assertEqual(result["status"], "created")
        new_failure = {"url": SCRIPT_URL, "msg": "permission denied"}
        with patch.object(b, "branch_rows", return_value=[new_failure, old_failure]):
            result = b.poll_creation(NAME, True, b.relevant_rows([old_failure], NAME, True))
        self.assertEqual(result["status"], "failed")

    def test_create_request_error_still_polls(self):
        with patch.object(b, "svn_info", return_value=None), \
                patch.object(b, "create_branch_request", side_effect=b.BranchError("网络请求失败：timed out")), \
                patch.object(b, "branch_rows", side_effect=[[], ROWS]), \
                patch.object(b.time, "sleep"):
            result = b.create("qixi", apply=True, config=CONFIG, today=date(2026, 10, 10), expected=NAME)
        self.assertEqual(result["status"], "created")
        self.assertIn("timed out", result["request_error"])

    def test_create_reports_non_ok_message(self):
        failed = [{"url": SCRIPT_URL, "msg": "permission denied"}]
        with patch.object(b, "branch_rows", return_value=failed):
            result = b.poll_creation(NAME, include_resources=True)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["msg"], "permission denied")

    def test_create_times_out_and_no_resource_only_needs_script(self):
        with patch.object(b, "branch_rows", return_value=[]), patch.object(b.time, "sleep") as sleep:
            result = b.poll_creation(NAME, include_resources=True)
        self.assertEqual(result["status"], "timeout")
        self.assertEqual(sleep.call_count, b.POLL_ATTEMPTS - 1)
        with patch.object(b, "branch_rows", return_value=[ROWS[0]]):
            no_res = b.poll_creation(NAME, include_resources=False)
        self.assertEqual(no_res["status"], "created")
        with patch.object(b, "branch_rows", return_value=[ROWS[0], {"url": URLS["resources"]["_test"], "msg": "failed"}]):
            no_res_ignores_resource_failure = b.poll_creation(NAME, include_resources=False)
        self.assertEqual(no_res_ignores_resource_failure["status"], "created")

    def test_http_errors_are_readable_and_requests_have_timeout(self):
        failure = HTTPError("https://example.invalid", 503, "unavailable", {}, None)
        with patch.object(b, "urlopen", side_effect=failure) as open_url:
            with self.assertRaisesRegex(b.BranchError, "HTTP 503"):
                b.http_get("https://example.invalid", timeout=7)
        self.assertEqual(open_url.call_args.kwargs["timeout"], 7)


class UrlResolutionTests(unittest.TestCase):
    def test_exact_record_urls_and_missing_resource_warning(self):
        def info(url, **kwargs):
            return None if url.endswith("_testhd") else url

        with patch.object(b, "svn_info", side_effect=info):
            urls, warnings = b.resolve_branch_urls(NAME, ROWS)
        self.assertEqual(urls["script"], SCRIPT_URL)
        self.assertEqual(urls["resources"], {"_test": URLS["resources"]["_test"]})
        self.assertEqual(len(warnings), 1)
        self.assertIn("_testhd", warnings[0])

    def test_fallback_urls_and_missing_script(self):
        with patch.object(b, "svn_info", side_effect=lambda url, **kwargs: url):
            urls, warnings = b.resolve_branch_urls(NAME, [])
        self.assertEqual(urls, URLS)
        self.assertEqual(warnings, [])
        with patch.object(b, "svn_info", return_value=None):
            with self.assertRaisesRegex(b.BranchError, "脚本分支不存在"):
                b.resolve_branch_urls(NAME, [])

    def test_svn_info_distinguishes_missing_url_from_authentication_failure(self):
        missing = subprocess.CompletedProcess([], 1, b"", b"svn: E160013: path not found")
        # 实际 svn 1.14 对不存在的 URL 输出的就是这两行。
        missing_url = subprocess.CompletedProcess([], 1, b"", b"svn: warning: W170000: URL 'x' non-existent in revision 1\n"
                                                             b"svn: E200009: Could not display info for all targets")
        authentication = subprocess.CompletedProcess([], 1, b"", b"svn: E170001: authentication failed")
        # 主机名解析失败的提示里含有 not found 字样，但不是“分支不存在”，必须报错。
        network = subprocess.CompletedProcess([], 1, b"", b"svn: E170013: Unable to connect\nsvn: E731001: host not found")
        for completed in (missing, missing_url):
            with patch.object(b, "run_svn", return_value=completed):
                self.assertIsNone(b.svn_info(SCRIPT_URL))
        for completed, code in ((authentication, "E170001"), (network, "E170013")):
            with patch.object(b, "run_svn", return_value=completed):
                with self.assertRaisesRegex(b.BranchError, code):
                    b.svn_info(SCRIPT_URL)


class PeriodicBranchTests(unittest.TestCase):
    ZLP = "zlp_2026_10_13"
    ZLP_URLS = {"script": f"{b.SCRIPT_BRANCH_ROOT}/2026_ship/zlp_2026_10_13",
                "resources": {"_test": f"{b.PERIODIC_RES_ROOT}/xyq_zlp"}}

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="branch-periodic-")
        self.root = Path(self.temporary.name).resolve()

    def tearDown(self):
        self.temporary.cleanup()

    def test_types_match_workspace_and_names_validate(self):
        self.assertEqual(set(b.PERIODIC_RESOURCES), set(b.workspace.PERIODIC_TYPES))
        for name in ("zlp_2026_10_13", "release2_2026_07_21", "test_2026_10_06"):
            self.assertEqual(b.validate_branch_name(name), "2026")
        for name in ("prod_2026_10_13", "zlp_2026_10_13_x/y", "zlp_2026_10"):
            with self.assertRaisesRegex(b.BranchError, "分支名格式无效"):
                b.validate_branch_name(name)
        self.assertIsNone(b.periodic_type(NAME))

    def test_urls_ignore_branch_records_and_release_has_no_resources(self):
        with patch.object(b, "svn_info", side_effect=lambda url, **kwargs: url), \
                patch.object(b, "branch_rows", side_effect=AssertionError("periodic must not query records")):
            urls, warnings = b.resolve_branch_urls(self.ZLP)
            self.assertEqual(urls, self.ZLP_URLS)
            self.assertEqual(warnings, [])
            urls, warnings = b.resolve_branch_urls("release_2026_08_11")
        self.assertEqual(urls, {"script": f"{b.SCRIPT_BRANCH_ROOT}/2026_ship/release_2026_08_11", "resources": {}})
        self.assertIn("只检出 mhimage", warnings[0])

    def reuse_with_test(self):
        reuse = self.root / "old"
        (reuse / "mhimage").mkdir(parents=True)
        (reuse / "_test").mkdir()
        return reuse

    def build(self, reuse, status=b"", urls=None, name=None, local="uuid-svn", remote="uuid-res"):
        def info(target, item=None, **kwargs):
            if item == "url":
                return f"old-url-of-{target}"
            return local if not str(target).startswith("svn://") else remote

        self.calls = []

        def run(*args, **kwargs):
            self.calls.append(args)
            return subprocess.CompletedProcess(args, 0, b"" if "--ignore-externals" in args else status, b"")

        with patch.object(b.Path, "cwd", return_value=self.root / "session"), \
                patch.object(b, "resolve_branch_urls", return_value=(urls or self.ZLP_URLS, [])), \
                patch.object(b, "svn_info", side_effect=info), \
                patch.object(b, "run_svn", side_effect=run):
            return b.build_checkout(name or self.ZLP, str(self.root), str(reuse))

    def test_cross_repository_resource_is_set_aside_checked_out_then_removed(self):
        reuse = self.reuse_with_test()
        old_file = reuse / "_test" / "file.tcp"
        old_file.write_text("x", encoding="utf-8")
        old_file.chmod(0o444)  # SVN 工作副本里常见的只读文件。
        result = self.build(reuse)
        self.assertEqual(result["checks"]["replaced_working_copies"], ["_test"])
        self.assertIn(("status", "--no-ignore", "_test"), self.calls)
        kinds = [step["type"] for step in result["steps"]]
        self.assertEqual(kinds, ["rename", "svn", "svn", "set_aside", "svn", "remove"])
        self.assertIn("different repository", result["steps"][3]["command"])
        self.assertEqual(result["steps"][4]["args"], ["checkout", "-q", self.ZLP_URLS["resources"]["_test"], "_test"])
        aside = Path(result["steps"][5]["path"])

        with patch.object(b, "run_svn", return_value=subprocess.CompletedProcess([], 0, b"", b"")):
            outcome = b.execute_steps(result)
        self.assertEqual(outcome["status"], "completed")
        self.assertEqual([step["status"] for step in outcome["completed_steps"]][3:],
                         ["set_aside", "ok", "removed"])
        self.assertFalse(aside.exists())

    def test_set_aside_directory_is_kept_when_not_clean_at_removal(self):
        aside = self.root / "_test.old-1"
        aside.mkdir()
        dirty = subprocess.CompletedProcess([], 0, b"?       _test.old-1\\new.tcp", b"")
        with patch.object(b, "run_svn", return_value=dirty):
            self.assertTrue(b.remove_set_aside(aside).startswith("kept"))
        self.assertTrue(aside.exists())

    def test_set_aside_directory_is_kept_when_status_or_delete_fails(self):
        aside = self.root / "_test.old-1"
        aside.mkdir()
        with patch.object(b, "run_svn", return_value=subprocess.CompletedProcess([], 1, b"", b"svn: E155007")):
            self.assertIn("无法检查", b.remove_set_aside(aside))
        with patch.object(b, "run_svn", side_effect=b.BranchError("timeout")):
            self.assertIn("无法检查", b.remove_set_aside(aside))
        with patch.object(b, "run_svn", return_value=subprocess.CompletedProcess([], 0, b"", b"")), \
                patch.object(b.shutil, "rmtree", side_effect=OSError("in use")):
            self.assertIn("删除", b.remove_set_aside(aside))
        self.assertTrue(aside.exists())

    def test_existing_set_aside_name_is_rejected(self):
        reuse = self.reuse_with_test()
        (reuse / "_test.old-20261010120000").mkdir()
        with patch.object(b.time, "strftime", return_value="20261010120000"):
            with self.assertRaisesRegex(b.BranchError, "名称已存在"):
                self.build(reuse)

    def test_cross_repository_resource_with_ignored_or_unversioned_files_is_rejected(self):
        reuse = self.reuse_with_test()
        with self.assertRaisesRegex(b.BranchError, "不在同一仓库"):
            self.build(reuse, status=b"I       _test\\mhimage.wdf")

    def test_unknown_repository_uuid_is_rejected(self):
        for local in (None, ""):
            reuse = self.reuse_with_test() if not (self.root / "old").exists() else self.root / "old"
            with self.assertRaisesRegex(b.BranchError, "无法确定"):
                self.build(reuse, local=local)

    def test_periodic_directory_reused_for_development_branch(self):
        reuse = self.reuse_with_test()
        result = self.build(reuse, urls=URLS, name=NAME, local="uuid-res", remote="uuid-svn")
        self.assertEqual(result["checks"]["replaced_working_copies"], ["_test"])
        self.assertEqual([step["type"] for step in result["steps"]],
                         ["rename", "svn", "svn", "set_aside", "svn", "svn", "remove"])

    def test_release_reuse_warns_about_stale_resource(self):
        reuse = self.reuse_with_test()
        urls = {"script": f"{b.SCRIPT_BRANCH_ROOT}/2026_ship/release_2026_08_11", "resources": {}}
        result = self.build(reuse, urls=urls, name="release_2026_08_11")
        self.assertTrue(any("_test 不在本次检出范围" in warning for warning in result["warnings"]))
        self.assertEqual([step["type"] for step in result["steps"]], ["rename", "svn", "svn"])

    def test_same_repository_resource_is_switched(self):
        reuse = self.reuse_with_test()
        quiet = subprocess.CompletedProcess([], 0, b"", b"")
        with patch.object(b.Path, "cwd", return_value=self.root / "session"), \
                patch.object(b, "resolve_branch_urls", return_value=(self.ZLP_URLS, [])), \
                patch.object(b, "svn_info", return_value="uuid-res"), \
                patch.object(b, "run_svn", return_value=quiet):
            result = b.build_checkout(self.ZLP, str(self.root), str(reuse))
        self.assertNotIn("replaced_working_copies", result["checks"])
        self.assertEqual([step["args"][0] for step in result["steps"] if step["type"] == "svn"],
                         ["cleanup", "switch", "cleanup", "switch"])


class CheckoutTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="branch-test-")
        self.root = Path(self.temporary.name).resolve()

    def tearDown(self):
        self.temporary.cleanup()

    def resolve_urls(self, name, rows=None):
        return URLS, []

    def build(self, name=NAME, reuse=None):
        with patch.object(b, "resolve_branch_urls", side_effect=self.resolve_urls):
            return b.build_checkout(name, root_arg=str(self.root), reuse_arg=reuse)

    def test_new_checkout_target_exists_and_step_order(self):
        target = self.root / NAME
        target.mkdir()
        with self.assertRaisesRegex(b.BranchError, "目标目录已存在"):
            self.build()
        target.rmdir()
        result = self.build()
        commands = [step["command"] for step in result["steps"]]
        self.assertIn(commands[0], (f"mkdir {target}", f"mkdir {target.as_posix()}"))
        self.assertEqual([step["args"][0] for step in result["steps"][1:]],
                         ["checkout", "checkout", "checkout"])
        self.assertEqual([step["args"][2] for step in result["steps"][1:]],
                         [SCRIPT_URL, URLS["resources"]["_test"], URLS["resources"]["_testhd"]])

    def test_new_checkout_apply_runs_in_order_and_stops_on_failure(self):
        result = self.build()
        calls = []
        def run(*args, **kwargs):
            calls.append(args)
            code = 1 if len(calls) == 2 else 0
            return subprocess.CompletedProcess(args, code, b"", b"svn checkout failed" if code else b"")

        with patch.object(b, "run_svn", side_effect=run):
            outcome = b.execute_steps(result)
        self.assertEqual([call[0] for call in calls], ["checkout", "checkout"])
        self.assertEqual(outcome["status"], "failed")
        self.assertEqual(len(outcome["completed_steps"]), 2)
        self.assertEqual(len(outcome["remaining_steps"]), 1)

    def test_reuse_dirty_directory_and_session_directory_guards(self):
        reuse = self.root / "old"
        (reuse / "mhimage").mkdir(parents=True)
        unrelated = self.root / "unrelated"
        unrelated.mkdir()
        with patch.object(b.Path, "cwd", return_value=self.root / "unrelated"):
            with patch.object(b, "run_svn", return_value=subprocess.CompletedProcess([], 0, b"M file.py", b"")):
                with patch.object(b, "resolve_branch_urls", side_effect=self.resolve_urls):
                    with self.assertRaisesRegex(b.BranchError, "状态检查有输出"):
                        b.build_checkout(NAME, str(self.root), str(reuse))
            with patch.object(b, "resolve_branch_urls", side_effect=self.resolve_urls):
                with self.assertRaisesRegex(b.BranchError, "当前会话目录或其祖先"):
                    b.resolve_reuse(self.root, str(self.root / "unrelated"))
                with self.assertRaisesRegex(b.BranchError, "当前会话目录或其祖先"):
                    b.resolve_reuse(self.root, str(self.root))

    def test_reuse_rejects_link_and_existing_target(self):
        reuse = self.root / "old"
        reuse.mkdir()
        with patch.object(b.workspace, "is_link", side_effect=lambda path: Path(path) == reuse):
            with self.assertRaisesRegex(b.BranchError, "符号链接"):
                b.resolve_reuse(self.root, str(reuse))

        target = self.root / NAME
        target.mkdir()
        outside = self.root / "other"
        outside.mkdir()
        with patch.object(b, "resolve_branch_urls", side_effect=self.resolve_urls), \
                patch.object(b, "working_copy_url", return_value=SCRIPT_URL):
            with self.assertRaisesRegex(b.BranchError, "目标目录已存在"):
                b.build_checkout(NAME, str(self.root), str(outside))

    def test_target_junction_to_reuse_is_rejected_before_same_directory_check(self):
        target = self.root / NAME
        reuse = self.root / "old"
        target.mkdir()
        reuse.mkdir()
        real_resolve = Path.resolve

        def junction_resolve(path, *args, **kwargs):
            if Path(path) == target:
                return reuse
            return real_resolve(path, *args, **kwargs)

        def reparse(path):
            return Path(path) == target

        with patch.object(Path, "resolve", autospec=True, side_effect=junction_resolve), \
                patch.object(b, "has_reparse_attribute", side_effect=reparse), \
                patch.object(b, "working_copy_url", return_value=SCRIPT_URL), \
                patch.object(b, "resolve_branch_urls", side_effect=self.resolve_urls):
            with self.assertRaisesRegex(b.BranchError, "目标目录不能是符号链接或目录联接"):
                b.build_checkout(NAME, str(self.root), str(reuse))

    def test_reuse_steps_rename_then_cleanup_switch_and_checkout_missing_children(self):
        reuse = self.root / "old"
        (reuse / "mhimage").mkdir(parents=True)
        (reuse / "_test").mkdir()
        status = subprocess.CompletedProcess([], 0, b"", b"")
        with patch.object(b, "run_svn", return_value=status) as run, \
                patch.object(b, "svn_info", return_value="uuid-svn"), \
                patch.object(b, "resolve_branch_urls", side_effect=self.resolve_urls):
            result = b.build_checkout(NAME, str(self.root), str(reuse))
        kinds = [step["type"] for step in result["steps"]]
        self.assertEqual(kinds, ["rename", "svn", "svn", "svn", "svn", "svn"])
        args = [step["args"] for step in result["steps"] if step["type"] == "svn"]
        self.assertEqual(args[0], ["cleanup", "mhimage"])
        self.assertEqual(args[1], ["switch", "-q", SCRIPT_URL, "mhimage", "--force", "--ignore-ancestry"])
        self.assertEqual(args[2], ["cleanup", "_test"])
        self.assertEqual(args[3], ["switch", "-q", URLS["resources"]["_test"], "_test", "--force", "--ignore-ancestry"])
        self.assertEqual(args[4], ["checkout", "-q", URLS["resources"]["_testhd"], "_testhd"])
        self.assertEqual(run.call_count, 2)  # mhimage、_test 状态检查各一次；_test 与目标同仓库，不做完整状态检查。

    def test_reuse_rejects_unversioned_files_but_not_externals(self):
        reuse = self.root / "old"
        (reuse / "mhimage").mkdir(parents=True)
        calls = []

        def run(*args, **kwargs):
            calls.append((args, kwargs))
            return subprocess.CompletedProcess(args, 0, b"X       mhimage\\prot\r\n?       mhimage\\new.py\r\n"
                                                        b"?       mhimage\\tmp\r\n", b"")

        with patch.object(b, "run_svn", side_effect=run):
            with self.assertRaisesRegex(b.BranchError, r"未纳入版本控制.*mhimage\\new\.py, mhimage\\tmp"):
                b.inspect_reuse(reuse)
        args, kwargs = calls[0]
        self.assertNotIn("-q", args)
        self.assertIn("--ignore-externals", args)
        self.assertEqual(kwargs["timeout"], b.SVN_TIMEOUT)
        externals_only = subprocess.CompletedProcess([], 0, b"X       mhimage\\prot\r\n", b"")
        with patch.object(b, "run_svn", return_value=externals_only):
            self.assertEqual(b.inspect_reuse(reuse), ["mhimage"])

    def test_reuse_ignores_workspace_local_files(self):
        reuse = self.root / "old"
        (reuse / "mhimage").mkdir(parents=True)
        initialized = subprocess.CompletedProcess([], 0, b"?       mhimage\\.claude\r\n?       mhimage\\.mhxy-workspace\r\n"
                                                         b"?       mhimage\\CLAUDE.md\r\n\r\n"
                                                         b"--- Changelist 'ignore-on-commit':\r\n"
                                                         b"M       mhimage\\AGENTS.md\r\n", b"")
        with patch.object(b, "run_svn", return_value=initialized):
            self.assertEqual(b.inspect_reuse(reuse), ["mhimage"])
        nested = subprocess.CompletedProcess([], 0, b"M       mhimage\\sub\\AGENTS.md\r\n", b"")
        with patch.object(b, "run_svn", return_value=nested):
            with self.assertRaisesRegex(b.BranchError, "拒绝切换"):
                b.inspect_reuse(reuse)

    def test_reuse_must_be_direct_child_with_mhimage_working_copy(self):
        nested = self.root / "group" / "old"
        (nested / "mhimage").mkdir(parents=True)
        plain = self.root / "plain"
        plain.mkdir()
        not_working_copy = self.root / "copy"
        (not_working_copy / "mhimage").mkdir(parents=True)
        missing = subprocess.CompletedProcess([], 1, b"", b"svn: E155007: not a working copy")
        with patch.object(b.Path, "cwd", return_value=self.root / "session"), \
                patch.object(b, "svn_info", return_value=SCRIPT_URL):
            with self.assertRaisesRegex(b.BranchError, "直接子目录"):
                b.resolve_reuse(self.root, str(nested))
            with self.assertRaisesRegex(b.BranchError, "没有 mhimage"):
                b.resolve_reuse(self.root, "plain")
        with patch.object(b.Path, "cwd", return_value=self.root / "session"), \
                patch.object(b, "run_svn", return_value=missing):
            with self.assertRaisesRegex(b.BranchError, "没有 mhimage"):
                b.resolve_reuse(self.root, "copy")
        with patch.object(b.Path, "cwd", return_value=self.root / "session"), \
                patch.object(b, "svn_info", return_value=SCRIPT_URL):
            self.assertEqual(b.resolve_reuse(self.root, "copy"), not_working_copy)

    def test_svn_timeout_is_reported_distinctly(self):
        with patch.object(b.precommit.subprocess, "run", side_effect=subprocess.TimeoutExpired(["svn"], 3600)):
            with self.assertRaisesRegex(b.BranchError, "SVN 命令超时"):
                b.run_svn("status", "mhimage", timeout=3600)

    def test_stale_resource_warning_without_url(self):
        reuse = self.root / "old"
        (reuse / "_test").mkdir(parents=True)
        with patch.object(b, "svn_info", return_value=None):
            warnings = b.stale_resource_warnings(reuse, {"script": SCRIPT_URL, "resources": {}})
        self.assertEqual(len(warnings), 1)
        self.assertNotIn("None", warnings[0])
        self.assertIn("未能读取", warnings[0])

    def test_reuse_rejects_link_or_file_child_and_status_stderr(self):
        reuse = self.root / "old"
        reuse.mkdir()
        child = reuse / "_test"
        child.mkdir()
        with patch.object(b, "has_reparse_attribute", side_effect=lambda path: Path(path) == child):
            with self.assertRaisesRegex(b.BranchError, "符号链接或目录联接"):
                b.inspect_reuse(reuse)

        child.rmdir()
        child.write_text("not a working copy", encoding="utf-8")
        with self.assertRaisesRegex(b.BranchError, "必须是普通目录"):
            b.inspect_reuse(reuse)

        child.unlink()
        child.mkdir()
        warning = subprocess.CompletedProcess([], 0, b"", b"svn: warning: not a working copy")
        with patch.object(b, "run_svn", return_value=warning):
            with self.assertRaisesRegex(b.BranchError, "状态检查有输出"):
                b.inspect_reuse(reuse)

    def test_same_directory_reuse_previews_and_executes(self):
        target = self.root / NAME
        (target / "mhimage").mkdir(parents=True)
        with patch.object(b.Path, "cwd", return_value=self.root / "session"):
            with patch.object(b, "run_svn", return_value=subprocess.CompletedProcess([], 0, b"", b"")) as run, \
                    patch.object(b, "working_copy_url", return_value=SCRIPT_URL), \
                    patch.object(b, "resolve_branch_urls", side_effect=self.resolve_urls):
                preview = b.checkout(NAME, str(self.root), str(target))
                self.assertEqual(preview["steps"][0]["type"], "same_directory")
                self.assertIn("already at target", preview["steps"][0]["command"])
                applied = b.checkout(NAME, str(self.root), str(target), apply=True)
        self.assertEqual(applied["status"], "completed")
        self.assertEqual(applied["completed_steps"][0]["status"], "already_at_target")
        self.assertEqual(run.call_count, 6)  # 两次预览各检查一次 mhimage，应用时再执行 mhimage 切换。

    def test_checkout_full_apply_success_and_preview_has_no_directory_write(self):
        target = self.root / NAME
        api_payload = json.dumps({"data": ROWS})
        success = subprocess.CompletedProcess([], 0, b"", b"")
        with patch.object(b, "http_get", return_value=api_payload) as http, \
                patch.object(b, "svn_info", side_effect=lambda url, **kwargs: url), \
                patch.object(b, "run_svn", return_value=success) as svn:
            preview = b.checkout(NAME, str(self.root))
            self.assertFalse(target.exists())
            self.assertTrue(preview["preview"])
            applied = b.checkout(NAME, str(self.root), apply=True)
        self.assertTrue(target.is_dir())
        self.assertEqual(applied["status"], "completed")
        self.assertEqual([args[0] for args, _ in svn.call_args_list], ["checkout"] * 3)
        self.assertEqual(http.call_count, 2)

    def test_reusable_listing_does_not_run_status(self):
        candidate = self.root / "old" / "mhimage"
        candidate.mkdir(parents=True)
        with patch.object(b, "svn_info", return_value=SCRIPT_URL), \
                patch.object(b, "run_svn", side_effect=AssertionError("reusable must not run svn status")) as svn:
            result = b.reusable(self.root)
        self.assertEqual(result["candidates"][0]["mhimage_url"], SCRIPT_URL)
        svn.assert_not_called()

    def test_switch_uses_long_svn_timeout(self):
        target = self.root / NAME
        target.mkdir()
        step = b.make_svn_step(["switch", SCRIPT_URL, "mhimage"], target, "switch")
        result = {"target": str(target), "steps": [{**step, "command": b.command_preview(step)}]}
        with patch.object(b, "run_svn", return_value=subprocess.CompletedProcess([], 0, b"", b"")) as run:
            outcome = b.execute_steps(result)
        self.assertEqual(outcome["status"], "completed")
        self.assertEqual(run.call_args.kwargs["timeout"], b.SVN_TIMEOUT)


class ConfigTests(unittest.TestCase):
    def test_email_prefix_uses_shared_account_rules(self):
        self.assertEqual(b.email_prefix({"openid_username": "WangZhuoWei@corp.netease.com"}), "wangzhuowei")
        for value in (None, "", "someone@example.com", "bad name@corp.netease.com"):
            with self.subTest(value=value), self.assertRaises(b.BranchError):
                b.email_prefix({"openid_username": value})

    def test_load_config_validates_and_applies_workspace_override(self):
        with tempfile.TemporaryDirectory(prefix="branch-config-") as temp:
            base = Path(temp)
            config = base / "global.json"
            config.write_text(json.dumps({"openid_username": "dev@corp.netease.com", "branches_root": "D:\\a"}),
                              encoding="utf-8")
            local = base / ".mhxy-workspace" / "config.json"
            local.parent.mkdir()
            local.write_text(json.dumps({"branches_root": "D:\\b"}), encoding="utf-8")
            with patch.object(b.Path, "cwd", return_value=base):
                self.assertEqual(b.load_config(config)["branches_root"], "D:\\b")
                config.write_text(json.dumps({"unknown_key": 1}), encoding="utf-8")
                with self.assertRaisesRegex(b.BranchError, "未知配置键"):
                    b.load_config(config)


class RootConfigurationTests(unittest.TestCase):
    def test_missing_root_message_and_settings_with_comments(self):
        with patch.object(b, "settings_suggestion", return_value="D:\\workspace"):
            with self.assertRaises(b.BranchError) as error:
                b.resolve_root(config={})
        self.assertIn('workspace.py" config --set-global "branches_root=<路径>" --apply', str(error.exception))
        self.assertIn("D:\\workspace", str(error.exception))

        with tempfile.TemporaryDirectory(prefix="branch-settings-") as temp:
            settings = Path(temp) / "Cursor" / "User" / "settings.json"
            settings.parent.mkdir(parents=True)
            settings.write_text('{\n // Cursor legacy setting\n "MHCoder.branchesBaseDir": "D:\\\\workspace",\n}\n',
                                encoding="utf-8")
            self.assertEqual(b.settings_suggestion(temp), "D:\\workspace")


if __name__ == "__main__":
    unittest.main()
