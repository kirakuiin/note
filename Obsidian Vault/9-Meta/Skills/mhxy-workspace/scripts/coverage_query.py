#!/usr/bin/env python3
"""Query website coverage with explicit task inputs and JSON-only output.

Uses read-only endpoints observed in the site's frontend. Authentication headers
come only from a caller-selected local file; redirects never forward credentials.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import HTTPRedirectHandler, HTTPCookieProcessor, Request, build_opener

sys.dont_write_bytecode = True  # 本地模块（coverage_auth、corp_login）不在 skill 目录留下缓存。

BASE_URL = "https://mh-mos2-coverage.eros.nie.netease.com"


class QueryError(Exception):
    """A classified failure that can be returned without exposing credentials."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


class NoRedirect(HTTPRedirectHandler):
    """Keep authentication headers on the explicitly selected coverage origin."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Client:
    """Read coverage JSON using optional Cookie/Authorization headers."""

    def __init__(self, auth_file=None, timeout=20):
        self.headers = {"Accept": "application/json"}
        self.timeout = timeout
        self.opener = build_opener(NoRedirect())
        if auth_file:
            try:
                values = json.loads(Path(auth_file).read_text(encoding="utf-8-sig"))
            except (OSError, ValueError):
                raise QueryError("auth_config_error", "无法读取认证文件；需要本机 JSON 请求头对象") from None
            if not isinstance(values, dict) or not values or set(values) - {"Cookie", "Authorization"}:
                raise QueryError("auth_config_error", "认证文件仅允许 Cookie 和 Authorization 请求头")
            if any(not isinstance(v, str) or not v or any(c in v for c in "\r\n\x00") for v in values.values()):
                raise QueryError("auth_config_error", "认证请求头无效")
            self.headers.update(values)

    def get(self, path, **params):
        """Return JSON or a classified failure; never print raw error bodies."""
        url = BASE_URL + path
        if params:
            url += "?" + urlencode(params)
        try:
            with self.opener.open(Request(url, headers=self.headers), timeout=self.timeout) as response:
                if "json" not in response.headers.get("Content-Type", "").lower():
                    raise QueryError("unexpected_response", "接口未返回 JSON，可能需要登录或接口已变更")
                data = response.read(16 * 1024 * 1024 + 1)
                if len(data) > 16 * 1024 * 1024:
                    raise QueryError("unexpected_response", "接口响应过大，未据此判断覆盖率")
                return json.loads(data)
        except HTTPError as error:
            status = "auth_required" if error.code in (301, 302, 303, 307, 308, 401, 403) else "http_error"
            raise QueryError(status, f"覆盖率接口返回 HTTP {error.code}") from None
        except (URLError, TimeoutError, OSError):
            raise QueryError("network_error", "覆盖率接口连接失败或超时") from None
        except (ValueError, UnicodeError):
            raise QueryError("unexpected_response", "接口 JSON 无法解析") from None


def object_value(value, label):
    """Reject an unexpected response shape rather than treating it as empty."""
    if not isinstance(value, dict):
        raise QueryError("schema_error", f"{label} 应为对象")
    return value


def line_numbers(value, label):
    """Validate the site's explicit positive line-number arrays."""
    if not isinstance(value, list) or any(type(n) is not int or n < 1 for n in value):
        raise QueryError("schema_error", f"{label} 应为正整数行号数组")
    return set(value)


def covered_lines(value):
    """Extract executed line numbers from the frontend's lines/ids payload."""
    value = object_value(value, "执行行")
    lines = object_value(value.get("lines"), "执行行 lines")
    if any(not isinstance(n, str) or not n.isascii() or not n.isdigit() or int(n) < 1 for n in lines):
        raise QueryError("schema_error", "执行行键无效")
    return {int(n) for n in lines}


def timestamp(value, server=False):
    """Parse caller offsets; the site explicitly interprets naive dates as UTC."""
    if not isinstance(value, str):
        raise QueryError("freshness_unknown", "网站提交时间缺失或无法解析")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise QueryError("freshness_unknown", "网站提交时间无法解析") from None
    if result.tzinfo is None:
        if server:
            return result.replace(tzinfo=timezone.utc)
        raise QueryError("freshness_unknown", "输入的提交时间必须带时区")
    return result


def encode_branch(branch, times):
    """Match the frontend's repeated branch encoding through its proxy routes."""
    for _ in range(times):
        branch = quote(branch, safe="")
    return branch


def query(client, task_name, branch, revision=None, coder_name=None, submitted_after=None):
    """Return website totals and missing lines for one exact submitted scope.

    Args:
        client: Read-only JSON client, injectable for offline contract tests.
        task_name: Developer-confirmed remote task identifier.
        branch: Current workspace's repository-relative branch.
        revision: Deprecated compatibility argument; use the website's cur_ver.
        coder_name: Coverage user filter (developer email prefix).
        submitted_after: ISO timestamp with offset recorded before finish.

    Returns:
        Structured evidence; passed is possible only with fresh, complete data.
    """
    task_path = "/api/tasks/" + quote(task_name, safe="")
    task = object_value(client.get(task_path), "任务")
    if task.get("cur_branch") != branch:
        raise QueryError("scope_mismatch", f"网站任务分支为 {task.get('cur_branch')!r}，传入 {branch!r}；"
                         "--branch 应为仓库相对路径（如 branchs/2026_dev/x），省略时自动推断")
    if "task_id" in task and task["task_id"] != task_name:
        raise QueryError("scope_mismatch", "网站返回了不同的任务")
    revision = task.get("cur_ver")
    if (type(revision) not in (int, str) or not str(revision).isascii()
            or not str(revision).isdigit() or int(revision) < 1):
        raise QueryError("schema_error", "网站任务缺少有效 cur_ver 查询参数")
    revision = int(revision)
    rates = object_value(client.get(task_path + "/coverage/rates/" + encode_branch(branch, 2),
                                   revision=revision, user=coder_name), "覆盖率")
    file_rates = object_value(rates.get("rates"), "各文件覆盖率")
    total_rate = rates.get("total_rate")
    if type(total_rate) not in (int, float) or not 0 <= total_rate <= 100:
        raise QueryError("schema_error", "网站总覆盖率不是有效数值")
    confirmers = object_value(client.get(task_path + "/coverage/confirmers",
                                        branch=encode_branch(branch, 2), revision=revision), "人工确认")
    history = object_value(client.get(task_path + "/commits/history", page=1, size=1,
                                     sorter="date", reverse="true"), "提交历史")
    items = history.get("items")
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise QueryError("schema_error", "提交历史 items 无效")
    last_submission = items[0].get("date") if items else None
    def collect_file(item):
        path, rate = item
        if not isinstance(path, str) or not path or type(rate) not in (int, float) or not 0 <= rate <= 100:
            raise QueryError("schema_error", "网站文件路径或覆盖率无效")
        suffix = encode_branch(branch, 3) + "/" + quote(path.lstrip("/"), safe="/")
        params = {"revision": revision}
        required = line_numbers(client.get(task_path + "/coverage/require/" + suffix, **params), "应覆盖行")
        executed = covered_lines(client.get(task_path + "/coverage/specific/" + suffix, user=coder_name, **params))
        executed |= covered_lines(client.get(task_path + "/coverage/history/" + suffix, user=coder_name, **params))
        # Ignore records may already have been removed from required lines.
        # Report them separately and never count them as observed execution.
        ignored = line_numbers(client.get(task_path + "/ignore/" + suffix,
                                         user=coder_name, **params), "忽略行")
        missing = sorted(required - executed)
        return {"path": path, "website_rate": rate, "required_count": len(required),
                      "executed_count": len(required & executed), "missing_lines": missing,
                      "ignored_lines": sorted(ignored)}
    # Independent read-only file queries avoid serial network latency. map keeps
    # deterministic path order; concurrency is bounded to protect the service.
    with ThreadPoolExecutor(max_workers=4) as executor:
        files = list(executor.map(collect_file, sorted(file_rates.items())))
    total_required = sum(file["required_count"] for file in files)
    total_covered = sum(file["executed_count"] for file in files)
    blockers = []
    if not files or total_required == 0:
        blockers.append("empty_scope")
    if confirmers or any(f["ignored_lines"] for f in files):
        blockers.append("manual_adjustments_require_review")
    if submitted_after is None:
        blockers.append("freshness_not_checked")
    else:
        try:
            if timestamp(last_submission, server=True) <= timestamp(submitted_after):
                blockers.append("submission_not_visible")
        except QueryError as error:
            blockers.append(error.status)
        # The live history identifies task_id and revision, without a branch.
        # Branch is checked on task metadata above; mismatched identity blocks.
        latest = items[0] if items else {}
        if (latest.get("task_id") != task_name or str(latest.get("revision")) != str(revision)
                or ("branch" in latest and latest["branch"] != branch)):
            blockers.append("submission_scope_unverified")
    complete = (total_rate == 100 and all(f["website_rate"] == 100 and not f["missing_lines"] for f in files))
    status = "passed" if complete and not blockers else ("blocked" if blockers else "incomplete")
    return {"status": status, "task_name": task_name, "branch": branch, "revision": str(revision),
            "coder_name": coder_name, "website_rate": total_rate, "required_count": total_required,
            "executed_count": total_covered, "last_submission": last_submission,
            "queried_at": datetime.now(timezone.utc).isoformat(), "blockers": blockers,
            "confirmed_files": sorted(confirmers), "files": files,
            "hints": (["应覆盖行为空，请检查网站基准与当前配置是否形成有效 diff；同分支同版本不能作为覆盖率通过依据。"]
                      if "empty_scope" in blockers else []),
            "url": BASE_URL + "/detail/taskId:" + quote(task_name, safe="") + "/commitId:" + str(revision) + "/" + quote(branch, safe="")}


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-name", required=True)
    parser.add_argument("--branch", help="仓库相对路径（如 branchs/2026_dev/x）；省略时从 svn 推断")
    parser.add_argument("--revision", type=int, help="兼容旧调用；已忽略，自动使用网站任务 cur_ver")
    parser.add_argument("--coder-name")
    parser.add_argument("--root", default=os.getcwd())
    parser.add_argument("--global-config", default=str(Path.home() / ".mhxy-workspace/config.json"))
    parser.add_argument("--submitted-after", help="ISO 8601 time with offset, recorded before finish")
    authentication = parser.add_mutually_exclusive_group()
    authentication.add_argument("--auth-file")
    authentication.add_argument("--openid-user", help="CORP account; prompt for password without saving")
    parser.add_argument("--timeout", type=float, default=20)
    args = parser.parse_args()
    try:
        if args.timeout <= 0:
            raise QueryError("input_error", "timeout 必须大于零")
        if args.submitted_after:
            timestamp(args.submitted_after)
        from workspace import WorkspaceError, load_config, svn_branch
        try:
            config = load_config(args.root, args.global_config)
        except (WorkspaceError, OSError, UnicodeError):
            raise QueryError("config_error", "无法读取或验证工作区／全局配置；请运行 workspace.py context 检查") from None
        branch = args.branch or (svn_branch(args.root) or {}).get("path")
        if not branch:
            raise QueryError("input_error", "无法从 svn 推断分支，请用 --branch 传仓库相对路径（如 branchs/2026_dev/x）")
        username = args.openid_user or config.get("openid_username")
        coder_name = args.coder_name or config.get("coder_name") or (username.split("@", 1)[0] if username else None)
        if not coder_name:
            raise QueryError("config_error", "缺少 coder_name 或可推导的 OpenID 账号")
        auth_file = args.auth_file or (None if args.openid_user else os.environ.get("MHXY_COVERAGE_AUTH_FILE"))
        client = Client(auth_file, args.timeout)
        config.pop("openid_password", None)  # 密码只经 corp_login.load_credentials 读取。
        if username and not auth_file:
            from coverage_auth import AuthError, login
            from corp_login import load_credentials
            password = None
            try:
                # 指定其他账号时不复用已存密码；规则见 corp_login.load_credentials。
                username, password = load_credentials(Path(args.global_config).expanduser(), args.openid_user)
                client.opener = build_opener(HTTPCookieProcessor(login(username, args.timeout, password=password)), NoRedirect())
            except AuthError as error:
                raise QueryError("auth_required", str(error)) from None
            finally:
                password = None
        result = query(client, args.task_name, branch,
                       args.revision, coder_name, args.submitted_after)
    except QueryError as error:
        result = {"status": error.status, "message": str(error)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "passed" else (2 if result["status"] == "incomplete" else 3)


if __name__ == "__main__":
    sys.exit(main())
