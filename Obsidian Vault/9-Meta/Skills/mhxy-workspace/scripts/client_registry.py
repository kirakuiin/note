"""自动启动的客户端登记（见 specs/2026-11-12-client-auto-close.md）。

client_launch.py 启动客户端后登记，close／reap 只关登记过的；select 选中复用、codex_cli.py release 释放锁时刷新 last_used。
每台客户端一个文件，先写临时文件再 os.replace，不同会话并发写不同文件。
"""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import time
import uuid

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
STILL_ACTIVE = 259
ERROR_ACCESS_DENIED = 5
EXE = "mhmain.exe"


def base():
    """与设备锁目录（mhxy-cli-testing/locks）同级；调用时读环境变量，便于测试替换。"""
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".cache"))) / "mhxy-cli-testing"


def directory():
    return base() / "clients"


def entry_path(pid, created):
    return directory() / f"{int(pid)}-{int(created)}.json"


def write(entry):
    """原子写入一条登记；返回文件路径。"""
    path = entry_path(entry["pid"], entry["created"])
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, path)
    return path


def register(pid, created, **fields):
    now = time.time()
    entry = {"devid": None, "pid": int(pid), "created": int(created), "platform": None, "account": None,
             "client_dir": None, "root": None, "owner": None, "started_at": now, "last_used": now}
    entry.update(fields)
    write(entry)
    return entry


def entries():
    """全部登记，按启动时间排序；读不出的文件跳过（可能正被替换）。"""
    folder = directory()
    if not folder.is_dir():
        return []
    result = []
    for path in folder.glob("*.json"):
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(entry, dict) and isinstance(entry.get("pid"), int) and isinstance(entry.get("created"), int):
            result.append(entry)
    return sorted(result, key=lambda item: item.get("started_at") or 0)


def read(entry):
    """重新读取一条登记的最新内容；已被删除返回 None。"""
    try:
        return json.loads(entry_path(entry["pid"], entry["created"]).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None


def remove(entry):
    entry_path(entry["pid"], entry["created"]).unlink(missing_ok=True)


def update(entry, **fields):
    """改登记字段；登记已被删除（已关闭）时不重建，返回 None。"""
    path = entry_path(entry["pid"], entry["created"])
    try:
        current = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    current.update(fields)
    write(current)
    return current


def touch(devid, now=None):
    """刷新 devid 对应登记的 last_used；返回刷新的条数。"""
    count = 0
    for entry in entries():
        if devid and entry.get("devid") == devid and update(entry, last_used=now or time.time()):
            count += 1
    return count


def same_root(a, b):
    if not a or not b:
        return False
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


# ---------- 进程核对 ----------

def _kernel32():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    kernel.GetProcessTimes.argtypes = (wintypes.HANDLE,) + (ctypes.POINTER(wintypes.FILETIME),) * 4
    kernel.QueryFullProcessImageNameW.argtypes = (wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                  ctypes.POINTER(wintypes.DWORD))
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    return kernel


def process_info(pid):
    """返回运行中进程的 {"created": FILETIME 整数, "image": 映像完整路径}；进程不存在或已退出返回 None。

    无权查询时抛 OSError：不能把“看不见”当成“已退出”而删掉登记。
    """
    kernel = _kernel32()
    handle = kernel.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        error = ctypes.get_last_error()
        if error == ERROR_ACCESS_DENIED:
            raise OSError(f"无权查询进程 {pid}")
        return None
    try:
        code = wintypes.DWORD()
        if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value != STILL_ACTIVE:
            return None
        times = [wintypes.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(handle, *(ctypes.byref(item) for item in times)):
            raise OSError(f"读不到进程 {pid} 的创建时间")
        created = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            raise OSError(f"读不到进程 {pid} 的映像路径")
        return {"created": created, "image": buffer.value}
    finally:
        kernel.CloseHandle(handle)


# ---------- close 持有的设备锁 ----------
# client_launch.py close 关闭期间占用 codex_cli.py 的设备锁（同一个文件），锁内容记下 close 进程的
# pid 和创建时间。close 进程被杀时锁会残留，持有者已退出的这种锁由 client_launch.py 和 codex_cli.py
# 加锁时回收（stale_close_lock／reclaim_close_lock）；codex_cli 自己的锁没有这两个字段，不受影响。

def close_lock_body(devid, pid):
    me = process_info(os.getpid())
    return {"job": f"client_launch close（客户端进程 {pid}）", "devid": devid,
            "closer_pid": os.getpid(), "closer_created": me["created"]}


def stale_close_lock(path):
    """path 是 close 留下的锁、且持有它的 close 进程已退出；读不清时视为不是。"""
    try:
        body = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    pid, created = body.get("closer_pid"), body.get("closer_created")
    if type(pid) is not int or type(created) is not int:
        return False
    try:
        info = process_info(pid)
    except OSError:
        return False
    return not (info and info["created"] == created)


def reclaim_close_lock(path):
    """删除持有者已退出的 close 锁，返回是否已删除。

    先原子改名再核对内容，避免删掉核对之后别人新加的锁；改名拿到的不是原来那把锁时用硬链接放回。
    """
    path = Path(path)
    if not stale_close_lock(path):  # 粗筛：有效的锁不去动它
        return False
    claimed = path.with_name(f"{path.name}.{uuid.uuid4().hex}.reclaiming")
    try:
        os.rename(path, claimed)
    except FileNotFoundError:
        return True
    if stale_close_lock(claimed):  # 以改名拿到的那份为准再判断，粗筛之后被换上的新锁不会被删
        claimed.unlink()
        return True
    try:
        os.link(claimed, path)
    except FileExistsError:
        return False  # 原位已有新锁：不覆盖，被改名的锁留在 claimed 供核实
    claimed.unlink()
    return False


def alive(entry):
    """登记的进程仍在：pid 存在、创建时间一致、映像名是 mhmain.exe。"""
    info = process_info(entry["pid"])
    return bool(info and info["created"] == entry["created"]
                and os.path.basename(info["image"]).lower() == EXE)
