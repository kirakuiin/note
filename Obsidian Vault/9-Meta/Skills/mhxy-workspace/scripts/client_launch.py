#!/usr/bin/env python3
"""自动启动并登录调试客户端，返回新设备的 devid（见 references/game-debugging.md「选择设备」）。

子命令：
  install    在管理员终端运行一次：把启动器复制到受保护目录，注册以最高权限运行的计划任务。可重复执行。
  uninstall  在管理员终端运行：删除计划任务和启动器。
  doctor     普通权限：检查部署和配置，列出缺什么、怎么补。
  launch     普通权限：确认客户端目录的类型（update.ini）与 --platform 一致；查本机在线设备占用的账号，
             选账号池中第一个空闲账号，触发计划任务启动客户端，
             等新设备登录上线后返回 devid。
  select     普通权限：为当前工作区确定指定类型（PC／互通）的测试设备。在线设备中选第一台类型相符、
             加载当前工作区源码、没有设备锁的；没有就 launch 一台。不需要用户确认。

客户端以管理员身份运行，agent 的普通权限进程直接启动会弹 UAC；计划任务由用户安装一次，之后
触发不再弹窗。账号密码只在用户级配置（workspace.py login-account 维护），不出现在输出和请求文件中。
"""
import argparse
import base64
import configparser
import ctypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request
import uuid

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "game-debugging"))
import workspace  # noqa: E402
import mcp_http  # noqa: E402

TASK = "mhxy-client-launch"
TASK_SCRIPT = "client_launch_task.py"
INSTALL_DIR = Path(os.environ.get("ProgramData", r"C:\ProgramData")) / TASK
STATE_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / TASK
SERVER_LIST = "http://mhxy.update.inner.netease.com/serverlist/serverlist.txt"
MOCK_PREFIX = "模拟"
MOCK_FIELD = "刘强98服"  # 模拟服所在大区
MORE_SERVER = "more_server"  # 客户端按名字在内服服务器列表中查找
EXE = "mhmain.exe"
PROBE_TIMEOUT = 20  # 秒；单次 MCP 调用
NO_DEVICE = "未找到任何在线设备"  # get_devices_by_ip 在本机没有设备时的报错文本
# 读设备当前登录的账号、加载的脚本位置（mainmenu 是登录流程必然加载的模块）和客户端类型
DEVICE_PROBE = ('(lambda s: {"account": getattr(s.modules.get("loginenter"), "Account", None), '
                '"source": getattr(s.modules.get("mainmenu"), "__file__", None), '
                '"platform": getattr(s.modules.get("C_app") or __import__("C_app"), "get_platform", lambda: None)()'
                '})(__import__("sys"))')
PLATFORMS = {"win32": "pc", "mobile": "ht"}  # C_app.get_platform() 的返回值 → --platform
PLATFORM_NAMES = {"pc": "PC", "ht": "互通"}
LOCKS = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".cache"))) / "mhxy-cli-testing/locks"


class LaunchError(Exception):
    def __init__(self, message, code="error", **detail):
        super().__init__(message)
        self.code = code
        self.detail = detail


# ---------- 纯逻辑（单元测试覆盖） ----------

def normalize_account(account):
    """客户端登录时可能省略 @163.com，比较前统一补全并转小写。"""
    if not isinstance(account, str) or not account.strip():
        return None
    account = account.strip().lower()
    return account if "@" in account else account + "@163.com"


def choose_account(pool, occupied):
    """按账号池顺序返回第一个未被占用的账号；都被占用时返回 None。"""
    for item in pool:
        if normalize_account(item["account"]) not in occupied:
            return item["account"]
    return None


def loads_workspace(source, root):
    """设备加载的脚本（mainmenu.__file__）是否在项目根目录下；客户端返回的路径大小写和分隔符不统一。"""
    if not isinstance(source, str) or not source:
        return False
    prefix = Path(root).resolve().as_posix().lower().rstrip("/") + "/"
    return source.replace("\\", "/").lower().startswith(prefix)


def locked(devid):
    """设备是否有 codex_cli.py 的全机设备锁（正在测试或待恢复）。"""
    return (LOCKS / (hashlib.sha256(devid.encode()).hexdigest() + ".json")).exists()


def resolve_server(name, names):
    """把用户说的服务器名解析成 (svrfield, svrname)。

    模拟服在大区 刘强98服；其他服务器按内服服务器列表（names）精确匹配，匹配不到再做不区分大小写
    的子串匹配，只有唯一候选才采用。

    Raises:
        LaunchError: 找不到或有多个候选（detail 带 candidates）。
    """
    name = name.strip()
    if name.startswith(MOCK_PREFIX):
        # 模拟服必须带编号（如 模拟15）；“模拟服”是类别不是服务器名，登录时只会报“服务器信息不正确”。
        if not name[len(MOCK_PREFIX):].isdigit():
            raise LaunchError(f"“{name}”不是具体的模拟服名，请写成 模拟<编号>（如 模拟15）", "server_invalid")
        return MOCK_FIELD, name
    if name in names:
        return MORE_SERVER, name
    candidates = [item for item in names if name.lower() in item.lower()]
    if len(candidates) == 1:
        return MORE_SERVER, candidates[0]
    if candidates:
        raise LaunchError(f"服务器名“{name}”有多个候选，请指定完整名称", "server_ambiguous",
                          candidates=candidates[:20])
    raise LaunchError(f"内服服务器列表中找不到“{name}”", "server_not_found")


def workspace_dir(root):
    """客户端 workspace 是项目根（mhimage）的上一级，其中的 mhimage/、_test/ 优先于客户端目录。"""
    root = Path(root).resolve()
    if root.name.lower() != "mhimage":
        raise LaunchError(f"项目根目录应名为 mhimage，才能把上一级作为 workspace：{root}", "bad_workspace")
    if (root.parent / "_test" / "mhimage.wdf").exists():
        raise LaunchError(f"{root.parent / '_test' / 'mhimage.wdf'} 存在，会让客户端不加载脚本源码", "bad_workspace")
    return root.parent.as_posix()


def client_platform(client_dir):
    """按客户端目录 update.ini 的 [Setting] 判断类型：Platform = HT 为 ht，Arch = X64／X86 为 pc。

    类型由目录当前同步的版本决定，与 xy1.ini、分辨率无关。读不到或判断不了返回 None。只读，不修改 ini。
    """
    try:
        raw = (Path(client_dir) / "update.ini").read_bytes()
    except OSError:
        return None
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    try:
        parser.read_string(raw.decode("gbk", errors="replace"))  # 其他段可能有 GBK 中文
    except configparser.Error:
        return None
    if not parser.has_section("Setting"):
        return None
    setting = parser["Setting"]
    if setting.get("Platform", "").strip().upper() == "HT":
        return "ht"
    if setting.get("Arch", "").strip().upper() in ("X64", "X86"):
        return "pc"
    return None


def check_client_platform(client, platform):
    """客户端目录的类型必须与要求的 platform 一致，否则抛 LaunchError。"""
    detected = client_platform(client)
    if detected is None:
        raise LaunchError(f"无法从 {Path(client) / 'update.ini'} 的 [Setting] 判断客户端类型"
                          "（PC 有 Arch = X64／X86，互通有 Platform = HT）", "platform_unknown", client_dir=str(client))
    if detected != platform:
        raise LaunchError(f"{client} 当前是{PLATFORM_NAMES[detected]}客户端，与要求的 {platform} 不符：报告用户，"
                          "不要改 ini 硬切", "platform_mismatch", client_dir=str(client), expected=platform,
                          detected=detected)
    return detected


def task_arguments(script, config, allowed):
    """计划任务的参数：启动器、请求文件、用户级配置和允许启动的客户端目录。"""
    parts = ["-X", "utf8", str(script), "--request", str(STATE_DIR / "request.json"), "--config", str(config)]
    for item in allowed:
        parts += ["--allow", str(item)]
    return subprocess.list2cmdline(parts)


# ---------- 外部交互 ----------

def mcp(name, arguments, timeout=PROBE_TIMEOUT):
    """调用 mh-game-mcp 工具，返回解析后的业务载荷。"""
    mcp_http.TIMEOUT = timeout
    body = mcp_http.post({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {
        "protocolVersion": "2024-11-05", "capabilities": {},
        "clientInfo": {"name": "client-launch", "version": "1.0"}}})
    if mcp_http.find_response(body, 0) is None:
        raise LaunchError("mh-game-mcp 握手失败", "mcp_error")
    mcp_http.post({"jsonrpc": "2.0", "method": "notifications/initialized"})
    body = mcp_http.post({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                          "params": {"name": name, "arguments": arguments}})
    response = mcp_http.find_response(body, 1)
    if response is None or "error" in response:
        raise LaunchError(f"{name} 调用失败：{(response or {}).get('error')}", "mcp_error")
    result = response["result"]
    if result.get("isError"):
        raise LaunchError(f"{name} 返回错误：{result.get('content')}", "mcp_error")
    if result.get("structuredContent") is not None:
        return result["structuredContent"]
    text = "".join(item.get("text", "") for item in result.get("content", []) if isinstance(item, dict))
    try:
        return json.loads(text)
    except ValueError:
        raise LaunchError(f"{name} 返回无法解析：{text[:200]}", "mcp_error") from None


def list_devices():
    try:
        value = mcp("get_devices_by_ip", {"ip": ""})
    except LaunchError as error:
        if NO_DEVICE in str(error):  # 没有在线设备时工具报错，而不是返回空列表
            return []
        raise
    devices = value.get("result", value) if isinstance(value, dict) else value
    if not isinstance(devices, list):
        raise LaunchError(f"设备列表无法识别：{value}", "mcp_error")
    return [item for item in devices if isinstance(item, dict) and item.get("devid")]


def device_info(devid):
    """读取设备当前登录的账号（未登录为 None）、加载的脚本路径和类型（pc／ht，无法识别为 None）。

    读取失败抛 LaunchError。
    """
    value = mcp("execute_code", {"devid": devid, "code": DEVICE_PROBE, "need_loginfo": False})
    value = value.get("result", value) if isinstance(value, dict) and "ret" not in value else value
    if not isinstance(value, dict) or value.get("error") or not isinstance(value.get("ret"), dict):
        raise LaunchError(f"读取 {devid} 的状态失败：{value}", "mcp_error")
    ret = value["ret"]
    return {"account": normalize_account(ret.get("account")), "source": ret.get("source"),
            "platform": PLATFORMS.get(ret.get("platform"))}


def device_account(devid):
    return device_info(devid)["account"]


def scan_accounts():
    """返回 (设备列表, {账号: devid}, [无法读取账号的 devid])。"""
    devices, occupied, unknown = list_devices(), {}, []
    for device in devices:
        try:
            account = device_account(device["devid"])
        except (LaunchError, OSError) as error:
            unknown.append({"devid": device["devid"], "name": device.get("name"), "reason": str(error)[:200]})
            continue
        if account:
            occupied[account] = device["devid"]
    return devices, occupied, unknown


def server_names():
    with urllib.request.urlopen(SERVER_LIST, timeout=15) as response:
        data = json.loads(response.read())
    return [item["cluster_name"] for item in data if isinstance(item, dict) and item.get("cluster_name")]


def powershell(script):
    """以 -EncodedCommand 运行 PowerShell，避免中文路径和引号转义问题。"""
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    completed = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                                "-EncodedCommand", encoded], capture_output=True, timeout=60)
    decode = workspace.decode_output
    return completed.returncode, decode(completed.stdout).strip(), decode(completed.stderr).strip()


def ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def query_task():
    """返回计划任务的 {execute, arguments, run_level, user}；不存在时返回 None。"""
    code, out, _ = powershell(
        f"$t = Get-ScheduledTask -TaskName {ps_quote(TASK)} -ErrorAction SilentlyContinue; "
        "if ($t) { [pscustomobject]@{execute=$t.Actions[0].Execute; arguments=$t.Actions[0].Arguments; "
        "run_level=[string]$t.Principal.RunLevel; user=$t.Principal.UserId} | ConvertTo-Json -Compress }")
    if code or not out:
        return None
    try:
        return json.loads(out)
    except ValueError:
        return None


def python_for_task():
    """计划任务用无控制台窗口的 pythonw.exe（与当前解释器同目录），没有时退回当前解释器。"""
    current = Path(sys.executable)
    windowless = current.with_name("pythonw.exe")
    return windowless if windowless.is_file() else current


def client_dirs(config):
    return [Path(config[key]) for key in ("pc_client_dir", "ht_client_dir")
            if config.get(key) and Path(config[key]).is_dir()]


# ---------- 子命令 ----------

def install(global_config, user=None):
    """全机安装一次，与工作区无关：只按用户级配置登记允许启动的客户端目录。"""
    if not is_admin():
        raise LaunchError("install 需要在管理员 PowerShell 中运行", "need_admin")
    path = workspace.absolute(global_config)
    raw = workspace.read_bytes(path)
    if raw is None:
        raise LaunchError(f"找不到用户级配置：{path}", "need_config")
    allowed = client_dirs(workspace.parse_json(raw, path))
    if not allowed:
        raise LaunchError("用户级配置里没有可用的 pc_client_dir／ht_client_dir", "need_config")
    workspace.no_links(INSTALL_DIR)
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    target = INSTALL_DIR / TASK_SCRIPT
    shutil.copyfile(SCRIPTS / TASK_SCRIPT, target)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    user = user or f"{os.environ.get('USERDOMAIN', '')}\\{os.environ.get('USERNAME', '')}".lstrip("\\")
    arguments = task_arguments(target, workspace.absolute(global_config), allowed)
    code, _, err = powershell(
        f"$a = New-ScheduledTaskAction -Execute {ps_quote(python_for_task())} -Argument {ps_quote(arguments)} "
        f"-WorkingDirectory {ps_quote(INSTALL_DIR)}; "
        f"$p = New-ScheduledTaskPrincipal -UserId {ps_quote(user)} -LogonType Interactive -RunLevel Highest; "
        "$s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries "
        "-ExecutionTimeLimit (New-TimeSpan -Minutes 5) -MultipleInstances IgnoreNew; "
        f"Register-ScheduledTask -TaskName {ps_quote(TASK)} -Action $a -Principal $p -Settings $s -Force | Out-Null")
    if code:
        raise LaunchError(f"注册计划任务失败：{err}", "install_failed")
    return {"action": "install", "task": TASK, "user": user, "launcher": str(target),
            "allowed_client_dirs": [str(item) for item in allowed],
            "note": "客户端目录或用户级配置路径变化、skill 更新启动器后，重新运行 install"}


def uninstall():
    if not is_admin():
        raise LaunchError("uninstall 需要在管理员 PowerShell 中运行", "need_admin")
    code, _, err = powershell(f"Unregister-ScheduledTask -TaskName {ps_quote(TASK)} -Confirm:$false "
                              "-ErrorAction SilentlyContinue")
    target = INSTALL_DIR / TASK_SCRIPT
    if target.exists():
        target.unlink()
    return {"action": "uninstall", "task": TASK, "removed_launcher": str(target), "warning": err or None}


def doctor(root, global_config, platform="pc"):
    """逐项检查部署和配置；problems 每条给出缺什么和怎么补。"""
    problems, info = [], {}
    fix_install = f'在管理员 PowerShell 运行（全机一次）：python "{SCRIPTS / "client_launch.py"}" install'
    task = query_task()
    if task is None:
        problems.append({"item": "计划任务", "problem": f"未找到 {TASK}", "fix": fix_install})
    else:
        info["task"] = task
        if task.get("run_level") not in ("Highest", "1"):
            problems.append({"item": "计划任务", "problem": "不是以最高权限运行", "fix": fix_install})
        installed = INSTALL_DIR / TASK_SCRIPT
        if not installed.is_file() or sha256(installed) != sha256(SCRIPTS / TASK_SCRIPT):
            problems.append({"item": "启动器", "problem": "未安装或与 skill 中的版本不一致", "fix": fix_install})
    try:
        config = workspace.load_config(root, global_config)
    except workspace.WorkspaceError as error:
        problems.append({"item": "配置", "problem": str(error), "fix": "按 workspace-management.md 修复配置"})
        return {"ok": False, "problems": problems, **info}
    if not config.get("login_accounts"):
        problems.append({"item": "账号池", "problem": "login_accounts 未配置",
                         "fix": f'在交互终端运行：python "{SCRIPTS / "workspace.py"}" login-account '
                                '--account <游戏账号> --apply'})
    else:
        info["login_accounts"] = [item["account"] for item in config["login_accounts"]]
    client = config.get(f"{platform}_client_dir")
    if not client or not (Path(client) / EXE).is_file():
        problems.append({"item": "客户端目录", "problem": f"{platform}_client_dir 未配置或缺少 {EXE}",
                         "fix": "用 workspace.py config --set-global 配置客户端目录"})
    elif not (Path(client) / "mhxy.key").is_file():
        problems.append({"item": "开发者模式", "problem": f"{client} 缺少 mhxy.key，客户端不会加载脚本源码",
                         "fix": "从 http://alubaserver.eros.nie.netease.com/static/mhxy.key 下载放到客户端根目录"})
    elif task and str(Path(client)).lower() not in task.get("arguments", "").lower():
        problems.append({"item": "计划任务", "problem": f"{client} 不在安装时登记的客户端目录中", "fix": fix_install})
    info["clients"] = {}
    for expected in PLATFORM_NAMES:
        key = f"{expected}_client_dir"
        if not config.get(key) or not Path(config[key]).is_dir():
            continue
        detected = client_platform(config[key])
        info["clients"][key] = {"path": config[key], "detected": detected}
        if detected is None:
            problems.append({"item": "客户端类型", "problem": f"{key}（{config[key]}）的 update.ini 无法判断类型",
                             "fix": "检查该目录是否完整同步过客户端"})
        elif detected != expected:
            problems.append({"item": "客户端类型",
                             "problem": f"{key}（{config[key]}）当前是{PLATFORM_NAMES[detected]}客户端",
                             "fix": f"由用户决定：把目录同步回{PLATFORM_NAMES[expected]}版，或把 {key} 改到正确的目录"})
    try:
        info["workspace"] = workspace_dir(root)
    except LaunchError as error:
        problems.append({"item": "workspace", "problem": str(error), "fix": "按问题描述调整目录"})
    server = config.get("login_server")
    if not server:
        problems.append({"item": "服务器", "problem": "当前工作区未配置 login_server",
                         "fix": f'python "{SCRIPTS / "workspace.py"}" config --root "<项目>" '
                                '--set-local "login_server=<服务器名>" --apply'})
    else:
        try:
            info["server"] = resolve_server(server, [] if server.startswith(MOCK_PREFIX) else server_names())
        except (LaunchError, OSError, ValueError) as error:
            problems.append({"item": "服务器", "problem": str(error), "fix": "改用完整的服务器名"})
    return {"ok": not problems, "problems": problems, **info}


def wait_result(request_id, timeout=30):
    path = STATE_DIR / "result.json"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            result = json.loads(path.read_text(encoding="utf-8"))
            if result.get("id") == request_id:
                return result
        except (OSError, ValueError):
            pass
        time.sleep(1)
    raise LaunchError("计划任务没有返回结果：确认已运行 install，任务未被禁用", "task_no_result")


def launch(root, global_config, platform="pc", server=None, timeout=240, dry_run=False):
    config = workspace.load_config(root, global_config)
    client = config.get(f"{platform}_client_dir")
    if not client or not (Path(client) / EXE).is_file():
        raise LaunchError(f"{platform}_client_dir 未配置或缺少 {EXE}", "need_config")
    check_client_platform(client, platform)
    work = workspace_dir(root)
    server = server or config.get("login_server")
    if not server:
        raise LaunchError("当前工作区未配置服务器：问用户这个分支用哪个服务器，用 workspace.py config --root "
                          "<项目> --set-local \"login_server=<名字>\" --apply 保存后重试", "need_server")
    svrfield, svrname = resolve_server(server, [] if server.strip().startswith(MOCK_PREFIX) else server_names())
    pool = config.get("login_accounts")
    if not pool:
        raise LaunchError("账号池为空：请用户在交互终端运行 workspace.py login-account 添加账号", "need_accounts")
    devices, occupied, unknown = scan_accounts()
    account = choose_account(pool, occupied)
    plan = {"client_dir": client, "platform": platform, "workspace": work, "svrfield": svrfield, "svrname": svrname,
            "occupied": occupied, "unknown_devices": unknown}
    if account is None:
        raise LaunchError("账号池中的账号都已被本机在线客户端占用，停止自动启动", "all_occupied", **plan)
    plan["account"] = account
    if dry_run:
        return {"action": "launch", "dry_run": True, **plan}
    request_id = uuid.uuid4().hex
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    request = {"id": request_id, "client_dir": str(Path(client)), "workspace": work, "account": account,
               "svrfield": svrfield, "svrname": svrname, "roleidx": 0}
    temporary = STATE_DIR / "request.json.tmp"
    temporary.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, STATE_DIR / "request.json")
    completed = subprocess.run(["schtasks", "/run", "/tn", TASK], capture_output=True, timeout=30)
    if completed.returncode:
        (STATE_DIR / "request.json").unlink(missing_ok=True)
        raise LaunchError(f"触发计划任务失败：{workspace.decode_output(completed.stderr).strip()}；"
                          "运行 doctor 检查部署", "task_failed")
    result = wait_result(request_id)
    if result.get("error"):
        raise LaunchError(f"启动器报错：{result['error']}", "launcher_error")
    plan["pid"] = result.get("pid")
    before = {device["devid"] for device in devices}
    target = normalize_account(account)
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(5)
        try:
            for device in list_devices():
                if device["devid"] in before:
                    continue
                try:
                    if device_account(device["devid"]) == target:
                        return {"action": "launch", "devid": device["devid"], "name": device.get("name"), **plan}
                except (LaunchError, OSError):
                    continue  # 客户端仍在初始化
        except (LaunchError, OSError):
            continue
    raise LaunchError(f"{timeout} 秒内没有等到账号 {account} 的新设备上线：检查客户端是否停在登录界面或报错，"
                      f"日志见 {client}/Log/ 中进程号 {plan['pid']} 对应的文件", "device_timeout", **plan)


def select(root, global_config, platform="pc", timeout=240, dry_run=False):
    """为当前工作区确定 platform 类型的测试设备，不需要用户确认。

    在线设备按列表顺序，取第一台类型相符、加载当前工作区源码、没有设备锁的；没有就自动启动一台
    （dry_run 时只返回启动计划，how 为 would_launch）。其余设备和跳过原因放在 skipped 里，供交付时说明。
    """
    skipped = []
    for device in list_devices():
        devid = device["devid"]
        if locked(devid):
            skipped.append({"devid": devid, "reason": "有设备锁（其他测试正在使用或待恢复）"})
            continue
        try:
            info = device_info(devid)
        except (LaunchError, OSError) as error:
            skipped.append({"devid": devid, "reason": f"无法读取状态：{str(error)[:120]}"})
            continue
        if info["platform"] is None:
            skipped.append({"devid": devid, "reason": "无法识别客户端类型（C_app.get_platform() 返回值未知）"})
        elif info["platform"] != platform:
            skipped.append({"devid": devid, "reason": f"是{PLATFORM_NAMES[info['platform']]}客户端，需要 {platform}"})
        elif not info["account"]:
            skipped.append({"devid": devid, "reason": "未登录"})
        elif not loads_workspace(info["source"], root):
            skipped.append({"devid": devid, "reason": f"加载的不是当前工作区源码：{info['source']}"})
        else:
            return {"action": "select", "how": "online", "devid": devid, "name": device.get("name"),
                    "platform": platform, "account": info["account"], "skipped": skipped}
    result = launch(root, global_config, platform, timeout=timeout, dry_run=dry_run)
    return {**result, "action": "select", "how": "would_launch" if dry_run else "launched", "skipped": skipped}


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=("install", "uninstall", "doctor", "launch", "select"))
    parser.add_argument("--root", default=os.getcwd())
    parser.add_argument("--global-config", default=str(Path.home() / workspace.DIRECTORY / "config.json"))
    parser.add_argument("--platform", choices=("pc", "ht"), default="pc")
    parser.add_argument("--server", help="launch：本次使用的服务器名，省略时用工作区配置 login_server")
    parser.add_argument("--timeout", type=int, default=240, help="launch：等待设备上线的秒数")
    parser.add_argument("--dry-run", action="store_true",
                        help="launch／select：只检查并给出将选用的设备或启动计划，不启动客户端")
    parser.add_argument("--user", help="install：计划任务的运行用户，默认当前用户")
    args = parser.parse_args()
    try:
        if args.action == "install":
            result = install(args.global_config, args.user)
        elif args.action == "uninstall":
            result = uninstall()
        elif args.action == "select":
            result = select(args.root, args.global_config, args.platform, args.timeout, args.dry_run)
        elif args.action == "doctor":
            result = doctor(args.root, args.global_config, args.platform)
        else:
            result = launch(args.root, args.global_config, args.platform, args.server, args.timeout, args.dry_run)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok", True) else 1
    except LaunchError as error:
        print(json.dumps({"error": str(error), "code": error.code, **error.detail}, ensure_ascii=False, indent=2))
        return 1
    except (workspace.WorkspaceError, OSError, ValueError, subprocess.SubprocessError) as error:
        print(json.dumps({"error": str(error), "code": "error"}, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    sys.exit(main())
