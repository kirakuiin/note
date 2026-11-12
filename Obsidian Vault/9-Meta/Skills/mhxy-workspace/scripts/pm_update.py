#!/usr/bin/env python3
"""修改易协作工单的状态、登记工时；默认只预览，--apply 才写入。

    pm_update.py --issue-id <工单号>
    pm_update.py --issue-id <工单号> [--status <状态名> [--status-from <状态名,状态名…>]]
                 [--hours <数值> --activity <活动名> [--spent-on YYYY-MM-DD] [--comments <备注>]] [--apply]

不带 --status 和 --hours 时只输出工单概况（标题、跟踪标签、状态、目标版本、已登记工时）。
本脚本只提供功能，不含约定：哪类工单改成什么状态、工时填多少，见 references/task-tracking.md「更新工单」。

登录复用 pm_issues.Client（CORP 密码，Cookie 只在内存）。写入顺序是先登记工时、再改状态，
每一步写完都读回核对；不自动重试。退出码：0 预览成功或全部写入并核对通过；1 没有写入任何内容；
2 部分完成（输出的 done 标明哪一步已完成，重试时只传未完成的那一步）。
"""

import argparse
from datetime import date
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import corp_login  # noqa: E402
import pm_issues  # noqa: E402
from pm_issues import SITE, as_dict  # noqa: E402
import workspace  # noqa: E402

LIMIT = 32 * 1024 * 1024  # 单个响应的大小上限。
MAX_HOURS = Decimal("999.99")  # 平台限制：整数最多 3 位，小数最多 2 位。


class UpdateError(pm_issues.QueryError):
    """可直接显示的错误；不包含密码、Cookie。"""


def server_message(raw):
    """从服务器的错误响应里取出可读的说明（最多 300 字）；取不到时返回空字符串。"""
    try:
        value = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError, AttributeError):
        return ""
    if not isinstance(value, dict):
        return ""
    for key in ("errors", "error", "res_msg", "message"):
        detail = value.get(key)
        if detail:
            text = detail if isinstance(detail, str) else json.dumps(detail, ensure_ascii=False)
            return text[:300]
    return ""


def request(client, method, path, body=None):
    """向本站发一个请求并解析 JSON；响应体为空时返回 None。

    Args:
        client: 已登录的 pm_issues.Client。
        method: HTTP 方法。
        path: 以 / 开头的本站路径。
        body: 非 None 时作为 JSON 请求体发送，并带上 CSRF token。

    Raises:
        UpdateError: HTTP 错误（附服务器说明）、网络失败、响应不是 JSON。
    """
    headers = {"Accept": "application/json"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        if client.csrf:
            headers["X-CSRF-Token"] = client.csrf
        data = json.dumps(body).encode("utf-8")
    try:
        with client.opener.open(Request(SITE + path, data=data, headers=headers, method=method),
                                timeout=client.timeout) as response:
            raw = response.read(LIMIT + 1)
    except HTTPError as error:
        try:
            detail = server_message(error.read(LIMIT))
        except OSError:
            detail = ""
        raise UpdateError(f"接口返回 HTTP {error.code}" + (f"：{detail}" if detail else "")) from None
    except (URLError, OSError):
        raise UpdateError("网络请求失败，结果不明") from None
    if len(raw) > LIMIT:
        raise UpdateError("接口响应过大")
    if not raw.strip():
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError):
        raise UpdateError("接口未返回 JSON，可能需要登录或认证已失效") from None


def api(client, method, path, body=None):
    """调用 /api/v6 接口，校验业务成功码并返回 data。"""
    value = request(client, method, "/api/v6" + path, body)
    if not isinstance(value, dict) or value.get("res_code") != 1:
        detail = server_message(json.dumps(value, ensure_ascii=False).encode("utf-8")) if isinstance(value, dict) else ""
        raise UpdateError("接口拒绝请求" + (f"：{detail}" if detail else "，请检查登录与权限"))
    return value.get("data")


def load_issue(client, issue_id):
    """读取工单概况（标题、跟踪标签、状态、目标版本）。"""
    value = as_dict(request(client, "GET", f"/issues/{issue_id}.json"), "工单概况")
    issue = as_dict(value.get("issue"), "工单概况")
    if issue.get("id") != issue_id:
        raise UpdateError(f"#{issue_id} 的概况标识不一致或无权限读取")
    as_dict(issue.get("status"), "工单状态")
    return issue


def load_form(client, issue_id):
    """读取编辑表单：返回 (表单里的工单字段, 可选状态列表)。"""
    data = as_dict(api(client, "POST", "/issue_form/form", {"id": issue_id}), "编辑表单")
    issue = as_dict(data.get("issue"), "编辑表单")
    if issue.get("id") != issue_id:
        raise UpdateError(f"#{issue_id} 的编辑表单标识不一致或无权限读取")
    left = as_dict(data.get("fields"), "编辑表单").get("left")
    fields = [field for field in left if isinstance(field, dict) and field.get("id") == "status_id"] \
        if isinstance(left, list) else []
    if len(fields) != 1 or not isinstance(fields[0].get("possible_values"), list):
        raise UpdateError("编辑表单里找不到状态字段，接口格式可能已变化")
    return issue, [as_dict(option, "状态选项") for option in fields[0]["possible_values"]]


def load_time(client, issue_id):
    """读取工时选项：活动、可登记的用户、是否可编辑、本单已有的工时记录。"""
    data = as_dict(api(client, "GET", f"/java_proxy/issues/{issue_id}/time_entries/new_options.json"), "工时选项")
    return as_dict(data.get("options"), "工时选项")


def time_entries(options):
    """本单（不含子单）已登记的工时记录列表。"""
    current = as_dict(as_dict(options.get("list"), "工时记录").get("current"), "工时记录")
    entries = current.get("currentIssueTimeEntry")
    if not isinstance(entries, list):
        raise UpdateError("工时记录格式已变化")
    return [as_dict(entry, "工时记录") for entry in entries]


def summary(issue, options, user_id):
    """整理给调用方看的工单概况。"""
    entries = time_entries(options)
    mine = [entry for entry in entries if str(entry.get("user_id")) == str(user_id)]
    version = issue.get("fixed_version")
    return {
        "issue_id": str(issue["id"]),
        "title": issue.get("subject"),
        "tracker": (issue.get("tracker") or {}).get("name"),
        "status": issue["status"].get("name"),
        "is_closed": issue["status"].get("is_closed"),
        "target_version": version.get("name") if isinstance(version, dict) else None,
        "time_entries": {
            "count": len(entries),
            "hours": round(sum(float(entry.get("hours") or 0) for entry in entries), 2),
            "mine_count": len(mine),
            "mine_hours": round(sum(float(entry.get("hours") or 0) for entry in mine), 2),
        },
    }


def split_names(value):
    """把“新建,10%，20%”拆成名称列表；空项报错。"""
    names = [name.strip() for name in re.split(r"[,，]", value)]
    if not all(names):
        raise UpdateError("--status-from 里有空的状态名")
    return names


def plan_status(issue, form_issue, statuses, target, sources):
    """决定状态这一步做什么。

    Args:
        issue: load_issue 的结果。
        form_issue: 表单里的工单字段（含 status_id、lock_version）。
        statuses: 可选状态列表。
        target: 目标状态名；None 表示不处理状态。
        sources: 允许改动的当前状态名列表；None 表示不限。

    Returns:
        {"action": "change"|"skip"|"none", "current", "target", "reason", "done"}，
        change 时另有 "target_id"。
    """
    current = issue["status"].get("name")
    plan = {"action": "none", "current": current, "target": target, "reason": "", "done": False}
    if target is None:
        return plan
    if form_issue.get("status_id") != issue["status"].get("id"):
        raise UpdateError("两次读取到的工单状态不一致，请重新运行")
    matches = [option for option in statuses if option.get("name") == target]
    if len(matches) != 1:
        names = "、".join(str(option.get("name")) for option in statuses)
        raise UpdateError(f"状态“{target}”不在该工单的可选状态里：{names}")
    if current == target:
        plan.update(action="skip", reason="当前已是目标状态")
    elif sources is not None and current not in sources:
        plan.update(action="skip", reason=f"当前状态“{current}”不在 --status-from 指定的范围内")
    elif matches[0].get("disabled"):
        raise UpdateError(f"状态“{target}”当前不可选（流程限制）")
    else:
        plan.update(action="change", target_id=matches[0].get("id"))
    return plan


def parse_hours(text):
    """校验工时数值：大于 0、不超过 999.99、最多两位小数；返回 Decimal。"""
    try:
        hours = Decimal(text)
    except (InvalidOperation, TypeError):
        raise UpdateError(f"工时不是有效数字：{text}") from None
    if not hours.is_finite() or hours <= 0 or hours > MAX_HOURS or hours != hours.quantize(Decimal("0.01")):
        raise UpdateError("工时须大于 0、不超过 999.99，且最多两位小数")
    return hours


def parse_date(text):
    """校验 YYYY-MM-DD 日期；None 时取当天。"""
    if text is None:
        return date.today().isoformat()
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        raise UpdateError(f"日期必须是 YYYY-MM-DD：{text}") from None


def plan_time(options, form_issue, user_id, hours, activity, spent_on, comments):
    """决定工时这一步做什么；hours 为 None 表示不登记。

    Returns:
        {"action": "add"|"none", "done": False, ...}；add 时含 hours、activity、spent_on、comments
        和发给接口的 "entry"。
    """
    if hours is None:
        return {"action": "none", "done": False}
    if options.get("can_edit") is not True:
        raise UpdateError("该工单不允许登记工时（可能已锁定或没有权限）")
    users = options.get("users") if isinstance(options.get("users"), list) else []
    me = [user for user in users if isinstance(user, dict) and str(user.get("id")) == str(user_id)]
    if len(me) != 1:
        raise UpdateError("当前账号不在该工单可登记工时的成员里")
    activities = options.get("activities") if isinstance(options.get("activities"), list) else []
    matches = [item for item in activities
               if isinstance(item, dict) and item.get("name") == activity and item.get("active") is not False]
    if len(matches) != 1:
        names = "、".join(str(item.get("name")) for item in activities if isinstance(item, dict))
        raise UpdateError(f"活动“{activity}”不在可选活动里：{names}")
    roles = matches[0].get("role_ids") or []
    if roles and not set(roles) & set(me[0].get("role_ids") or []):
        raise UpdateError(f"活动“{activity}”限定了角色，当前账号不能选")
    project_id = form_issue.get("project_id")
    if type(project_id) is not int:
        raise UpdateError("编辑表单里没有项目 ID，接口格式可能已变化")
    entry = {"issue_id": form_issue["id"], "project_id": project_id, "activity_id": matches[0].get("id"),
             "hours": float(hours), "spent_on": spent_on, "user_id": int(user_id), "comments": comments}
    return {"action": "add", "done": False, "hours": float(hours), "activity": activity,
            "spent_on": spent_on, "comments": comments, "entry": entry}


def find_new_entry(options, before_ids, entry):
    """在读回的工时记录里找本次新增的那条；找不到返回 None。"""
    for item in time_entries(options):
        if item.get("id") in before_ids:
            continue
        try:
            same_hours = abs(float(item.get("hours")) - entry["hours"]) < 0.005
        except (TypeError, ValueError):
            same_hours = False
        if (same_hours and str(item.get("user_id")) == str(entry["user_id"])
                and item.get("activity_id") == entry["activity_id"] and item.get("spent_on") == entry["spent_on"]):
            return item
    return None


def apply_time(client, issue_id, plan, before_ids):
    """登记工时并读回核对；成功时在 plan 里记下 done 和新记录的 id，失败返回错误文字。"""
    error = None
    try:
        api(client, "POST", "/java_proxy/time_entries/save.json", {"time_entry": [plan["entry"]]})
    except UpdateError as failure:
        error = str(failure)
    # 无论请求是否报错都读回：超时等情况下服务器可能已经写入。
    created = find_new_entry(load_time(client, issue_id), before_ids, plan["entry"])
    if created is None:
        return "登记工时失败：" + (error or "接口返回成功，但读回没有找到新记录")
    plan.update(done=True, id=created.get("id"))
    return None


def apply_status(client, issue_id, plan):
    """修改状态并读回核对；成功时在 plan 里记下 done，失败返回错误文字。"""
    try:
        form_issue, _ = load_form(client, issue_id)  # 取最新的 lock_version。
    except pm_issues.QueryError as failure:
        return f"修改状态失败（写入请求尚未发出）：{failure}"
    body = {"id": issue_id, "issue": {"status_id": plan["target_id"], "lock_version": form_issue.get("lock_version")},
            "last_journal_id": form_issue.get("last_journal_id"), "project_id": form_issue.get("project_id")}
    error = None
    try:
        value = request(client, "PUT", f"/issues/{issue_id}.json", body)
        if isinstance(value, dict) and value.get("res_code") not in (None, 1):
            error = server_message(json.dumps(value, ensure_ascii=False).encode("utf-8")) or "接口拒绝请求"
    except UpdateError as failure:
        error = str(failure)
    after = load_issue(client, issue_id)["status"]
    if after.get("id") != plan["target_id"]:
        return "修改状态失败：" + (error or f"接口返回成功，但读回状态仍是“{after.get('name')}”")
    plan.update(done=True)
    return None


def run(client, user_id, args):
    """执行一次预览或写入。

    Returns:
        (输出字典, 退出码)。
    """
    issue_id = int(args.issue_id)
    issue = load_issue(client, issue_id)
    options = load_time(client, issue_id)
    output = {"issue": summary(issue, options, user_id), "applied": False, "errors": []}
    if args.status is None and args.hours is None:
        return output, 0
    form_issue, statuses = load_form(client, issue_id)
    sources = split_names(args.status_from) if args.status_from is not None else None
    status = plan_status(issue, form_issue, statuses, args.status, sources)
    hours = parse_hours(args.hours) if args.hours is not None else None
    time = plan_time(options, form_issue, user_id, hours, args.activity, parse_date(args.spent_on), args.comments)
    output.update(status={key: value for key, value in status.items() if key != "target_id"},
                  time_entry={key: value for key, value in time.items() if key != "entry"})
    if not args.apply:
        return output, 0
    output["applied"] = True
    if time["action"] == "add":
        before_ids = {entry.get("id") for entry in time_entries(options)}
        try:
            error = apply_time(client, issue_id, time, before_ids)
        except pm_issues.QueryError as failure:
            # 写入请求已发出但读回失败：结果不明，不能当作没有写入。
            output["errors"].append(f"登记工时后读回失败，结果不明，请到工单页面核对：{failure}")
            return output, 2
        output["time_entry"] = {key: value for key, value in time.items() if key != "entry"}
        if error:
            output["errors"].append(error)
            if status["action"] == "change":
                output["errors"].append("工时没有登记成功，未修改状态")
            return output, 1
    if status["action"] == "change":
        try:
            error = apply_status(client, issue_id, status)
        except pm_issues.QueryError as failure:
            output["errors"].append(f"修改状态后读回失败，结果不明，请到工单页面核对：{failure}")
            return output, 2
        output["status"] = {key: value for key, value in status.items() if key != "target_id"}
        if error:
            output["errors"].append(error)
            return output, 2 if time["done"] else 1
    return output, 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--global-config", "--config", dest="config", type=Path,
                        default=Path.home() / ".mhxy-workspace/config.json", help="用户级配置（--config 为旧写法）")
    parser.add_argument("--username", help="登录账号；省略时使用配置中的 openid_username")
    parser.add_argument("--issue-id", required=True, metavar="工单号")
    parser.add_argument("--status", metavar="状态名", help="目标状态的完整名称")
    parser.add_argument("--status-from", metavar="状态名,…", help="只有当前状态在其中才修改，否则跳过；逗号分隔")
    parser.add_argument("--hours", metavar="数值", help="要登记的工时")
    parser.add_argument("--activity", metavar="活动名", help="工时的活动，完整名称")
    parser.add_argument("--spent-on", metavar="YYYY-MM-DD", help="工时日期，默认当天")
    parser.add_argument("--comments", default="", help="工时备注")
    parser.add_argument("--apply", action="store_true", help="实际写入；不带时只预览")
    parser.add_argument("--timeout", type=float, default=30)
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    try:
        workspace.validate_issue_id(args.issue_id)
        if args.timeout <= 0:
            raise UpdateError("超时须大于零")
        if args.status is not None and not args.status.strip():
            raise UpdateError("状态名不能为空")
        if args.status_from is not None and args.status is None:
            raise UpdateError("--status-from 要和 --status 一起使用")
        if (args.hours is None) != (args.activity is None):
            raise UpdateError("--hours 和 --activity 要一起给出")
        if args.hours is None and (args.spent_on is not None or args.comments):
            raise UpdateError("--spent-on、--comments 要和 --hours 一起使用")
        if args.apply and args.status is None and args.hours is None:
            raise UpdateError("--apply 需要 --status 或 --hours")
        if args.apply and workspace.pm_write_forbidden():
            raise UpdateError(f"这个会话没有得到写工单的批准（环境变量 {workspace.NO_PM_WRITE_ENV}=1），拒绝写入；"
                              "去掉 --apply 只预览，写入由用户或调用方执行")
        if args.hours is not None:
            parse_hours(args.hours)
            parse_date(args.spent_on)
        username, password = corp_login.load_credentials(args.config.expanduser(), args.username)
        client = pm_issues.Client(args.timeout)
        user = client.login(username, password)
        password = None
        output, code = run(client, int(user["id"]), args)
        sys.stdout.write(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
        return code
    except corp_login.LoginError as error:
        print(f"更新失败：{error}", file=sys.stderr)
        return 1
    except workspace.WorkspaceError as error:
        print(f"更新失败：{error}", file=sys.stderr)
        return 1
    except (AttributeError, KeyError, TypeError, ValueError):
        print("更新失败：接口数据结构已变化", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
