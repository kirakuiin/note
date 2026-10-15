"""skill_links 的隔离测试：只在临时目录里建链接，不碰真实家目录。"""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("skill_links", SOURCE / "scripts/skill_links.py")
links = importlib.util.module_from_spec(spec)
spec.loader.exec_module(links)


class SkillLinksTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="mhxy-links-")
        self.base = Path(self.temporary.name).resolve()
        self.shared = self.base / "共享 Skills"
        for name in ("甲", "乙"):
            (self.shared / name).mkdir(parents=True)
            (self.shared / name / "SKILL.md").write_text("---\nname: x\n---\n", encoding="utf-8")
        (self.shared / "不是skill").mkdir()
        self.claude = self.base / "家" / ".claude" / "skills"
        self.codex = self.base / "家" / ".codex" / "skills"

    def tearDown(self):
        for directory in (self.claude, self.codex):
            if directory.is_dir():
                for link in directory.iterdir():
                    if links._is_link(link):
                        links._remove_link(link)
        self.temporary.cleanup()

    def repair(self):
        return links.repair(self.shared, [self.claude, self.codex])

    def test_creates_missing_links_then_is_idempotent(self):
        result = self.repair()
        self.assertEqual(len(result["created"]), 4)
        self.assertEqual(result["problems"], [])
        for directory in (self.claude, self.codex):
            self.assertEqual(sorted(path.name for path in directory.iterdir()), ["乙", "甲"])
            self.assertTrue(links._is_link(directory / "甲"))
            self.assertTrue((directory / "甲" / "SKILL.md").is_file())
        self.assertEqual(self.repair(), {"created": [], "replaced": [], "problems": []})

    def test_replaces_wrong_or_broken_links_without_touching_targets(self):
        self.claude.mkdir(parents=True)
        elsewhere = self.base / "别处"
        elsewhere.mkdir()
        (elsewhere / "keep.txt").write_text("keep")
        links._make_link(self.claude / "甲", elsewhere)
        gone = self.base / "已删除"
        gone.mkdir()
        links._make_link(self.claude / "乙", gone)
        gone.rmdir()
        result = self.repair()
        self.assertEqual(sorted(result["replaced"]), sorted([str(self.claude / "甲"), str(self.claude / "乙")]))
        self.assertTrue((elsewhere / "keep.txt").is_file())
        self.assertEqual((self.claude / "甲").resolve(), (self.shared / "甲").resolve())

    def test_never_replaces_real_directories(self):
        (self.claude / "甲").mkdir(parents=True)
        (self.claude / "甲" / "own.txt").write_text("own")
        result = self.repair()
        self.assertEqual(len(result["problems"]), 1)
        self.assertIn("普通目录", result["problems"][0])
        self.assertTrue((self.claude / "甲" / "own.txt").is_file())

    def test_skips_when_skill_is_installed_directly(self):
        self.assertEqual(links.repair(self.shared, [self.shared, self.codex]),
                         {"created": [], "replaced": [], "problems": []})
        self.assertFalse(self.codex.exists())

    def test_tool_dirs_only_for_installed_tools(self):
        home = self.base / "家"
        (home / ".codex").mkdir(parents=True)
        self.assertEqual(links.tool_skill_dirs(home), [home / ".codex" / "skills"])


if __name__ == "__main__":
    unittest.main()
