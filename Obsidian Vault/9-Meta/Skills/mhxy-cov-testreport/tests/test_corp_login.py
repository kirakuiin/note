"""CORP 账号配置与登录公共逻辑的单元测试。"""
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import corp_login  # noqa: E402


class CorpLoginConfigTests(unittest.TestCase):
    def test_update_config_preserves_existing_keys_and_masks_password(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg = Path(directory) / "config.json"
            cfg.write_text(json.dumps({"pc_client_dir": "D:/client", "openid_username": "old@corp.netease.com",
                                       "openid_password": "old-secret"}), encoding="utf-8")
            out = io.StringIO()
            with patch.object(corp_login, "interactive_terminal", return_value=True), \
                 patch.object(corp_login.getpass, "getpass", side_effect=["new-secret", "new-secret"]), \
                 patch.object(sys, "stdout", out):
                code = corp_login.main(["config", "--config", str(cfg), "--username", "DevUser",
                                        "--prompt-password", "--apply"])
            self.assertEqual(code, 0)
            self.assertNotIn("new-secret", out.getvalue())
            self.assertNotIn("old-secret", out.getvalue())
            result = json.loads(out.getvalue())
            self.assertEqual(result["openid_username"], "devuser@corp.netease.com")
            self.assertEqual(result["openid_password"], "***")
            self.assertEqual(result["coder_name"], "devuser")
            saved = json.loads(cfg.read_text(encoding="utf-8"))
            self.assertEqual(saved["pc_client_dir"], "D:/client")
            self.assertEqual(saved["openid_username"], "devuser@corp.netease.com")
            self.assertEqual(saved["openid_password"], "new-secret")

    def test_username_change_without_prompt_clears_old_password(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg = Path(directory) / "config.json"
            cfg.write_text(json.dumps({"openid_username": "a@corp.netease.com", "openid_password": "secret"}), encoding="utf-8")
            res = corp_login.update_config(cfg, username="b@corp.netease.com", apply=True)
            self.assertIsNone(res["openid_password"])
            saved = json.loads(cfg.read_text(encoding="utf-8"))
            self.assertNotIn("openid_password", saved)

    def test_prompt_password_rejects_mismatch_or_non_interactive(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg = Path(directory) / "config.json"
            with self.assertRaisesRegex(corp_login.LoginError, "--apply"):
                corp_login.update_config(cfg, username="a", prompt_password=True, apply=False)
            with patch.object(corp_login, "interactive_terminal", return_value=False):
                with self.assertRaisesRegex(corp_login.LoginError, "交互终端"):
                    corp_login.update_config(cfg, username="a", prompt_password=True, apply=True)
            with patch.object(corp_login, "interactive_terminal", return_value=True), \
                 patch.object(corp_login.getpass, "getpass", side_effect=["p1", "p2"]):
                with self.assertRaisesRegex(corp_login.LoginError, "不一致"):
                    corp_login.update_config(cfg, username="a", prompt_password=True, apply=True)
            self.assertFalse(cfg.exists())

    def test_show_command_returns_masked_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg = Path(directory) / "config.json"
            cfg.write_text(json.dumps({"openid_username": "u@corp.netease.com", "openid_password": "secret"}), encoding="utf-8")
            out = io.StringIO()
            with patch.object(sys, "stdout", out):
                self.assertEqual(corp_login.main(["show", "--config", str(cfg)]), 0)
            self.assertNotIn("secret", out.getvalue())
            data = json.loads(out.getvalue())
            self.assertEqual(data["openid_password"], "***")
            self.assertEqual(data["coder_name"], "u")


if __name__ == "__main__":
    unittest.main()
