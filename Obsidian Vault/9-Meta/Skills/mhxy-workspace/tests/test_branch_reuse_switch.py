"""复用目录切换前的 relocate 和入口文件处理；SVN 均为模拟。"""
from pathlib import Path
import subprocess
import tempfile
import unittest
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
SVN_ROOT = "svn://svn-xyq.gz.netease.com/svn"
HTTPS_ROOT = "https://svn-xyq.gz.netease.com/svn"
BASE = "# AGENTS.md\n\n规则正文\n"
BLOCK = ("<!-- mhxy-workspace:begin -->\n## 梦幻西游工作区\n\n### 管理元数据\n```json\n"
         '{\n  "skill": "mhxy-workspace",\n  "applied_version": "0.3.51",\n  "schema_version": 2\n}\n'
         "```\n<!-- mhxy-workspace:end -->\n")
OK = subprocess.CompletedProcess([], 0, b"", b"")


class ReuseSwitchTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="branch-switch-")
        self.root = Path(self.temporary.name).resolve()
        self.reuse = self.root / "old"
        (self.reuse / "mhimage").mkdir(parents=True)
        (self.reuse / "_test").mkdir()
        self.https_folders = set()
        self.entry_status = {}
        self.base = BASE.encode("utf-8")

    def tearDown(self):
        self.temporary.cleanup()

    def info(self, target, item=None, cwd=None):
        if item == "repos-root-url":
            return HTTPS_ROOT if cwd is not None and str(target) in self.https_folders else SVN_ROOT
        return "uuid-svn"

    def fake_svn(self, *args, **kwargs):
        if args[0] == "status" and args[-1] in self.entry_status:
            return subprocess.CompletedProcess(args, 0, self.entry_status[args[-1]].encode("utf-8"), b"")
        if args[0] == "cat":
            return subprocess.CompletedProcess(args, 0, self.base, b"")
        return OK

    def build(self):
        with patch.object(b.Path, "cwd", return_value=self.root / "session"), \
                patch.object(b, "resolve_branch_urls", return_value=(URLS, [])), \
                patch.object(b, "svn_info", side_effect=self.info), \
                patch.object(b, "run_svn", side_effect=self.fake_svn):
            return b.build_checkout(NAME, str(self.root), str(self.reuse))

    def svn_args(self, result):
        return [step["args"] for step in result["steps"] if step["type"] == "svn"]

    def test_scheme_mismatch_relocates_before_switch(self):
        self.https_folders = {"_test"}
        result = self.build()
        self.assertEqual(result["checks"]["relocated_working_copies"], {"_test": f"{HTTPS_ROOT} -> {SVN_ROOT}"})
        self.assertEqual([args[0] for args in self.svn_args(result)],
                         ["cleanup", "switch", "cleanup", "relocate", "switch", "checkout"])
        self.assertEqual(self.svn_args(result)[3], ["relocate", HTTPS_ROOT, SVN_ROOT, "_test"])

    def test_same_root_or_different_repository_is_not_relocated(self):
        result = self.build()
        self.assertNotIn("relocated_working_copies", result["checks"])
        with patch.object(b, "svn_info", side_effect=lambda target, item=None, cwd=None:
                          (HTTPS_ROOT if cwd is not None else SVN_ROOT) if item == "repos-root-url"
                          else ("uuid-local" if cwd is not None else "uuid-target")):
            self.assertEqual(b.relocations(self.reuse, URLS), {})

    def test_entry_file_with_only_managed_block_is_reverted_before_switch(self):
        (self.reuse / "mhimage" / "AGENTS.md").write_text(BASE + "\n" + BLOCK, encoding="utf-8")
        self.entry_status = {"mhimage/AGENTS.md": "\n--- Changelist 'ignore-on-commit':\nM       mhimage\\AGENTS.md\n"}
        result = self.build()
        self.assertEqual(result["checks"]["entry_files_reset"], ["mhimage/AGENTS.md"])
        self.assertEqual(self.svn_args(result)[:3],
                         [["cleanup", "mhimage"], ["revert", "mhimage/AGENTS.md"],
                          ["switch", "-q", SCRIPT_URL, "mhimage", "--force", "--ignore-ancestry"]])
        self.assertTrue(any("sync" in warning for warning in result["warnings"]))

    def test_base_already_holding_an_older_block_still_counts_as_block_only(self):
        self.base = (BASE + "\n" + BLOCK.replace("0.3.51", "0.3.40")).encode("utf-8")
        (self.reuse / "mhimage" / "AGENTS.md").write_text(BASE + "\n" + BLOCK, encoding="utf-8")
        self.entry_status = {"mhimage/AGENTS.md": "M       mhimage\\AGENTS.md\n"}
        self.assertEqual(self.build()["checks"]["entry_files_reset"], ["mhimage/AGENTS.md"])

    def test_entry_file_with_user_edits_is_rejected(self):
        (self.reuse / "mhimage" / "AGENTS.md").write_text(BASE + "我的改动\n\n" + BLOCK, encoding="utf-8")
        self.entry_status = {"mhimage/AGENTS.md": "M       mhimage\\AGENTS.md\n"}
        with self.assertRaisesRegex(b.BranchError, "受管区段以外有本地修改"):
            self.build()

    def test_conflicted_entry_file_is_rejected(self):
        (self.reuse / "mhimage" / "AGENTS.md").write_text(BASE, encoding="utf-8")
        self.entry_status = {"mhimage/AGENTS.md": "C       mhimage\\AGENTS.md\n"}
        with self.assertRaisesRegex(b.BranchError, "状态为 C"):
            self.build()

    def test_unversioned_block_only_entry_file_is_removed_before_switch(self):
        path = self.reuse / "mhimage" / "CLAUDE.md"
        path.write_text(BLOCK, encoding="utf-8")
        self.entry_status = {"mhimage/CLAUDE.md": "?       mhimage\\CLAUDE.md\n"}
        result = self.build()
        kinds = [step["type"] for step in result["steps"]]
        self.assertEqual(kinds[:4], ["rename", "svn", "remove_entry", "svn"])
        self.assertIn("unversioned entry file", result["steps"][2]["command"])
        step = result["steps"][2]

        moved = self.root / NAME / "mhimage" / "CLAUDE.md"
        self.assertEqual(Path(step["path"]), moved)
        moved.parent.mkdir(parents=True)
        moved.write_text(BLOCK, encoding="utf-8")
        self.assertEqual(b.remove_entry_file(step["path"], step["sha256"]), "removed")
        self.assertFalse(moved.exists())
        moved.write_text(BLOCK + "后来加的\n", encoding="utf-8")
        with self.assertRaisesRegex(b.BranchError, "预览后被修改"):
            b.remove_entry_file(step["path"], step["sha256"])
        self.assertTrue(moved.exists())

    def test_unversioned_entry_file_with_other_content_is_rejected(self):
        (self.reuse / "mhimage" / "CLAUDE.md").write_text("自己写的说明\n", encoding="utf-8")
        self.entry_status = {"mhimage/CLAUDE.md": "?       mhimage\\CLAUDE.md\n"}
        with self.assertRaisesRegex(b.BranchError, "受管区段以外的内容"):
            self.build()

    def test_unmodified_entry_file_needs_no_step(self):
        (self.reuse / "mhimage" / "AGENTS.md").write_text(BASE, encoding="utf-8")
        result = self.build()
        self.assertNotIn("entry_files_reset", result["checks"])


if __name__ == "__main__":
    unittest.main()
