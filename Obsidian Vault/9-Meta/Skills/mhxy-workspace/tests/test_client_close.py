"""自动启动客户端的登记、关闭和空闲兜底（specs/2026-11-12-client-auto-close.md）。

不访问 MCP、计划任务或本机真实登记目录；进程核对用当前测试进程和临时子进程。
"""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
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
cli = load("codex_cli")
r = c.registry


class ClientCloseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="mhxy-close-")
        self.base = Path(self.temporary.name).resolve()
        self.environment = patch.dict(os.environ, {"LOCALAPPDATA": str(self.base / "local")})
        self.environment.start()
        os.environ.pop(c.OWNER_ENV, None)
        self.locks = self.base / "local" / "mhxy-cli-testing" / "locks"
        self.lock_path = patch.object(c, "LOCKS", self.locks)
        self.lock_path.start()
        self.root = self.base / "w" / "mhimage"
        self.root.mkdir(parents=True)
        self.alive = set()  # 测试中视为仍在运行的 (pid, created)
        self.alive_patch = patch.object(r, "alive", side_effect=lambda e: (e["pid"], e["created"]) in self.alive)
        self.alive_patch.start()
        self.sleep = patch.object(c.time, "sleep")
        self.sleep.start()

    def tearDown(self):
        patch.stopall()
        self.temporary.cleanup()

    def add(self, pid, alive=True, **fields):
        fields.setdefault("root", str(self.root))
        entry = r.register(pid, pid * 10, **fields)
        if alive:
            self.alive.add((pid, pid * 10))
        return entry

    def lock(self, devid):
        self.locks.mkdir(parents=True, exist_ok=True)
        (self.locks / (c.hashlib.sha256(devid.encode()).hexdigest() + ".json")).write_text("{}", encoding="utf-8")

    def pids(self):
        return sorted(item["pid"] for item in r.entries())

    # ---------- 登记 ----------

    def test_registry_roundtrip_is_atomic_and_touch_updates_last_used(self):
        entry = self.add(11, devid="d1", account="a@163.com", owner="issue:1")
        self.add(12, devid="d2")
        self.assertEqual(self.pids(), [11, 12])
        self.assertEqual(list(r.directory().glob("*.tmp")), [])
        self.assertEqual(r.directory().parent.name, "mhxy-cli-testing")
        self.assertEqual(r.touch("d1", now=123.0), 1)
        self.assertEqual(next(e for e in r.entries() if e["pid"] == 11)["last_used"], 123.0)
        r.remove(entry)
        self.assertIsNone(r.update(entry, last_used=1))  # 已删除的登记不重建
        self.assertEqual(self.pids(), [12])

    def test_process_info_and_pid_reuse_guard(self):
        self.alive_patch.stop()
        info = r.process_info(os.getpid())
        self.assertTrue(info["created"] > 0)
        self.assertTrue(info["image"].lower().endswith(".exe"))
        self.assertIsNone(r.process_info(0x7FFFFFF0))
        # 创建时间不符（进程号被复用）或映像不是 mhmain.exe 都不算登记的客户端
        self.assertFalse(r.alive({"pid": os.getpid(), "created": info["created"] + 1}))
        self.assertFalse(r.alive({"pid": os.getpid(), "created": info["created"]}))
        self.alive_patch.start()

    def test_owner_and_idle_limit(self):
        self.assertIsNone(c.resolve_owner())
        with patch.dict(os.environ, {c.OWNER_ENV: "issue:9"}):
            self.assertEqual(c.resolve_owner(), "issue:9")
            self.assertEqual(c.resolve_owner("x"), "x")
        self.assertEqual(c.idle_limit({}), 30)
        self.assertEqual(c.idle_limit({"client_idle_minutes": "45"}), 45)
        self.assertEqual(c.idle_limit({"client_idle_minutes": "45"}, 0), 0)
        with self.assertRaises(c.LaunchError):
            c.idle_limit({"client_idle_minutes": "abc"})

    def test_config_validates_idle_minutes(self):
        c.workspace.validate_config({"client_idle_minutes": "30"}, {"client_idle_minutes": None}, "x")
        c.workspace.validate_config({"client_idle_minutes": 30}, {"client_idle_minutes": None}, "x")
        for bad in ("0", "-1", "abc", True):
            with self.assertRaises(c.workspace.WorkspaceError):
                c.workspace.validate_config({"client_idle_minutes": bad}, {"client_idle_minutes": None}, "x")

    # ---------- close ----------

    def test_gone_entry_is_removed_without_closing(self):
        self.add(21, alive=False, devid="d")
        with patch.object(c, "mcp") as mcp, patch.object(c, "close_by_task") as task:
            result = c.close(self.root, devid="d")
        self.assertEqual([item["outcome"] for item in result["results"]], ["gone"])
        mcp.assert_not_called()
        task.assert_not_called()
        self.assertEqual(self.pids(), [])

    def test_locked_client_is_kept_and_refreshed(self):
        entry = self.add(22, devid="busy")
        r.update(entry, last_used=1.0)
        self.lock("busy")
        with patch.object(c, "mcp") as mcp, patch.object(c, "close_by_task") as task:
            result = c.close(self.root, devid="busy")
        self.assertEqual(result["results"][0]["outcome"], "locked")
        mcp.assert_not_called()
        task.assert_not_called()
        self.assertGreater(r.entries()[0]["last_used"], 1.0)

    def test_close_holds_device_lock_against_new_tests(self):
        self.add(25, devid="d25")
        job = self.base / "job"

        def quit_(name, arguments, timeout):
            # 关闭进行中：别的会话加锁会失败，不会在关闭中途开始测试
            with self.assertRaises(ValueError):
                cli.acquire_lock("d25", job)
            self.alive.discard((25, 250))
            return {"ret": "quit"}

        with patch.object(cli.client_registry, "base", r.base), patch.object(c, "mcp", side_effect=quit_):
            result = c.close(self.root, devid="d25")
        self.assertEqual(result["results"][0]["outcome"], "closed")
        self.assertFalse(c.locked("d25"))  # 关闭结束后释放自己占的锁

    def test_unreadable_process_is_failed_not_gone(self):
        self.add(26, devid="d26")
        with patch.object(r, "alive", side_effect=OSError("读不到进程 26 的映像路径")), \
                patch.object(c, "mcp") as mcp:
            result = c.close(self.root, devid="d26")
        self.assertEqual(result["results"][0]["outcome"], "failed")
        mcp.assert_not_called()
        self.assertEqual(self.pids(), [26])

    def test_release_refreshes_before_deleting_lock(self):
        self.add(27, devid="d27")
        state = cli.lock(self.root, "d27")
        seen = []
        original = cli.client_registry.touch
        with patch.object(cli.client_registry, "touch",
                          side_effect=lambda devid: (seen.append(c.locked(devid)), original(devid))[1]):
            cli.release(Path(state["job"]))
        self.assertEqual(seen, [True])
        self.assertFalse(c.locked("d27"))

    def test_mine_matches_root_and_owner_only(self):
        self.add(31, devid="a")
        self.add(32, devid="b", owner="issue:7")
        self.add(33, devid="c", root=str(self.base / "other" / "mhimage"))
        with patch.object(c, "mcp") as mcp:
            result = c.close(self.root, owner=None, dry_run=True)
        self.assertEqual([(item["pid"], item["outcome"]) for item in result["results"]], [(31, "would_close")])
        mcp.assert_not_called()
        self.assertEqual(self.pids(), [31, 32, 33])  # dry-run 不动登记
        result = c.close(self.root, owner="issue:7", dry_run=True)
        self.assertEqual([item["pid"] for item in result["results"]], [32])
        self.assertEqual(c.close(self.root, devid="unregistered", dry_run=True)["results"], [])

    def test_close_by_mcp_checks_pid_in_client(self):
        self.add(41, devid="d41")

        def quit_(name, arguments, timeout):
            self.assertIn("getpid() == 41", arguments["code"])
            self.assertIn("quit_game(1)", arguments["code"])
            self.alive.discard((41, 410))
            raise c.LaunchError("连接断开", "mcp_error")  # 客户端退出时调用本身可能报错

        with patch.object(c, "mcp", side_effect=quit_), patch.object(c, "close_by_task") as task:
            result = c.close(self.root, owner=None)
        self.assertEqual((result["results"][0]["outcome"], result["results"][0]["method"]), ("closed", "mcp"))
        task.assert_not_called()
        self.assertTrue(result["ok"])
        self.assertEqual(self.pids(), [])

    def test_close_falls_back_to_task_and_reports_failure(self):
        self.add(51, devid="d51")
        self.add(52)  # device_timeout：没有 devid，直接走计划任务
        with patch.object(c, "QUIT_WAIT", 0), patch.object(c, "mcp", return_value={"ret": "pid_mismatch"}), \
                patch.object(c, "close_by_task", side_effect=lambda e: self.alive.discard((e["pid"], e["created"]))):
            result = c.close(self.root, owner=None)
        self.assertEqual([(i["pid"], i["outcome"], i["method"]) for i in result["results"]],
                         [(51, "closed", "task"), (52, "closed", "task")])
        self.add(53)
        with patch.object(c, "close_by_task", side_effect=c.LaunchError("启动器报错：x", "launcher_error")):
            result = c.close(self.root, pid=53)
        self.assertEqual(result["results"][0]["outcome"], "failed")
        self.assertFalse(result["ok"])
        self.assertEqual(self.pids(), [53])  # 失败时保留登记

    def test_close_by_task_writes_close_request(self):
        state = self.base / "state"
        entry = self.add(61)
        written = {}

        def run(argv, **kwargs):
            written.update(json.loads((state / "request.json").read_text(encoding="utf-8")))
            return subprocess.CompletedProcess(argv, 0, b"", b"")

        with patch.object(c, "STATE_DIR", state), patch.object(c.subprocess, "run", side_effect=run), \
                patch.object(c, "wait_result", return_value={"error": "启动请求字段无效"}):
            with self.assertRaises(c.LaunchError) as error:
                c.close_by_task(entry)
        self.assertEqual(set(written), t.CLOSE_KEYS)
        self.assertEqual((written["action"], written["pid"], written["created"]), ("close", 61, 610))
        self.assertIn("重新运行 install", str(error.exception))

    # ---------- reap ----------

    def test_reap_closes_only_idle_unlocked_registered_clients(self):
        now = time.time()
        for pid, minutes, devid in ((71, 40, "idle"), (72, 5, "recent"), (73, 90, "busy")):
            r.update(self.add(pid, devid=devid), last_used=now - minutes * 60)
        self.add(74, alive=False, devid="dead")
        self.lock("busy")
        with patch.object(c, "close_by_task") as task, \
                patch.object(c, "mcp", side_effect=lambda *a, **k: self.alive.discard((71, 710))):
            result = c.reap(30, now=now)
        outcomes = {item["pid"]: item["outcome"] for item in result["results"]}
        self.assertEqual(outcomes, {71: "closed", 72: "kept", 73: "locked", 74: "gone"})
        task.assert_not_called()
        self.assertEqual(self.pids(), [72, 73])
        preview = c.reap(0, dry_run=True, now=now)
        self.assertEqual({i["pid"]: i["outcome"] for i in preview["results"]}, {72: "would_close", 73: "locked"})

    def test_auto_reap_reports_error_without_failing(self):
        with patch.object(c.workspace, "load_config", side_effect=c.workspace.WorkspaceError("坏配置")):
            self.assertEqual(c.auto_reap(self.root, self.base / "c.json", False), {"action": "reap", "error": "坏配置"})
        self.add(81)
        with patch.object(c.workspace, "load_config", return_value={}):
            self.assertEqual(c.auto_reap(self.root, self.base / "c.json", True)["results"], [])  # kept 不列出

    # ---------- launch／select 登记 ----------

    def test_launch_registers_and_fills_devid(self):
        config = {"pc_client_dir": str(self.base), "login_server": "模拟14",
                  "login_accounts": [{"account": "a@163.com", "password": "synthetic-secret"}]}
        (self.base / "mhmain.exe").write_bytes(b"")
        state = self.base / "state"
        with patch.object(c.workspace, "load_config", return_value=config), \
                patch.object(c, "check_client_platform"), \
                patch.object(c, "workspace_dir", return_value=self.root.parent.as_posix()), \
                patch.object(c, "scan_accounts", return_value=([], {}, [])), \
                patch.object(c, "STATE_DIR", state), \
                patch.object(c.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, b"", b"")), \
                patch.object(c, "wait_result", return_value={"pid": 91}), \
                patch.object(r, "process_info", return_value={"created": 910, "image": "x/mhmain.exe"}), \
                patch.object(c, "list_devices", return_value=[{"devid": "new"}]), \
                patch.object(c, "device_account", return_value="a@163.com"):
            result = c.launch(self.root, self.base / "c.json", owner="issue:5")
        self.assertEqual((result["devid"], result["registered"]), ("new", True))
        entry = r.entries()[0]
        self.assertEqual((entry["pid"], entry["created"], entry["devid"], entry["owner"], entry["account"]),
                         (91, 910, "new", "issue:5", "a@163.com"))
        self.assertTrue(r.same_root(entry["root"], str(self.root)))
        self.assertNotIn("synthetic-secret", json.dumps(entry))

    def test_select_reuse_refreshes_registered_client(self):
        entry = self.add(95, devid="mine")
        r.update(entry, last_used=1.0)
        source = (self.root / "xlogin" / "mainmenu.py").as_posix()
        with patch.object(c, "list_devices", return_value=[{"devid": "mine"}]), \
                patch.object(c, "device_info", return_value={"account": "a@163.com", "source": source,
                                                              "platform": "pc"}):
            result = c.select(self.root, self.base / "c.json")
        self.assertEqual(result["devid"], "mine")
        self.assertGreater(r.entries()[0]["last_used"], 1.0)

    # ---------- 设备锁刷新 ----------

    def test_codex_release_refreshes_last_used(self):
        entry = self.add(97, devid="dev97")
        state = cli.lock(self.root, "dev97")
        r.update(entry, last_used=2.0)
        released = cli.release(Path(state["job"]))
        self.assertTrue(released["released"])
        self.assertGreater(r.entries()[0]["last_used"], 2.0)

    def test_release_keeps_lock_when_refresh_fails(self):
        self.add(98, devid="dev98")
        state = cli.lock(self.root, "dev98")
        with patch.object(cli.client_registry, "touch", side_effect=OSError("磁盘错误")):
            with self.assertRaises(ValueError):
                cli.release(Path(state["job"]))
        self.assertTrue(c.locked("dev98"))
        self.assertTrue(cli.release(Path(state["job"]))["released"])

    def test_stale_close_lock_is_reclaimed(self):
        child = subprocess.Popen([sys.executable, "-c", "pass"])
        created = r.process_info(child.pid)["created"] if child.poll() is None else 1
        child.wait()
        self.locks.mkdir(parents=True, exist_ok=True)
        stale = {"job": "client_launch close", "devid": "d99", "closer_pid": child.pid, "closer_created": created}
        c.lock_file("d99").write_text(json.dumps(stale), encoding="utf-8")
        self.assertFalse(c.locked("d99"))  # 持有者已退出，不算有锁
        cli.acquire_lock("d99", self.base / "job")  # 加锁时回收
        self.assertEqual(json.loads(c.lock_file("d99").read_text(encoding="utf-8"))["job"], str(self.base / "job"))
        # 持有者还活着（本测试进程）的 close 锁不回收；codex_cli 自己的锁也不回收
        c.lock_file("d99").unlink()
        live = r.close_lock_body("d99", 1)
        c.lock_file("d99").write_text(json.dumps(live), encoding="utf-8")
        self.assertTrue(c.locked("d99"))
        self.assertFalse(r.reclaim_close_lock(c.lock_file("d99")))
        with self.assertRaises(ValueError):
            cli.acquire_lock("d99", self.base / "job2")

    def test_reclaim_does_not_delete_lock_replaced_after_precheck(self):
        self.locks.mkdir(parents=True, exist_ok=True)
        path = c.lock_file("d88")
        path.write_text(json.dumps({"job": "codex job", "devid": "d88"}), encoding="utf-8")  # 新加的有效锁
        real = r.stale_close_lock
        calls = []

        def stale(p):  # 粗筛时看到的还是旧的残留锁，改名后拿到的是新锁
            calls.append(p)
            return True if len(calls) == 1 else real(p)

        with patch.object(r, "stale_close_lock", side_effect=stale):
            self.assertFalse(r.reclaim_close_lock(path))
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["job"], "codex job")
        self.assertEqual(list(self.locks.glob("*.reclaiming")), [])

    def test_reap_rechecks_idle_after_taking_lock(self):
        now = time.time()
        entry = self.add(96, devid="d96")
        r.update(entry, last_used=now - 40 * 60)
        snapshot = r.entries()
        # 取快照之后、拿锁之前，另一会话 release 刷新了 last_used
        with patch.object(r, "entries", return_value=snapshot), patch.object(c, "mcp") as mcp:
            r.update(entry, last_used=time.time())
            result = c.reap(30, now=now)
        self.assertEqual(result["results"][0]["outcome"], "kept")
        mcp.assert_not_called()
        self.assertFalse(c.locked("d96"))

    def test_reap_continues_when_one_process_unreadable(self):
        self.add(93, devid="d93")
        r.update(self.add(94, alive=False, devid="d94"), last_used=1.0)
        with patch.object(r, "alive", side_effect=lambda e: (_ for _ in ()).throw(OSError("x"))
                          if e["pid"] == 93 else False):
            result = c.reap(30)
        self.assertEqual({i["pid"]: i["outcome"] for i in result["results"]}, {93: "failed", 94: "gone"})

    # ---------- 启动器的关闭请求 ----------

    def test_task_validates_close_request(self):
        good = {"id": "x", "action": "close", "pid": 5, "created": 50}
        self.assertEqual(t.validate_close(good), (5, 50))
        for bad in ({**good, "extra": 1}, {**good, "pid": "5"}, {**good, "created": 0}, {**good, "action": "kill"}):
            with self.assertRaises(t.LaunchError):
                t.validate_close(bad)
        allowed = [r"D:\mhxy_dev"]
        t.check_target(r"d:\MHXY_DEV\mhmain.exe", 1, 1, allowed)
        for image, created in ((r"D:\mhxy_dev\mhmain.exe", 2), (r"D:\mhxy_dev\other.exe", 1),
                               (r"D:\elsewhere\mhmain.exe", 1)):
            with self.assertRaises(t.LaunchError):
                t.check_target(image, created, 1, allowed)

    def test_task_close_refuses_non_client_process(self):
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            created = r.process_info(child.pid)["created"]
            with self.assertRaises(t.LaunchError):  # 映像不是 mhmain.exe
                t.close(child.pid, created, [str(Path(sys.executable).parent)])
            with self.assertRaises(t.LaunchError):  # 创建时间不符
                t.close(child.pid, created + 1, [str(Path(sys.executable).parent)])
            self.assertIsNone(child.poll())
        finally:
            child.kill()
            child.wait()
        self.assertEqual(t.close(child.pid, created, []), "gone")

    def test_task_main_dispatches_close(self):
        request = self.base / "request.json"
        request.write_text(json.dumps({"id": "r1", "action": "close", "pid": 5, "created": 50}), encoding="utf-8")
        with patch.object(t, "close", return_value="closed") as closer:
            code = t.main(["--request", str(request), "--config", str(self.base / "c.json"), "--allow", "D:/x"])
        self.assertEqual(code, 0)
        closer.assert_called_once_with(5, 50, ["D:/x"])
        result = json.loads((self.base / "result.json").read_text(encoding="utf-8"))
        self.assertEqual((result["id"], result["pid"], result["closed"], result["error"]), ("r1", 5, "closed", None))
        self.assertFalse(request.exists())


if __name__ == "__main__":
    unittest.main()
