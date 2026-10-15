"""codex_cli：命令构造、环境与防递归、续接、并发状态读写和设备锁；不调用真实 Codex。"""
import importlib.util
import json
from pathlib import Path
import sys
import threading
from unittest.mock import MagicMock, patch

import pytest

spec = importlib.util.spec_from_file_location("codex_cli", Path(__file__).resolve().parents[1] / "scripts/codex_cli.py")
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)

CONFIG = {"model_provider": "p", "model_providers": {"p": {"base_url": "http://x"}},
          "mcp_servers": {"mh-game-mcp": {"url": "https://game/mcp", "disabled_tools": ["x"]},
                          "codeviewer-mcp": {"url": "https://cv/mcp", "http_headers": {"X-Access-Token": "secret"}},
                          "other": {"url": "http://other"}}}
TEST_RESULT = {"status": "passed", "cases": ["local probe"], "errors": [],
               "unverified": [], "restoration": "not_needed"}


@pytest.fixture(autouse=True)
def fake_cli(monkeypatch, tmp_path):
    monkeypatch.setattr(c, "cli_prefix", lambda: ["codex"])
    monkeypatch.setattr(c, "user_config", lambda: CONFIG)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.delenv(c.GUARD, raising=False)


def option(command, value):
    """返回某个 -c 覆盖是否存在。"""
    return any(a == "-c" and b == value for a, b in zip(command, command[1:]))


def make_root(tmp_path, name="proj"):
    root = tmp_path / name
    (root / ".mhxy-workspace").mkdir(parents=True)
    (root / "AGENTS.md").write_text("rules", encoding="utf-8")
    return root


# ---- 命令构造 ----

@pytest.mark.parametrize("kind", ["investigate", "review"])
def test_read_only_kinds_use_project_root_and_no_mcp(tmp_path, kind):
    command = c.cli_command(tmp_path, {"instructions": "x"}, {"kind": kind, "root": "R"})
    assert command[:2] == ["codex", "exec"] and command[-1] == "-"
    assert command[command.index("--sandbox") + 1] == "read-only"
    assert command[command.index("-C") + 1] == "R"
    assert command[command.index("-m") + 1] == "gemini-4-argon"
    for value in ('model_reasoning_effort="medium"', "agents.enabled=false", "features.multi_agent=false",
                  "features.hooks=false", "plugins={}", "mcp_servers={}", 'approval_policy="never"',
                  'model_provider="p"'):
        assert option(command, value), value
    assert "--ignore-user-config" in command and "-o" in command and "--add-dir" not in command


def test_test_kind_whitelists_mcp_and_write_dirs(tmp_path):
    task = {"mcp_tools": {"mh-game-mcp": ["execute_code"]}, "write_dirs": ["W"]}
    command = c.cli_command(tmp_path, task, {"kind": "test", "root": "R"})
    assert command[command.index("--sandbox") + 1] == "workspace-write"
    assert command[command.index("-C") + 1] == str(tmp_path)
    assert command[command.index("--add-dir") + 1] == "W"
    servers = [b for a, b in zip(command, command[1:]) if a == "-c" and b.startswith("mcp_servers=")]
    assert "execute_code" in servers[0] and '"approve"' in servers[0]
    assert "other" not in servers[0] and "disabled_tools" not in servers[0]


def test_investigate_gets_only_listed_read_only_mcp(tmp_path):
    task = {"instructions": "x", "mcp_tools": {"codeviewer-mcp": ["get_commit_info_by_rid"]}}
    c.prepare(tmp_path, "investigate", task, None)
    command = c.cli_command(tmp_path, task, {"kind": "investigate", "root": "R"})
    servers = [b for a, b in zip(command, command[1:]) if a == "-c" and b.startswith("mcp_servers=")][0]
    assert "get_commit_info_by_rid" in servers and "X-Access-Token" in servers and '"approve"' in servers
    assert "other" not in servers and command[command.index("--sandbox") + 1] == "read-only"


@pytest.mark.parametrize("kind,tools", [("investigate", {"mh-game-mcp": ["execute_code"]}),
                                        ("investigate", ["codeviewer-mcp"]),
                                        ("review", {"codeviewer-mcp": ["read_file"]})])
def test_mcp_outside_read_only_allowlist_rejected(tmp_path, kind, tools):
    with pytest.raises(ValueError, match="只读 MCP"):
        c.prepare(tmp_path, kind, {"instructions": "x", "mcp_tools": tools}, None)


def test_unconfigured_mcp_rejected(tmp_path):
    with pytest.raises(ValueError, match="未配置"):
        c.cli_command(tmp_path, {"mcp_tools": {"nope": ["a"]}}, {"kind": "test", "root": "R"})


def test_resume_command_continues_session(tmp_path):
    command = c.cli_command(tmp_path, {}, {"kind": "review", "root": "R", "resume_session": "S1"})
    assert command[:3] == ["codex", "exec", "resume"]
    assert command[-2:] == ["S1", "-"]
    assert "--sandbox" not in command and "-C" not in command
    assert option(command, 'sandbox_mode="read-only"') and option(command, "agents.enabled=false")


def test_command_uses_state_model(tmp_path):
    command = c.cli_command(tmp_path, {}, {"kind": "review", "root": "R", "model": "gemini-4-argon", "effort": "medium"})
    assert command[command.index("-m") + 1] == "gemini-4-argon"
    assert option(command, 'model_reasoning_effort="medium"')
    # Gemini 带 --output-schema 会被上游拒绝，只有 GPT 系列传。
    assert "--output-schema" not in command
    assert "--output-schema" in c.cli_command(tmp_path, {}, {"kind": "review", "root": "R", "model": "gpt-6-sol"})


# ---- 模型选择 ----

CATALOG = {"models": [
    {"slug": "gpt-6.1-sol", "default_reasoning_level": "high",
     "supported_reasoning_levels": [{"effort": "high"}, {"effort": "xhigh"}]},
    {"slug": "gemini-4-argon", "default_reasoning_level": "medium",
     "supported_reasoning_levels": [{"effort": "low"}, {"effort": "medium"}]}]}


def catalog_config(tmp_path):
    c.write_json(tmp_path / "catalog.json", CATALOG)
    return {"model_catalog_json": str(tmp_path / "catalog.json")}


def test_pick_model_defaults_without_catalog():
    assert c.pick_model(None, None, {}) == (c.MODEL, c.EFFORT)
    assert c.pick_model("any-model", "low", {}) == ("any-model", "low")


def test_pick_model_validates_against_catalog(tmp_path):
    config = catalog_config(tmp_path)
    assert c.pick_model(None, None, config) == ("gemini-4-argon", "medium")
    # 默认强度不受支持时退回目录给的默认档位。
    assert c.pick_model("gpt-6.1-sol", None, config) == ("gpt-6.1-sol", "high")
    with pytest.raises(ValueError, match="模型目录中没有"):
        c.pick_model("nope", None, config)
    with pytest.raises(ValueError, match="不支持推理强度"):
        c.pick_model("gemini-4-argon", "high", config)


def test_pick_model_resume_inherits_previous(tmp_path):
    previous = {"model": "gemini-4-argon", "effort": "low"}
    assert c.pick_model(None, None, {}, previous) == ("gemini-4-argon", "low")
    # 换模型时不沿用上一轮的强度。
    assert c.pick_model("gpt-6.1-sol", None, catalog_config(tmp_path), previous) == ("gpt-6.1-sol", "high")


# ---- 环境与防递归 ----

def test_child_env_strips_codex_vars_and_sets_guard():
    env = c.child_env({"CODEX_THREAD_ID": "t", "codex_x": "y", "CODEX_HOME": "h", "PATH": "p"})
    assert env == {"CODEX_HOME": "h", "PATH": "p", c.GUARD: "1"}


def test_start_refuses_inside_child(tmp_path, monkeypatch):
    monkeypatch.setenv(c.GUARD, "1")
    with pytest.raises(ValueError, match="不得再委派"):
        c.start(make_root(tmp_path), "investigate", tmp_path / "missing.json")


def test_monitor_launches_cli_with_child_env(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_SESSION_ID", "parent")
    c.write_json(tmp_path / "state.json", {"status": "starting", "kind": "investigate"})
    (tmp_path / "prompt.txt").write_text("p", encoding="utf-8")
    with patch.object(c.subprocess, "Popen", side_effect=OSError("x")) as launch:
        c.monitor(tmp_path, ["codex"], idle_seconds=.1)
    env = launch.call_args.kwargs["env"]
    assert env[c.GUARD] == "1" and "CODEX_SESSION_ID" not in env


# ---- 任务内容 ----

def test_references_append_to_defaults(tmp_path):
    root = make_root(tmp_path)
    refs = c.references(root, "review", {"references": ["X.md", str(root / "AGENTS.md")]})
    assert refs[0] == str(root / "AGENTS.md")
    assert refs[1].endswith("code-review.md") and refs[2].endswith("engineering-principles.md")
    assert refs[-1] == "X.md" and len(refs) == 4


def test_prompt_keeps_default_references_and_no_delegation(tmp_path):
    root = make_root(tmp_path)
    task = tmp_path / "t.json"
    c.write_json(task, {"instructions": "q", "references": ["extra.md"]})
    with patch.object(c.subprocess, "Popen", side_effect=publish_worker):
        job = Path(c.start(root, "investigate", task)["job"])
    prompt = (job / "prompt.txt").read_text(encoding="utf-8")
    payload, end = json.JSONDecoder().raw_decode(prompt, prompt.index("{"))
    assert payload["references"] == [str(root / "AGENTS.md"), "extra.md"]
    assert "不得派生、调用或者请求新的子代理" in prompt
    # 非 GPT 模型没有 --output-schema，schema 写进提示末尾约束最终回复。
    assert prompt.endswith(json.dumps(c.SCHEMAS["investigate"], ensure_ascii=False))
    assert job.parent == root / ".mhxy-workspace" / "codex-cli"


def test_non_test_kind_rejects_device_fields(tmp_path):
    with pytest.raises(ValueError, match="只有 test"):
        c.prepare(tmp_path, "investigate", {"instructions": "x", "devid": "d"}, None)


def test_resume_requires_finished_review(tmp_path):
    previous = tmp_path / "prev"
    previous.mkdir()
    c.write_json(previous / "state.json", {"kind": "review", "status": "running", "session_id": "S"})
    with pytest.raises(ValueError, match="会话 ID"):
        c.prepare(tmp_path, "review", {"instructions": "x"}, previous)
    c.write_json(previous / "state.json", {"kind": "review", "status": "completed", "session_id": "S"})
    with pytest.raises(ValueError, match="只用于 review"):
        c.prepare(tmp_path, "investigate", {"instructions": "x"}, previous)
    assert c.prepare(tmp_path, "review", {"instructions": "x"}, previous)[1] == "S"


def test_start_resume_records_session(tmp_path):
    root = make_root(tmp_path)
    previous = tmp_path / "prev"
    previous.mkdir()
    c.write_json(previous / "state.json", {"kind": "review", "status": "completed", "session_id": "S"})
    task = tmp_path / "t.json"
    c.write_json(task, {"instructions": "round 2"})
    with patch.object(c.subprocess, "Popen", side_effect=publish_worker):
        job = Path(c.start(root, "review", task, previous)["job"])
    state = c.read_json(job / "state.json")
    assert state["resume_session"] == "S" and state["kind"] == "review"
    assert (state["model"], state["effort"]) == (c.MODEL, c.EFFORT)


def test_start_records_chosen_model(tmp_path):
    root = make_root(tmp_path)
    task = tmp_path / "t.json"
    c.write_json(task, {"instructions": "q"})
    with patch.object(c.subprocess, "Popen", side_effect=publish_worker):
        job = Path(c.start(root, "investigate", task, model="gemini-4-argon", effort="low")["job"])
    state = c.read_json(job / "state.json")
    assert (state["model"], state["effort"]) == ("gemini-4-argon", "low")


# ---- 并发读写 ----

def test_read_json_retries_permission_error(tmp_path):
    path = tmp_path / "s.json"
    path.write_text('{"a": 1}', encoding="utf-8")
    original = Path.read_text
    calls = []

    def flaky(self, *args, **kwargs):
        calls.append(1)
        if len(calls) < 3:
            raise PermissionError("busy")
        return original(self, *args, **kwargs)

    with patch.object(Path, "read_text", flaky), patch.object(c.time, "sleep"):
        assert c.read_json(path) == {"a": 1}
    assert len(calls) == 3


def test_write_json_retries_replace_and_cleans_temp(tmp_path):
    original = c.os.replace
    calls = []

    def flaky(src, dst):
        calls.append(1)
        if len(calls) == 1:
            raise PermissionError("busy")
        original(src, dst)

    with patch.object(c.os, "replace", flaky), patch.object(c.time, "sleep"):
        c.write_json(tmp_path / "s.json", {"b": 2})
    assert c.read_json(tmp_path / "s.json") == {"b": 2}
    assert [p.name for p in tmp_path.iterdir()] == ["s.json"]


def test_concurrent_reads_during_writes(tmp_path):
    path = tmp_path / "s.json"
    c.write_json(path, {"n": 0})
    errors = []

    def reader():
        for _ in range(200):
            try:
                c.read_json(path)
            except Exception as error:
                errors.append(error)

    thread = threading.Thread(target=reader)
    thread.start()
    for n in range(200):
        c.write_json(path, {"n": n})
    thread.join()
    assert not errors


# ---- worker 与状态 ----

def worker_job(tmp_path, **state):
    c.write_json(tmp_path / "state.json", {"status": "starting", "kind": "investigate", "root": "R", **state})
    c.write_json(tmp_path / "task.json", {"instructions": "x"})
    return tmp_path


def test_worker_runs_once(tmp_path):
    job = worker_job(tmp_path)
    with patch.object(c, "monitor") as run:
        assert c.worker(job) == 0
        assert c.worker(job) == 1
    assert run.call_count == 1


@pytest.mark.parametrize("state", [{"status": "running"}, {"cli_pid": 1}])
def test_worker_refuses_reentry(tmp_path, state):
    job = worker_job(tmp_path, **state)
    with patch.object(c, "monitor") as run, patch.object(c, "alive", return_value=True):
        assert c.worker(job) == 1
    run.assert_not_called()
    assert c.read_json(job / "state.json").get("monitor_pid") is None


def test_status_persists_failure_when_monitor_gone(tmp_path):
    c.write_json(tmp_path / "state.json", {"status": "running", "monitor_pid": 99})
    with patch.object(c, "alive", return_value=False):
        assert c.status(tmp_path)["status"] == "failed"
    assert c.read_json(tmp_path / "state.json")["status"] == "failed"


def test_status_detects_dead_worker_before_publish(tmp_path):
    c.write_json(tmp_path / "state.json", {"status": "starting"})
    c.write_json(tmp_path / "worker.json", {"pid": 99, "started": 1})
    with patch.object(c, "alive", return_value=False):
        assert c.status(tmp_path)["status"] == "failed"


# ---- 设备锁 ----

def publish_worker(argv, **kwargs):
    """模拟 worker 启动后发布自己的 PID。"""
    job = Path(argv[argv.index("--job") + 1])
    state = c.read_json(job / "state.json")
    state["monitor_pid"] = 4242
    c.write_json(job / "state.json", state)
    process = MagicMock(pid=4242)
    process.poll.return_value = None
    return process


def silent_worker(exited):
    def launch(argv, **kwargs):
        process = MagicMock(pid=4343)
        process.poll.return_value = 1 if exited else None
        return process
    return launch


def device_task(tmp_path):
    task = tmp_path / "task.json"
    c.write_json(task, {"devid": "dev", "instructions": "t", "write_dirs": []})
    return task


def test_device_locked_across_workspaces(tmp_path):
    task = device_task(tmp_path)
    with patch.object(c.subprocess, "Popen", side_effect=publish_worker):
        first = c.start(make_root(tmp_path, "one"), "test", task)
        with pytest.raises(ValueError, match="设备已有任务"):
            c.start(make_root(tmp_path, "two"), "test", task)
    state = c.read_json(Path(first["job"]) / "state.json")
    assert Path(state["lock"]).exists() and state["released"] is False


def test_start_timeout_keeps_starting_and_lock(tmp_path, monkeypatch):
    monkeypatch.setattr(c, "START_SECONDS", 0.2)
    with patch.object(c.subprocess, "Popen", side_effect=silent_worker(exited=False)):
        result = c.start(make_root(tmp_path), "test", device_task(tmp_path))
    state = c.read_json(Path(result["job"]) / "state.json")
    assert result["status"] == "starting" and "note" in result
    assert state["status"] == "starting" and Path(state["lock"]).exists()


def test_dead_worker_releases_lock(tmp_path):
    with patch.object(c.subprocess, "Popen", side_effect=silent_worker(exited=True)):
        result = c.start(make_root(tmp_path), "test", device_task(tmp_path))
    state = c.read_json(Path(result["job"]) / "state.json")
    assert state["status"] == "failed" and not Path(state["lock"]).exists()


def test_setup_failure_removes_job_and_lock(tmp_path):
    root = make_root(tmp_path)
    with patch.object(c, "cli_prefix", side_effect=RuntimeError("未安装 Codex CLI")):
        with pytest.raises(RuntimeError):
            c.start(root, "test", device_task(tmp_path))
    assert list((root / ".mhxy-workspace/codex-cli").iterdir()) == []
    assert not list((tmp_path / "local/mhxy-cli-testing/locks").iterdir())


def test_release_rules(tmp_path, capsys):
    lock = tmp_path / "lock.json"
    c.write_json(lock, {"job": str(tmp_path)})
    base = {"kind": "test", "lock": str(lock), "released": False}
    c.write_json(tmp_path / "state.json", {**base, "status": "running", "monitor_pid": 1})
    argv = ["codex_cli", "release", "--job", str(tmp_path), "--restored"]
    with patch.object(sys, "argv", argv), patch.object(c, "alive", return_value=True):
        assert c.main() == 2
    c.write_json(tmp_path / "state.json", {**base, "status": "timed_out"})
    with patch.object(sys, "argv", argv[:-1]):
        assert c.main() == 2
    assert lock.exists()
    with patch.object(sys, "argv", argv):
        assert c.main() == 0
    assert not lock.exists()
    assert c.read_json(tmp_path / "state.json")["released"] is True
    c.write_json(tmp_path / "state.json", {"kind": "review", "status": "completed"})
    with patch.object(sys, "argv", argv):
        assert c.main() == 2


# ---- 监控真实本地子进程 ----

EXITS = 60  # 会自行退出的探针用宽松的静默上限，机器负载高时启动慢也不会被误判为超时。


def run_probe(tmp_path, code, kind="test", idle=0.4, cancel=False):
    c.write_json(tmp_path / "state.json", {"status": "starting", "kind": kind, "restoration": "unknown"})
    (tmp_path / "prompt.txt").write_text("probe", encoding="utf-8")
    timer = threading.Timer(0.15, lambda: (tmp_path / "cancel").touch()) if cancel else None
    if timer:
        timer.start()
    c.monitor(tmp_path, [sys.executable, "-u", "-c", code], idle_seconds=idle)
    if timer:
        timer.join()
    return c.read_json(tmp_path / "state.json")


def result_code(result):
    return "from pathlib import Path; Path('result.json').write_text(" + repr(json.dumps(result, ensure_ascii=False)) + ", encoding='utf-8')"


def test_silent_process_is_stopped(tmp_path):
    state = run_probe(tmp_path, "import time; time.sleep(10)")
    assert state["status"] == "timed_out" and state["exit_code"] is not None


def test_output_refreshes_idle_and_records_session(tmp_path):
    code = ("import time,sys\nprint('{\"type\":\"thread.started\",\"thread_id\":\"T1\"}', flush=True)\n"
            "for i in range(8):\n sys.stderr.write('x'); sys.stderr.flush(); time.sleep(.1)\n" + result_code(TEST_RESULT))
    state = run_probe(tmp_path, code)
    assert state["status"] == "completed" and state["result"] == TEST_RESULT
    assert state["restoration"] == "not_needed" and state["session_id"] == "T1"


def test_review_result_is_formatted(tmp_path):
    result = {"summary": "s", "items": [{"level": "必须修改", "location": "a.py:3", "problem": "p",
                                         "basis": "b", "suggestion": "fix"}]}
    state = run_probe(tmp_path, result_code(result), kind="review", idle=EXITS)
    assert state["status"] == "completed" and state["must_fix"] == 1
    assert state["formatted"] == ["[必须修改] a.py:3 —— p；b；fix"]


def test_fenced_json_result_is_accepted(tmp_path):
    text = "```json\n" + json.dumps({"conclusion": "c", "evidence": ["a:1"], "uncertainties": []}) + "\n```"
    code = "from pathlib import Path; Path('result.json').write_text(" + repr(text) + ", encoding='utf-8')"
    state = run_probe(tmp_path, code, kind="investigate", idle=EXITS)
    assert state["status"] == "completed" and state["result"]["conclusion"] == "c"


def test_zero_exit_without_valid_result_is_failed(tmp_path):
    state = run_probe(tmp_path, result_code({"conclusion": "x"}), kind="investigate", idle=EXITS)
    assert state["status"] == "failed" and state["exit_code"] == 0


def test_nonzero_exit_cannot_pass(tmp_path):
    state = run_probe(tmp_path, result_code(TEST_RESULT) + "; raise SystemExit(3)", idle=EXITS)
    assert state["status"] == "failed"


def test_cancel_stops_process(tmp_path):
    state = run_probe(tmp_path, "import time; time.sleep(10)", cancel=True)
    assert state["status"] == "cancelled" and state["restoration"] == "unknown"


def test_monitor_failure_never_records_command(tmp_path):
    c.write_json(tmp_path / "state.json", {"status": "starting", "kind": "test"})
    (tmp_path / "prompt.txt").write_text("probe", encoding="utf-8")
    with patch.object(c.subprocess, "Popen", side_effect=OSError("secret-auth-value")):
        c.monitor(tmp_path, ["secret-auth-value"], idle_seconds=.1)
    state = c.read_json(tmp_path / "state.json")
    assert state["status"] == "failed" and "secret-auth-value" not in json.dumps(state)


def test_outside_and_linked_write_directory_rejected(tmp_path):
    base = tmp_path / ".mhxy-workspace"
    base.mkdir()
    with pytest.raises(ValueError):
        c.checked_directory(tmp_path / "business", base)
    with pytest.raises(ValueError):
        c.checked_directory(base, base)
    assert c.checked_directory(base / "tests", base) == base / "tests"


# ---- 孤儿 CLI、release 复核与原生 verifier 设备锁 ----

def test_prompt_marks_main_session_rules(tmp_path):
    root = make_root(tmp_path)
    task = tmp_path / "t.json"
    c.write_json(task, {"instructions": "q"})
    with patch.object(c.subprocess, "Popen", side_effect=publish_worker):
        job = Path(c.start(root, "investigate", task)["job"])
    prompt = (job / "prompt.txt").read_text(encoding="utf-8")
    assert "「会话开始」「开发流程」「按需读取」是主会话规则" in prompt and "「项目约定」「边界」" in prompt


def test_alive_detects_pid_reuse():
    pid = c.os.getpid()
    assert c.alive(pid, c.started_at(pid)) and not c.alive(pid, -1)


def test_orphan_cli_keeps_lock_and_blocks_release(tmp_path, monkeypatch):
    monkeypatch.setattr(c, "RELEASE_GRACE", 0)
    lock = tmp_path / "lock.json"
    c.write_json(lock, {"job": str(tmp_path)})
    c.write_json(tmp_path / "state.json", {"kind": "test", "status": "running", "monitor_pid": 99,
                                           "cli_pid": 100, "lock": str(lock), "released": False})
    with patch.object(c, "alive", side_effect=lambda pid, started=None: pid == 100):
        state = c.status(tmp_path)
        assert state["status"] == "failed" and state["orphan_cli_pid"] == 100 and "仍在运行" in state["error"]
        with pytest.raises(ValueError, match="100"):
            c.release(tmp_path)
    assert lock.exists() and c.read_json(tmp_path / "state.json")["released"] is False
    with patch.object(c, "alive", return_value=False):
        assert c.release(tmp_path)["released"] is True
    assert not lock.exists()


def test_release_waits_for_monitor_exit(tmp_path, monkeypatch):
    monkeypatch.setattr(c, "RELEASE_GRACE", 0)
    c.write_json(tmp_path / "state.json", {"kind": "test", "status": "completed", "monitor_pid": 99,
                                           "lock": str(tmp_path / "lock.json"), "released": False})
    with patch.object(c, "alive", return_value=True), pytest.raises(ValueError, match="仍在运行"):
        c.release(tmp_path)


def test_busy_device_leaves_no_job_directory(tmp_path):
    task = device_task(tmp_path)
    second = make_root(tmp_path, "two")
    with patch.object(c.subprocess, "Popen", side_effect=publish_worker):
        c.start(make_root(tmp_path, "one"), "test", task)
        with pytest.raises(ValueError, match="设备已有任务"):
            c.start(second, "test", task)
    assert list((second / ".mhxy-workspace/codex-cli").iterdir()) == []


def run_main(argv, capsys):
    with patch.object(sys, "argv", ["codex_cli", *argv]):
        code = c.main()
    return code, json.loads(capsys.readouterr().out)


def test_native_lock_and_release(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv(c.GUARD, "1")  # lock／release 不启动 Codex，与防递归标记无关。
    root = make_root(tmp_path)
    code, state = run_main(["lock", "--root", str(root), "--devid", "dev"], capsys)
    assert code == 0 and state["status"] == c.NATIVE and state["kind"] == "test" and state["released"] is False
    job = state["job"]
    assert Path(state["lock"]).exists() and c.read_json(Path(job) / "state.json") == state
    # 同一设备不能再被 lock 或 test 任务占用，失败时不留下任务目录。
    code, error = run_main(["lock", "--root", str(root), "--devid", "dev"], capsys)
    assert code == 2 and "设备已有任务" in error["error"]
    assert [p.name for p in (root / ".mhxy-workspace/codex-cli").iterdir()] == [Path(job).name]
    for command in ("wait", "cancel"):
        assert run_main([command, "--job", job], capsys)[0] == 2
    code, state = run_main(["release", "--job", job, "--restored"], capsys)
    assert code == 0 and state["released"] is True and not Path(state["lock"]).exists()


def test_lock_failure_before_state_removes_lock_and_job(tmp_path):
    root = make_root(tmp_path)
    with patch.object(c, "write_json", side_effect=OSError("disk")), pytest.raises(OSError):
        c.lock(root, "dev")
    assert list((root / ".mhxy-workspace/codex-cli").iterdir()) == []
    assert not list((tmp_path / "local/mhxy-cli-testing/locks").iterdir())


# ---- 启动记录、PID 复用与 release 竞争 ----

def test_worker_record_failure_keeps_job_and_lock(tmp_path):
    original = c.write_json

    def failing(path, value):
        if Path(path).name == "worker.json":
            raise OSError("disk")
        original(path, value)

    root = make_root(tmp_path)
    with patch.object(c.subprocess, "Popen", side_effect=silent_worker(exited=False)),             patch.object(c, "write_json", side_effect=failing), patch.object(c, "stop_tree") as stop,             pytest.raises(OSError):
        c.start(root, "test", device_task(tmp_path))
    stop.assert_called_once()
    job = next((root / ".mhxy-workspace/codex-cli").iterdir())
    state = c.read_json(job / "state.json")
    assert state["status"] == "failed" and Path(state["lock"]).exists()


def test_starting_fallback_detects_worker_pid_reuse(tmp_path):
    c.write_json(tmp_path / "state.json", {"status": "starting"})
    c.write_json(tmp_path / "worker.json", {"pid": c.os.getpid(), "started": -1})
    assert c.status(tmp_path)["status"] == "failed"
    c.write_json(tmp_path / "state.json", {"status": "starting"})
    c.write_json(tmp_path / "worker.json", {"pid": c.os.getpid(), "started": c.started_at(c.os.getpid())})
    assert c.status(tmp_path)["status"] == "starting"


def released_job(tmp_path, name="a"):
    job = tmp_path / name
    job.mkdir()
    lock = tmp_path / "lock.json"
    c.write_json(job / "state.json", {"kind": "test", "status": "completed", "lock": str(lock), "released": False})
    return job, lock


def test_release_is_idempotent(tmp_path):
    job, lock = released_job(tmp_path)
    c.write_json(lock, {"job": str(job)})
    assert c.release(job)["released"] is True and not lock.exists()
    c.write_json(lock, {"job": "other"})  # 之后其他任务加的锁不受影响。
    assert c.release(job)["released"] is True and c.read_json(lock) == {"job": "other"}


def test_release_does_not_delete_lock_taken_over_during_check(tmp_path):
    job, lock = released_job(tmp_path)
    c.write_json(lock, {"job": str(job)})
    original = c.os.rename

    def racing(src, dst):
        c.write_json(lock, {"job": "new"})  # 核对归属之后、改名之前，锁换成了新任务的。
        original(src, dst)

    with patch.object(c.os, "rename", racing), pytest.raises(ValueError, match="不属于本任务"):
        c.release(job)
    assert c.read_json(lock) == {"job": "new"} and [p.name for p in tmp_path.iterdir()] == ["a", "lock.json"]
    assert c.read_json(job / "state.json")["released"] is False


def test_release_keeps_moved_lock_when_device_reacquired(tmp_path):
    job, lock = released_job(tmp_path)
    c.write_json(lock, {"job": str(job)})
    original = c.os.rename

    def racing(src, dst):
        c.write_json(lock, {"job": "new"})
        original(src, dst)
        c.write_json(lock, {"job": "third"})  # 改名后原位置又被另一个任务占用。

    with patch.object(c.os, "rename", racing), pytest.raises(ValueError, match="原锁文件保留"):
        c.release(job)
    assert c.read_json(lock) == {"job": "third"}
    assert [c.read_json(p) for p in tmp_path.glob("lock.json.*.releasing")] == [{"job": "new"}]
