# -*- coding: utf-8 -*-
"""开发分支打 patch：查／建 Sunshine 打包模板、发起打包、查打包进度。流程说明见 references/patch.md。

通过 HTTP 直连打包服务 mh-patch-mcp（MCP，有状态，需 X-Access-Token）。令牌每次运行时向本机 CodeMaker Hub
的 helper 现取（与 OpenForge 的 MCP 代理同一来源），不落盘、不输出；服务判定令牌失效时续签一次再试。
每个子命令向 stdout 输出一个 JSON 对象（字段固定，见 empty_result），供 agent 和以后的 popo-agent-service 读取。
建模板、发起打包只在加 --apply 时执行；不加时只发只读请求并输出将要做什么。

退出码：0 成功（含预览）；1 失败且未改远端；2 远端已改但后续步骤失败（输出说明已完成哪一步）。
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import unquote
from urllib.request import Request, urlopen
from time import sleep

sys.dont_write_bytecode = True
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "game-debugging"))
import branch  # noqa: E402
from mcp_http import find_response  # noqa: E402
import workspace  # noqa: E402

URL = "http://aluba-mh-patch-mcp.eros.nie.netease.com/mcp"
TIMEOUT = 180  # 秒；与 Codex 配置中该服务的工具超时一致。
RES_SUBDIR = "_test"  # 已有模板的 respath 都填到资源分支下的 _test（2026-11-12 只读核实）。
DEV_SCRIPT = re.compile(rf"^{re.escape(branch.SCRIPT_BRANCH_ROOT)}/(\d{{4}})_dev/([^/]+)$")
# 资源分支不一定与脚本分支同名、同年份（已有模板中有 2026_dev 脚本配 2025_dev 资源、dct_dev/hc27 等），
# 只要求在 share/patch 仓库下、以 _test 结尾。
RES_PREFIX = branch.RES_BRANCH_ROOT.rsplit("/", 1)[0] + "/"
NOT_DEV = "只支持开发分支（wzimage/branchs/<年>_dev/<分支>）；外放分支请走单独流程"
TOKEN_INVALID = ("v2_token", "X-Access-Token")  # 服务报令牌问题时错误文本中出现的词。
# CodeMaker Hub 本地 helper：mcp-token-helper 秒回当前令牌，hub-auth-helper renew-token 走网络续签。
HUB_ENV = "CODEMAKER_HUB_AUTH_HELPER_BIN"  # 与 OpenForge 代理相同的覆盖变量，Hub 装在自定义目录时使用。
HUB_EXE = "codemaker-hub-gui.exe"
HUB_CURRENT = ("mcp-token-helper",)
HUB_RENEW = ("hub-auth-helper", "renew-token")
HUB_TOKEN_KEYS = ("X-Access-Token", "access_token")
HUB_TIMEOUT = 30
TOKEN_HINT = "请确认 CodeMaker Hub 已安装、正在运行并已登录（Hub 装在自定义目录时设置环境变量 CODEMAKER_HUB_AUTH_HELPER_BIN）"
DEFAULT_RECENT = 10
# pack_issue 的模板名规则与读回等待（2026-11-12 实测，见 specs/2026-11-12-dev-patch.md）：
# 模板名为“#<总单号> ”加截到 10 个字符的标题；新模板一两分钟后才能查到。
# 总单号必须真实：issue_id=0 时服务会无视传入的地址，写入一个固定的他人分支。
SUBJECT_LIMIT = 10
READBACK_TIMEOUT = 300
READBACK_INTERVAL = 20


class PatchError(Exception):
    """可直接呈现给用户的错误；code 为退出码（2 表示远端已改）。"""

    def __init__(self, message, code=1):
        super().__init__(message)
        self.code = code


def empty_result(action, applied=False):
    """所有子命令共用的输出结构；不适用的字段保持 null 或空列表。"""
    return {"action": action, "applied": applied, "branch": None, "template": None, "package": None,
            "job": None, "candidates": [], "tables": None, "next": None, "warnings": [], "errors": []}


def hub_paths():
    """Hub helper 的候选路径：环境变量 → 常见安装目录 → PATH。"""
    candidates = [os.environ.get(HUB_ENV)]
    for key in ("LOCALAPPDATA", "ProgramFiles", "ProgramFiles(x86)"):
        base = os.environ.get(key)
        if base:
            candidates.append(os.path.join(base, "CodeMaker Hub", HUB_EXE))
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates.append(os.path.join(local, "Programs", "CodeMaker Hub", HUB_EXE))
    candidates.append(shutil.which(HUB_EXE))
    return [path for path in candidates if path and os.path.isfile(path)]


def hub_token(renew=False):
    """向 CodeMaker Hub helper 取令牌；renew 时先走续签。失败抛 PatchError，不输出 helper 的原始内容。"""
    paths = hub_paths()
    if not paths:
        raise PatchError(f"没有找到 CodeMaker Hub（{HUB_EXE}），取不到打包令牌；{TOKEN_HINT}")
    commands = (HUB_RENEW, HUB_CURRENT) if renew else (HUB_CURRENT, HUB_RENEW)
    for exe in paths:
        for args in commands:
            try:
                completed = subprocess.run([exe, *args], capture_output=True, timeout=HUB_TIMEOUT,
                                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except (OSError, subprocess.SubprocessError):
                continue
            if completed.returncode:
                continue
            for line in reversed(completed.stdout.decode("utf-8", "replace").splitlines()):
                try:
                    payload = json.loads(line)
                except ValueError:
                    continue
                if isinstance(payload, dict):
                    for key in HUB_TOKEN_KEYS:
                        token = payload.get(key)
                        if isinstance(token, str) and re.fullmatch(r"[\x21-\x7e]+", token.strip()):
                            return token.strip()
                    break
    raise PatchError(f"CodeMaker Hub 没有返回打包令牌；{TOKEN_HINT}")


class Remote:
    """打包服务的 MCP 会话：initialize 拿到 mcp-session-id 后在同一会话里调用工具。"""

    def __init__(self, token_source=hub_token, url=URL, timeout=TIMEOUT):
        self.token_source, self.url, self.timeout = token_source, url, timeout
        self.token = None
        self.session = None
        self.next_id = 1

    def post(self, payload):
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                   "X-Access-Token": self.token}
        if self.session:
            headers["Mcp-Session-Id"] = self.session
        request = Request(self.url, data=json.dumps(payload).encode("utf-8"), headers=headers)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                self.session = response.headers.get("mcp-session-id") or self.session
                return response.read().decode("utf-8", "replace")
        except HTTPError as error:
            raise PatchError(f"打包服务返回 HTTP {error.code}") from None
        except (URLError, OSError) as error:
            raise PatchError(f"打包服务请求失败或超时：{getattr(error, 'reason', error)}；"
                             "请求可能已经执行，先用 prepare／status 查清再决定是否重试") from None

    def request(self, method, params):
        request_id = self.next_id
        self.next_id += 1
        body = self.post({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        response = find_response(body, request_id)
        if response is None or "error" in response:
            raise PatchError(f"打包服务 {method} 失败：{(response or {}).get('error') or body[:200]}")
        return response["result"]

    def open(self, renew=False):
        self.token = self.token_source(renew=renew)
        self.session = None
        self.request("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                    "clientInfo": {"name": "mhxy-workspace", "version": "1.0"}})
        self.post({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def call(self, name, arguments=None):
        """调用工具，返回业务载荷（structuredContent，否则把文本按 JSON 解析）。

        服务判定令牌失效时请求不会执行：续签令牌、重开会话后再试一次。
        """
        if self.session is None:
            self.open()
        for renewed in (False, True):
            result = self.request("tools/call", {"name": name, "arguments": arguments or {}})
            text = "".join(item.get("text", "") for item in result.get("content", []) if isinstance(item, dict))
            if not result.get("isError"):
                break
            if not any(word in text for word in TOKEN_INVALID):
                raise PatchError(f"{name} 返回错误：{text[:300]}")
            if renewed:
                raise PatchError(f"打包服务拒绝了续签后的令牌；{TOKEN_HINT}")
            self.open(renew=True)
        payload = result.get("structuredContent")
        if isinstance(payload, dict) and set(payload) == {"result"}:
            payload = payload["result"]  # FastMCP 把非字典返回值包在 result 里。
        if payload is not None:
            return payload
        try:
            return json.loads(text)
        except ValueError:
            raise PatchError(f"{name} 返回无法解析：{text[:200]}") from None


def normalize(url):
    return unquote((url or "").strip()).rstrip("/")


def dev_branch(root, result):
    """读取工作区脚本和资源工作副本的地址：脚本必须是开发分支，资源必须是 share/patch 下的 _test。"""
    root = Path(root).resolve()
    try:
        script = branch.svn_info(root, item="url")
        resource = branch.svn_info(root.parent / RES_SUBDIR, item="url")
    except branch.BranchError as error:
        raise PatchError(f"读取工作副本地址失败：{error}") from None
    if not script:
        raise PatchError(f"{root} 不是 SVN 工作副本")
    script = normalize(script)
    script_match = DEV_SCRIPT.match(script)
    if not script_match:
        raise PatchError(f"{NOT_DEV}；当前脚本地址：{script}")
    if not resource:
        raise PatchError(f"没有找到资源工作副本 {root.parent / RES_SUBDIR}")
    resource = normalize(resource)
    if not resource.startswith(RES_PREFIX) or not resource.endswith("/" + RES_SUBDIR):
        raise PatchError(f"资源工作副本不是 share/patch 下的 {RES_SUBDIR}：{resource}")
    result["branch"] = {"name": script_match.group(2), "year": script_match.group(1),
                        "script_svn": script, "res_svn": resource}
    if resource.rsplit("/", 2)[-2] != script_match.group(2):
        result["warnings"].append(f"资源分支与脚本分支名称不同（资源：{resource}），请确认是本需求的资源")
    return result["branch"]


def workspace_config():
    return str(Path.home() / workspace.DIRECTORY / "config.json")


def recorded_template(root):
    """读取工作区记录的模板名；同时确认工作区已初始化，使记录模板名不会在远端改完之后才失败。"""
    try:
        workspace.require_initialized(Path(root).resolve())
        return workspace.load_config(root, workspace_config())["patch_template"]
    except (workspace.WorkspaceError, OSError, UnicodeError) as error:
        raise PatchError(f"读取工作区配置失败：{error}") from None


def check_name(name):
    if not workspace.valid_patch_template(name):
        raise PatchError("模板名必须是 1–64 字符的单行文本，不含引号、反斜杠，首尾无空白")
    return name


def describe_template(info, branch_info):
    """把服务返回的模板整理为输出结构，并判断它是否绑定本分支。"""
    template = info.get("template") or {}
    script = normalize(template.get("scriptpath"))
    resource = normalize(template.get("respath"))
    return {"name": info.get("matched_name") or template.get("name"), "exists": True,
            "script_svn": script, "res_svn": resource, "description": template.get("description"),
            "matches_branch": script == branch_info["script_svn"],
            "res_matches_branch": resource == branch_info["res_svn"]}


def describe_package(package):
    if not package:
        return None
    keys = ("upload_time", "packer_username", "script_url", "res_url", "res_missing", "table_config", "patch_info")
    return {key: package.get(key) for key in keys}


def lookup(remote, name, branch_info, result):
    """按模板名精确查找，填入 result；返回是否存在。模糊命中只作为候选提醒，不算存在。"""
    info = remote.call("query_patch_by_template", {"template_name": name})
    status = info.get("status")
    if status not in ("no_template", "packed", "not_packed"):
        raise PatchError(f"query_patch_by_template 返回未知状态：{status!r}")
    fuzzy = list(info.get("candidates") or [])
    if status != "no_template":
        matched = info.get("matched_name") or (info.get("template") or {}).get("name")
        if matched == name:
            result["template"] = describe_template(info, branch_info)
            result["package"] = describe_package(info.get("package"))
            if not result["template"]["res_matches_branch"]:
                result["warnings"].append(f"模板资源地址 {result['template']['res_svn']} 与本分支资源 "
                                          f"{branch_info['res_svn']} 不同")
            return True
        fuzzy = [matched]
    result["template"] = {"name": name, "exists": False}
    result["candidates"] = fuzzy
    if fuzzy:
        result["warnings"].append(f"没有名为“{name}”的模板；名称相近的已有模板：{'、'.join(fuzzy)}，"
                                  "如果其中有本需求的模板，请改用它的准确名称")
    return False


def find_candidates(remote, branch_info):
    """按分支名关键词反查已有模板（服务只搜模板名和描述），只保留脚本地址等于本分支的。"""
    found = remote.call("query_patch_template", {"keyword": branch_info["name"]})
    candidates = []
    for match in found.get("matches") or []:
        data = match.get("data") or {}
        if normalize(data.get("scriptpath") or data.get("patch")) == branch_info["script_svn"]:
            candidates.append(match.get("name"))
    return candidates


def remember(root, name, result):
    """远端完成后把模板名记到工作区级配置；任何失败都按“远端已改”报告。"""
    try:
        if workspace.load_config(root, workspace_config())["patch_template"] == name:
            return
        workspace.configure_local(root, workspace_config(), [f"patch_template={name}"], apply=True)
    except (workspace.WorkspaceError, OSError, UnicodeError) as error:
        raise PatchError(f"远端已完成，但记录模板名失败：{error}", code=2) from None
    result["warnings"].append(f"已把模板名“{name}”记到工作区配置 patch_template")


def prepare(remote, result, root, name):
    branch_info = dev_branch(root, result)
    name = name or recorded_template(root)
    if not name:
        result["candidates"] = find_candidates(remote, branch_info)
        result["next"] = "name"
        return
    check_name(name)
    if not lookup(remote, name, branch_info, result):
        result["next"] = "create"
    elif result["template"]["matches_branch"]:
        result["next"] = "start"
    else:
        result["next"] = "stop"
        result["errors"].append(f"模板“{name}”绑定的脚本地址 {result['template']['script_svn']} "
                                "不是本分支，不在这里打包；请在 Sunshine 上处理或换一个模板名")


def tables(remote, result, issue_id):
    found = remote.call("query_ca_table_options", {"issue_id": str(issue_id)})
    if not found.get("success"):
        raise PatchError(f"查询导表选项失败：{found.get('error')}")
    result["tables"] = {"issue_id": found.get("issue_id"), "tables": found.get("tables") or [],
                        "options": found.get("options") or []}


def expected_name(subject, issue_id):
    """服务实际使用的模板名：“#<总单号> ”加截到 SUBJECT_LIMIT 个字符的标题（2026-11-12 三次实测）。"""
    return f"#{issue_id} {subject[:SUBJECT_LIMIT]}"


def read_back(remote, name, branch_info, result):
    """新建的模板要等服务的模板列表刷新（实测一两分钟）才查得到：在 READBACK_TIMEOUT 内反复查。"""
    waited = 0
    while True:
        try:
            if lookup(remote, name, branch_info, result):
                return True
        except PatchError as error:
            raise PatchError(f"模板“{name}”已建，读回失败：{error}", code=2) from None
        if waited >= READBACK_TIMEOUT:
            return False
        sleep(READBACK_INTERVAL)
        waited += READBACK_INTERVAL


def create(remote, result, root, subject, issue_id, table, apply):
    branch_info = dev_branch(root, result)
    check_name(subject)
    recorded_template(root)  # 远端写入前确认工作区配置可读、可记录。
    name = expected_name(subject, issue_id)
    if len(subject) > SUBJECT_LIMIT:
        result["warnings"].append(f"服务会把标题截到 {SUBJECT_LIMIT} 个字符，模板名将是“{name}”")
    if lookup(remote, name, branch_info, result):
        raise PatchError(f"模板“{name}”已存在，不再新建；打包用 start")
    arguments = {"subject": subject, "script_svn": branch_info["script_svn"], "res_svn": branch_info["res_svn"],
                 "issue_id": issue_id, "tableinfo": list(table), "auto_start": False}
    result["job"] = {"tool": "pack_issue", "arguments": arguments, "expected_name": name}
    if not apply:
        result["next"] = "confirm"
        return
    created = remote.call("pack_issue", arguments)
    if not created.get("success"):
        raise PatchError(f"建模板失败：{created.get('error')}")
    actual = created.get("template_name") or name
    result["job"]["result"] = {"template_name": actual, "tableinfo": created.get("tableinfo"),
                               "tableinfo_source": created.get("tableinfo_source")}
    if actual != name:
        result["warnings"].append(f"服务实际使用的模板名是“{actual}”，与预计的“{name}”不同")
    exists = read_back(remote, actual, branch_info, result)
    template = result["template"]
    if not exists:
        raise PatchError(f"模板“{actual}”已建，但 {READBACK_TIMEOUT} 秒内没有查到；稍后用 prepare --name 核对", code=2)
    if not template["matches_branch"] or not template["res_matches_branch"]:
        raise PatchError(f"模板“{actual}”已建，但读回的地址与本分支不符：脚本 {template['script_svn']}，"
                         f"资源 {template['res_svn']}；不要用它打包", code=2)
    remember(root, actual, result)
    result["next"] = "start"


def start(remote, result, root, name, apply):
    branch_info = dev_branch(root, result)
    name = name or recorded_template(root)
    if not name:
        raise PatchError("没有模板名：用 --name 指定，或先用 prepare 确定模板名")
    check_name(name)
    recorded_template(root)  # 远端写入前确认工作区配置可读、可记录。
    if not lookup(remote, name, branch_info, result):
        raise PatchError(f"模板“{name}”不存在，先用 create 新建")
    if not result["template"]["matches_branch"]:
        raise PatchError(f"模板“{name}”绑定的脚本地址 {result['template']['script_svn']} 不是本分支，不打包")
    result["job"] = {"tool": "start_patching", "arguments": {"template_name": name}}
    if not apply:
        result["next"] = "confirm"
        return
    started = remote.call("start_patching", {"template_name": name})
    if not started.get("started"):
        raise PatchError(f"发起打包失败：{started.get('message')}")
    result["job"]["result"] = {key: started.get(key) for key in ("job_id", "batch_id", "message")}
    remember(root, name, result)
    result["next"] = "status"


def status(remote, result, job_id, recent, raw):
    if job_id:
        found = remote.call("query_pack_job_status", {"job_id": job_id})
        if not found.get("found"):
            raise PatchError(f"没有找到打包任务 {job_id}（服务重启会清空任务记录）")
        if not raw:
            found.pop("raw_error", None)
        result["job"] = found
        result["next"] = None if found.get("status") in ("success", "failed") else "status"
    else:
        result["job"] = remote.call("query_recent_pack_jobs", {"limit": recent})


def main(argv=None, remote=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "tables", "create", "start", "status"))
    parser.add_argument("--root", default=".")
    parser.add_argument("--name", help="中文模板名；省略时用工作区配置 patch_template")
    parser.add_argument("--issue-id", type=int, help="易协作总单号；tables、create 必填")
    parser.add_argument("--table", action="append", default=[], help="create：导表选项序号，可重复；默认不导表")
    parser.add_argument("--job-id")
    parser.add_argument("--recent", type=int, nargs="?", const=DEFAULT_RECENT)
    parser.add_argument("--raw", action="store_true", help="status：输出完整打包日志 raw_error")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    result = empty_result(args.action, args.apply)
    try:
        if args.apply and args.action not in ("create", "start"):
            raise PatchError("--apply 只用于 create、start")
        if args.table and args.action != "create":
            raise PatchError("--table 只用于 create")
        if any(not re.fullmatch(r"\d+", item) for item in args.table):
            raise PatchError("--table 应为导表选项的序号（tables 输出的 options 里的 index）")
        if args.action == "status" and bool(args.job_id) == (args.recent is not None):
            raise PatchError("status 需要 --job-id 或 --recent（二选一）")
        if args.action == "tables" and not args.issue_id:
            raise PatchError("tables 需要 --issue-id")
        if args.action == "create" and not args.name:
            raise PatchError("create 需要 --name")
        if args.action == "create" and not (args.issue_id and args.issue_id > 0):
            raise PatchError("create 需要 --issue-id 总单号（单号为 0 时服务会写入错误的分支地址）")
        remote = remote or Remote()
        if args.action == "prepare":
            prepare(remote, result, args.root, args.name)
        elif args.action == "tables":
            tables(remote, result, args.issue_id)
        elif args.action == "create":
            create(remote, result, args.root, args.name, args.issue_id, args.table, args.apply)
        elif args.action == "start":
            start(remote, result, args.root, args.name, args.apply)
        else:
            status(remote, result, args.job_id, min(max(DEFAULT_RECENT if args.recent is None else args.recent, 1), 50), args.raw)
        code = 1 if result["errors"] else 0
    except PatchError as error:
        result["errors"].append(str(error))
        code = error.code
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
