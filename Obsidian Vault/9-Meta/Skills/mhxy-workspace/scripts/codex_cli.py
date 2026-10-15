"""把调查、review、真机测试委派给 Codex CLI：后台运行、无输出超时、取消与设备锁。"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import queue
import shutil
import signal
import subprocess
import sys
import threading
import time
import tomllib
import uuid

SKILL = Path(__file__).resolve().parents[1]
TERMINAL = {"completed", "failed", "timed_out", "cancelled"}
KINDS = ("investigate", "review", "test")
MODEL = "gpt-6.1-sol"
EFFORT = "high"
IDLE_SECONDS = 600
START_SECONDS = 10
GUARD = "MHXY_CODEX_CHILD"
GAME_URL = "https://mh-game-mcp.eros.nie.netease.com/mcp"
PROVIDER_KEYS = ("model_provider", "model_providers", "model_catalog_json")
LEVELS = ["必须修改", "建议修改", "疑问"]
STRINGS = {"type": "array", "items": {"type": "string"}}


def obj(**properties):
    """构造 --output-schema 要求的严格对象：全部字段必填、不允许多余字段。"""
    return {"type": "object", "additionalProperties": False,
            "properties": properties, "required": list(properties)}


SCHEMAS = {
    "investigate": obj(conclusion={"type": "string"},
                       evidence=STRINGS, uncertainties=STRINGS),
    "review": obj(summary={"type": "string"},
                  items={"type": "array", "items": obj(
                      level={"type": "string", "enum": LEVELS}, location={"type": "string"},
                      problem={"type": "string"}, basis={"type": "string"},
                      suggestion={"type": "string"})}),
    "test": obj(status={"type": "string", "enum": ["passed", "failed", "blocked"]},
                cases=STRINGS, errors=STRINGS, unverified=STRINGS,
                restoration={"type": "string", "enum": ["restored", "unknown", "not_needed"]}),
}

ROLE = {
    "investigate": ("你是只读调查者。只读：不修改任何文件。回答任务中的问题，证据足够即停止；"
                    "conclusion 直接回答问题，evidence 每条写成“文件:行号 —— 说明”，"
                    "uncertainties 列出未确认的事项和最快的验证方法，严格区分事实与推断。"),
    "review": ("你是代码审查者。只读：不修改任何文件。按 code-review.md 的审查清单逐条审查，"
               "items 每条给出级别、文件:行号、问题、依据、建议的改法；"
               "没有必须修改的问题时 summary 写明“没有必须修改的问题”。"),
    "test": ("你是测试执行者。只写任务目录和允许的测试目录，不修改业务源码；需要用户判断时返回 blocked。"
             "默认按 exec-check.md 做改动执行检查。测试结束尽力恢复；结果按 schema 返回证据，"
             "不能把发送成功或覆盖率百分比当作测试通过。"),
}
DEFAULT_REFS = {"investigate": [], "review": ["code-review.md", "engineering-principles.md"],
                "test": ["cli.md", "game-debugging.md", "exec-check.md"]}
COMMON = ("你是被委派的执行者，不是顶层主会话：不得派生、调用或者请求新的子代理，"
          "不得运行 codex 或 codex_cli.py，不与用户核对需求。先读取 references 中的文件，再执行任务。\n")


def retry(action, attempts=40):
    """Windows 上 state.json 被并发读写时 os.replace／读取会短暂报 PermissionError，短暂重试。"""
    for attempt in range(attempts):
        try:
            return action()
        except (PermissionError, json.JSONDecodeError):
            if attempt == attempts - 1:
                raise
            time.sleep(0.05)


def read_json(path):
    """读取 UTF-8 JSON；文件被占用或正在替换时重试。"""
    return retry(lambda: json.loads(Path(path).read_text(encoding="utf-8-sig")))


def write_json(path, value):
    """原子发布 JSON，避免查询读到半个文件；目标被占用时重试替换。"""
    path = Path(path)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        retry(lambda: os.replace(temporary, path))
    finally:
        temporary.unlink(missing_ok=True)


def update_state(job, **fields):
    """读取并更新任务状态；只在没有并发写者的时刻调用。"""
    state = read_json(Path(job) / "state.json")
    state.update(fields)
    write_json(Path(job) / "state.json", state)
    return state


def checked_directory(path, base):
    """限制辅助目录范围并拒绝路径上的符号链接和 Windows junction。"""
    path, base = Path(path).absolute(), Path(base).resolve()
    if not path.is_relative_to(base):
        raise ValueError("write_dirs 必须位于当前项目 .mhxy-workspace 内")
    for component in [path, *path.parents]:
        if component.is_symlink() or (component.exists() and component.resolve() != component):
            raise ValueError("辅助目录不能经过符号链接或 junction")
        if component == base:
            break
    if path.resolve() == base:
        raise ValueError("write_dirs 必须是辅助目录的子目录")
    return path


def toml_value(value):
    """将已解析的配置值转成单次 CLI 覆盖参数，保留标量和嵌套表。"""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(toml_value(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{" + ", ".join(json.dumps(k) + "=" + toml_value(v) for k, v in value.items()) + "}"
    raise ValueError("不支持的 TOML 配置值")


def matches(value, schema):
    """按本文件 SCHEMAS 用到的 JSON Schema 子集校验结果。"""
    kind = schema["type"]
    if kind == "string":
        return isinstance(value, str) and value in schema.get("enum", [value])
    if kind == "array":
        return isinstance(value, list) and all(matches(v, schema["items"]) for v in value)
    return (isinstance(value, dict) and set(value) == set(schema["properties"])
            and all(matches(value[k], s) for k, s in schema["properties"].items()))


def child_env(environ=None):
    """子 Codex 的环境：去掉继承的 CODEX_*（保留 CODEX_HOME），加上防递归标记。"""
    environ = dict(os.environ if environ is None else environ)
    env = {k: v for k, v in environ.items() if not k.upper().startswith("CODEX_") or k.upper() == "CODEX_HOME"}
    env[GUARD] = "1"
    return env


def cli_prefix():
    """解析 CLI；Windows npm shim 通过 node 运行，避免 shell 引号展开。"""
    executable = shutil.which("codex")
    if not executable:
        raise RuntimeError("未安装 Codex CLI")
    if os.name == "nt" and Path(executable).suffix.lower() in {".cmd", ".ps1", ""}:
        script = Path(executable).parent / "node_modules/@openai/codex/bin/codex.js"
        node = shutil.which("node")
        if not script.is_file() or not node:
            raise RuntimeError("无法解析 npm Codex CLI 的 node 启动器")
        return [node, str(script)]
    return [executable]


def user_config():
    """读取用户 Codex 配置，只用于复制模型连接和 MCP 服务定义。"""
    path = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "config.toml"
    return tomllib.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def mcp_servers(task, config):
    """只接入任务列出的 MCP 工具并自动批准；未列出的服务一律不加载。"""
    servers = {}
    for server, tools in task.get("mcp_tools", {}).items():
        if not isinstance(tools, list) or not tools or any(not isinstance(t, str) or not t for t in tools):
            raise ValueError("mcp_tools 必须逐服务列出非空工具白名单")
        source = config.get("mcp_servers", {}).get(server)
        if server == "mh-game-mcp" and source is None:
            source = {"url": GAME_URL}
        if source is None:
            raise ValueError("请求的 MCP 服务未配置：" + server)
        servers[server] = dict(source, enabled=True, enabled_tools=tools,
                               default_tools_approval_mode="approve")
        servers[server].pop("disabled_tools", None)
    return servers


def cli_command(job, task, state):
    """构造固定模型、按类型限制沙箱和 MCP、禁用子代理的执行命令。

    Args:
        job: 任务目录。
        task: 任务文件内容。
        state: 任务状态，提供 kind、root 和 resume 的会话 ID。

    Returns:
        参数列表；可能含认证配置，不得写入日志或输出。
    """
    config = user_config()
    kind = state["kind"]
    sandbox = "workspace-write" if kind == "test" else "read-only"
    options = ["--ignore-user-config", "--skip-git-repo-check", "-m", MODEL,
               "-c", f'model_reasoning_effort="{EFFORT}"', "-c", 'approval_policy="never"',
               "-c", f'sandbox_mode="{sandbox}"', "-c", "agents.enabled=false",
               "-c", "features.multi_agent=false", "-c", "features.hooks=false", "-c", "plugins={}",
               "-c", "mcp_servers=" + toml_value(mcp_servers(task, config) if kind == "test" else {}),
               "--json", "--output-schema", str(job / "schema.json"), "-o", str(job / "result.json")]
    # 只复用模型连接配置，避免加载宿主插件、hooks 和无关 MCP；不记录含认证的命令。
    for key in PROVIDER_KEYS:
        if key in config:
            options += ["-c", key + "=" + toml_value(config[key])]
    if state.get("resume_session"):
        # resume 不接受 --sandbox／-C：沙箱用 -c 覆盖，目录由进程 cwd 决定。
        return cli_prefix() + ["exec", "resume", *options, state["resume_session"], "-"]
    options += ["--sandbox", sandbox, "-C", str(job if kind == "test" else state["root"])]
    for directory in task.get("write_dirs", []):
        options += ["--add-dir", directory]
    return cli_prefix() + ["exec", *options, "-"]


def stop_tree(process):
    """终止所持有的 CLI 进程树；不恢复远端客户端状态。"""
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait(timeout=10)


def session_id(job):
    """从 --json 事件流里取 thread.started 的会话 ID，供下一轮 review 续接。"""
    try:
        lines = (job / "stdout.jsonl").read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for line in lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get("type") == "thread.started" and event.get("thread_id"):
            return event["thread_id"]
    return None


def format_review(result):
    """把 review 结果排成 code-review.md 的逐条格式。"""
    return [f"[{i['level']}] {i['location']} —— {i['problem']}；{i['basis']}；{i['suggestion']}"
            for i in result["items"]]


def finish(job, state, returncode):
    """CLI 正常退出后校验结构化结果；退出码为 0 但结果不完整仍是 failed。"""
    state["exit_code"] = returncode
    try:
        result = read_json(job / "result.json")
        valid = matches(result, SCHEMAS[state["kind"]])
    except (OSError, ValueError):
        valid = False
    state["status"] = "completed" if returncode == 0 and valid else "failed"
    if valid:
        state["result"] = result
        if state["kind"] == "test":
            state["restoration"] = result["restoration"]
        if state["kind"] == "review":
            state["formatted"] = format_review(result)
            state["must_fix"] = sum(i["level"] == "必须修改" for i in result["items"])
    else:
        state["error"] = "CLI 未返回完整的结构化结果"


def monitor(job, command, idle_seconds=IDLE_SECONDS):
    """持续排空两路输出；只有 CLI 字节输出刷新静默计时，无总时长上限。"""
    state = read_json(job / "state.json")
    state.update(status="running", monitor_pid=os.getpid())
    write_json(job / "state.json", state)
    process = None
    streams = queue.Queue()
    last_output = time.monotonic()
    published = 0.0
    ended = 0

    def pump(pipe, name):
        """读取非换行输出，避免长行或 stderr 活跃被误判为静默。"""
        try:
            while True:
                data = os.read(pipe.fileno(), 4096)
                if not data:
                    break
                streams.put((name, data, time.monotonic()))
        finally:
            pipe.close()
            streams.put((name, None, time.monotonic()))

    try:
        if (job / "cancel").exists():
            state["status"] = "cancelled"
            return
        with open(job / "prompt.txt", "rb") as prompt:
            process = subprocess.Popen(command, stdin=prompt, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, cwd=state.get("cwd", job), env=child_env(),
                                       start_new_session=os.name != "nt",
                                       creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW)
                                       if os.name == "nt" else 0)
        state["cli_pid"] = process.pid
        state["last_output_at"] = time.time()
        write_json(job / "state.json", state)
        for pipe, name in ((process.stdout, "stdout"), (process.stderr, "stderr")):
            threading.Thread(target=pump, args=(pipe, name), daemon=True).start()
        with open(job / "stdout.jsonl", "ab") as stdout, open(job / "stderr.log", "ab") as stderr:
            while True:
                try:
                    name, data, timestamp = streams.get(timeout=0.05)
                    if data is None:
                        ended += 1
                    else:
                        (stdout if name == "stdout" else stderr).write(data)
                        (stdout if name == "stdout" else stderr).flush()
                        last_output = max(last_output, timestamp)
                        if time.time() - published >= 1:
                            # 限制写频率，减少与查询进程争用 state.json。
                            published = state["last_output_at"] = time.time()
                            write_json(job / "state.json", state)
                except queue.Empty:
                    pass
                if (job / "cancel").exists():
                    state["status"] = "cancelled"
                    stop_tree(process)
                    break
                if time.monotonic() - last_output >= idle_seconds:
                    state["status"] = "timed_out"
                    stop_tree(process)
                    break
                if process.poll() is not None and ended == 2:
                    finish(job, state, process.returncode)
                    break
    except Exception as error:
        state.update(status="failed", error=type(error).__name__ + ": 执行失败，检查日志和运行环境")
        if process is not None:
            try:
                stop_tree(process)
            except Exception:
                state["error"] += "；进程终止失败"
    finally:
        if process is not None:
            state["exit_code"] = process.poll()
        state["session_id"] = session_id(job) or state.get("resume_session")
        state["finished_at"] = time.time()
        write_json(job / "state.json", state)


def worker(job):
    """后台监控入口；只在任务仍为 starting 且没有存活的监控／CLI 时运行，防止重复启动。"""
    try:
        with (job / "worker.claim").open("x", encoding="utf-8") as handle:
            handle.write(str(os.getpid()))
    except FileExistsError:
        return 1
    state = read_json(job / "state.json")
    pids = [state.get("cli_pid"), state.get("monitor_pid")]
    if state["status"] != "starting" or any(pid and pid != os.getpid() and alive(pid) for pid in pids):
        return 1
    state["monitor_pid"] = os.getpid()
    write_json(job / "state.json", state)
    try:
        command = cli_command(job, read_json(job / "task.json"), state)
    except Exception:
        state.update(status="failed", error="CLI 启动配置不可用", finished_at=time.time())
        write_json(job / "state.json", state)
        return 2
    monitor(job, command)
    return 0


def references(root, kind, task):
    """默认规范在前，任务追加的 references 在后，去重但不覆盖默认项。"""
    refs = [str(root / "AGENTS.md")] if (root / "AGENTS.md").exists() else []
    refs += [str(SKILL / "references" / name) for name in DEFAULT_REFS[kind]]
    extra = task.get("references", [])
    if not isinstance(extra, list) or any(not isinstance(p, str) for p in extra):
        raise ValueError("references 必须是路径字符串列表")
    return list(dict.fromkeys(refs + extra))


def acquire_lock(devid, job):
    """全机设备锁：不同工作区也不能同时委派同一个客户端；锁只由 release --restored 删除。"""
    locks = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".cache"))) / "mhxy-cli-testing/locks"
    locks.mkdir(parents=True, exist_ok=True)
    lock = locks / (hashlib.sha256(devid.encode()).hexdigest() + ".json")
    try:
        with lock.open("x", encoding="utf-8") as handle:
            json.dump({"job": str(job), "devid": devid}, handle)
    except FileExistsError:
        raise ValueError("设备已有任务或待恢复状态：" + str(read_json(lock).get("job"))) from None
    return lock


def prepare(root, kind, task, resume):
    """校验任务文件，补齐 kind 相关字段；返回 (task, 续接的会话 ID)。"""
    if kind not in KINDS:
        raise ValueError("kind 必须是 investigate、review 或 test")
    if not isinstance(task, dict) or not isinstance(task.get("instructions"), str) or not task["instructions"].strip():
        raise ValueError("任务必须有 instructions")
    session = None
    if resume:
        if kind != "review":
            raise ValueError("--resume 只用于 review")
        previous = read_json(Path(resume) / "state.json")
        if previous.get("kind") != "review" or previous.get("status") not in TERMINAL or not previous.get("session_id"):
            raise ValueError("--resume 需要已结束且记录了会话 ID 的 review 任务")
        session = previous["session_id"]
    if kind == "test":
        if not isinstance(task.get("devid"), str) or not task["devid"].strip():
            raise ValueError("test 任务必须有已选定的非空 devid")
        base = root / ".mhxy-workspace"
        task["write_dirs"] = [str(checked_directory(Path(p), base)) for p in task.get("write_dirs", [])]
    elif task.get("write_dirs") or task.get("mcp_tools") or task.get("devid"):
        raise ValueError("只有 test 任务可以设置 devid、mcp_tools 和 write_dirs")
    return task, session


def start(root, kind, task_file, resume=None):
    """创建任务目录，test 任务独占设备，启动脱离控制台的后台 worker 后立即返回。"""
    if os.environ.get(GUARD):
        raise ValueError("当前进程是被委派的子 Codex，不得再委派")
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError("项目根目录不存在")
    task, session = prepare(root, kind, read_json(task_file), resume)
    base = root / ".mhxy-workspace"
    jobs = checked_directory(base / "codex-cli", base)
    jobs.mkdir(parents=True, exist_ok=True)
    for directory in task.get("write_dirs", []):
        Path(directory).mkdir(parents=True, exist_ok=True)
    job = jobs / (time.strftime("%Y%m%d-%H%M%S-") + kind + "-" + uuid.uuid4().hex[:8])
    job.mkdir()
    lock = acquire_lock(task["devid"], job) if kind == "test" else None
    published = False
    try:
        refs = references(root, kind, task)
        write_json(job / "task.json", task)
        write_json(job / "schema.json", SCHEMAS[kind])
        payload = {**task, "root": str(root), "kind": kind, "references": refs}
        prompt = COMMON + ROLE[kind] + "\n" + json.dumps(payload, ensure_ascii=False, indent=2)
        if session:
            prompt = "这是同一审查会话的下一轮。按新的任务说明重新审查，重点检查上轮意见的处理。\n" + prompt
        (job / "prompt.txt").write_text(prompt, encoding="utf-8")
        state = {"job": str(job), "kind": kind, "status": "starting", "model": MODEL, "effort": EFFORT,
                 "root": str(root), "cwd": str(job if kind == "test" else root),
                 "idle_seconds": IDLE_SECONDS, "started_at": time.time()}
        if session:
            state.update(resume_session=session, resume_from=str(Path(resume).resolve()))
        if lock:
            state.update(lock=str(lock), devid=task["devid"], restoration="unknown", released=False)
        write_json(job / "state.json", state)
        cli_command(job, task, state)  # 启动前检查 CLI 与服务配置，不输出可能含认证头的 argv。
        with open(job / "monitor.log", "ab") as log:
            process = subprocess.Popen([sys.executable, "-X", "utf8", str(Path(__file__).resolve()),
                                        "_worker", "--job", str(job)], stdin=subprocess.DEVNULL,
                                       stdout=log, stderr=log, start_new_session=os.name != "nt",
                                       creationflags=(subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
                                                      | subprocess.CREATE_NO_WINDOW) if os.name == "nt" else 0)
        (job / "worker.pid").write_text(str(process.pid), encoding="utf-8")
        deadline = time.monotonic() + START_SECONDS
        while time.monotonic() < deadline:
            state = read_json(job / "state.json")
            if state.get("monitor_pid") or state["status"] in TERMINAL:
                published = True
                break
            if process.poll() is not None:
                state = read_json(job / "state.json")
                published = bool(state.get("monitor_pid"))
                if not published:
                    # worker 已退出且从未接手，这里是唯一写者，可以安全记为失败并释放设备锁。
                    state = update_state(job, status="failed", error="后台 worker 未成功启动", finished_at=time.time())
                    if lock:
                        lock.unlink(missing_ok=True)
                break
            time.sleep(0.05)
        # 超时仍未发布时 worker 可能仍在启动：不写 failed，不删锁，交给 status／wait 判断。
        result = {"job": str(job), "kind": kind, "status": state["status"]}
        if state["status"] == "starting":
            result["note"] = "后台 worker 尚未接手，用 status／wait 继续查询"
        return result
    except Exception:
        if not published and not (job / "worker.pid").exists():
            # worker 未启动：删除半成品目录和设备锁，避免 clean 被永远停在 starting 的任务挡住。
            if lock:
                lock.unlink(missing_ok=True)
            shutil.rmtree(job, ignore_errors=True)
        raise


def status(job):
    """读取任务状态；监控进程已消失却没有终态时持久化为 failed。"""
    job = Path(job)
    state = read_json(job / "state.json")
    if state["status"] in TERMINAL:
        return state
    pid = state.get("monitor_pid")
    if not pid and state["status"] == "starting":
        try:
            pid = int((job / "worker.pid").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pid = None
    if pid and not alive(pid):
        # 监控已经不在，没有并发写者，可以安全写回，避免 clean 永远等待。
        state = read_json(job / "state.json")
        if state["status"] not in TERMINAL:
            state.update(status="failed", error="后台监控已退出但未发布结果", finished_at=time.time())
            write_json(job / "state.json", state)
    return state


def alive(pid):
    """不发送信号地查询 Windows 进程；POSIX 使用零信号。"""
    if os.name == "nt":
        import ctypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        kernel.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return ctypes.get_last_error() == 5
        code = ctypes.c_uint32()
        try:
            return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def release(job):
    """test 任务终止并由主线程核对恢复后，删除设备锁并标记 released。"""
    state = status(job)
    if state.get("kind") != "test":
        raise ValueError("只有 test 任务需要 release")
    if state["status"] not in TERMINAL:
        raise ValueError("任务终止并核对恢复后才可 release --restored")
    lock = Path(state["lock"])
    if lock.exists():
        if read_json(lock)["job"] != str(job):
            raise ValueError("设备锁不属于本任务")
        lock.unlink()
    state.update(restoration="restored", released=True)
    write_json(job / "state.json", state)
    return state


def main():
    """命令行入口；状态使用 JSON，错误不打印含凭据的命令或配置。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["start", "status", "wait", "cancel", "release", "_worker"])
    parser.add_argument("--root")
    parser.add_argument("--kind", choices=KINDS)
    parser.add_argument("--task-file")
    parser.add_argument("--resume")
    parser.add_argument("--job")
    parser.add_argument("--timeout", type=float, default=None)
    parser.add_argument("--restored", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "start":
            if not args.root or not args.kind or not args.task_file:
                raise ValueError("start 需要 --root、--kind 和 --task-file")
            result = start(args.root, args.kind, args.task_file, args.resume)
        else:
            if not args.job:
                raise ValueError("需要 --job")
            job = Path(args.job).resolve()
            if args.command == "_worker":
                return worker(job)
            if args.command == "release":
                if not args.restored:
                    raise ValueError("release 需要 --restored，表示已核对并恢复客户端")
                result = release(job)
            else:
                result = status(job)
            if args.command == "wait":
                if args.timeout is not None and args.timeout < 0:
                    raise ValueError("timeout 不能为负数")
                deadline = None if args.timeout is None else time.monotonic() + args.timeout
                while result["status"] not in TERMINAL:
                    if deadline is not None and time.monotonic() >= deadline:
                        break
                    time.sleep(0.5)
                    result = status(job)
            elif args.command == "cancel" and result["status"] not in TERMINAL:
                (job / "cancel").touch()
                result["cancel_requested"] = True
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as error:
        message = str(error) if isinstance(error, (ValueError, RuntimeError)) else "操作失败，请检查任务文件、日志与配置"
        print(json.dumps({"status": "error", "error": message}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
