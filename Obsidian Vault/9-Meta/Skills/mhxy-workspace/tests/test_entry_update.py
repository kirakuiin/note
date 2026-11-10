"""context 自动更新入口文件受管区段的测试；只用临时目录，不碰真实家目录和工作区。"""
import codecs
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("workspace_entry_update", SOURCE / "scripts/workspace.py")
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)


class EntryUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="mhxy-test-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.root = self.base / "项目 空格"
        self.root.mkdir()
        self.global_config = self.base / "用户配置" / "config.json"
        self.skill = self.base / "安装 空格"
        shutil.copytree(SOURCE, self.skill, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
        self.agents = self.root / "AGENTS.md"
        self.claude = self.root / "CLAUDE.md"
        self.initial = json.loads((self.skill / "config/version.json").read_text())["applied_version"]
        major, minor, revision = w.release(self.initial)
        self.next = f"{major}.{minor}.{revision + 1}"
        for name, value in (("svn_local_changes", ("unavailable", set())), ("svn_branch", None),
                            ("svn_changelist", None)):
            patcher = patch.object(w, name, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(w.skill_links, "repair", return_value={"created": [], "replaced": [], "problems": []})
        patcher.start()
        self.addCleanup(patcher.stop)
        assignments = [f"{key}={self.root}" for key in w.PATH_KEYS]
        w.sync(self.root, self.global_config, assignments, True, self.skill)

    def bump(self, release=None):
        (self.skill / "config/version.json").write_text(json.dumps(
            {"skill": w.NAME, "applied_version": release or self.next, "schema_version": 2}))

    def context(self, **kwargs):
        return w.context(self.root, self.global_config, skill=self.skill, **kwargs)

    def versions(self):
        return [w.block_info(path.read_text(encoding="utf-8"))[2]["applied_version"]
                for path in (self.agents, self.claude)]

    def add_rule(self):
        template = self.skill / "assets/managed-block.md"
        template.write_text(template.read_text(encoding="utf-8").replace("### 边界", "### 边界\n- 新规则"),
                            encoding="utf-8")

    def test_current_version_is_left_alone(self):
        before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in (self.agents, self.claude)}
        self.add_rule()  # 版本没升：内容不同也不自动更新，由 sync 处理
        result = self.context()
        self.assertNotIn("entry_rules_updated", result)
        self.assertEqual(result["problems"], [])
        self.assertEqual(before, {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in before})

    def test_version_bump_updates_both_files_without_notice(self):
        self.bump()
        updated = self.context()["entry_rules_updated"]
        self.assertEqual(updated, {"from": self.initial, "to": self.next, "files": ["AGENTS.md", "CLAUDE.md"],
                                   "rules_changed": False, "notice": ""})
        self.assertEqual(self.versions(), [self.next, self.next])
        self.assertNotIn("entry_rules_updated", self.context())  # 幂等
        self.assertEqual(w.sync(self.root, self.global_config, (), False, self.skill)["changes"], [])

    def test_rule_change_is_reported_and_matches_sync_output(self):
        self.add_rule()
        self.bump()
        updated = self.context()["entry_rules_updated"]
        self.assertTrue(updated["rules_changed"])
        self.assertIn("重新读取 AGENTS.md", updated["notice"])
        self.assertIn("- 新规则", self.agents.read_text(encoding="utf-8"))
        preview = w.sync(self.root, self.global_config, (), False, self.skill)
        self.assertEqual((preview["changes"], preview["entry_rules_changed"]), ([], False))

    def test_opt_out_keeps_old_copy(self):
        self.bump()
        before = self.agents.read_bytes()
        self.assertNotIn("entry_rules_updated", self.context(entry_update=False))
        self.assertEqual(before, self.agents.read_bytes())

    def test_outside_content_encoding_and_newlines_preserved(self):
        block = self.agents.read_bytes().decode("utf-8").replace("\n", "\r\n")
        wrapped = "# 人工约定\r\n" + block + "\r\n# 后置约定\r\n"
        major, minor, revision = w.release(self.initial)
        cases = (("utf-8", codecs.BOM_UTF8), ("utf-16-le", codecs.BOM_UTF16_LE), ("gb18030", b""))
        for step, (encoding, bom) in enumerate(cases, 1):
            with self.subTest(encoding=encoding):
                self.agents.write_bytes(bom + wrapped.encode(encoding))  # 每轮都从初始版本的副本开始
                release = f"{major}.{minor}.{revision + step}"
                self.bump(release)
                self.assertEqual(self.context()["entry_rules_updated"]["to"], release)
                data = self.agents.read_bytes()
                self.assertTrue(data.startswith(bom + "# 人工约定\r\n".encode(encoding)))
                self.assertTrue(data.endswith("\r\n# 后置约定\r\n".encode(encoding)))
                body = data[len(bom):].decode(encoding)
                self.assertNotIn("\n", body.replace("\r\n", ""))
                self.assertEqual(w.block_info(body)[2]["applied_version"], release)

    def test_newer_or_incompatible_copies_are_not_touched(self):
        original = self.agents.read_text(encoding="utf-8")
        cases = {
            "newer": original.replace(json.dumps(self.initial), '"9.0.0"'),
            "schema": original.replace('"schema_version": 2', '"schema_version": 1'),
            "legacy": original.replace(w.NAME, w.LEGACY_NAME),
        }
        self.bump()
        for label, text in cases.items():
            with self.subTest(label):
                self.agents.write_text(text, encoding="utf-8")
                result = self.context()
                self.assertNotIn("entry_rules_updated", result)
                self.assertEqual(self.agents.read_text(encoding="utf-8"), text)

    def test_claude_without_block_or_newer_is_skipped(self):
        self.bump()
        self.claude.write_text("manual\n", encoding="utf-8")
        self.assertEqual(self.context()["entry_rules_updated"]["files"], ["AGENTS.md"])
        self.assertEqual(self.claude.read_text(encoding="utf-8"), "manual\n")
        self.claude.unlink()
        self.bump("9.0.1")
        self.assertEqual(self.context()["entry_rules_updated"]["files"], ["AGENTS.md"])
        self.assertFalse(self.claude.exists())
        newer = self.agents.read_text(encoding="utf-8").replace('"9.0.1"', '"9.9.9"')
        self.claude.write_text(newer, encoding="utf-8")
        self.bump("9.0.2")
        self.assertEqual(self.context()["entry_rules_updated"]["files"], ["AGENTS.md"])
        self.assertEqual(self.claude.read_text(encoding="utf-8"), newer)

    def test_read_only_file_becomes_problem_and_nothing_is_written(self):
        self.bump()
        before = (self.agents.read_bytes(), self.claude.read_bytes())
        os.chmod(self.claude, stat.S_IREAD)
        self.addCleanup(os.chmod, self.claude, stat.S_IREAD | stat.S_IWRITE)
        result = self.context()
        self.assertNotIn("entry_rules_updated", result)
        self.assertTrue(any(item.startswith("入口规则自动更新：") for item in result["problems"]))
        self.assertIn("index", result)  # 其余部分照常返回
        self.assertEqual(before, (self.agents.read_bytes(), self.claude.read_bytes()))

    def test_updated_files_join_ignore_on_commit(self):
        self.bump()
        with patch.object(w, "svn_changelist", return_value=""), \
                patch.object(w, "apply_ignore_on_commit", return_value=["警告"]) as apply:
            updated = self.context()["entry_rules_updated"]
        apply.assert_called_once_with(self.root, ["AGENTS.md", "CLAUDE.md"])
        self.assertEqual(updated["warnings"], ["警告"])

    def test_cli_flag_and_hook_output(self):
        self.bump()
        env = {**os.environ, "USERPROFILE": str(self.base / "家"), "HOME": str(self.base / "家")}
        command = [sys.executable, str(self.skill / "scripts/workspace.py"), "context", "--root", str(self.root),
                   "--global-config", str(self.global_config)]
        skipped = subprocess.run([*command, "--no-entry-update"], capture_output=True, env=env)
        self.assertNotIn("entry_rules_updated", json.loads(skipped.stdout.decode("utf-8")))
        self.assertEqual(self.versions(), [self.initial, self.initial])
        hook = subprocess.run([*command, "--from-hook"], capture_output=True, env=env)
        injected = json.loads(hook.stdout.decode("utf-8"))["hookSpecificOutput"]["additionalContext"]
        self.assertIn('"entry_rules_updated"', injected)
        self.assertEqual(self.versions(), [self.next, self.next])
        rejected = subprocess.run([*command[:2], "clean", *command[3:], "--no-entry-update"],
                                  capture_output=True, env=env)
        self.assertEqual(rejected.returncode, 1)


class EntryTemplateTests(unittest.TestCase):
    def test_templates_import_nothing_but_agents(self):
        """CLAUDE.md 的 @AGENTS.md 会递归引入；规则里提到细则文档只能写普通路径，否则每次会话都被加载。"""
        mention = re.compile(r"(?<![\w`])@[\w~./\\{]")
        managed = (SOURCE / "assets/managed-block.md").read_text(encoding="utf-8")
        self.assertEqual(mention.findall(managed), [])
        claude = (SOURCE / "assets/claude-block.md").read_text(encoding="utf-8")
        self.assertEqual(re.findall(r"(?m)^@.*$", claude), ["@AGENTS.md"])
        self.assertEqual(len(mention.findall(claude)), 1)


if __name__ == "__main__":
    unittest.main()
