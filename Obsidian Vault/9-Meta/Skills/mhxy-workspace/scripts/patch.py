# -*- coding: utf-8 -*-
"""开发分支打 patch：查／建 Sunshine 打包模板、发起打包、查打包进度。流程说明见 references/patch.md。

通过 HTTP 直连打包服务 mh-patch-mcp（MCP，有状态，需 X-Access-Token），令牌取自用户级配置 patch_token。
每个子命令向 stdout 输出一个 JSON 对象（字段固定，见 empty_result），供 agent 和以后的 popo-agent-service 读取。
建模板、发起打包只在加 --apply 时执行；不加时只发只读请求并输出将要做什么。

退出码：0 成功（含预览）；1 失败且未改远端；2 远端已改但后续步骤失败（输出说明已完成哪一步）。
"""
import argparse
import json
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import unquote
from urllib.request import Request, urlopen

sys.dont_write_bytecode = True
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "game-debugging"))
import branch  # noqa: E402
from mcp_http import find_response  # noqa: E402
import workspace  # noqa: E402

URL = "http://aluba-mh-patch-mcp.eros.nie.netease.com/mcp"
TIMEOUT = 180  # 秒；与 Codex 配置中该服务的工具超时一致。
RES_SUBDIR = "_test"  # 模板资源地址填到资源分支下的 _test（待用已有模板核实，见 specs/2026-11-12-dev-patch.md）。
DEV_SCRIPT = re.compile(rf"^{re.escape(branch.SCRIPT_BRANCH_ROOT)}/(\d{{4}})_dev/([^/]+)$")
DEV_RES = re.compile(rf"^{re.escape(branch.RES_BRANCH_ROOT)}/(\d{{4}})_dev/([^/]+)/{RES_SUBDIR}$")
NOT_DEV = "只支持开发分支（wzimage/branchs/<年>_dev/<分支>）；外放分支请走单独流程"
TOKEN_INVALID = ("v2_token", "X-Access-Token")  # 服务报令牌问题时错误文本中出现的词。
TOKEN_HINT = ("打包令牌无效或已过期，请重新设置："
              "python \"<skill>/scripts/workspace.py\" config --prompt-patch-token --apply")
DEFAULT_RECENT = 10


class PatchError(Exception):
    """可直接呈现给用户的错误；code 为退出码（2 表示远端已改）。"""

    def __init__(self, message, code=1):
        super().__init__(message)
        self.code = code


def empty_result(action, applied=False):
    """所有子命令共用的输出结构；不适用的字段保持 null 或空列表。"""
    return {"action": action, "applied": applied, "branch": None, "template": None, "package": None,
            "job": None, "candidates": [], "tables": None, "next": None, "warnings": [], "errors": []}


class Remote:
    """打包服务的 MCP 会话：initialize 拿到 mcp-session-id 后在同一会话里调用工具。"""

    def __init__(self, token, url=URL, timeout=TIMEOUT):
        if not token:
            raise PatchError("没有配置打包令牌：" + TOKEN_HINT.split("：", 1)[1])
        self.token, self.url, self.timeout = token, url, timeout
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

    def call(self, name, arguments=None):
        """调用工具，返回业务载荷（structuredContent，否则把文本按 JSON 解析）。"""
        if self.session is None:
            self.request("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                        "clientInfo": {"name": "mhxy-workspace", "version": "1.0"}})
            self.post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        result = self.request("tools/call", {"name": name, "arguments": arguments or {}})
        text = "".join(item.get("text", "") for item in result.get("content", []) if isinstance(item, dict))
        if result.get("isError"):
            if any(word in text for word in TOKEN_INVALID):
                raise PatchError(TOKEN_HINT)
            raise PatchError(f"{name} 返回错误：{text[:300]}")
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


def dev_branch(root):
    """读取工作区脚本和资源工作副本的地址，校验是同一个开发分支。"""
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
    res_match = DEV_RES.match(resource)
    if not res_match or res_match.groups() != script_match.groups():
        raise PatchError(f"资源工作副本与脚本不是同一个开发分支：{resource}")
    return {"name": script_match.group(2), "year": script_match.group(1), "script_svn": script, "res_svn": resource}


def recorded_template(root):
    try:
        return workspace.load_config(root, workspace_config())["patch_template"]
    except workspace.WorkspaceError as error:
        raise PatchError(f"读取工作区配置失败：{error}") from None


def workspace_config():
    return str(Path.home() / workspace.DIRECTORY / "config.json")


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
    """查模板现状，填入 result；返回模板是否存在。"""
    info = remote.call("query_patch_by_template", {"template_name": name})
    status = info.get("status")
    if status == "no_template":
        result["template"] = {"name": name, "exists": False}
        result["candidates"] = list(info.get("candidates") or [])
        if result["candidates"]:
            result["warnings"].append(f"模板名“{name}”没有精确命中，模糊候选：{'、'.join(result['candidates'])}")
        return False
    if status not in ("packed", "not_packed"):
        raise PatchError(f"query_patch_by_template 返回未知状态：{status!r}")
    result["template"] = describe_template(info, branch_info)
    result["package"] = describe_package(info.get("package"))
    if result["template"]["name"] != name:
        result["warnings"].append(f"模板名“{name}”模糊命中“{result['template']['name']}”，请确认是否就是它")
    if not result["template"]["res_matches_branch"]:
        result["warnings"].append(f"模板资源地址 {result['template']['res_svn']} 与本分支资源 "
                                  f"{branch_info['res_svn']} 不同")
    return True


def find_candidates(remote, branch_info):
    """按分支名反查已有模板，只保留脚本地址等于本分支的。"""
    found = remote.call("query_patch_template", {"keyword": branch_info["name"]})
    candidates = []
    for match in found.get("matches") or []:
        data = match.get("data") or {}
        script = normalize(data.get("scriptpath") or data.get("patch"))
        if script == branch_info["script_svn"]:
            candidates.append(match.get("name"))
    return candidates


def remember(root, name, result):
    """把模板名记到工作区级配置；已经记录同名时不写。"""
    if recorded_template(root) == name:
        return
    try:
        workspace.configure_local(root, workspace_config(), [f"patch_template={name}"], apply=True)
    except workspace.WorkspaceError as error:
        raise PatchError(f"远端已完成，但记录模板名失败：{error}", code=2) from None
    result["warnings"].append(f"已把模板名“{name}”记到工作区配置 patch_template")


def prepare(remote, root, name):
    result = empty_result("prepare")
    branch_info = dev_branch(root)
    result["branch"] = branch_info
    name = name or recorded_template(root)
    if not name:
        result["candidates"] = find_candidates(remote, branch_info)
        result["next"] = "name"
        return result
    check_name(name)
    if not lookup(remote, name, branch_info, result):
        result["next"] = "create"
    elif result["template"]["matches_branch"]:
        result["next"] = "start"
    else:
        result["next"] = "stop"
        result["errors"].append(f"模板“{result['template']['name']}”绑定的脚本地址 {result['template']['script_svn']} "
                                f"不是本分支，不在这里打包；请在 Sunshine 上处理或换一个模板名")
    return result


def tables(remote, issue_id):
    result = empty_result("tables")
    found = remote.call("query_ca_table_options", {"issue_id": str(issue_id)})
    if not found.get("success"):
        raise PatchError(f"查询导表选项失败：{found.get('error')}")
    result["tables"] = {"issue_id": found.get("issue_id"), "tables": found.get("tables") or [],
                        "options": found.get("options") or []}
    return result


def create(remote, root, name, issue_id, table, apply):
    result = empty_result("create", apply)
    branch_info = dev_branch(root)
    result["branch"] = branch_info
    check_name(name)
    if lookup(remote, name, branch_info, result):
        raise PatchError(f"模板“{result['template']['name']}”已存在，不再新建；打包用 start")
    arguments = {"subject": name, "script_svn": branch_info["script_svn"], "res_svn": branch_info["res_svn"],
                 "issue_id": int(issue_id or 0), "tableinfo": list(table), "auto_start": False}
    result["job"] = {"tool": "pack_issue", "arguments": arguments}
    if not apply:
        result["next"] = "confirm"
        return result
    created = remote.call("pack_issue", arguments)
    if not created.get("success"):
        raise PatchError(f"建模板失败：{created.get('error')}")
    actual = created.get("template_name") or name
    result["job"]["result"] = {"template_name": actual, "tableinfo": created.get("tableinfo"),
                               "tableinfo_source": created.get("tableinfo_source")}
    try:
        exists = lookup(remote, actual, branch_info, result)
    except PatchError as error:
        raise PatchError(f"模板“{actual}”已建，读回失败：{error}", code=2) from None
    if not exists or not result["template"]["matches_branch"] or not result["template"]["res_matches_branch"]:
        raise PatchError(f"模板“{actual}”已建，但读回的地址与本分支不符：{result['template']}", code=2)
    if actual != name:
        result["warnings"].append(f"服务实际使用的模板名是“{actual}”，与输入的“{name}”不同")
    remember(root, actual, result)
    result["next"] = "start"
    return result


def start(remote, root, name, apply):
    result = empty_result("start", apply)
    branch_info = dev_branch(root)
    result["branch"] = branch_info
    name = name or recorded_template(root)
    if not name:
        raise PatchError("没有模板名：用 --name 指定，或先用 prepare 确定模板名")
    check_name(name)
    if not lookup(remote, name, branch_info, result):
        raise PatchError(f"模板“{name}”不存在，先用 create 新建")
    template = result["template"]
    if not template["matches_branch"]:
        raise PatchError(f"模板“{template['name']}”绑定的脚本地址 {template['script_svn']} 不是本分支，不打包")
    if template["name"] != name:
        raise PatchError(f"模板名“{name}”没有精确命中（命中“{template['name']}”），请用准确的模板名")
    result["job"] = {"tool": "start_patching", "arguments": {"template_name": name}}
    if not apply:
        result["next"] = "confirm"
        return result
    started = remote.call("start_patching", {"template_name": name})
    if not started.get("started"):
        raise PatchError(f"发起打包失败：{started.get('message')}")
    result["job"]["result"] = {key: started.get(key) for key in ("job_id", "batch_id", "message")}
    remember(root, name, result)
    result["next"] = "status"
    return result


def status(remote, job_id, recent, raw):
    result = empty_result("status")
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
    return result


def load_token():
    try:
        values = workspace.parse_json(workspace.read_bytes(Path(workspace_config())) or b"{}", "用户级配置")
    except workspace.WorkspaceError as error:
        raise PatchError(f"读取用户级配置失败：{error}") from None
    return values.get("patch_token")


def main(argv=None, remote=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "tables", "create", "start", "status"))
    parser.add_argument("--root", default=".")
    parser.add_argument("--name", help="中文模板名；省略时用工作区配置 patch_template")
    parser.add_argument("--issue-id", type=int, help="tables 必填；create 可选，写进模板描述")
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
        remote = remote or Remote(load_token())
        if args.action == "prepare":
            result = prepare(remote, args.root, args.name)
        elif args.action == "tables":
            if not args.issue_id:
                raise PatchError("tables 需要 --issue-id")
            result = tables(remote, args.issue_id)
        elif args.action == "create":
            if not args.name:
                raise PatchError("create 需要 --name")
            result = create(remote, args.root, args.name, args.issue_id, args.table, args.apply)
        elif args.action == "start":
            result = start(remote, args.root, args.name, args.apply)
        else:
            if not args.job_id and not args.recent:
                raise PatchError("status 需要 --job-id 或 --recent")
            result = status(remote, args.job_id, min(max(args.recent or DEFAULT_RECENT, 1), 50), args.raw)
        code = 1 if result["errors"] else 0
    except PatchError as error:
        result["errors"].append(str(error))
        code = error.code
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
