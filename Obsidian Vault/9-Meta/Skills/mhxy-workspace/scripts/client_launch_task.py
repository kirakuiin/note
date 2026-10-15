# -*- coding: utf-8 -*-
"""计划任务（以最高权限运行）调用的客户端启动器。由 client_launch.py install 复制到受保护目录。

只做一件事：读取 client_launch.py launch 写下的启动请求，校验后启动客户端，写回结果。
- 只启动安装时登记的客户端目录下的 mhmain.exe；目录列表写在计划任务参数里，改它需要管理员权限。
- 请求里没有密码：按账号从用户级配置的账号池读取，生成启动参数后直接传给客户端，不落盘。
- 只用标准库，不导入 skill 目录中的其他脚本（那些文件普通权限即可修改）。
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

EXE = "mhmain.exe"
LAUNCH_FLAG = "__start_by_mh_launcher__"
REQUEST_KEYS = {"id", "client_dir", "workspace", "account", "svrfield", "svrname", "roleidx"}
CREATE_BREAKAWAY_FROM_JOB = 0x01000000


class LaunchError(Exception):
    pass


def norm(path):
    return os.path.normcase(os.path.abspath(path))


def caps(password):
    """客户端会把启动参数转成小写，大写字母的位置用 caps（逗号分隔的下标）还原。"""
    return ",".join(str(i) for i, c in enumerate(password) if c != c.lower())


def build_payload(request, password):
    """生成传给 mhmain.exe 的启动 JSON（含密码，只用于进程参数）。

    引擎从原始命令行中按空白切出 __start_by_mh_launcher__ 之后的一段，直接当 JSON 解析
    （xymain/myapp.cpp check_launcher），所以整段不能含空白，也不能被加引号或转义；
    workspace 必须是第一个键。
    """
    payload = {
        "workspace": request["workspace"],
        "account": request["account"],
        "pwd": password,
        "svrfield": request["svrfield"],
        "svrname": request["svrname"],
        "roleidx": request["roleidx"],
    }
    if caps(password):
        payload["caps"] = caps(password)
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if any(c.isspace() for c in text):
        raise LaunchError("启动参数（workspace、服务器名或密码）含空白，引擎无法解析")
    return text


def validate_request(request, allowed):
    """校验请求结构、客户端目录白名单和 workspace 路径；返回 mhmain.exe 路径。"""
    if not isinstance(request, dict) or set(request) != REQUEST_KEYS:
        raise LaunchError("启动请求字段无效")
    for key in REQUEST_KEYS - {"roleidx"}:
        value = request[key]
        if not isinstance(value, str) or not value or any(c in value for c in "\r\n\x00\""):
            raise LaunchError(f"启动请求字段无效：{key}")
    if type(request["roleidx"]) is not int or not 0 <= request["roleidx"] < 16:
        raise LaunchError("启动请求字段无效：roleidx")
    if "\\" in request["workspace"] or not Path(request["workspace"]).is_dir():
        raise LaunchError("workspace 必须是已存在的目录，用 / 分隔")
    if norm(request["client_dir"]) not in {norm(item) for item in allowed}:
        raise LaunchError(f"客户端目录未在安装时登记：{request['client_dir']}")
    exe = Path(request["client_dir"]) / EXE
    if not exe.is_file():
        raise LaunchError(f"找不到 {exe}")
    return exe


def account_password(config_path, account):
    """从用户级配置的账号池取密码；账号不区分大小写。"""
    try:
        values = json.loads(Path(config_path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise LaunchError(f"无法读取用户级配置：{error}") from None
    for item in values.get("login_accounts") or []:
        if isinstance(item, dict) and str(item.get("account", "")).lower() == account.lower():
            password = item.get("password")
            if isinstance(password, str) and password:
                return password
    raise LaunchError(f"账号池中没有 {account} 或密码为空")


def start(exe, payload):
    """脱离计划任务启动客户端，任务结束不影响客户端；返回进程号。

    命令行手工拼接：payload 原样跟在标志后面，不能经过 list2cmdline（会给引号加反斜杠）。
    """
    command = f'"{exe}" {LAUNCH_FLAG} {payload}'
    flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    for extra in (CREATE_BREAKAWAY_FROM_JOB, 0):  # 所在作业不允许脱离时退回普通启动
        try:
            process = subprocess.Popen(command, cwd=str(exe.parent),
                                       creationflags=flags | extra, close_fds=True)
            return process.pid
        except OSError:
            if not extra:
                raise
    raise LaunchError("无法启动客户端")


def write_result(path, result):
    temporary = Path(str(path) + ".tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--allow", action="append", default=[])
    args = parser.parse_args(argv)
    request_path = Path(args.request)
    result_path = request_path.with_name("result.json")
    result = {"id": None, "pid": None, "error": None, "finished": None}
    try:
        try:
            request = json.loads(request_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise LaunchError(f"无法读取启动请求：{error}") from None
        finally:
            try:
                request_path.unlink()  # 请求只用一次，避免重复触发时再次启动
            except OSError:
                pass
        result["id"] = request.get("id") if isinstance(request, dict) else None
        exe = validate_request(request, args.allow)
        password = account_password(args.config, request["account"])
        result["pid"] = start(exe, build_payload(request, password))
    except (LaunchError, OSError) as error:
        result["error"] = str(error)
    result["finished"] = time.time()
    write_result(result_path, result)
    return 0 if result["error"] is None else 1


if __name__ == "__main__":
    sys.exit(main())
