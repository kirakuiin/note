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
        infos = {"other": {"account": "a@163.com", "source": "D:/other/mhimage/xlogin/mainmenu.py"},
                 "idle": {"account": None, "source": mine},
                 "mine": {"account": "b@163.com", "source": mine},
                 "mine2": {"account": "c@163.com", "source": mine}}
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

    def test_task_arguments_quote_paths(self):
        arguments = c.task_arguments(Path(r"C:\Program Data\x.py"), Path(r"C:\Users\u\cfg.json"),
                                     [Path(r"D:\mhxy dev")])
        self.assertIn('"C:\\Program Data\\x.py"', arguments)
        self.assertIn('--allow "D:\\mhxy dev"', arguments)


if __name__ == "__main__":
    unittest.main()
