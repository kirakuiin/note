"""处理报告和无人值守结果文件的测试；SVN 用临时仓库。"""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import svn_fixture  # noqa: E402


def load(name):
    spec = importlib.util.spec_from_file_location(f"{name}_under_test", SOURCE / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


report = load("report")
unattended = load("unattended")


def run(module, *argv):
    """调用脚本入口，返回 (退出码, stdout 的 JSON, stderr 的 JSON)。"""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = module.main([str(item) for item in argv])
    return code, json.loads(out.getvalue() or "null"), json.loads(err.getvalue() or "null")


class Workspace(unittest.TestCase):
    """一个已初始化的临时工作副本：trunk 里有 gameplay/a.py，入口文件未纳管。"""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="mhxy-report-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.repository = svn_fixture.Repository(self.base)
        self.repository.import_tree({"gameplay/a.py": "# -*- coding: utf-8 -*-\nVALUE = 1\n",
                                     "gameplay/b.py": "# -*- coding: utf-8 -*-\n"}, "wzimage/trunk")
        self.root = self.repository.checkout("wzimage/trunk", self.base / "wc")
        (self.root / "AGENTS.md").write_text(
            "<!-- mhxy-workspace:begin -->\n### 管理元数据\n```json\n"
            '{"skill": "mhxy-workspace", "applied_version": "0.3.31", "schema_version": 2}\n```\n'
            "<!-- mhxy-workspace:end -->\n", encoding="utf-8")
        self.personal = self.root / ".mhxy-workspace"
        self.personal.mkdir()
        self.config = self.base / "config.json"
        self.common = ("--root", self.root, "--issue-id", "860053", "--global-config", self.config)

    def write(self, name, text):
        path = self.personal / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path


@svn_fixture.requires_svn
class ReportTests(Workspace):
    def setUp(self):
        super().setUp()
        self.analysis = self.write("analysis.md", "真因在 `gameplay/a.py`：\n\n- 取值 <错误>\n- 第二点\n\n```\nraise X\n```\n")
        self.solution = self.write("solution.md", "把 **VALUE** 改为 2。\n\n1. 改常量\n2. 补用例\n")
        (self.root / "gameplay/a.py").write_text("# -*- coding: utf-8 -*-\nVALUE = 2\n", encoding="utf-8")
        (self.root / "gameplay/new_mod.py").write_text("# -*- coding: utf-8 -*-\nNEW = '<b>'\n", encoding="utf-8")
        self.build_args = ("build", *self.common, "--analysis-file", self.analysis,
                           "--solution-file", self.solution, "--title", "战斗 <成语> 弹窗")

    def case_report(self, status="passed"):
        reports = self.personal / "cases/reports"
        (reports / "run1").mkdir(parents=True)
        (reports / "run1/case1_shot.png").write_bytes(b"\x89PNG fake")
        (reports / "run1/case1.mp4").write_bytes(b"fake mp4")
        (reports / "run1/case1_step1_ret.json").write_text("{}")
        path = reports / "run1.json"
        path.write_text(json.dumps({"status": status, "cases": ["弹窗：passed（3 秒）"], "errors": [],
                                    "unverified": ["监听 <多> 1"], "restoration": "restored", "results": []},
                                   ensure_ascii=False), encoding="utf-8")
        return path

    def test_build_collects_changes_and_escapes_everything(self):
        self.case_report()
        message = self.write("msg.txt", "finish #860053 战斗成语弹窗：修正 <取值>\n")
        problem = self.write("tasks/860053/problem.png", "png")
        code, result, error = run(report, *self.build_args, "--message-file", message, "--case-report", "latest",
                                  "--problem-media", problem)
        self.assertEqual((code, error), (0, None))
        self.assertEqual(result["changed_files"], ["gameplay/a.py", "gameplay/new_mod.py"])
        self.assertEqual((result["blocking"], result["media"], result["problem_media"]), (0, 2, 1))
        self.assertEqual(result["case_reports"], ["run1：passed"])
        self.assertNotIn("diff", json.dumps(result))  # 输出只有路径和统计
        folder = Path(result["report_dir"])
        self.assertEqual(folder, self.personal / "reports/860053")
        page = (folder / "index.html").read_text(encoding="utf-8")
        for expected in ("战斗 &lt;成语&gt; 弹窗", "取值 &lt;错误&gt;", "<code>gameplay/a.py</code>", "<strong>VALUE</strong>",
                         "<ol><li>改常量</li>", '<span class="l del">-VALUE = 1</span>',
                         '<span class="l add">+VALUE = 2</span>', "+NEW = '&lt;b&gt;'", "监听 &lt;多&gt; 1",
                         "修正 &lt;取值&gt;", "<video controls", "<details><summary>gameplay/a.py</summary>",
                         "无阻断问题", "尚未提交", "问题现象", "trunk"):
            self.assertIn(expected, page)
        self.assertNotIn("<details open", page)  # diff 默认折叠
        self.assertNotIn("http://", page)  # 自包含：不引用外部资源
        self.assertNotIn("https://", page)
        media = sorted(path.name for path in (folder / "media").iterdir())
        self.assertEqual(media, ["after01_case1.mp4", "after02_case1_shot.png", "problem01_problem.png"])
        for name in media:
            self.assertIn(f"media/{name}", page)

    def test_case_files_are_copied_for_rerun(self):
        meta = {"issue": "860053", "spec": None, "targets": ["gameplay/a.py"], "keywords": []}
        json_case = self.write("cases/860053/popup.json", json.dumps({"name": "弹窗", **meta, "steps": []}))
        spec = self.root / "spec/成语弹窗.md"
        spec.parent.mkdir()
        spec.write_text("# 成语弹窗\n## 测试用例\n```json\n" + json.dumps({"name": "回归", "steps": []})
                        + "\n```\n", encoding="utf-8")
        path = self.case_report()
        data = json.loads(path.read_text(encoding="utf-8"))
        data["sources"] = [str(json_case), str(spec), str(json_case)]
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        code, result, error = run(report, *self.build_args, "--case-report", "latest")
        self.assertEqual((code, error), (0, None))
        self.assertEqual(result["case_files"], ["cases/popup.json", "cases/成语弹窗.json"])  # 同一来源只拷一次
        folder = Path(result["report_dir"])
        self.assertEqual(json.loads((folder / "cases/popup.json").read_text(encoding="utf-8"))["name"], "弹窗")
        self.assertEqual([item["name"] for item in json.loads((folder / "cases/成语弹窗.json").read_text(
            encoding="utf-8"))], ["回归"])
        page = (folder / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="cases/popup.json"', page)
        self.assertIn("case_runner.py", page)
        _, again, _ = run(report, *self.build_args)  # 重建时 cases/ 一并清掉
        self.assertEqual(again["case_files"], [])
        self.assertFalse((folder / "cases").exists())
        data["sources"] = [str(self.personal / "cases/860053/gone.json")]
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        code, _, error = run(report, *self.build_args, "--case-report", "latest")
        self.assertEqual(code, 1)
        self.assertIn("用例文件不存在", error["error"])

    def test_local_only_and_data_changes_are_left_out(self):
        (self.root / "data").mkdir()
        (self.root / "data/info.py").write_text("X = 1\n")
        (self.root / "CLAUDE.md").write_text("x\n")
        code, result, _ = run(report, *self.build_args)
        self.assertEqual(code, 0)
        self.assertEqual(result["changed_files"], ["gameplay/a.py", "gameplay/new_mod.py"])
        self.assertEqual(result["case_reports"], [])

    def test_path_filter_and_unknown_path(self):
        code, result, _ = run(report, *self.build_args, "--path", "gameplay/a.py")
        self.assertEqual((code, result["changed_files"]), (0, ["gameplay/a.py"]))
        code, _, error = run(report, *self.build_args, "--path", "gameplay/b.py")
        self.assertEqual(code, 1)
        self.assertIn("gameplay/b.py", error["error"])

    def test_blocking_precheck_is_shown(self):
        (self.root / "gameplay/a.py").write_text("# -*- coding: utf-8 -*-\nVALUE = (\n", encoding="utf-8")
        code, result, _ = run(report, *self.build_args)
        self.assertEqual(code, 0)
        self.assertGreater(result["blocking"], 0)
        self.assertIn("有阻断问题", (Path(result["report_dir"]) / "index.html").read_text(encoding="utf-8"))

    def test_rebuild_replaces_old_media_and_commit_adds_revision(self):
        shot = self.write("shot.png", "png")
        _, first, _ = run(report, *self.build_args, "--media", shot,
                          "--message-file", self.write("msg.txt", "finish #860053 x：y\n"))
        folder = Path(first["report_dir"])
        self.assertEqual(first["media"], 1)
        _, second, _ = run(report, *self.build_args, "--message-file", self.personal / "msg.txt")
        self.assertEqual(second["media"], 0)
        self.assertFalse((folder / "media").exists())
        before = (folder / "index.html").read_text(encoding="utf-8")
        code, committed, _ = run(report, "commit", *self.common, "--revision", "123456")
        self.assertEqual((code, committed["revision"], committed["status"]), (0, 123456, "已提交"))
        after = (folder / "index.html").read_text(encoding="utf-8")
        self.assertIn("r123456", after)
        self.assertNotIn("尚未提交", after)
        self.assertIn("+VALUE = 2", after)  # 其余内容来自 report.json，不重新收集
        self.assertNotEqual(before, after)

    def test_rejections_write_nothing(self):
        cases = {
            "标题": (("build", *self.common, "--analysis-file", self.analysis, "--solution-file", self.solution), "--title"),
            "状态": ((*self.build_args, "--status", "完成"), "--status"),
            "空文本": ((*self.build_args[:-4], "--solution-file", self.write("empty.md", " \n"), "--title", "t"), "为空"),
            "媒体类型": ((*self.build_args, "--media", self.analysis), "媒体类型"),
            "用例报告": ((*self.build_args, "--case-report", "latest"), "没有用例执行器报告"),
            "工单号": (("build", "--root", self.root, "--issue-id", "abc", "--global-config", self.config,
                     "--analysis-file", self.analysis, "--solution-file", self.solution), "工单号"),
            "版本号": (("commit", *self.common, "--revision", "r12"), "正整数"),
            "无报告": (("commit", *self.common, "--revision", "12"), "还没有处理报告"),
        }
        for label, (argv, expected) in cases.items():
            with self.subTest(label):
                code, _, error = run(report, *argv)
                self.assertEqual(code, 1)
                self.assertIn(expected, error["error"])
                self.assertFalse((self.personal / "reports/860053/index.html").exists())

    def test_title_from_tracking_and_unknown_files_stop_rebuild(self):
        self.write("tracking.json", json.dumps({"tracked_tasks": [
            {"issue_id": "860053", "title": "追踪的标题", "description_path": ".mhxy-workspace/tasks/860053/issue.md"}],
            "coverage_tasks": []}, ensure_ascii=False))
        argv = ("build", *self.common, "--analysis-file", self.analysis, "--solution-file", self.solution)
        code, result, _ = run(report, *argv)
        self.assertEqual((code, result["title"]), (0, "追踪的标题"))
        stray = self.personal / "reports/860053/notes.txt"
        stray.write_text("用户放的")
        code, _, error = run(report, *argv)
        self.assertEqual(code, 1)
        self.assertIn("不认识的文件", error["error"])
        self.assertTrue(stray.exists())

    def test_uninitialized_root_is_refused(self):
        (self.root / "AGENTS.md").unlink()
        for module, argv in ((report, self.build_args), (report, ("commit", *self.common, "--revision", "12")),
                             (unattended, ("show", *self.common))):
            code, _, error = run(module, *argv)
            self.assertEqual(code, 1)
            self.assertIn("不是已初始化的工作区", error["error"])


class RenderTests(unittest.TestCase):
    def test_long_diff_is_truncated(self):
        text, truncated = report.clip_lines("\n".join(["+x"] * (report.DIFF_LINE_LIMIT + 5)))
        self.assertTrue(truncated)
        self.assertEqual(len(text.splitlines()), report.DIFF_LINE_LIMIT)

    def test_inline_code_is_not_rescanned_for_bold(self):
        self.assertEqual(report.render_text("`a**b` 和 **c** 以及 `d**`"),
                         "<p><code>a**b</code> 和 <strong>c</strong> 以及 <code>d**</code></p>")

    def test_unclosed_code_block_and_mixed_lists(self):
        page = report.render_text("- a\n1. b\n\n```\n<x>")
        self.assertEqual(page, '<ul><li>a</li></ul>\n<ol><li>b</li></ol>\n<pre class="code">&lt;x&gt;</pre>')


class UnattendedResultTests(Workspace):
    def setUp(self):
        super().setUp()
        patcher = patch.object(unattended.workspace, "svn_branch", return_value={"name": "trunk"})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.report = self.write("reports/860053/index.html", "<html>")
        self.ready = ("result", *self.common, "--status", "待提交", "--reason", "已修复",
                      "--file", "gameplay\\a.py", "--file", "gameplay/a.py", "--message", "finish #860053 x：y",
                      "--self-check", "自检通过", "--report", self.report.parent)

    def test_ready_result_has_fixed_fields(self):
        code, output, error = run(unattended, *self.ready)
        self.assertEqual((code, error), (0, None))
        path = self.personal / "unattended/860053/result.json"
        self.assertEqual(Path(output["path"]), path)
        saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(tuple(saved), unattended.FIELDS)
        self.assertEqual((saved["status"], saved["changed_files"], saved["branch"]),
                         ("待提交", ["gameplay/a.py"], {"name": "trunk"}))
        self.assertEqual(Path(saved["report_path"]), self.report)
        code, shown, _ = run(unattended, "show", *self.common)
        self.assertEqual((code, shown["result"]), (0, saved))

    def test_pm_update_is_optional_and_validated(self):
        pm = ("--pm-status", "代码审查", "--pm-status-from", "新建,10%", "--pm-hours", "0.2",
              "--pm-activity", "程序开发-制作")
        code, output, error = run(unattended, *self.ready, *pm)
        self.assertEqual((code, error), (0, None))
        saved = output["result"]
        self.assertEqual(tuple(saved), unattended.FIELDS + ("pm_update",))
        self.assertEqual(saved["pm_update"], {"status": "代码审查", "status_from": "新建,10%", "hours": "0.2",
                                              "activity": "程序开发-制作", "comments": ""})
        code, shown, _ = run(unattended, "show", *self.common)
        self.assertEqual((code, shown["result"]), (0, saved))
        for bad in (("--pm-hours", "0.2"), ("--pm-activity", "程序开发-制作"), ("--pm-status-from", "新建"),
                    ("--pm-hours", "0", "--pm-activity", "a"), ("--pm-hours", "0.125", "--pm-activity", "a"),
                    ("--pm-comments", "只有备注"), ("--pm-status", "代码审查", "--pm-comments", "备注"),
                    ("--pm-status", " "), ("--pm-status", "代码审查", "--pm-status-from", "新建,,10%")):
            with self.subTest(bad):
                code, _, error = run(unattended, *self.ready, *bad)
                self.assertEqual(code, 1)
        code, _, error = run(unattended, "result", *self.common, "--status", "放弃", "--reason", "x",
                             "--pm-status", "代码审查")
        self.assertEqual(code, 1)
        self.assertIn("待提交", error["error"])

    def test_ready_requires_every_field(self):
        for flag, label in (("--file", "改动文件"), ("--message", "提交说明"), ("--self-check", "自检结果"),
                            ("--report", "报告路径")):
            with self.subTest(flag):
                argv = list(self.ready)
                while flag in argv:
                    position = argv.index(flag)
                    del argv[position:position + 2]
                code, _, error = run(unattended, *argv)
                self.assertEqual(code, 1)
                self.assertIn(label, error["error"])
        self.assertFalse((self.personal / "unattended").exists())

    def test_stopped_results_only_need_a_reason(self):
        reason = self.write("reason.txt", "需要策划确认表现\n")
        code, output, _ = run(unattended, "result", *self.common, "--status", "需要你处理", "--reason-file", reason)
        self.assertEqual(code, 0)
        self.assertEqual((output["result"]["reason"], output["result"]["changed_files"],
                          output["result"]["report_path"]), ("需要策划确认表现", [], ""))
        code, output, _ = run(unattended, "result", *self.common, "--status", "放弃", "--reason", "新功能，C 类")
        self.assertEqual((code, output["result"]["status"]), (0, "放弃"))  # 覆盖上一次的结果

    def test_rejections(self):
        cases = {
            "状态": (("--status", "完成", "--reason", "x"), "状态只能是"),
            "原因": (("--status", "放弃", "--reason", "  "), "原因"),
            "重复给出": (("--status", "放弃", "--reason", "x", "--reason-file", self.report), "不能同时"),
            "绝对路径": (("--status", "放弃", "--reason", "x", "--file", str(self.root / "a.py")), "相对项目根目录"),
            "上级路径": (("--status", "放弃", "--reason", "x", "--file", "../a.py"), "相对项目根目录"),
            "报告缺失": (("--status", "放弃", "--reason", "x", "--report", "nowhere"), "报告不存在"),
        }
        for label, (extra, expected) in cases.items():
            with self.subTest(label):
                code, _, error = run(unattended, "result", *self.common, *extra)
                self.assertEqual(code, 1)
                self.assertIn(expected, error["error"])
        code, _, error = run(unattended, "show", *self.common)
        self.assertEqual(code, 1)
        self.assertIn("还没有结果文件", error["error"])


if __name__ == "__main__":
    unittest.main()
