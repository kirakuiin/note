"""svn_update.py 的测试：全部在临时仓库和临时工作副本上进行。"""
from datetime import date
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import svn_fixture  # noqa: E402

spec = importlib.util.spec_from_file_location("svn_update_under_test", SOURCE / "scripts/svn_update.py")
u = importlib.util.module_from_spec(spec)
spec.loader.exec_module(u)

BLOCK = ("<!-- mhxy-workspace:begin -->\n### 管理元数据\n```json\n"
         '{"skill": "mhxy-workspace", "applied_version": "0.3.31", "schema_version": 2}\n```\n'
         "<!-- mhxy-workspace:end -->\n")
SHIP = "wzimage/branchs/2026_ship"


class DateTests(unittest.TestCase):
    def test_next_maintenance_day(self):
        self.assertEqual(u.next_maintenance_day(date(2026, 11, 9)), date(2026, 11, 10))   # 周一 → 次日
        self.assertEqual(u.next_maintenance_day(date(2026, 11, 10)), date(2026, 11, 17))  # 周二当天 → 下周二
        self.assertEqual(u.next_maintenance_day(date(2026, 11, 11)), date(2026, 11, 17))
        self.assertEqual(u.next_maintenance_day(date(2026, 12, 30)), date(2027, 1, 5))    # 跨年


@svn_fixture.requires_svn
class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="mhxy-update-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.repository = svn_fixture.Repository(self.base)
        self.repository.import_tree({"a.py": "A = 1\n", "b.py": "B = 1\n", "sub/c.py": "C = 1\n",
                                     "AGENTS.md": "# 团队规范\n"}, "wzimage/trunk")
        self.repository.import_tree({"ui/x.txt": "x\n"}, "res/trunk")
        self.config = self.base / "config.json"
        self.stamp = 0

    def checkout(self, source="wzimage/trunk", resource=True):
        self.root = self.repository.checkout(source, self.base / "ws/mhimage")
        agents = self.root / "AGENTS.md"
        agents.write_text(agents.read_text(encoding="utf-8") + "\n" + BLOCK, encoding="utf-8")
        (self.root / ".mhxy-workspace").mkdir()
        if resource:
            self.resource = self.repository.checkout("res/trunk", self.base / "ws/_test")
        return self.root

    def update(self, **kwargs):
        self.stamp += 1
        kwargs.setdefault("stamp", f"20261110-12000{self.stamp}")
        return u.update(self.root, self.config, **kwargs)

    def text(self, relative):
        return (self.root / relative).read_text(encoding="utf-8")

    def status(self):
        return svn_fixture.svn("status", cwd=self.root).stdout.decode("utf-8", "replace")

    def patch_text(self, result):
        return self.backup(result, "local-changes.patch").read_bytes().decode("utf-8", "replace")

    def backup(self, result, *parts):
        return Path(result["backup_dir"]).joinpath(self.root.name, *parts)

    def test_plain_update_keeps_local_changes_and_updates_resources(self):
        self.checkout()
        (self.root / "b.py").write_text("B = 'local'\n")
        (self.root / "loose.txt").write_text("mine\n")
        self.repository.commit_through("wzimage/trunk", {"a.py": "A = 2\n", "new.py": "N = 1\n"})
        self.repository.commit_through("res/trunk", {"ui/x.txt": "x2\n"})
        result = self.update()
        self.assertEqual(result["status"], "success")
        code, resource = result["working_copies"]
        self.assertEqual((code["operation"], code["status"], code["target"]["reason"]),
                         ("update", "updated", "不是周期分支，保持当前分支"))
        self.assertGreater(code["after"]["revision"], code["before"]["revision"])
        self.assertEqual((self.text("a.py"), self.text("b.py"), self.text("loose.txt")),
                         ("A = 2\n", "B = 'local'\n", "mine\n"))
        self.assertEqual(code["handled"], {"cleanup": False, "reverted": [], "conflicts_resolved": [],
                                           "moved_unversioned": []})
        self.assertIn("B = 'local'", self.patch_text(result))  # 有本地修改就先备份
        self.assertEqual((resource["name"], resource["status"]), ("_test", "updated"))
        self.assertEqual((self.resource / "ui/x.txt").read_text(), "x2\n")
        self.assertIn("mhxy-workspace:begin", self.text("AGENTS.md"))

    def test_clean_working_copy_makes_no_backup(self):
        self.checkout(resource=False)
        svn_fixture.svn("changelist", "ignore-on-commit", "AGENTS.md", cwd=self.root)
        svn_fixture.svn("revert", "AGENTS.md", cwd=self.root)
        (self.root / "AGENTS.md").write_text("# 团队规范\n\n" + BLOCK, encoding="utf-8")
        result = self.update(code_only=True)
        self.assertEqual(result["status"], "success")
        self.assertEqual(len(result["working_copies"]), 1)
        # AGENTS.md 的受管区段本身是本地修改，会备份成 patch，但不被还原
        self.assertIn("mhxy-workspace:begin", self.text("AGENTS.md"))

    def test_missing_resource_is_skipped(self):
        self.checkout(resource=False)
        result = self.update()
        self.assertIn("跳过资源更新", result["resource_skipped"])
        self.assertEqual(len(result["working_copies"]), 1)

    def test_conflict_takes_server_version_and_backs_up_local(self):
        self.checkout(resource=False)
        (self.root / "a.py").write_text("A = 'local'\n")
        (self.root / "b.py").write_text("B = 'kept'\n")
        self.repository.commit_through("wzimage/trunk", {"a.py": "A = 'server'\n"})
        result = self.update()
        code = result["working_copies"][0]
        self.assertEqual((result["status"], code["handled"]["conflicts_resolved"], code["conflicts"]),
                         ("success", ["a.py"], []))
        self.assertEqual((self.text("a.py"), self.text("b.py")), ("A = 'server'\n", "B = 'kept'\n"))
        self.assertIn("A = 'local'", self.patch_text(result))
        self.assertTrue(self.backup(result, "files", "a.py").is_file())
        self.assertEqual([p.name for p in self.root.glob("a.py.*")], [])  # 没有残留的 .mine／.rN
        self.assertNotIn("C ", self.status())

    def test_tree_conflict_follows_server_delete(self):
        self.checkout(resource=False)
        (self.root / "a.py").write_text("A = 'local'\n")
        self.repository.commit_through("wzimage/trunk", {}, deletes=["a.py"])
        result = self.update()
        code = result["working_copies"][0]
        self.assertEqual((result["status"], code["conflicts"]), ("success", []))
        self.assertEqual(code["handled"]["conflicts_resolved"], ["a.py"])
        self.assertFalse((self.root / "a.py").exists())
        self.assertEqual(self.backup(result, "files", "a.py").read_text(), "A = 'local'\n")

    def test_unversioned_file_blocking_an_add_is_moved_to_backup(self):
        self.checkout(resource=False)
        (self.root / "new.py").write_text("LOCAL = 1\n")
        (self.root / "same.py").write_bytes(b"S = 1\n")  # 与服务器内容逐字节相同
        (self.root / "newdir").mkdir()
        (self.root / "newdir/inner.py").write_text("LOCAL = 2\n")
        (self.root / "newdir/other.txt").write_text("stay\n")
        self.repository.commit_through("wzimage/trunk", {"new.py": "SERVER = 1\n", "same.py": "S = 1\n",
                                                         "newdir/inner.py": "SERVER = 2\n"})
        result = self.update()
        code = result["working_copies"][0]
        self.assertEqual(result["status"], "success")
        self.assertEqual(sorted(code["handled"]["moved_unversioned"]), ["new.py", "newdir/inner.py"])
        self.assertEqual((self.text("new.py"), self.text("newdir/inner.py"), self.text("newdir/other.txt")),
                         ("SERVER = 1\n", "SERVER = 2\n", "stay\n"))
        self.assertEqual(self.backup(result, "files", "new.py").read_text(), "LOCAL = 1\n")
        self.assertEqual(self.backup(result, "files", "newdir", "inner.py").read_text(), "LOCAL = 2\n")
        self.assertFalse(self.backup(result, "files", "same.py").exists())  # 内容相同，不算挡路

    def test_unversioned_directory_blocking_a_file_is_backed_up(self):
        """svn 把“未纳管目录挡住新增文件”报成树冲突，按冲突处理：备份本地目录，换成服务器的文件。"""
        self.checkout(resource=False)
        (self.root / "thing").mkdir()
        (self.root / "thing/keep.txt").write_text("local\n")
        self.repository.commit_through("wzimage/trunk", {"thing": "now a file\n"})
        result = self.update()
        code = result["working_copies"][0]
        self.assertEqual((result["status"], code["handled"]["conflicts_resolved"], code["conflicts"]),
                         ("success", ["thing"], []))
        self.assertEqual(self.text("thing"), "now a file\n")
        self.assertEqual(self.backup(result, "files", "thing", "keep.txt").read_text(), "local\n")

    def test_failed_revert_never_deletes_local_content(self):
        self.checkout(resource=False)
        (self.root / "thing").mkdir()
        (self.root / "thing/keep.txt").write_text("local\n")
        self.repository.commit_through("wzimage/trunk", {"thing": "now a file\n"})
        failed = subprocess.CompletedProcess([], 1, b"", b"svn: E155010: revert refused")
        real = u.svn
        with patch.object(u, "svn", side_effect=lambda cwd, *args, **kw: failed if args[0] == "revert" else real(cwd, *args, **kw)):
            result = self.update()
        code = result["working_copies"][0]
        self.assertEqual((result["status"], code["conflicts"], code["handled"]["conflicts_resolved"]),
                         ("failed", ["thing"], []))
        self.assertIn("revert refused", code["errors"][0])
        self.assertEqual(self.text("thing/keep.txt"), "local\n")  # 还原失败后不再删除

    def test_unbackupable_link_is_left_alone(self):
        self.checkout(resource=False)
        (self.root / "a.py").write_text("A = 'local'\n")
        self.repository.commit_through("wzimage/trunk", {"a.py": "A = 'server'\n"})
        real = u.workspace.is_link
        with patch.object(u.workspace, "is_link", side_effect=lambda path: Path(path).name == "a.py" or real(path)):
            result = self.update()
        code = result["working_copies"][0]
        self.assertEqual((code["status"], code["conflicts"]), ("failed", ["a.py"]))
        self.assertIn("无法备份", code["errors"][0])
        self.assertIn("A = 'local'", self.text("a.py"))  # 没有备份就不采用服务器版本

    def test_tree_conflict_on_local_helper_directory_is_not_touched(self):
        self.checkout(resource=False)
        (self.root / ".claude").mkdir()
        (self.root / ".claude/settings.local.json").write_text("{}")
        self.repository.commit_through("wzimage/trunk", {".claude": "a file upstream\n"})
        result = self.update()
        code = result["working_copies"][0]
        self.assertEqual((code["status"], code["conflicts"]), ("failed", [".claude"]))
        self.assertIn("不自动处理", code["errors"][0])
        self.assertEqual(self.text(".claude/settings.local.json"), "{}")

    def test_backup_never_overwrites_and_take_renames(self):
        self.checkout(resource=False)
        backup = u.Backup(self.root / ".mhxy-workspace", "20261110-130000")
        (self.root / "a.py").write_text("first\n")
        backup.save("wc", self.root, "a.py")
        (self.root / "a.py").write_text("second\n")
        backup.save("wc", self.root, "a.py")
        backup.take("wc", self.root, "a.py")
        files = backup.base / "wc/files"
        self.assertEqual(((files / "a.py").read_text(), (files / "a.py.2").read_text()), ("first\n", "second\n"))
        self.assertFalse((self.root / "a.py").exists())
        backup.save("wc", self.root, "missing.py")  # 本地不存在：没有可备份的，不报错

    def test_locked_working_copy_is_cleaned_up(self):
        self.checkout(resource=False)
        import sqlite3
        database = sqlite3.connect(self.root / ".svn/wc.db")
        database.execute("insert into wc_lock (wc_id, local_dir_relpath, locked_levels) values (1, '', -1)")
        database.commit()
        database.close()
        self.repository.commit_through("wzimage/trunk", {"a.py": "A = 2\n"})
        result = self.update()
        self.assertEqual(result["status"], "success")
        self.assertTrue(result["working_copies"][0]["handled"]["cleanup"])
        self.assertEqual(self.text("a.py"), "A = 2\n")

    def test_clean_blockers_reverts_everything_but_entry_files(self):
        self.checkout(resource=False)
        (self.root / "a.py").write_text("A = 'local'\n")
        (self.root / "sub/c.py").unlink()
        svn_fixture.svn("delete", "b.py", cwd=self.root)
        (self.root / "added").mkdir()
        (self.root / "added/n.py").write_text("N = 1\n")
        svn_fixture.svn("add", "added", cwd=self.root)
        (self.root / "loose.txt").write_text("mine\n")
        self.repository.commit_through("wzimage/trunk", {"a.py": "A = 'server'\n"})
        result = self.update(clean_blockers=True)
        code = result["working_copies"][0]
        self.assertEqual((result["mode"], result["status"]), ("clean-blockers", "success"))
        self.assertEqual(code["handled"]["reverted"], ["a.py", "added", "b.py"])
        self.assertEqual((self.text("a.py"), self.text("b.py"), self.text("sub/c.py"), self.text("loose.txt")),
                         ("A = 'server'\n", "B = 1\n", "C = 1\n", "mine\n"))
        self.assertIn("mhxy-workspace:begin", self.text("AGENTS.md"))  # 入口文件不还原
        self.assertEqual(self.text("added/n.py"), "N = 1\n")  # 还原后留在原地成为未纳管文件
        patch_text = self.patch_text(result)
        self.assertIn("A = 'local'", patch_text)
        self.assertEqual(self.backup(result, "files", "a.py").read_text(), "A = 'local'\n")
        self.assertEqual(self.backup(result, "files", "added", "n.py").read_text(), "N = 1\n")
        changed = [line for line in self.status().splitlines() if line[:1] in "MADRC"]
        self.assertEqual([line.split()[-1] for line in changed], ["AGENTS.md"])

    def test_entry_file_conflict_restores_managed_block(self):
        self.checkout(resource=False)
        self.repository.commit_through("wzimage/trunk", {"AGENTS.md": "# 团队规范\n\n## 新增一节\n"})
        with patch.object(u.workspace, "sync") as sync:
            result = self.update()
        sync.assert_called_once_with(self.root, self.config, apply=True)
        code = result["working_copies"][0]
        self.assertEqual(code["handled"]["conflicts_resolved"], ["AGENTS.md"])
        self.assertIn("受管区段丢失，已重新写入", code["notes"][0])
        self.assertIn("mhxy-workspace:begin", self.backup(result, "files", "AGENTS.md").read_text(encoding="utf-8"))

    def test_dry_run_changes_nothing(self):
        self.checkout()
        (self.root / "a.py").write_text("A = 'local'\n")
        self.repository.commit_through("wzimage/trunk", {"a.py": "A = 'server'\n"})
        result = self.update(dry_run=True)
        self.assertEqual((result["status"], result["backup_dir"]), ("planned", None))
        self.assertEqual([item["status"] for item in result["working_copies"]], ["planned", "planned"])
        self.assertEqual(result["working_copies"][0]["local_changes"], 2)  # a.py 和 AGENTS.md
        self.assertEqual(self.text("a.py"), "A = 'local'\n")
        self.assertFalse((self.root / ".mhxy-workspace/backups").exists())

    def test_backups_keep_latest_five(self):
        self.checkout(resource=False)
        for number in range(7):
            (self.root / "b.py").write_text(f"B = {number + 10}\n")
            self.update(stamp=f"20261110-12000{number}")
        (self.root / ".mhxy-workspace/backups/notes").mkdir()
        self.update(stamp="20261110-120009")
        names = sorted(item.name for item in (self.root / ".mhxy-workspace/backups").iterdir())
        self.assertEqual(len([name for name in names if u.BACKUP_NAME.match(name)]), u.BACKUP_KEEP)
        self.assertIn("notes", names)
        self.assertIn("20261110-120009", names)
        self.assertNotIn("20261110-120000", names)

    def periodic(self, *days):
        for day in days:
            self.repository.copy("wzimage/trunk", f"{SHIP}/test_{day}")

    def test_periodic_switches_to_target_week(self):
        self.periodic("2026_11_10", "2026_11_17", "2026_11_24")
        self.repository.copy("wzimage/trunk", f"{SHIP}/release_2026_11_17")
        self.repository.commit_through(f"{SHIP}/test_2026_11_17", {"a.py": "A = 'week17'\n"})
        self.checkout(f"{SHIP}/test_2026_11_10", resource=False)
        (self.root / "b.py").write_text("B = 'kept'\n")
        result = self.update(today=date(2026, 11, 12))
        code = result["working_copies"][0]
        self.assertEqual((result["status"], code["operation"]), ("success", "switch"))
        self.assertEqual((code["before"]["branch"], code["after"]["branch"]), ("test_2026_11_10", "test_2026_11_17"))
        self.assertEqual(code["target"]["reason"], "目标维护周 test_2026_11_17")
        self.assertEqual((self.text("a.py"), self.text("b.py")), ("A = 'week17'\n", "B = 'kept'\n"))

    def test_periodic_target_not_published(self):
        self.periodic("2026_11_03", "2026_11_10", "2026_11_24")
        self.checkout(f"{SHIP}/test_2026_11_03", resource=False)
        result = self.update(today=date(2026, 11, 12))  # 目标 11-17 未发布：切到 11-10，不跳到 11-24
        code = result["working_copies"][0]
        self.assertEqual((code["operation"], code["after"]["branch"]), ("switch", "test_2026_11_10"))
        self.assertIn("尚未发布，切到已发布的最新分支 test_2026_11_10", code["target"]["reason"])
        result = self.update(today=date(2026, 11, 12))  # 已在最新：原地更新，不退回旧周
        code = result["working_copies"][0]
        self.assertEqual((code["operation"], code["after"]["branch"]), ("update", "test_2026_11_10"))
        self.assertIn("保持当前分支", code["target"]["reason"])

    def test_shiwan_stays_unless_advance(self):
        for day in ("2026_11_10", "2026_11_17"):
            self.repository.copy("wzimage/trunk", f"{SHIP}/shiwan_{day}")
        self.checkout(f"{SHIP}/shiwan_2026_11_10", resource=False)
        result = self.update(today=date(2026, 11, 12))   # 试玩分支默认原地更新
        code = result["working_copies"][0]
        self.assertEqual((code["operation"], code["after"]["branch"]), ("update", "shiwan_2026_11_10"))
        self.assertIn("--advance", code["target"]["reason"])
        result = self.update(today=date(2026, 11, 12), advance=True)   # 明确要求才切到下一个维护周
        code = result["working_copies"][0]
        self.assertEqual((code["operation"], code["after"]["branch"]), ("switch", "shiwan_2026_11_17"))

    def test_periodic_crosses_year(self):
        self.periodic("2026_12_29")
        self.repository.copy("wzimage/trunk", "wzimage/branchs/2027_ship/test_2027_01_05")
        self.checkout(f"{SHIP}/test_2026_12_29", resource=False)
        result = self.update(today=date(2026, 12, 30))
        self.assertTrue(result["working_copies"][0]["after"]["url"].endswith("/2027_ship/test_2027_01_05"))

    def test_remote_listing_failure_is_not_treated_as_missing(self):
        self.periodic("2026_11_10")
        self.checkout(f"{SHIP}/test_2026_11_10", resource=False)
        failed = subprocess.CompletedProcess([], 1, b"", b"svn: E170013: Unable to connect to a repository")
        real = u.svn
        with patch.object(u, "svn", side_effect=lambda cwd, *args, **kw: failed if args[0] == "list" else real(cwd, *args, **kw)):
            result = self.update(today=date(2026, 11, 12))
        code = result["working_copies"][0]
        self.assertEqual((result["status"], code["status"]), ("failed", "failed"))
        self.assertIn("无法列出远端分支", code["errors"][0])
        self.assertEqual(code["after"]["branch"], "test_2026_11_10")

    def test_external_failure_is_partial(self):
        self.checkout(resource=False)
        failed = subprocess.CompletedProcess([], 1, b"", b"svn: warning: W205011: Error handling externals definition for 'ext'\n"
                                                         b"svn: E205011: Failure occurred processing one or more externals definitions\n")
        real = u.svn
        with patch.object(u, "svn", side_effect=lambda cwd, *args, **kw: failed if args[0] == "update" else real(cwd, *args, **kw)):
            result = self.update()
        code = result["working_copies"][0]
        self.assertEqual((result["status"], code["status"]), ("partial", "partial"))
        self.assertEqual(len(code["external_failures"]), 2)

    def test_uninitialized_root_and_cli(self):
        self.checkout(resource=False)
        self.repository.commit_through("wzimage/trunk", {"a.py": "A = 2\n"})
        script = str(SOURCE / "scripts/svn_update.py")
        done = subprocess.run([sys.executable, script, "--root", str(self.root), "--global-config", str(self.config)],
                              capture_output=True)
        self.assertEqual(done.returncode, 0, done.stderr.decode("utf-8", "replace"))
        self.assertEqual(json.loads(done.stdout.decode("utf-8"))["status"], "success")
        svn_fixture.svn("revert", "AGENTS.md", cwd=self.root)
        done = subprocess.run([sys.executable, script, "--root", str(self.root), "--global-config", str(self.config)],
                              capture_output=True)
        self.assertEqual(done.returncode, 1)
        self.assertIn("不是已初始化的工作区", json.loads(done.stderr.decode("utf-8"))["error"])


if __name__ == "__main__":
    unittest.main()
