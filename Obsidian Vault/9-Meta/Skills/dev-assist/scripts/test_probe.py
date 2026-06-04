import os
import unittest
from pathlib import Path

import dev_assist_probe as probe


TASK = "搜打撤模式下，战斗外法术施放要走 infosdc 里面的法术白名单，机制和原本的战斗外施法类似"
EXPECTED_PAGE = "战斗外师门法术使用链路.md"


class ProbeTests(unittest.TestCase):
    def test_extractor_uses_configured_rules_not_script_business_constants(self):
        self.assertFalse(hasattr(probe, "SPELL_ACTIONS"))
        self.assertFalse(hasattr(probe, "CHINESE_PRIORITY_TERMS"))

        rules = probe.load_rules()
        synonym_groups = [set(group["terms"]) for group in rules["synonym_groups"]]
        self.assertIn({"施放", "施法", "释放", "使用"}, synonym_groups)

    def test_extracts_phrases_and_configured_synonyms(self):
        tokens = probe.extract_tokens(TASK, cwd="D:/workspace/trunk/mhimage/", open_files=[])

        self.assertIn("infosdc", tokens)
        self.assertIn("战斗外法术施放", tokens)
        self.assertIn("战斗外法术使用", tokens)
        self.assertIn("法术白名单", tokens)
        self.assertIn("施放", tokens)
        self.assertIn("施法", tokens)
        self.assertIn("释放", tokens)
        self.assertNotIn("战斗外", tokens)
        self.assertNotIn("法术", tokens)
        self.assertLessEqual(len(tokens), 8)

    def test_probe_finds_out_of_combat_spell_flow_page(self):
        vault = os.environ.get("OBSIDIAN_VAULT")
        if not vault:
            self.skipTest("OBSIDIAN_VAULT is not set")

        result = probe.run_probe(
            TASK,
            cwd="D:/workspace/trunk/mhimage/",
            open_files=[],
            vault=Path(vault),
        )

        self.assertEqual(result["status"], "hits")
        names = {Path(path).name for path in result["hits"]}
        self.assertIn(EXPECTED_PAGE, names)

    def test_probe_keeps_generic_usage_from_swamping_results(self):
        vault = os.environ.get("OBSIDIAN_VAULT")
        if not vault:
            self.skipTest("OBSIDIAN_VAULT is not set")

        result = probe.run_probe(
            TASK,
            cwd="D:/workspace/trunk/mhimage/",
            open_files=[],
            vault=Path(vault),
        )

        hit_names = {Path(path).name for path in result["hits"]}
        self.assertNotIn("GTD - The Art of Stress-Free Productivity.md", hit_names)


if __name__ == "__main__":
    unittest.main()
