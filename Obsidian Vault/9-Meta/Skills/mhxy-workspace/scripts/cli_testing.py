"""管理 Codex CLI 测试任务：后台运行、输出间隔超时、取消与设备锁。"""

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
IDLE_SECONDS = 600
GAME_URL = "https://mh-game-mcp.eros.nie.netease.com/mcp"


def read_json(path):
    """读取 UTF-8 JSON；不存在或格式错误由调用边界处理。"""
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, value):
    """原子发布状态，避免查询读到半个 JSON。"""
    path = Path(path)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


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


def cli_command(job, task):
    """构造固定模型、辅助目录写权限和 MCP 工具白名单的执行命令。"""
    config_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    config_path = config_home / "config.toml"
    config = tomllib.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
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
    command = cli_prefix() + ["exec", "--ignore-user-config", "--skip-git-repo-check",
                             "--sandbox", "workspace-write", "-C", str(job),
                             "-m", "gpt-6-luna", "-c", 'model_reasoning_effort="max"',
                             "-c", 'approval_policy="never"', "-c", "agents.enabled=false",
                             "-c", "features.multi_agent=false", "-c", "features.hooks=false",
                             "-c", "plugins={}", "-c", "mcp_servers=" + toml_value(servers),
                             "--json", "--output-schema", str(job / "schema.json"),
                             "-o", str(job / "result.json")]
    # 只复用模型连接配置，避免加载宿主插件、hooks 和无关 MCP；不记录含认证的命令。
    for key in ("model_provider", "model_providers", "model_catalog_json"):
        if key in config:
            command += ["-c", key + "=" + toml_value(config[key])]
    for directory in task.get("write_dirs", []):
        command += ["--add-dir", directory]
    command += ["-"]
    return command


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


def monitor(job, command, idle_seconds=IDLE_SECONDS):
    """持续排空两路输出；只有 CLI 字节输出刷新静默计时，无总时长上限。"""
    state = read_json(job / "state.json")
    state.update(status="running", monitor_pid=os.getpid(), restoration="unknown")
    write_json(job / "state.json", state)
    process = None
    streams = queue.Queue()
    last_output = time.monotonic()
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
                                       stderr=subprocess.PIPE, cwd=job,
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
                        state["last_output_at"] = time.time()
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
                    state["exit_code"] = process.returncode
                    try:
                        result = read_json(job / "result.json")
                        valid = (isinstance(result, dict) and result.get("status") in {"passed", "failed", "blocked"}
                                 and result.get("restoration") in {"restored", "unknown", "not_needed"}
                                 and all(isinstance(result.get(k), list) for k in ("cases", "errors", "unverified")))
                    except (OSError, ValueError):
                        valid = False
                    state["status"] = "completed" if process.returncode == 0 and valid else "failed"
                    if valid:
                        state["result"] = result
                        state["restoration"] = result["restoration"]
                    if not valid:
                        state["error"] = "CLI 未返回完整的结构化测试结果"
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
        state["finished_at"] = time.time()
        write_json(job / "state.json", state)


def start(root, task_file):
    """创建任务并独占设备，启动隐藏的独立监控进程。"""
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError("项目根目录不存在")
    task = read_json(task_file)
    if not isinstance(task.get("devid"), str) or not task["devid"].strip():
        raise ValueError("任务必须有已选定的非空 devid")
    if not isinstance(task.get("instructions"), str) or not task["instructions"].strip():
        raise ValueError("任务必须有 instructions")
    base = root / ".mhxy-workspace"
    jobs = checked_directory(base / "cli-testing", base)
    jobs.mkdir(parents=True, exist_ok=True)
    task["write_dirs"] = [str(checked_directory(Path(p), base)) for p in task.get("write_dirs", [])]
    for directory in task["write_dirs"]:
        Path(directory).mkdir(parents=True, exist_ok=True)
    job = jobs / uuid.uuid4().hex
    job.mkdir()
    # 全机设备锁使不同工作区也不能同时委派同一个客户端；不自动回收未知恢复状态。
    locks = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".cache"))) / "mhxy-cli-testing/locks"
    locks.mkdir(parents=True, exist_ok=True)
    lock = locks / (hashlib.sha256(task["devid"].encode()).hexdigest() + ".json")
    try:
        with lock.open("x", encoding="utf-8") as handle:
            json.dump({"job": str(job), "devid": task["devid"]}, handle)
    except FileExistsError:
        job.rmdir()
        raise ValueError("设备已有任务或待恢复状态：" + str(read_json(lock).get("job"))) from None
    try:
        write_json(job / "task.json", task)
        schema = {"type": "object", "additionalProperties": False,
                  "properties": {"status": {"type": "string", "enum": ["passed", "failed", "blocked"]},
                                 "cases": {"type": "array", "items": {"type": "string"}},
                                 "errors": {"type": "array", "items": {"type": "string"}},
                                 "unverified": {"type": "array", "items": {"type": "string"}},
                                 "restoration": {"type": "string", "enum": ["restored", "unknown", "not_needed"]}},
                  "required": ["status", "cases", "errors", "unverified", "restoration"]}
        write_json(job / "schema.json", schema)
        refs = ([str(root / "AGENTS.md")] if (root / "AGENTS.md").exists() else []) + [
            str(SKILL / "references/cli-testing.md"), str(SKILL / "references/game-debugging.md"),
            *task.get("references", [])]
        prompt = ("你是测试执行者，不是顶层主会话。不得派生、调用或请求新的代理。只写任务目录和允许的测试目录，"
                  "不修改业务源码；需要用户判断时返回 blocked。先读取下列规范，不执行设计或代码审查委派流程。"
                  "测试结束尽力恢复；结果按 schema 返回证据，不能把发送成功或覆盖率百分比当作测试通过。\n"
                  + json.dumps({"root": str(root), "references": refs, **task}, ensure_ascii=False))
        (job / "prompt.txt").write_text(prompt, encoding="utf-8")
        write_json(job / "state.json", {"job": str(job), "status": "starting", "model": "gpt-6-luna",
                                        "effort": "max", "idle_seconds": IDLE_SECONDS,
                                        "started_at": time.time(), "lock": str(lock), "restoration": "unknown"})
        cli_command(job, task)  # 启动前检查 CLI 与服务配置，不输出可能含认证头的 argv。
        with open(job / "monitor.log", "ab") as log:
            process = subprocess.Popen([sys.executable, "-X", "utf8", str(Path(__file__).resolve()),
                                        "_worker", "--job", str(job)], stdin=subprocess.DEVNULL,
                                       stdout=log, stderr=log, start_new_session=os.name != "nt",
                                       creationflags=(subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
                                                      | subprocess.CREATE_NO_WINDOW) if os.name == "nt" else 0)
        # 等待 worker 发布自身 PID，避免启动器退出被宿主回收时 status 永远停在 starting。
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            state = read_json(job / "state.json")
            if state.get("monitor_pid") or state["status"] in TERMINAL:
                break
            if process.poll() is not None:
                state.update(status="failed", error="后台监控未成功启动", restoration="unknown")
                break
            time.sleep(0.05)
        else:
            state.update(status="failed", error="后台监控启动超时", restoration="unknown")
        if not state.get("monitor_pid"):
            state["monitor_pid"] = process.pid
            write_json(job / "state.json", state)
        return {"job": str(job), "status": state["status"], "monitor_pid": process.pid}
    except Exception:
        lock.unlink(missing_ok=True)
        raise


def status(job):
    """读取任务状态；进程消失但未发布终态时标记监控中断。"""
    state = read_json(Path(job) / "state.json")
    pid = state.get("monitor_pid")
    if state["status"] not in TERMINAL and pid and not alive(pid):
        state.update(status="failed", error="监控进程已退出但未发布结果", restoration="unknown")
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


def main():
    """命令行入口；状态使用 JSON，错误不打印含凭据的命令或配置。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["start", "status", "wait", "cancel", "release", "_worker"])
    parser.add_argument("--root")
    parser.add_argument("--task-file")
    parser.add_argument("--job")
    parser.add_argument("--timeout", type=float, default=None)
    parser.add_argument("--restored", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "start":
            if not args.root or not args.task_file:
                raise ValueError("start 需要 --root 和 --task-file")
            result = start(args.root, args.task_file)
        else:
            if not args.job:
                raise ValueError("需要 --job")
            job = Path(args.job).resolve()
            if args.command == "_worker":
                state = read_json(job / "state.json")
                state["monitor_pid"] = os.getpid()
                write_json(job / "state.json", state)
                try:
                    command = cli_command(job, read_json(job / "task.json"))
                except Exception:
                    state.update(status="failed", error="CLI 启动配置不可用", restoration="unknown", finished_at=time.time())
                    write_json(job / "state.json", state)
                    return 2
                monitor(job, command)
                return 0
            result = status(job)
            if args.command == "wait":
                if args.timeout is not None and args.timeout < 0:
                    raise ValueError("timeout 不能为负数")
                deadline = None if args.timeout is None else time.monotonic() + args.timeout
                while result["status"] not in TERMINAL:
                    if deadline is not None and time.monotonic() >= deadline:
                        break
                    time.sleep(0.2)
                    result = status(job)
            elif args.command == "cancel" and result["status"] not in TERMINAL:
                (job / "cancel").touch()
                result["cancel_requested"] = True
            elif args.command == "release":
                if not args.restored or result["status"] not in TERMINAL:
                    raise ValueError("任务终止并核对恢复后才可 release --restored")
                lock = Path(result["lock"])
                if lock.exists():
                    if read_json(lock)["job"] != str(job):
                        raise ValueError("设备锁不属于本任务")
                    lock.unlink()
                result.update(restoration="restored", released=True)
                write_json(job / "state.json", result)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as error:
        message = str(error) if isinstance(error, (ValueError, RuntimeError)) else "操作失败，请检查任务文件、日志与配置"
        print(json.dumps({"status": "error", "error": message}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
