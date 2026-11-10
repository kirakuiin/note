"""复用旧目录检出时自动清理 mhimage/.mhxy-workspace/ 的测试；SVN 全部模拟，只用临时目录。"""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import branch as b  # noqa: E402

NAME = "wzw_2026_10_10_qixi"
URLS = {"script": f"{b.SCRIPT_BRANCH_ROOT}/2026_dev/{NAME}", "resources": {}}
OK = subprocess.CompletedProcess([], 0, b"", b"")


class ReuseCleanTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="branch-clean-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.reuse = self.root / "old"
        self.personal = self.reuse / "mhimage" / ".mhxy-workspace"
        (self.reuse / "mhimage").mkdir(parents=True)
        for patcher in (patch.object(b, "resolve_branch_urls", return_value=(URLS, [])),
                        patch.object(b, "svn_info", return_value="uuid"),
                        patch.object(b, "CONFIG_PATH", self.root / "home" / "config.json")):
            patcher.start()
            self.addCleanup(patcher.stop)

    def fill(self):
        (self.personal / "tasks/1").mkdir(parents=True)
        (self.personal / "tasks/1/issue.md").write_text("old")
        (self.personal / "tracking.json").write_text("{}")

    def job(self, name, state):
        directory = self.personal / "codex-cli" / name
        directory.mkdir(parents=True)
        (directory / "state.json").write_text(json.dumps(state))

    def checkout(self, apply=False, run=None, reuse="old"):
        with patch.object(b, "run_svn", side_effect=run, return_value=OK):
            return b.checkout(NAME, str(self.root), reuse, apply)

    def test_preview_lists_clean_step_after_svn_steps(self):
        self.fill()
        result = self.checkout()
        self.assertEqual(result["checks"]["workspace_clean"], ["tasks", "tracking.json"])
        self.assertEqual([step["type"] for step in result["steps"]], ["rename", "svn", "svn", "clean_workspace"])
        self.assertIn(str(self.root / NAME / "mhimage" / ".mhxy-workspace"), result["steps"][-1]["command"])
        self.assertTrue((self.personal / "tracking.json").exists())  # 预览不删除

    def test_apply_cleans_after_switch(self):
        self.fill()
        result = self.checkout(apply=True)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["completed_steps"][-1]["status"], "cleaned")
        personal = self.root / NAME / "mhimage" / ".mhxy-workspace"
        self.assertTrue(personal.is_dir())
        self.assertEqual(list(personal.iterdir()), [])

    def test_no_personal_content_keeps_old_plan(self):
        for prepare in (lambda: None, self.personal.mkdir):
            prepare()
            result = self.checkout()
            self.assertNotIn("workspace_clean", result["checks"])
            self.assertEqual([step["type"] for step in result["steps"]], ["rename", "svn", "svn"])

    def test_new_checkout_has_no_clean_step(self):
        result = self.checkout(reuse=None)
        self.assertNotIn("clean_workspace", [step["type"] for step in result["steps"]])

    def test_busy_jobs_refuse_reuse_in_preview(self):
        cases = {"running": {"kind": "review", "status": "running"},
                 "unreleased": {"kind": "test", "status": "completed", "released": False},
                 "unknown": None}
        for label, state in cases.items():
            with self.subTest(label):
                self.fill()
                if state is None:
                    (self.personal / "codex-cli/job").mkdir(parents=True)
                else:
                    self.job("job", state)
                with self.assertRaisesRegex(b.BranchError, "无法清理，拒绝复用"):
                    self.checkout(apply=True)
                self.assertTrue((self.personal / "tracking.json").exists())
                self.assertTrue(self.reuse.is_dir())  # 没有改名，也没有切换
                self.assertFalse((self.root / NAME).exists())
                shutil.rmtree(self.personal)

    def test_finished_jobs_do_not_block(self):
        self.job("done", {"kind": "test", "status": "completed", "released": True})
        result = self.checkout()
        self.assertEqual(result["checks"]["workspace_clean"], ["codex-cli"])

    def test_failed_switch_leaves_personal_directory(self):
        self.fill()

        def run(*args, **kwargs):
            failed = args[0] == "switch"
            return subprocess.CompletedProcess(args, int(failed), b"", b"switch failed" if failed else b"")

        result = self.checkout(apply=True, run=run)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(any(item.startswith("clean ") for item in result["remaining_steps"]))
        self.assertTrue((self.root / NAME / "mhimage/.mhxy-workspace/tracking.json").exists())


if __name__ == "__main__":
    unittest.main()
