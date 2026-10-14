"""用真实本地子进程核验 CLI 监控，不操作游戏。"""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
from unittest.mock import patch

import pytest

spec = importlib.util.spec_from_file_location("cli_testing", Path(__file__).resolve().parents[1] / "scripts/cli_testing.py")
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)

RESULT = {"status": "passed", "cases": ["local probe"], "errors": [],
          "unverified": [], "restoration": "not_needed"}


def run_probe(tmp_path, code, idle=0.4, cancel=False):
    c.write_json(tmp_path / "state.json", {"status": "starting", "restoration": "unknown"})
    (tmp_path / "prompt.txt").write_text("probe", encoding="utf-8")
    timer = None
    if cancel:
        timer = threading.Timer(0.15, lambda: (tmp_path / "cancel").touch())
        timer.start()
    c.monitor(tmp_path, [sys.executable, "-u", "-c", code], idle_seconds=idle)
    if timer:
        timer.join()
    return c.read_json(tmp_path / "state.json")


def result_code():
    return "from pathlib import Path; Path('result.json').write_text(" + repr(json.dumps(RESULT)) + ")"


def test_silent_process_is_stopped(tmp_path):
    state = run_probe(tmp_path, "import time; time.sleep(10)")
    assert state["status"] == "timed_out"
    assert state["exit_code"] is not None
    assert state["restoration"] == "unknown"


def test_output_refreshes_idle_without_total_limit(tmp_path):
    code = "import time,sys\nfor i in range(8):\n sys.stderr.write('x'); sys.stderr.flush(); time.sleep(.1)\n" + result_code()
    state = run_probe(tmp_path, code)
    assert state["status"] == "completed"
    assert state["result"] == RESULT
    assert (tmp_path / "stderr.log").read_bytes() == b"xxxxxxxx"


def test_zero_exit_without_result_is_failed(tmp_path):
    state = run_probe(tmp_path, "print('done')")
    assert state["status"] == "failed"
    assert state["exit_code"] == 0


def test_cancel_stops_process_and_keeps_recovery_unknown(tmp_path):
    state = run_probe(tmp_path, "import time; time.sleep(10)", cancel=True)
    assert state["status"] == "cancelled"
    assert state["exit_code"] is not None
    assert state["restoration"] == "unknown"


def test_nonzero_exit_cannot_pass(tmp_path):
    state = run_probe(tmp_path, result_code() + "; raise SystemExit(3)")
    assert state["status"] == "failed"


def test_outside_and_linked_write_directory_rejected(tmp_path):
    base = tmp_path / ".mhxy-workspace"
    base.mkdir()
    with pytest.raises(ValueError):
        c.checked_directory(tmp_path / "business", base)
    with pytest.raises(ValueError):
        c.checked_directory(base, base)
    assert c.checked_directory(base / "tests", base) == base / "tests"


def test_device_is_locked_across_workspaces(tmp_path):
    task = tmp_path / "task.json"
    c.write_json(task, {"devid": "test-device", "instructions": "local test"})
    root1, root2 = tmp_path / "one", tmp_path / "two"
    root1.mkdir()
    root2.mkdir()
    with patch.dict(c.os.environ, {"LOCALAPPDATA": str(tmp_path / "local")}), \
         patch.object(c, "cli_command", return_value=["unused"]), \
         patch.object(c.subprocess, "Popen") as popen:
        popen.return_value.pid = 123
        popen.return_value.poll.return_value = None
        original_read = c.read_json
        def worker_ready(path):
            value = original_read(path)
            if Path(path).name == "state.json":
                value["monitor_pid"] = 123
            return value
        with patch.object(c, "read_json", side_effect=worker_ready):
            first = c.start(root1, task)
        with pytest.raises(ValueError, match="设备已有任务"):
            c.start(root2, task)
        state = c.read_json(Path(first["job"]) / "state.json")
        assert Path(state["lock"]).exists()


def test_monitor_failure_never_prints_sensitive_command(tmp_path):
    c.write_json(tmp_path / "state.json", {"status": "starting"})
    (tmp_path / "prompt.txt").write_text("probe", encoding="utf-8")
    with patch.object(c.subprocess, "Popen", side_effect=OSError("secret-auth-value")):
        c.monitor(tmp_path, ["secret-auth-value"], idle_seconds=.1)
    state = c.read_json(tmp_path / "state.json")
    assert state["status"] == "failed"
    assert "secret-auth-value" not in json.dumps(state)


def test_release_requires_terminal_state_and_explicit_restoration(tmp_path, capsys):
    lock = tmp_path / "lock.json"
    c.write_json(lock, {"job": str(tmp_path)})
    c.write_json(tmp_path / "state.json", {"status": "running", "lock": str(lock)})
    with patch.object(sys, "argv", ["cli_testing", "release", "--job", str(tmp_path), "--restored"]):
        assert c.main() == 2
    assert lock.exists()
    c.write_json(tmp_path / "state.json", {"status": "timed_out", "lock": str(lock)})
    with patch.object(sys, "argv", ["cli_testing", "release", "--job", str(tmp_path)]):
        assert c.main() == 2
    assert lock.exists()
    with patch.object(sys, "argv", ["cli_testing", "release", "--job", str(tmp_path), "--restored"]):
        assert c.main() == 0
    assert not lock.exists()
