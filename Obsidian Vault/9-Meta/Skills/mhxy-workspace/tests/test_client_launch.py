"""client_launch.py／client_launch_task.py 的纯逻辑测试；不访问网络、MCP、计划任务或真实配置。"""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, SOURCE / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sys.path.insert(0, str(SOURCE / "scripts"))
c = load("client_launch")
t = load("client_launch_task")
PC_INI = "[Setting]\r\nVersion = 3.0.635\r\nArch = X64\r\n\r\n[Richman]\r\nResName = \"梦幻大富翁\"\r\n"
HT_INI = "[Setting]\r\nVersion = 3.0.635\r\nPlatform = HT\r\n"


class ClientLaunchTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="mhxy-launch-")
        self.base = Path(self.temporary.name).resolve()

    def tearDown(self):
        self.temporary.cleanup()

    def test_normalize_and_choose_account(self):
        self.assertEqual(c.normalize_account("NicoTest3"), "nicotest3@163.com")
        self.assertEqual(c.normalize_account("a@126.com"), "a@126.com")
        self.assertIsNone(c.normalize_account(None))
        pool = [{"account": "a@163.com", "password": "x"}, {"account": "B", "password": "y"}]
        self.assertEqual(c.choose_account(pool, {}), "a@163.com")
        self.assertEqual(c.choose_account(pool, {"a@163.com": "d1"}), "B")
        self.assertIsNone(c.choose_account(pool, {"a@163.com": "d1", "b@163.com": "d2"}))

    def test_resolve_server(self):
        names = ["王卓为-trunk", "王卓为-rel", "模拟1401", "陈瑞峰-trunk"]
        self.assertEqual(c.resolve_server("模拟14", []), ("刘强98服", "模拟14"))
        self.assertEqual(c.resolve_server("王卓为-rel", names), ("more_server", "王卓为-rel"))
        self.assertEqual(c.resolve_server("陈瑞峰", names), ("more_server", "陈瑞峰-trunk"))
        with self.assertRaises(c.LaunchError) as error:
            c.resolve_server("王卓为", names)
        self.assertEqual(error.exception.code, "server_ambiguous")
        self.assertEqual(error.exception.detail["candidates"], ["王卓为-trunk", "王卓为-rel"])
        with self.assertRaises(c.LaunchError):
            c.resolve_server("不存在", names)

    def test_resolve_server_from_server_ini(self):
        text = ("-26 1 1 刘强98服\r\n-32 3 7 孙锐贤\r\n-40 1 1 孙锐贤-test\r\n"
                "26 1 2 模拟15 10.0.0.1 1 1 10.0.0.1 1 2 0 0 0 0 欢迎 2\r\n"
                "32 2 2 test_branch 10.0.0.2 4377 1 10.0.0.2 4377 2 0 0 0 0 欢迎 4378\r\n"
                "32 2 1 test 10.0.0.2 9991 1 10.0.0.2 9991 2 0 0 0 0 欢迎 9992\r\n"
                "40 1 2 branch 10.0.0.3 1 1 10.0.0.3 1 2 0 0 0 0 欢迎 2\r\n"
                "50 3 1 test_branch 10.0.0.4 1 1 10.0.0.4 1 2 0 0 0 0 欢迎 2\r\n")
        areas = c.parse_server_ini(text)
        self.assertEqual(areas["孙锐贤"], ["test_branch", "test"])
        self.assertEqual(c.resolve_server("孙锐贤-test", [], areas), ("孙锐贤", "test"))
        self.assertEqual(c.resolve_server("孙锐贤-test-branch", [], areas), ("孙锐贤-test", "branch"))
        self.assertEqual(c.resolve_server("王卓为-rel", ["王卓为-rel"], areas), ("more_server", "王卓为-rel"))
        with self.assertRaises(c.LaunchError) as error:
            c.resolve_server("孙锐贤-test-branch", [], {**areas, "孙锐贤": ["test-branch"]})
        self.assertEqual(error.exception.code, "server_ambiguous")
        with self.assertRaises(c.LaunchError) as error:
            c.resolve_server("孙锐贤-nope", [], areas)
        self.assertEqual(error.exception.code, "server_not_found")
        client = self.base / "client"
        (client / "common").mkdir(parents=True)
        (client / "common" / "server.ini").write_bytes(text.encode("gb18030"))
        config = {"pc_client_dir": str(self.base / "missing"), "ht_client_dir": str(client)}
        self.assertEqual(c.server_areas(config, "pc"), areas)
        self.assertEqual(c.server_areas({}, "pc"), {})

    def test_workspace_dir(self):
        root = self.base / "branch" / "mhimage"
        root.mkdir(parents=True)
        self.assertEqual(c.workspace_dir(root), (self.base / "branch").as_posix())
        (self.base / "branch" / "_test").mkdir()
        (self.base / "branch" / "_test" / "mhimage.wdf").write_bytes(b"x")
        with self.assertRaises(c.LaunchError):
            c.workspace_dir(root)
        other = self.base / "src"
        other.mkdir()
        with self.assertRaises(c.LaunchError):
            c.workspace_dir(other)

    def test_launch_stops_when_all_accounts_occupied(self):
        config = {"pc_client_dir": str(self.base), "login_server": "模拟14",
                  "login_accounts": [{"account": "a@163.com", "password": "synthetic-secret"}]}
        (self.base / "mhmain.exe").write_bytes(b"")
        (self.base / "update.ini").write_bytes(PC_INI.encode("gbk"))
        root = self.base / "w" / "mhimage"
        root.mkdir(parents=True)
        with patch.object(c.workspace, "load_config", return_value=config), \
                patch.object(c, "scan_accounts", return_value=([], {"a@163.com": "dev1"}, [])), \
                patch.object(c.subprocess, "run") as run:
            with self.assertRaises(c.LaunchError) as error:
                c.launch(root, self.base / "config.json")
        run.assert_not_called()
        self.assertEqual(error.exception.code, "all_occupied")
        self.assertNotIn("synthetic-secret", json.dumps(error.exception.detail, ensure_ascii=False))
        with patch.object(c.workspace, "load_config", return_value=config), \
                patch.object(c, "scan_accounts", return_value=([], {}, [])):
            plan = c.launch(root, self.base / "config.json", dry_run=True)
        self.assertEqual((plan["account"], plan["svrfield"]), ("a@163.com", "刘强98服"))
        self.assertNotIn("synthetic-secret", json.dumps(plan, ensure_ascii=False))

    def test_task_payload_restores_uppercase(self):
        self.assertEqual(t.caps("abC1D"), "2,4")
        request = {"workspace": "D:/w", "account": "a@163.com", "svrfield": "f", "svrname": "s", "roleidx": 0}
        payload = json.loads(t.build_payload(request, "aBc"))
        self.assertEqual((payload["pwd"], payload["caps"]), ("aBc", "1"))
        self.assertNotIn("caps", json.loads(t.build_payload(request, "abc")))
        self.assertTrue(t.build_payload(request, "abc").startswith('{"workspace":'))
        with self.assertRaises(t.LaunchError):
            t.build_payload({**request, "svrname": "a b"}, "abc")

    def test_task_passes_payload_unquoted(self):
        exe = self.base / "mhmain.exe"
        with patch.object(t.subprocess, "Popen") as popen:
            popen.return_value.pid = 7
            self.assertEqual(t.start(exe, '{"workspace":"D:/w"}'), 7)
        self.assertEqual(popen.call_args.args[0], f'"{exe}" __start_by_mh_launcher__ {{"workspace":"D:/w"}}')

    def test_task_validates_request_and_allowlist(self):
        client = self.base / "client"
        client.mkdir()
        (client / "mhmain.exe").write_bytes(b"")
        work = self.base / "work"
        work.mkdir()
        request = {"id": "1", "client_dir": str(client), "workspace": work.as_posix(), "account": "a@163.com",
                   "svrfield": "f", "svrname": "s", "roleidx": 0}
        self.assertEqual(t.validate_request(request, [str(client)]), client / "mhmain.exe")
        with self.assertRaisesRegex(t.LaunchError, "未在安装时登记"):
            t.validate_request(request, [str(self.base / "other")])
        for key, value in (("roleidx", "0"), ("workspace", str(work).replace("/", "\\") + "\\"),
                           ("account", 'a"b'), ("extra", 1)):
            with self.subTest(key=key), self.assertRaises(t.LaunchError):
                t.validate_request({**request, key: value}, [str(client)])

    def test_task_reads_password_and_reports_error_without_secret(self):
        config = self.base / "config.json"
        config.write_text(json.dumps({"login_accounts": [{"account": "A@163.com", "password": "synthetic-Pw"}]}),
                          encoding="utf-8")
        self.assertEqual(t.account_password(config, "a@163.com"), "synthetic-Pw")
        request_path = self.base / "request.json"
        request_path.write_text(json.dumps({"id": "abc", "client_dir": str(self.base)}), encoding="utf-8")
        self.assertEqual(t.main(["--request", str(request_path), "--config", str(config)]), 1)
        result = json.loads((self.base / "result.json").read_text(encoding="utf-8"))
        self.assertEqual(result["id"], "abc")
        self.assertIsNone(result["pid"])
        self.assertFalse(request_path.exists())
        self.assertNotIn("synthetic-Pw", json.dumps(result))

    def test_no_online_device_is_empty_list(self):
        error = c.LaunchError(f"get_devices_by_ip 返回错误：IP=1.2.3.4 {c.NO_DEVICE}", "mcp_error")
        with patch.object(c, "mcp", side_effect=error):
            self.assertEqual(c.list_devices(), [])
        with patch.object(c, "mcp", side_effect=c.LaunchError("其他错误", "mcp_error")):
            with self.assertRaises(c.LaunchError):
                c.list_devices()

    def test_loads_workspace_ignores_case_and_separators(self):
        root = self.base / "Branch" / "mhimage"
        root.mkdir(parents=True)
        source = str(root).lower().replace("\\", "/") + "/xlogin\\mainmenu.py"
        self.assertTrue(c.loads_workspace(source, root))
        self.assertFalse(c.loads_workspace(str(self.base / "Branch" / "mhimage2" / "mainmenu.py"), root))
        self.assertFalse(c.loads_workspace(None, root))

    def test_select_prefers_unlocked_device_with_workspace_source(self):
        root = self.base / "w" / "mhimage"
        root.mkdir(parents=True)
        mine = (root / "xlogin" / "mainmenu.py").as_posix()
        devices = [{"devid": "locked"}, {"devid": "other"}, {"devid": "idle"}, {"devid": "mine"}, {"devid": "mine2"}]
        infos = {"other": {"account": "a@163.com", "source": "D:/other/mhimage/xlogin/mainmenu.py", "platform": "pc"},
                 "idle": {"account": None, "source": mine, "platform": "pc"},
                 "mine": {"account": "b@163.com", "source": mine, "platform": "pc"},
                 "mine2": {"account": "c@163.com", "source": mine, "platform": "pc"}}
        with patch.object(c, "list_devices", return_value=devices), \
                patch.object(c, "locked", side_effect=lambda devid: devid == "locked"), \
                patch.object(c, "device_info", side_effect=lambda devid: infos[devid]), \
                patch.object(c, "launch") as launch:
            result = c.select(root, self.base / "config.json")
        launch.assert_not_called()
        self.assertEqual((result["how"], result["devid"]), ("online", "mine"))
        self.assertEqual([item["devid"] for item in result["skipped"]], ["locked", "other", "idle"])
        with patch.object(c, "list_devices", return_value=devices[:2]), \
                patch.object(c, "locked", side_effect=lambda devid: devid == "locked"), \
                patch.object(c, "device_info", side_effect=lambda devid: infos[devid]), \
                patch.object(c, "launch", return_value={"action": "launch", "devid": "new"}):
            result = c.select(root, self.base / "config.json")
        self.assertEqual((result["how"], result["devid"]), ("launched", "new"))

    def test_select_filters_platform_and_dry_run(self):
        root = self.base / "w" / "mhimage"
        root.mkdir(parents=True)
        mine = (root / "xlogin" / "mainmenu.py").as_posix()
        devices = [{"devid": "pc1"}, {"devid": "ht1"}, {"devid": "odd"}]
        infos = {"pc1": {"account": "a@163.com", "source": mine, "platform": "pc"},
                 "ht1": {"account": "b@163.com", "source": mine, "platform": "ht"},
                 "odd": {"account": "c@163.com", "source": mine, "platform": None}}
        common = (patch.object(c, "list_devices", return_value=devices),
                  patch.object(c, "locked", return_value=False),
                  patch.object(c, "device_info", side_effect=lambda devid: infos[devid]))
        with common[0], common[1], common[2], patch.object(c, "launch") as launch:
            result = c.select(root, self.base / "config.json", "ht")
        launch.assert_not_called()
        self.assertEqual((result["devid"], result["platform"]), ("ht1", "ht"))
        self.assertEqual([item["devid"] for item in result["skipped"]], ["pc1"])
        infos["ht1"]["platform"] = "pc"
        with common[0], common[1], common[2], \
                patch.object(c, "launch", return_value={"action": "launch", "dry_run": True}) as launch:
            result = c.select(root, self.base / "config.json", "ht", dry_run=True)
        self.assertTrue(launch.call_args.kwargs["dry_run"])
        self.assertEqual(result["how"], "would_launch")
        self.assertEqual([item["devid"] for item in result["skipped"]], ["pc1", "ht1", "odd"])
        self.assertIn("无法识别", result["skipped"][2]["reason"])

    def test_device_info_maps_platform(self):
        with patch.object(c, "mcp", return_value={"ret": {"account": "A", "source": "x", "platform": "mobile"}}):
            self.assertEqual(c.device_info("d"), {"account": "a@163.com", "source": "x", "platform": "ht"})
        with patch.object(c, "mcp", return_value={"ret": {"account": None, "source": None, "platform": "ios"}}):
            self.assertIsNone(c.device_info("d")["platform"])

    def test_client_platform_from_update_ini(self):
        pc, ht, odd, empty = (self.base / name for name in ("pc", "ht", "odd", "empty"))
        for folder in (pc, ht, odd, empty):
            folder.mkdir()
        (pc / "update.ini").write_bytes(PC_INI.encode("gbk"))
        (ht / "update.ini").write_bytes(b"\xef\xbb\xbf" + HT_INI.encode())
        (odd / "update.ini").write_text("[Setting]\nVersion = 1\n", encoding="utf-8")
        before = (pc / "update.ini").read_bytes()
        self.assertEqual([c.client_platform(item) for item in (pc, ht, odd, empty)], ["pc", "ht", None, None])
        self.assertEqual((pc / "update.ini").read_bytes(), before)
        self.assertEqual(c.check_client_platform(ht, "ht"), "ht")
        with self.assertRaises(c.LaunchError) as error:
            c.check_client_platform(ht, "pc")
        self.assertEqual((error.exception.code, error.exception.detail["detected"]), ("platform_mismatch", "ht"))
        with self.assertRaises(c.LaunchError) as error:
            c.check_client_platform(odd, "pc")
        self.assertEqual(error.exception.code, "platform_unknown")

    def test_launch_stops_on_platform_mismatch(self):
        (self.base / "mhmain.exe").write_bytes(b"")
        (self.base / "update.ini").write_text(HT_INI, encoding="utf-8")
        config = {"pc_client_dir": str(self.base), "login_server": "模拟14",
                  "login_accounts": [{"account": "a@163.com", "password": "synthetic-secret"}]}
        with patch.object(c.workspace, "load_config", return_value=config), \
                patch.object(c, "scan_accounts") as scan, patch.object(c.subprocess, "run") as run:
            with self.assertRaises(c.LaunchError) as error:
                c.launch(self.base / "w" / "mhimage", self.base / "config.json", "pc", dry_run=True)
        self.assertEqual(error.exception.code, "platform_mismatch")
        scan.assert_not_called()
        run.assert_not_called()

    def test_doctor_reports_client_types(self):
        pc, ht = self.base / "mhxy_dev", self.base / "mhxy_mini"
        for folder in (pc, ht):
            folder.mkdir()
            (folder / "mhmain.exe").write_bytes(b"")
            (folder / "mhxy.key").write_bytes(b"")
            (folder / "update.ini").write_text(HT_INI, encoding="utf-8")  # PC 目录被同步成了互通版
        root = self.base / "w" / "mhimage"
        root.mkdir(parents=True)
        config = {"pc_client_dir": str(pc), "ht_client_dir": str(ht), "login_server": "模拟14",
                  "login_accounts": [{"account": "a@163.com", "password": "synthetic-secret"}]}
        with patch.object(c, "query_task", return_value=None), \
                patch.object(c.workspace, "load_config", return_value=config):
            result = c.doctor(root, self.base / "config.json")
        self.assertEqual(result["clients"], {"pc_client_dir": {"path": str(pc), "detected": "ht"},
                                             "ht_client_dir": {"path": str(ht), "detected": "ht"}})
        kinds = [item for item in result["problems"] if item["item"] == "客户端类型"]
        self.assertEqual(len(kinds), 1)
        self.assertIn("pc_client_dir", kinds[0]["problem"])
        self.assertNotIn("synthetic-secret", json.dumps(result, ensure_ascii=False))

    def test_task_arguments_quote_paths(self):
        arguments = c.task_arguments(Path(r"C:\Program Data\x.py"), Path(r"C:\Users\u\cfg.json"),
                                     [Path(r"D:\mhxy dev")])
        self.assertIn('"C:\\Program Data\\x.py"', arguments)
        self.assertIn('--allow "D:\\mhxy dev"', arguments)


if __name__ == "__main__":
    unittest.main()
