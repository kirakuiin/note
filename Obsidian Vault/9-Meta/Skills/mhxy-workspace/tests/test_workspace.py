"""Isolated standard-library tests; never use the real home configuration."""
import codecs
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("workspace", SOURCE / "scripts/workspace.py")
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="mhxy-test-")
        self.base = Path(self.temporary.name).resolve()
        self.root = self.base / "项目 空格"
        self.root.mkdir()
        self.global_config = self.base / "用户配置" / "config.json"
        self.skill = self.base / "安装 空格"
        shutil.copytree(SOURCE, self.skill, ignore=shutil.ignore_patterns("__pycache__"))
        self.values = {key: str(self.root) for key in w.PATH_KEYS}
        self.values["coder_name"] = "test_developer"
        self.assignments = [f"{key}={value}" for key, value in self.values.items()]
        self.agents = self.root / "AGENTS.md"
        self.personal = self.root / w.DIRECTORY
        self.initial_version = json.loads((self.skill / "config/version.json").read_text())["applied_version"]
        major, minor, revision = w.release(self.initial_version)
        self.next_version = f"{major}.{minor}.{revision + 1}"

        # 默认把 svn 视为不可用，避免测试依赖本机 svn；需要时在用例中设置 return_value。
        self.svn_patch = patch.object(w, "svn_local_changes", return_value=None)
        self.svn = self.svn_patch.start()
        self.branch_patch = patch.object(w, "svn_branch", return_value=None)
        self.branch = self.branch_patch.start()
        self.changelist_patch = patch.object(w, "svn_changelist", return_value=None)
        self.changelist = self.changelist_patch.start()

    def tearDown(self):
        self.changelist_patch.stop()
        self.branch_patch.stop()
        self.svn_patch.stop()
        self.temporary.cleanup()

    def sync(self, apply=True, assignments=()):
        return w.sync(self.root, self.global_config, assignments, apply, self.skill)

    def initialize(self):
        return self.sync(assignments=self.assignments)

    def snapshot(self):
        return {str(p.relative_to(self.base)): p.read_bytes() for p in self.base.rglob("*") if p.is_file()}

    def version(self, release=None, schema=2):
        release = release or self.next_version
        (self.skill / "config/version.json").write_text(json.dumps({"skill": w.NAME, "applied_version": release, "schema_version": schema}))

    def test_preview_and_missing_config_never_write(self):
        before = self.snapshot()
        self.assertEqual(len(self.sync(False)["missing_fields"]), 5)
        self.assertEqual(self.sync(False)["optional_fields_to_confirm"], ["openid_password", "openid_username"])
        self.assertEqual(before, self.snapshot())
        with self.assertRaises(w.WorkspaceError):
            self.sync()
        self.assertEqual(before, self.snapshot())

    def test_first_init_accepts_explicit_null_credentials(self):
        assignments = self.assignments + ["openid_username=null", "openid_password=null"]
        result = self.sync(assignments=assignments)
        self.assertEqual(result["missing_fields"], [])
        self.assertEqual(result["optional_fields_to_confirm"], [])
        saved = json.loads(self.global_config.read_text(encoding="utf-8"))
        self.assertIsNone(saved["openid_username"])
        self.assertIsNone(saved["openid_password"])
        self.assertTrue(self.agents.exists())
        self.assertEqual(self.sync()["changes"], [])
        self.assertEqual(self.sync()["optional_fields_to_confirm"], [])

    def test_password_can_be_cleared_without_changing_other_settings(self):
        w.configure_global(self.global_config, ["openid_username=developer@corp.netease.com"], "synthetic-password", True)
        w.configure_global(self.global_config, ["openid_password=null"], apply=True)
        values = w.load_config(self.root, self.global_config)
        self.assertIsNone(values["openid_password"])
        self.assertEqual(values["openid_username"], "developer@corp.netease.com")
        self.assertEqual(values["coder_name"], "developer")

    def test_first_init_and_idempotency(self):
        self.initialize()
        claude = (self.root / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn("\n@AGENTS.md\n", claude)
        self.assertNotIn("### 会话开始", claude)
        self.assertIn("### 会话开始", self.agents.read_text(encoding="utf-8"))
        self.assertEqual(w.block_info(claude)[2], w.block_info(self.agents.read_text(encoding="utf-8"))[2])
        self.assertEqual(json.loads((self.personal / "config.json").read_text()), {})
        self.assertEqual(self.agents.read_text(encoding="utf-8").count(w.BEGIN), 1)
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(self.sync()["changes"], [])
        self.assertEqual(before, {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in before})

    def test_encoding_and_outside_content_preserved(self):
        for encoding, bom in (("utf-8", b""), ("utf-8", codecs.BOM_UTF8),
                              ("utf-16-le", codecs.BOM_UTF16_LE), ("gb18030", b"")):
            with self.subTest(encoding=encoding, bom=bom):
                prefix = "# 人工约定\r\n原文保留\r\n"
                self.agents.write_bytes(bom + prefix.encode(encoding))
                self.initialize()
                suffix = "\r\n# 后置约定\r\n也保留\r\n".encode(encoding)
                self.agents.write_bytes(self.agents.read_bytes() + suffix)
                self.version()
                self.sync()
                self.assertTrue(self.agents.read_bytes().startswith(bom + prefix.encode(encoding)))
                self.assertTrue(self.agents.read_bytes().endswith(suffix))

    def test_upgrade_retains_local_and_regenerates_index(self):
        (self.root / "CLAUDE.md").write_text("manual\n")
        self.initialize()
        local = self.personal / "config.json"
        index = self.personal / "index.md"
        local.write_text('{"pc_client_dir": null}\n')
        index.write_text("手工内容会被覆盖\n", encoding="utf-8")
        self.version()
        result = self.sync()
        self.assertIsNone(result["effective_config"]["pc_client_dir"])
        self.assertNotIn("手工内容", index.read_text(encoding="utf-8"))
        self.assertEqual(local.read_text(), '{"pc_client_dir": null}\n')
        for filename in ("AGENTS.md", "CLAUDE.md"):
            self.assertEqual(w.block_info((self.root / filename).read_text(encoding="utf-8"))[2]["applied_version"], self.next_version)

    def test_explicit_sync_replaces_previous_static_template(self):
        self.initialize()
        text = self.agents.read_text(encoding="utf-8")
        self.agents.write_text(text.replace('"schema_version": 2', '"schema_version": 1'), encoding="utf-8")
        self.sync()
        self.assertEqual(w.block_info(self.agents.read_text(encoding="utf-8"))[2]["schema_version"], 2)
        self.assertFalse((self.personal / "tracking.json").exists())

    def test_sync_reports_entry_rule_changes(self):
        preview = self.sync(False, self.assignments)
        self.assertTrue(preview["entry_rules_changed"])
        self.assertIn("应用后请重新读取", preview["notice"])
        applied = self.initialize()
        self.assertTrue(applied["entry_rules_changed"])
        self.assertNotIn("应用后", applied["notice"])
        unchanged = self.sync()
        self.assertEqual((unchanged["entry_rules_changed"], unchanged["notice"]), (False, ""))
        self.version()
        self.assertTrue(self.sync()["entry_rules_changed"])

    def test_claude_full_block_migrates_to_import(self):
        self.initialize()
        claude = self.root / "CLAUDE.md"
        full_block = self.agents.read_text(encoding="utf-8")
        claude.write_text("# 人工前言\n\n" + full_block + "\n# 人工后记\n", encoding="utf-8")
        self.version()
        self.sync()
        text = claude.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# 人工前言\n\n"))
        self.assertTrue(text.endswith("\n# 人工后记\n"))
        self.assertNotIn("### 会话开始", text)
        self.assertEqual(text.count("@AGENTS.md"), 1)
        self.assertEqual(w.block_info(text)[2]["applied_version"], self.next_version)
        self.assertEqual(self.sync()["changes"], [])

    def test_new_claude_and_moved_installation(self):
        self.initialize()
        (self.root / "CLAUDE.md").write_text("manual\n")
        old = self.skill
        self.skill = self.base / "迁移目录"
        shutil.move(old, self.skill)
        self.sync()
        self.assertIn(self.skill.as_posix(), self.agents.read_text(encoding="utf-8"))
        self.assertEqual(self.sync()["changes"], [])

    def test_claude_follows_agents_metadata_but_refuses_downgrade(self):
        (self.root / "CLAUDE.md").write_text("manual\n")
        self.initialize()
        self.agents.write_text(self.agents.read_text(encoding="utf-8").replace(json.dumps(self.initial_version), '"0.0.9"'), encoding="utf-8")
        self.sync()
        for filename in ("AGENTS.md", "CLAUDE.md"):
            self.assertEqual(w.block_info((self.root / filename).read_text(encoding="utf-8"))[2]["applied_version"], self.initial_version)
        for filename in ("AGENTS.md", "CLAUDE.md"):
            path = self.root / filename
            original = path.read_text(encoding="utf-8")
            path.write_text(original.replace(json.dumps(self.initial_version), '"9.0.0"'), encoding="utf-8")
            before = self.snapshot()
            with self.assertRaisesRegex(w.WorkspaceError, "降级"):
                self.sync()
            self.assertEqual(before, self.snapshot())
            path.write_text(original, encoding="utf-8")

    def test_unknown_schema_and_bad_markers(self):
        self.initialize()
        original = self.agents.read_text(encoding="utf-8")
        for text in (original + w.BEGIN, original.replace(w.END, ""),
                     original.replace(w.END, "同一行人工文字" + w.END),
                     original.replace(w.BEGIN, w.BEGIN + "同行文字"),
                     original.replace('"schema_version": 2', '"schema_version": 99'),
                     original.replace('"schema_version": 2', '"schema_version": true')):
            self.agents.write_text(text, encoding="utf-8")
            before = self.snapshot()
            with self.assertRaises(w.WorkspaceError):
                self.sync()
            self.assertEqual(before, self.snapshot())

    def test_corrupt_config(self):
        self.initialize()
        for value in ('{"pc_client_dir": "relative"}', '{"unexpected": null}', '{"pc_client_dir":null,"pc_client_dir":null}', '{'):
            (self.personal / "config.json").write_text(value)
            with self.assertRaises(w.WorkspaceError):
                self.sync()

    def test_rollback_after_existing_file_write(self):
        (self.root / "CLAUDE.md").write_text("manual\n")
        self.initialize()
        self.version()
        before = self.snapshot()
        original = w.atomic_write
        count = 0

        def fail_second(path, data):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError("simulated disk failure")
            original(path, data)

        with patch.object(w, "atomic_write", side_effect=fail_second):
            with self.assertRaisesRegex(w.WorkspaceError, "已恢复"):
                self.sync()
        self.assertEqual(before, self.snapshot())

    def test_first_init_failure_removes_created_files(self):
        before = self.snapshot()
        original = w.atomic_write

        def fail_agents(path, data):
            if path == self.agents:
                raise OSError("simulated failure")
            original(path, data)

        with patch.object(w, "atomic_write", side_effect=fail_agents):
            with self.assertRaises(w.WorkspaceError):
                self.initialize()
        self.assertEqual(before, self.snapshot())
        self.assertFalse(self.personal.exists())

    def test_clean_preserves_outside_and_reinitialize(self):
        self.initialize()
        (self.root / "spec").mkdir()
        spec_file = self.root / "spec" / "需求.md"
        spec_file.write_text("business spec")
        (self.personal / "nested").mkdir()
        (self.personal / "nested" / "data").write_text("temporary")
        protected = {p: p.read_bytes() for p in (spec_file, self.agents, self.global_config)}
        before = self.snapshot()
        w.clean(self.root, self.global_config)
        self.assertEqual(before, self.snapshot())
        w.clean(self.root, self.global_config, True)
        self.assertTrue(self.personal.is_dir())
        self.assertEqual(list(self.personal.iterdir()), [])
        self.assertEqual(protected, {p: p.read_bytes() for p in protected})
        self.sync()
        self.assertTrue((self.personal / "index.md").exists())
        self.assertEqual(spec_file.read_text(), "business spec")

    def test_global_overlap_rejected(self):
        with self.assertRaisesRegex(w.WorkspaceError, "重叠"):
            w.clean(self.root, self.personal / "config.json", True)

    def test_clean_nonexistent_does_not_create(self):
        w.clean(self.root, self.global_config, True)
        self.assertFalse(self.personal.exists())

    def test_link_rejected_before_any_deletion(self):
        self.initialize()
        outside = self.base / "outside"
        outside.mkdir()
        sentinel = outside / "keep.txt"
        sentinel.write_text("keep")
        link = self.personal / "z-link"
        junction = os.name == "nt"
        if junction:
            result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            link.symlink_to(outside, target_is_directory=True)
        try:
            with self.assertRaisesRegex(w.WorkspaceError, "reparse"):
                w.clean(self.root, self.global_config, True)
            self.assertTrue((self.personal / "index.md").exists())
            self.assertEqual(sentinel.read_text(), "keep")
        finally:
            if junction:
                link.rmdir()
            else:
                link.unlink()

    def test_cli_default_is_preview(self):
        result = subprocess.run([sys.executable, str(self.skill / "scripts/workspace.py"), "sync",
                                 "--root", str(self.root), "--global-config", str(self.global_config)],
                                capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(result.stdout)["applied"])
        self.assertFalse(self.personal.exists())

    def test_cli_global_and_local_parameters_are_deterministic(self):
        command = [sys.executable, str(self.skill / "scripts/workspace.py"), "sync",
                   "--root", str(self.root), "--global-config", str(self.global_config),
                   "--set-local", "pc_client_dir=null"]
        for assignment in self.assignments:
            command.extend(["--set-global", assignment])
        preview = subprocess.run(command, capture_output=True)
        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertFalse(self.global_config.exists())
        self.assertFalse(self.personal.exists())
        applied = subprocess.run(command + ["--apply"], capture_output=True)
        self.assertEqual(applied.returncode, 0, applied.stderr)
        self.assertIsNone(json.loads(applied.stdout)["effective_config"]["pc_client_dir"])
        self.assertEqual(json.loads(self.global_config.read_text(encoding="utf-8")), self.values)
        self.assertEqual(json.loads((self.personal / "config.json").read_text()), {"pc_client_dir": None})
        repeated = subprocess.run(command + ["--apply"], capture_output=True)
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        self.assertEqual(json.loads(repeated.stdout)["changes"], [])

    def test_invalid_local_parameters_write_nothing(self):
        before = self.snapshot()
        for assignment in ("pc_client_dir=relative", "unknown=null", "missing-equals"):
            with self.assertRaises(w.WorkspaceError):
                w.sync(self.root, self.global_config, self.assignments, True, self.skill,
                       local_assignments=[assignment])
            self.assertEqual(before, self.snapshot())

    def write_spec(self, relative, text="# 标题\n正文\n", encoding="utf-8", age=None):
        """写入 spec；age 为秒数时把修改时间设到 age 秒以前（模拟起点之前的旧文件）。"""
        path = self.root / "spec" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode(encoding))
        if age is not None:
            moment = time.time() - age
            os.utime(path, (moment, moment))
        return path

    def index_text(self):
        return (self.personal / "index.md").read_text(encoding="utf-8")

    def members(self):
        return json.loads((self.personal / "index-state.json").read_text(encoding="utf-8"))["specs"]

    def test_init_and_clean_start_with_empty_index(self):
        self.write_spec("他人/旧需求.md", age=3600)
        self.svn.return_value = {"spec/他人/旧需求.md"}
        self.initialize()
        self.assertEqual(self.members(), [])
        self.assertIn("共 0 篇", self.index_text())
        w.clean(self.root, self.global_config, True)
        self.assertEqual(list(self.personal.iterdir()), [])
        result = w.context(self.root, self.global_config)
        self.assertEqual(result["problems"], [])
        self.assertEqual((result["index"]["specs"], result["index"]["updated"]), (0, True))
        self.assertEqual(self.members(), [])
        self.assertFalse((self.personal / "tracking.json").exists())
        self.assertFalse((self.personal / "config.json").exists())

    def test_only_local_changes_after_start_are_collected_and_kept(self):
        self.initialize()
        old_modified = self.write_spec("bugfix/旧但本地改过.md", age=3600)
        mine = self.write_spec("bugfix/新方案.md", "# 新方案\n内容\n")
        self.write_spec("bugfix/他人更新.md")  # svn update 拉下：时间新，但本地无改动
        self.svn.return_value = {"spec/bugfix/旧但本地改过.md", "spec/bugfix/新方案.md"}
        result = w.context(self.root, self.global_config)
        self.assertEqual(result["index"]["svn"], "ok")
        self.assertEqual(self.members(), ["spec/bugfix/新方案.md"])
        self.svn.return_value = set()  # 提交后本地无改动，仍保留在名单中
        self.assertEqual(w.context(self.root, self.global_config)["index"]["specs"], 1)
        self.svn.return_value = None  # svn 不可用时不报错，只是跳过
        self.assertEqual(w.context(self.root, self.global_config)["index"]["svn"], "unavailable")
        mine.unlink()
        self.assertEqual(w.context(self.root, self.global_config)["index"]["specs"], 0)
        self.assertTrue(old_modified.exists())

    def test_manual_add_remove_and_query(self):
        self.write_spec("chat/群聊日志.md", "# 好友群聊加日志\n记录 groupchat 发送\n", age=3600)
        self.write_spec("chat/头像.md", "# at 提醒头像适配\n", age=3600)
        self.initialize()
        result = w.query_index(self.root, self.global_config, add=["spec/chat/群聊日志.md", str(self.root / "spec/chat/头像.md")])
        self.assertEqual(result["index"]["specs"], 2)
        result = w.query_index(self.root, self.global_config, ["CHAT", "日志"])
        self.assertEqual(result["matches"], ["spec/chat/群聊日志.md：好友群聊加日志 — 记录 groupchat 发送"])
        w.query_index(self.root, self.global_config, remove=["spec/chat/头像.md"])
        self.assertEqual(self.members(), ["spec/chat/群聊日志.md"])
        for bad in ("spec/chat/不存在.md", "README.md", "spec/chat/notes.txt", "../spec/x.md"):
            with self.assertRaises(w.WorkspaceError):
                w.query_index(self.root, self.global_config, add=[bad])

    def test_summary_extraction_with_mixed_encodings(self):
        self.initialize()
        root_spec = self.write_spec("根需求.md", "---\nstatus: draft\n---\n# 根需求标题\n\n| a | b |\n\n- **背景**：`func()` 需要修复\n")
        gbk = self.write_spec("520dunhuang/预览.md", "# -*- coding: GB18030 -*-\n# 敦煌预览\n\n## 概述\n\n```\ncode line\n```\n礼盒预览界面的方案。\n", "gb18030")
        plain = self.write_spec("bugfix/deep/fix.md", "无标题，只有正文" + "长" * 80 + "\n")
        self.assertEqual(w.spec_summary(root_spec), ("根需求标题", "背景：func() 需要修复"))
        self.assertEqual(w.spec_summary(gbk), ("敦煌预览", "礼盒预览界面的方案。"))
        title, summary = w.spec_summary(plain)
        self.assertEqual(title, "fix")
        self.assertTrue(summary.endswith("…"))
        w.query_index(self.root, self.global_config, add=["spec/根需求.md", "spec/520dunhuang/预览.md", "spec/bugfix/deep/fix.md"])
        text = self.index_text()
        self.assertIn("共 3 篇", text)
        self.assertIn("# 520dunhuang（1）\n- spec/520dunhuang/预览.md：敦煌预览 — 礼盒预览界面的方案。", text)
        self.assertIn("# bugfix（1）\n- spec/bugfix/deep/fix.md：", text)
        self.assertLess(text.index("# spec 根目录"), text.index("# 520dunhuang"))

    def test_legacy_handwritten_index_is_migrated(self):
        self.write_spec("功能/方案.md", age=3600)
        self.personal.mkdir()
        (self.personal / "index.md").write_text(
            "# 需求1：名称\n描述：一句话。\n- spec/功能/方案.md：说明。\n- spec/已删除.md：说明。\n", encoding="utf-8")
        w.context(self.root, self.global_config)
        self.assertEqual(self.members(), ["spec/功能/方案.md"])
        self.assertTrue(self.index_text().startswith(w.INDEX_HEADER))

    def test_svn_status_parsing(self):
        self.write_spec("改过.md")
        self.write_spec("新目录/a.md")
        self.write_spec("新目录/sub/b.md")
        self.write_spec("没改.md")
        xml = ('<?xml version="1.0" encoding="UTF-8"?><status><target path="spec">'
               '<entry path="spec\\改过.md"><wc-status item="modified"/></entry>'
               '<entry path="spec\\新目录"><wc-status item="unversioned"/></entry>'
               '<entry path="spec\\没改.md"><wc-status item="normal" props="modified"/></entry>'
               '<entry path="spec\\已删.md"><wc-status item="missing"/></entry>'
               '</target></status>').encode("utf-8")
        self.svn_patch.stop()
        try:
            with patch.object(w.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, xml, b"")):
                self.assertEqual(w.svn_local_changes(self.root),
                                 {"spec/改过.md", "spec/新目录/a.md", "spec/新目录/sub/b.md"})
            with patch.object(w.subprocess, "run", side_effect=FileNotFoundError("svn")):
                self.assertIsNone(w.svn_local_changes(self.root))
            with patch.object(w.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, b"", b"E155007")):
                self.assertIsNone(w.svn_local_changes(self.root))
        finally:
            self.svn_patch.start()

    def test_branch_classification(self):
        base = "svn://svn-xyq.gz.netease.com/svn/products/xy1/develop/client/wzimage"
        cases = {f"{base}/trunk": "trunk",
                 f"{base}/branchs/2026_ship/test_2026_10_13": "周期分支",
                 "https://svn-xyq.gz.netease.com/svn/products/xy1/develop/client/wzimage/branchs/2026_ship/release2_2026_07_21": "周期分支",
                 f"{base}/branchs/2026_ship/release3_2026_07_21/": "周期分支",
                 f"{base}/branchs/2026_dev/hxw_fullscreen_war_0920": "研发分支",
                 f"{base}/branchs/2026_ship/hotfix_2026_07_21": "研发分支",
                 f"{base}/branchs/2026_dev/trunk_copy": "研发分支"}
        for url, kind in cases.items():
            self.assertEqual(w.classify_branch(url), kind, url)
        self.assertEqual(w.branch_path(f"{base}/branchs/2026_ship/release3_2026_07_21/"), "branchs/2026_ship/release3_2026_07_21")
        self.assertEqual(w.branch_path(f"{base}/trunk"), "trunk")
        self.assertIsNone(w.branch_path("svn://example.invalid/other/trunk"))
        self.branch_patch.stop()
        try:
            with patch.object(w.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, (base + "/trunk" + chr(10)).encode(), b"")):
                self.assertEqual(w.svn_branch(self.root), {"url": base + "/trunk", "name": "trunk", "path": "trunk", "kind": "trunk"})
            with patch.object(w.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, b"", b"E155007")):
                self.assertIsNone(w.svn_branch(self.root))
        finally:
            self.branch = self.branch_patch.start()

    def test_context_lists_branch_and_recent_specs_then_clean_clears_them(self):
        self.initialize()
        self.branch.return_value = {"url": "u", "name": "test_2026_10_13", "kind": "周期分支"}
        older = self.write_spec("a/旧.md", "# 旧方案" + chr(10))
        newer = self.write_spec("b/新.md", "# 新方案" + chr(10))
        os.utime(older, (time.time() - 100, time.time() - 100))
        w.query_index(self.root, self.global_config, add=["spec/a/旧.md", "spec/b/新.md"])
        result = w.context(self.root, self.global_config)
        self.assertEqual(result["branch"]["kind"], "周期分支")
        self.assertEqual(result["index"]["recent"], ["spec/b/新.md：新方案", "spec/a/旧.md：旧方案"])
        w.clean(self.root, self.global_config, True)
        result = w.context(self.root, self.global_config)
        self.assertEqual(result["index"]["recent"], [])
        self.assertEqual(result["branch"]["name"], "test_2026_10_13")
        self.assertTrue(newer.exists() and older.exists())

    def test_versioned_entry_files_go_to_ignore_on_commit(self):
        (self.root / "CLAUDE.md").write_text("manual" + chr(10))
        states = {"AGENTS.md": "", "CLAUDE.md": None}
        self.changelist.side_effect = lambda root, name: states[name]
        self.assertEqual(self.sync(False, self.assignments)["ignore_on_commit"], [])  # AGENTS.md 尚不存在
        self.agents.write_text("# 团队规范" + chr(10), encoding="utf-8")
        preview = self.sync(False, self.assignments)
        self.assertEqual(preview["ignore_on_commit"], ["AGENTS.md"])
        with patch.object(w, "apply_ignore_on_commit", return_value=[]) as applied:
            self.initialize()
        applied.assert_called_once_with(self.root, ["AGENTS.md"])
        states["AGENTS.md"] = w.IGNORE_ON_COMMIT
        self.assertEqual(self.sync()["ignore_on_commit"], [])
        states["AGENTS.md"] = "我的列表"
        result = self.sync()
        self.assertEqual(result["ignore_on_commit"], [])
        self.assertTrue(any("我的列表" in warning for warning in result["warnings"]))

    def test_ignore_on_commit_failures_only_warn(self):
        self.agents.write_text("# 团队规范" + chr(10), encoding="utf-8")
        self.changelist.side_effect = w.WorkspaceError("svn 不可用")
        result = self.initialize()
        self.assertTrue(result["applied"])
        self.assertTrue(any("svn 不可用" in warning for warning in result["warnings"]))
        self.changelist.side_effect = None
        self.changelist.return_value = ""
        with patch.object(w.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, b"", b"E1")):
            result = self.sync()
        self.assertTrue(any("E1" in warning for warning in result["warnings"]))
        with patch.object(w.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, b"", b"")) as run:
            self.assertEqual(w.apply_ignore_on_commit(self.root, ["AGENTS.md"]), [])
        self.assertEqual(run.call_args.args[0][:3], ["svn", "changelist", w.IGNORE_ON_COMMIT])

    def test_svn_changelist_query(self):
        self.changelist_patch.stop()
        try:
            for completed, expected in ((subprocess.CompletedProcess([], 0, b"ignore-on-commit" + bytes([13, 10]), b""), "ignore-on-commit"),
                                        (subprocess.CompletedProcess([], 0, b"", b""), ""),
                                        (subprocess.CompletedProcess([], 1, b"", b"svn: warning: W155010: not found"), None),
                                        (subprocess.CompletedProcess([], 1, b"", b"svn: E155007: not a working copy"), None)):
                with patch.object(w.subprocess, "run", return_value=completed):
                    self.assertEqual(w.svn_changelist(self.root, "AGENTS.md"), expected)
            with patch.object(w.subprocess, "run", side_effect=FileNotFoundError("svn")):
                with self.assertRaises(w.WorkspaceError):
                    w.svn_changelist(self.root, "AGENTS.md")
        finally:
            self.changelist = self.changelist_patch.start()

    def test_context_reports_problems_without_failing(self):
        self.initialize()
        (self.personal / "tracking.json").write_text("{", encoding="utf-8")
        result = w.context(self.root, self.global_config)
        self.assertTrue(any(p.startswith("追踪") for p in result["problems"]))
        self.assertIn("effective_config", result)
        self.assertIn("index", result)

    def test_claude_hooks_are_merged_and_idempotent(self):
        settings = self.root / ".claude/settings.local.json"
        settings.parent.mkdir()
        other = {"type": "command", "command": "echo other"}
        settings.write_text(json.dumps({"permissions": {"allow": ["Bash(svn status)"]},
                                        "hooks": {"SessionStart": [{"hooks": [other]}],
                                                  "Stop": [{"hooks": [other]}]}}), encoding="utf-8")
        self.initialize()
        value = json.loads(settings.read_text(encoding="utf-8"))
        self.assertEqual(value["permissions"], {"allow": ["Bash(svn status)"]})
        self.assertEqual(value["hooks"]["Stop"], [{"hooks": [other]}])
        session = value["hooks"]["SessionStart"]
        self.assertEqual(session[0], {"hooks": [other]})
        self.assertIn('workspace.py" context --root', session[1]["hooks"][0]["command"])
        post = value["hooks"]["PostToolUse"]
        self.assertEqual(post[0]["matcher"], "Write|Edit|MultiEdit")
        self.assertIn('workspace.py" index --root', post[0]["hooks"][0]["command"])
        self.assertIn(w.HOOK_FLAG, post[0]["hooks"][0]["command"])
        self.assertEqual(self.sync()["changes"], [])
        old = self.skill
        self.skill = self.base / "迁移目录"
        shutil.move(old, self.skill)
        self.sync()
        value = json.loads(settings.read_text(encoding="utf-8"))
        self.assertEqual((len(value["hooks"]["SessionStart"]), len(value["hooks"]["PostToolUse"])), (2, 1))
        self.assertIn(self.skill.as_posix(), value["hooks"]["PostToolUse"][0]["hooks"][0]["command"])

    def test_write_hook_records_spec_and_ignores_others(self):
        self.initialize()
        spec = self.write_spec("新功能/方案.md", age=3600)  # hook 收录不受起点限制
        outside = self.root / "gameplay.py"
        outside.write_text("x = 1\n")
        w.record_hook_write(self.root, self.global_config, {"tool_input": {"file_path": str(outside)}})
        w.record_hook_write(self.root, self.global_config, {"tool_name": "Bash", "tool_input": {"command": "ls"}})
        self.assertEqual(self.members(), [])
        w.record_hook_write(self.root, self.global_config, {"tool_input": {"file_path": str(spec).upper()}})
        self.assertEqual(self.members(), ["spec/新功能/方案.md"])

    def test_hooks_never_fail_the_session(self):
        self.initialize()
        script = self.skill / "scripts/workspace.py"
        for root in (self.root, self.base / "不存在"):
            completed = subprocess.run([sys.executable, str(script), "context", "--root", str(root),
                                        "--global-config", str(self.global_config), w.HOOK_FLAG], capture_output=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            output = json.loads(completed.stdout)["hookSpecificOutput"]
            self.assertEqual(output["hookEventName"], "SessionStart")
            self.assertIn("mhxy-workspace context", output["additionalContext"])
            for stdin in (b"not json", json.dumps({"tool_input": {"file_path": str(root / "spec/x.md")}}).encode()):
                completed = subprocess.run([sys.executable, str(script), "index", "--root", str(root),
                                            "--global-config", str(self.global_config), w.HOOK_FLAG],
                                           input=stdin, capture_output=True)
                self.assertEqual((completed.returncode, completed.stdout), (0, b""), completed.stderr)

    def test_coverage_identity_survives_sync_but_clean_resets_without_touching_entries(self):
        (self.root / "CLAUDE.md").write_text("manual\n")
        self.initialize()
        task = {"task_name": "unit_task", "branch": "branchs/dev/example", "redmine_id": "123",
                "coder_name": "test_developer", "created": True}
        before = self.snapshot()
        w.record_coverage_task(self.root, self.global_config, task)
        self.assertEqual(before, self.snapshot())
        w.record_coverage_task(self.root, self.global_config, task, True)
        self.assertEqual(w.read_tracking(self.personal)[2]["coverage_tasks"], [task])
        for filename in ("AGENTS.md", "CLAUDE.md"):
            self.assertNotIn("unit_task", (self.root / filename).read_text(encoding="utf-8"))
        self.version()
        self.sync()
        self.assertEqual(w.read_tracking(self.personal)[2]["coverage_tasks"], [task])
        self.assertEqual(w.record_coverage_task(self.root, self.global_config, task, True)["changes"], [])
        entries = {name: (self.root / name).read_bytes() for name in ("AGENTS.md", "CLAUDE.md")}
        w.clean(self.root, self.global_config, True)
        self.assertEqual(w.read_tracking(self.personal)[2]["coverage_tasks"], [])
        self.assertEqual(entries, {name: (self.root / name).read_bytes() for name in entries})

    def test_coverage_conflict_and_invalid_identity_do_not_write(self):
        (self.root / "CLAUDE.md").write_text("manual\n")
        self.initialize()
        before = self.snapshot()
        with self.assertRaises(w.WorkspaceError):
            w.record_coverage_task(self.root, self.global_config, {"created": True}, True)
        self.assertEqual(before, self.snapshot())
        task = {"task_name": "unit_task", "branch": "branchs/dev/example", "redmine_id": "123",
                "coder_name": "test_developer", "created": True}
        w.record_coverage_task(self.root, self.global_config, task, True)
        (self.personal / "tracking.json").write_text('{"tracked_tasks": [], "coverage_tasks": [null]}')
        before = self.snapshot()
        with self.assertRaises(w.WorkspaceError):
            w.record_coverage_task(self.root, self.global_config, task, True)
        self.assertEqual(before, self.snapshot())

    def test_coder_name_optional_and_not_a_directory(self):
        old_assignments = [item for item in self.assignments if not item.startswith("coder_name=")]
        result = self.sync(assignments=old_assignments)
        self.assertEqual(result["missing_fields"], [])
        self.assertIsNone(result["effective_config"]["coder_name"])
        result = self.sync(assignments=["coder_name=developer.name"])
        self.assertEqual(result["warnings"], [])
        with self.assertRaises(w.WorkspaceError):
            self.sync(assignments=["coder_name=bad/name"])

    def test_global_credentials_derive_coder_and_stay_masked(self):
        secret = "synthetic-secret-for-test"
        before = self.snapshot()
        assignments = ["openid_username=developer@corp.netease.com"]
        preview = w.configure_global(self.global_config, assignments, secret)
        self.assertEqual(before, self.snapshot())
        self.assertNotIn(secret, json.dumps(preview))
        result = w.configure_global(self.global_config, assignments, secret, True)
        self.assertFalse(self.agents.exists())
        self.assertFalse(self.personal.exists())
        self.assertEqual(result["effective_config"]["coder_name"], "developer")
        self.assertEqual(result["effective_config"]["openid_password"], "***")
        self.assertEqual(w.load_config(self.root, self.global_config)["openid_password"], secret)
        result = w.sync(self.root, self.global_config, [f"{key}={self.root}" for key in self.values if key != "coder_name"], True, self.skill)
        self.assertNotIn(secret, json.dumps(result))
        self.assertNotIn(secret, self.agents.read_text(encoding="utf-8"))
        self.assertEqual(result["warnings"], [])
        self.assertEqual(self.sync()["changes"], [])

    def test_coder_override_and_account_change(self):
        self.assertEqual(w.effective_values({"openid_username": "a@corp.netease.com"}, {})["coder_name"], "a")
        self.assertEqual(w.effective_values({"openid_username": "b@corp.netease.com"}, {})["coder_name"], "b")
        self.assertEqual(w.effective_values({"openid_username": "a@corp.netease.com", "coder_name": "global"}, {"coder_name": "local"})["coder_name"], "local")
        self.assertEqual(w.effective_values({"openid_username": "a@corp.netease.com", "coder_name": "global"}, {"coder_name": None})["coder_name"], "a")
        with self.assertRaises(w.WorkspaceError):
            w.effective_values({}, {"openid_password": "synthetic-secret"})
        changed = w.apply_settings({"openid_username": "old@corp.netease.com", "openid_password": "synthetic-secret"}, ["openid_username=new@corp.netease.com"], "--set-global")
        self.assertNotIn("openid_password", changed)

    def test_config_rejects_command_line_password_without_echo(self):
        secret = "synthetic-secret-for-test"
        with self.assertRaises(w.WorkspaceError) as result:
            w.configure_global(self.global_config, ["openid_password=" + secret], apply=True)
        self.assertNotIn(secret, str(result.exception))
        self.assertFalse(self.global_config.exists())

    def test_coverage_write_failure_preserves_previous_state(self):
        (self.root / "CLAUDE.md").write_text("manual\n")
        self.initialize()
        task = {"task_name": "unit_task", "branch": "branchs/dev/example", "redmine_id": "123",
                "coder_name": "test_developer", "created": True}
        before = self.snapshot()
        original_write = w.atomic_write

        def fail_tracking(path, data):
            if path.name == "tracking.json":
                raise OSError("injected write failure")
            return original_write(path, data)

        with patch.object(w, "atomic_write", fail_tracking):
            with self.assertRaises(w.WorkspaceError):
                w.record_coverage_task(self.root, self.global_config, task, True)
        self.assertEqual(before, self.snapshot())

    def test_legacy_name_updates_in_place(self):
        self.initialize()
        original = self.agents.read_text(encoding="utf-8")
        legacy = original.replace(w.NAME + ":", w.LEGACY_NAME + ":").replace(
            '"skill": "' + w.NAME + '"', '"skill": "' + w.LEGACY_NAME + '"')
        self.agents.write_text(legacy, encoding="utf-8")
        self.sync()
        current = self.agents.read_text(encoding="utf-8")
        self.assertEqual(current, original)
        self.assertEqual(self.sync()["changes"], [])
        self.agents.write_text(current + legacy, encoding="utf-8")
        with self.assertRaisesRegex(w.WorkspaceError, "同时存在"):
            self.sync()


if __name__ == "__main__":
    unittest.main()
