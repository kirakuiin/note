#!/usr/bin/env python3
"""提单平台（popomgr）的 bug 单：按群找任务、找单、读单、建单、加备注、改状态。

设计与接口见 specs/2026-11-12-popo-bug-group-fix.md。子命令：

    popo_bug.py task   --group <群号>
    popo_bug.py find   --task <任务ID> --text <引用的原文>
    popo_bug.py show   --task <任务ID> --id <bug _id> [--save <项目根>]
    popo_bug.py create --task <任务ID> --text <内容> --reporter <报告人> [--type <工单类型>] [--assignee <账号>]
    popo_bug.py note   --task <任务ID> --id <bug _id> --prefix <已修复|未处理> --text <不超过 20 字>
    popo_bug.py status --task <任务ID> --id <bug _id> --to 已完成 [--followqa <账号>]

登录用用户级配置里的 CORP 账号（eros_auth，中转站 auth2.qkit），会话只在内存中。
create、note、status 是写操作：环境变量 MHXY_NO_PM_WRITE=1 时拒绝（自动会话都带着它），只由调用方
（popo-agent-service）在用户批准的时点调用。输出 JSON；出错时 stderr 输出 {"error": …}，退出码 1。
"""
import argparse
import json
import mimetypes
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener
import uuid

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import corp_login  # noqa: E402
from corp_login import LoginError  # noqa: E402
import eros_auth  # noqa: E402
import workspace  # noqa: E402

SITE = "https://popomgr.eros.nie.netease.com"
BUGS = "bugs"              # 个人目录下存 bug 正文和截图的目录，每张单一个子目录（按 readable_id）
NOTE_MAX = 20              # 备注正文字数上限（用户 2026-11-12 定）
NOTE_PREFIXES = ("已修复", "未处理")
REPORT_HEAD = "【群里报告】"  # create 建的单第一行，后接报告人；会话据此识别真正的报告人
DONE = "已完成"
IMAGE_LIMIT = 20 * 1024 * 1024


class PopoBugError(LoginError):
    """可直接显示的错误；不包含密码、Cookie 或服务器原始响应。"""


def normalize(text):
    """比较原文用：去掉首尾空白，连续空白合并成一个空格。"""
    return re.sub(r"\s+", " ", str(text or "")).strip()


class Client:
    """已登录的提单平台会话，只提供本脚本用到的接口。"""

    def __init__(self, opener, timeout=30):
        self.opener = opener   # eros_auth.login 返回的 opener，Cookie 只在内存中。
        self.timeout = timeout

    def _raw(self, path, params=None, data=None, headers=None):
        url = SITE + path + ("?" + urlencode(params) if params else "")
        try:
            with self.opener.open(Request(url, data=data, headers=headers or {}), timeout=self.timeout) as response:
                if "/auth/login" in urlsplit(response.url).path:
                    raise PopoBugError("提单平台会话失效，请重试")
                return response.read()
        except HTTPError as error:
            raise PopoBugError(f"提单平台返回 HTTP {error.code}（{path}）") from None
        except (URLError, OSError):
            raise PopoBugError(f"提单平台网络请求失败（{path}）") from None

    def _json(self, path, **kw):
        raw = self._raw(path, **kw)
        try:
            return json.loads(raw.decode("utf-8", "replace"))
        except ValueError:
            raise PopoBugError(f"提单平台返回的不是 JSON（{path}），接口可能已变化") from None

    def get(self, path, params):
        return self._json(path, params=params)

    def post_json(self, path, body):
        return self._json(path, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                          headers={"Content-Type": "application/json"})

    def post_form(self, path, fields):
        """multipart/form-data，与前端的 FormData 一致。"""
        boundary = uuid.uuid4().hex
        parts = []
        for key, value in fields.items():
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n')
        body = ("".join(parts) + f"--{boundary}--\r\n").encode("utf-8")
        return self._json(path, data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})

    # ---- 接口 ----
    def tasks(self, account):
        """与该账号相关的进行中任务。"""
        data = self.get("/api/index/tasks", {"start": 0, "length": 500, "qa": account, "task_name": "",
                                             "status": "true", "category": ""})
        rows = data.get("data") if isinstance(data, dict) else None
        if isinstance(rows, dict):
            rows = rows.get("data")
        if not isinstance(rows, list):
            raise PopoBugError("任务列表结构已变化")
        return [row for row in rows if isinstance(row, dict)]

    def init(self):
        """/api/index/init：人员表、平台配置等，一次调用内缓存。"""
        if getattr(self, "_init", None) is None:
            data = self.get("/api/index/init", None)
            self._init = (data.get("data") or data) if isinstance(data, dict) else {}
        return self._init

    def type_prefix(self):
        """平台机器人认的消息前缀 → 工单类型（平台配置 type_prefix，如 bug→BUG、mark→备忘、sug→建议），键为小写。"""
        table = (self.init().get("config") or {}).get("type_prefix")
        if not isinstance(table, dict) or not table:
            raise PopoBugError("平台配置里没有 type_prefix，结构可能已变化")
        return {str(k).lower(): str(v) for k, v in table.items() if k and v}

    def people(self):
        """账号 → {"name": 平台显示的姓名（如 W王卓为）, "mail": 邮箱}，来自 /api/index/init 的 person_dict。"""
        groups = self.init().get("person_dict")
        if not isinstance(groups, dict):
            raise PopoBugError("人员表结构已变化")
        out = {}
        for rows in groups.values():
            for row in rows if isinstance(rows, list) else []:
                if isinstance(row, dict) and row.get("_id"):
                    out[str(row["_id"])] = {"name": str(row.get("firstname") or row["_id"]),
                                            "mail": str(row.get("mail") or "").lower()}
        return out

    def issues(self, task_id, keyword="", length=200):
        params = {"react": "1", "taskid": task_id, "start": 0, "length": length, "keyword": keyword,
                  "order_by": "status", "order_dir": "desc"}
        for key in ("status", "type", "priority", "author", "assignee", "followqa", "claim", "design_reply",
                    "design", "coder", "tag", "daily_red"):
            params[key] = ""
        rows = self.get("/mgr/task/get_issues_by_task", params).get("data")
        if not isinstance(rows, list):
            raise PopoBugError("工单列表结构已变化")
        return [row for row in rows if isinstance(row, dict)]

    def issue(self, task_id, bug_id):
        data = self.post_form("/mgr/get_issue_data", {"_id": bug_id, "taskid": task_id})
        if not isinstance(data, dict) or data.get("_id") != bug_id:
            raise PopoBugError(f"读不到工单 {bug_id}，ID 可能有误或接口已变化")
        return data

    def download(self, url):
        """下载截图。图片在对象存储上，用不带登录 Cookie、不限跳转站点的独立请求，不把 CORP 会话发给图床。"""
        target = urlsplit(url)
        if target.scheme not in ("http", "https"):
            raise PopoBugError(f"图片地址不是 http(s)：{url[:80]}")
        try:
            with build_opener().open(Request(url), timeout=self.timeout) as response:
                data = response.read(IMAGE_LIMIT + 1)
                kind = response.headers.get("Content-Type", "")
        except (HTTPError, URLError, OSError):
            raise PopoBugError(f"图片下载失败：{url[:80]}") from None
        if len(data) > IMAGE_LIMIT:
            raise PopoBugError(f"图片超过 20MB：{url[:80]}")
        return data, kind


def connect(config):
    username, password = corp_login.load_credentials(config)
    try:
        opener = eros_auth.login(SITE, username, password, auth_host=eros_auth.QKIT_AUTH_HOST)
    finally:
        password = None
    return Client(opener), corp_login.account_prefix(username)


def require_write():
    if workspace.pm_write_forbidden():
        raise PopoBugError("这个会话没有写工单的批准（MHXY_NO_PM_WRITE），提单平台的写操作由调用方执行")


def members(task):
    """任务成员账号：related_person 与 related_redmine 的账号并集。"""
    people = [str(p) for p in task.get("related_person") or [] if p]
    for account in (task.get("related_redmine") or {}):
        if account and account not in people:
            people.append(str(account))
    return people


def task_brief(task, people=None):
    """people 给出时多一个 member_mails：成员邮箱（小写），POPO 事件里的发送人是邮箱，账号和邮箱前缀不一定相同。"""
    brief = {"id": str(task.get("_id") or ""), "name": str(task.get("task_name") or ""),
             "planner_id": str(task.get("parentid") or ""), "members": members(task),
             "subtickets": {str(k): str(v) for k, v in (task.get("related_redmine") or {}).items()},
             "qa": str(task.get("qa") or ""), "groups": [str(g) for g in task.get("popo_group_num") or []]}
    if people is not None:
        brief["member_mails"] = [people[a]["mail"] for a in brief["members"] if people.get(a, {}).get("mail")]
    return brief


def find_tasks(client, account, group):
    people = client.people()
    return [task_brief(t, people) for t in client.tasks(account)
            if str(group) in {str(g) for g in t.get("popo_group_num") or []}]


def task_result(client, account, group):
    """task 命令的输出：任务列表，加上平台的消息前缀表（调用方据此判断群消息是不是在报问题）。"""
    return {"tasks": find_tasks(client, account, group), "type_prefix": client.type_prefix()}


def bug_brief(row):
    return {"id": str(row.get("_id") or ""), "readable_id": str(row.get("readable_id") or ""),
            "task_id": str(row.get("taskid") or ""), "subject": str(row.get("subject") or ""),
            "status": str(row.get("status") or ""), "type": str(row.get("type") or ""),
            "author": str(row.get("author") or ""), "assignee": str(row.get("assignee") or ""),
            "followqa": str(row.get("followqa") or ""), "group": str(row.get("popo_group_num") or "")}


def keyword_for(text):
    """搜索关键词：原文里最长的一段连续非空白文字（取前 30 字），避免 mark 前缀和标点干扰。"""
    pieces = sorted(re.split(r"\s+", normalize(text)), key=len, reverse=True)
    return pieces[0][:30] if pieces and pieces[0] else ""


OPEN_STATUSES = ("新建", "描述不清", "完成转回")   # 还需要开发处理的状态（与 popo-issue-fetch 的 --status open 一致）


def reported_text(subject):
    """create 代建的单去掉“【群里报告】<报告人>”那一行后的原文（归一后）；不是代建的单返回 None。"""
    text = normalize(subject)
    if not text.startswith(REPORT_HEAD):
        return None
    return re.sub(rf"^{re.escape(REPORT_HEAD)}\S+\s*", "", text)


def find_bug(client, task_id, text):
    """按原文找还没处理完的单：平台机器人建的（origin_subject）或本脚本代建的（去掉报告人行后的正文），
    归一后与原文相同；多张时取单号最大的。已完成、关闭等状态的不算，同样的问题再报要新建。"""
    wanted = normalize(text)
    if not wanted:
        raise PopoBugError("原文为空")
    rows = [row for row in client.issues(task_id, keyword_for(text))
            if str(row.get("status") or "") in OPEN_STATUSES
            and (normalize(row.get("origin_subject")) == wanted or reported_text(row.get("subject")) == wanted)]
    return bug_brief(max(rows, key=lambda r: int(r.get("readable_id") or 0))) if rows else None


def fill_images(text, paths):
    """按顺序把正文里的 [图片] 换成本地路径；占位符不够时把多出的图片接在段落末尾。"""
    parts = str(text or "").split("[图片]")
    out = parts[0]
    for index, rest in enumerate(parts[1:]):
        out += (f"[图片 {paths[index]}]" if index < len(paths) else "[图片]") + rest
    extra = paths[len(parts) - 1:]
    return (out.strip() + ("\n\n" + "\n".join(f"[图片 {p}]" for p in extra) if extra else "")).strip()


def render(detail, task, images=None):
    """issue.md：会话读的正文。images：{"img": [本地路径或说明], "way_img": [...]}，按顺序填进 [图片]。"""
    images = images or {}
    subject = fill_images(detail.get("subject"), images.get("img") or [])
    way = fill_images(detail.get("way_text"), images.get("way_img") or [])
    lines = [f"# popo-{detail.get('readable_id')} {normalize(detail.get('subject'))[:60]}", "",
             f"- 类型/状态/优先级：{detail.get('type', '')} / {detail.get('status', '')} / {detail.get('priority', '')}",
             f"- 提单：{detail.get('author_name') or detail.get('author', '')}（{detail.get('author', '')}）",
             f"- 指派：{detail.get('assignee', '')}　跟进 QA：{detail.get('followqa', '')}",
             f"- 所属任务：{task.get('name') or detail.get('task_name') or ''}　策划单号：{task.get('planner_id', '')}",
             "", "## 问题描述", "", subject or "（空）"]
    if way:
        lines += ["", "## 重现步骤", "", way]
    if str(detail.get("markdown") or "").strip():
        lines += ["", "## 已有备注", "", str(detail["markdown"]).strip()]
    return "\n".join(lines) + "\n"


def save(client, detail, task, root, config):
    """把正文和截图写到 <项目根>/.mhxy-workspace/bugs/<readable_id>/。单张图片下载失败不中断，正文里写明。"""
    root_path, personal, _ = workspace.paths(root, str(config))
    workspace.require_initialized(root_path)
    rid = str(detail.get("readable_id") or "")
    workspace.validate_issue_id(rid)
    folder = personal / BUGS / rid
    workspace.no_links(folder)
    folder.mkdir(parents=True, exist_ok=True)
    images, local, failed = [], {}, []
    for field, label in (("img", "问题描述"), ("way_img", "重现步骤")):
        for index, url in enumerate(detail.get(field) or [], 1):
            try:
                data, kind = client.download(str(url))
            except PopoBugError as error:
                failed.append(str(error))
                local.setdefault(field, []).append(f"下载失败，原链接 {url}")
                continue
            ext = mimetypes.guess_extension(kind.split(";")[0].strip()) or Path(urlsplit(str(url)).path).suffix or ".png"
            name = f"{field}_{index}{ext}"
            (folder / name).write_bytes(data)
            images.append({"section": label, "path": str(folder / name)})
            local.setdefault(field, []).append(str(folder / name))
    text = render(detail, task, local)
    path = folder / "issue.md"
    path.write_text(text, encoding="utf-8")
    return {"issue_path": str(path.relative_to(root_path)).replace("\\", "/"), "images": images,
            "image_errors": failed}


def display_name(client, who):
    """邮箱、账号 → 平台显示的姓名（如 Y袁延亮）；查不到时原样返回（已经是姓名的也一样）。"""
    who = normalize(who)
    if not who:
        return "未知"
    people = client.people()
    if who in people:
        return people[who]["name"]
    lowered = who.lower()
    return next((p["name"] for p in people.values() if p["mail"] and p["mail"] == lowered), who)


def create_bug(client, account, task_id, text, reporter, assignee=None, issue_type="BUG"):
    require_write()
    if issue_type not in set(client.type_prefix().values()):
        raise PopoBugError(f"工单类型不在平台的前缀表里：{issue_type}")
    body = normalize(text)
    if not body:
        raise PopoBugError("内容为空")
    subject = f"{REPORT_HEAD}{display_name(client, reporter)}\n{str(text).strip()}"
    result = client.post_form("/mgr/task/save_issue", {
        "subject": subject, "img_path": "", "taskid": task_id, "_id": "", "ctype": "0",
        "assignee": assignee or account, "issue_type": issue_type, "way_text": "", "way_img": "", "priority": "P2"})
    if not isinstance(result, dict) or result.get("success") is False or result.get("result") == "error":
        raise PopoBugError("建单失败：" + str((result or {}).get("msg") or (result or {}).get("retmsg") or "未知原因")[:200])
    # 平台不返回新单 ID：按完整标题找回，同样内容的多张里取单号最大的（刚建的）
    rows = [row for row in client.issues(task_id, keyword_for(text)) if normalize(row.get("subject")) == normalize(subject)]
    if not rows:
        raise PopoBugError("建单接口返回成功，但按内容找不到新单，请到平台核对")
    return bug_brief(max(rows, key=lambda r: int(r.get("readable_id") or 0)))


def append_note(client, task_id, bug_id, prefix, text):
    require_write()
    text = normalize(text)
    if prefix not in NOTE_PREFIXES:
        raise PopoBugError(f"备注前缀只能是：{'、'.join(NOTE_PREFIXES)}")
    if not text or len(text) > NOTE_MAX:
        raise PopoBugError(f"备注正文要写、且不超过 {NOTE_MAX} 个字")
    line = f"{prefix}：{text}"
    for _ in range(3):
        before = str(client.issue(task_id, bug_id).get("markdown") or "")
        merged = (before.rstrip("\n") + "\n" + line) if before.strip() else line
        if str(client.issue(task_id, bug_id).get("markdown") or "") != before:
            continue   # 读出之后有人改了备注：重新拼接，不覆盖别人的内容
        result = client.post_json("/mgr/task/update_issue", {"_id": bug_id, "taskid": task_id, "markdown": merged})
        if isinstance(result, dict) and (result.get("success") is False or result.get("result") == "error"):
            raise PopoBugError("备注保存失败：" + str(result.get("msg") or result.get("retmsg") or "")[:200])
        return {"note": line, "markdown": merged}
    raise PopoBugError("备注在读写之间反复被别人修改，未写入")


def set_done(client, task_id, bug_id, followqa=None):
    require_write()
    result = client.post_json("/mgr/task/judge_change_status", {"_id": bug_id, "status": DONE, "taskid": task_id})
    if not isinstance(result, dict):
        raise PopoBugError("改状态返回结构已变化")
    if result.get("success"):
        return {"status": DONE, "followqa": None}
    if result.get("ret_code") == 2:     # 非 QA 改“已完成”：要指定跟进 QA
        qa = followqa or str(client.issue(task_id, bug_id).get("followqa") or "")
        if not qa:
            raise PopoBugError("改成已完成需要跟进 QA，但 bug 单和参数里都没有")
        done = client.post_json("/mgr/task/update_issue", {"_id": bug_id, "status": DONE, "taskid": task_id,
                                                            "followqa": qa})
        if isinstance(done, dict) and (done.get("success") is False or done.get("result") == "error"):
            raise PopoBugError("改状态失败：" + str(done.get("msg") or done.get("retmsg") or "")[:200])
        return {"status": DONE, "followqa": qa}
    raise PopoBugError(f"改状态被拒绝（ret_code {result.get('ret_code')}）：{str(result.get('retmsg') or '')[:200]}")


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=("task", "find", "show", "create", "note", "status"))
    parser.add_argument("--group", help="task：群号")
    parser.add_argument("--task", help="任务 ID（task 输出的 id）")
    parser.add_argument("--id", help="bug 单的 _id（find、create 输出的 id）")
    parser.add_argument("--text", help="find：引用的原文；create：内容；note：备注正文")
    parser.add_argument("--reporter", help="create：报告人（邮箱、账号或姓名，按人员表换成平台显示的姓名）")
    parser.add_argument("--assignee", help="create：指派人账号，默认登录账号")
    parser.add_argument("--type", help="create：工单类型（平台 type_prefix 里的值，如 BUG、备忘、建议），默认 BUG")
    parser.add_argument("--prefix", choices=NOTE_PREFIXES, help="note：备注前缀")
    parser.add_argument("--to", help="status：目标状态，只支持“已完成”")
    parser.add_argument("--followqa", help="status：需要指定跟进 QA 时用的账号，默认 bug 单原来的跟进 QA")
    parser.add_argument("--save", help="show：把正文和截图写到这个项目根的 .mhxy-workspace/bugs/<单号>/")
    parser.add_argument("--global-config", "--config", dest="config", type=Path,
                        default=Path.home() / workspace.DIRECTORY / "config.json")
    args = parser.parse_args(argv)
    try:
        need = {"task": ("group",), "find": ("task", "text"), "show": ("task", "id"),
                "create": ("task", "text", "reporter"), "note": ("task", "id", "prefix", "text"),
                "status": ("task", "id", "to")}[args.action]
        missing = [f"--{name}" for name in need if not getattr(args, name)]
        if missing:
            raise PopoBugError(f"{args.action} 需要 " + "、".join(missing))
        if args.action == "status" and args.to != DONE:
            raise PopoBugError("status 只支持改成“已完成”")
        if args.action in ("create", "note", "status"):
            require_write()
        if args.action == "note" and not 0 < len(normalize(args.text)) <= NOTE_MAX:
            raise PopoBugError(f"备注正文要写、且不超过 {NOTE_MAX} 个字")
        client, account = connect(args.config)
        if args.action == "task":
            result = task_result(client, account, args.group)
        elif args.action == "find":
            result = {"bug": find_bug(client, args.task, args.text)}
        elif args.action == "show":
            detail = client.issue(args.task, args.id)
            people = client.people()
            detail["author_name"] = people.get(str(detail.get("author") or ""), {}).get("name") or detail.get("author")
            task = next((task_brief(t) for t in client.tasks(account) if str(t.get("_id")) == args.task), {})
            result = {"bug": {**bug_brief(detail), "markdown": str(detail.get("markdown") or ""),
                              "author_name": str(detail.get("author_name") or "")}, "task": task}
            if args.save:
                result.update(save(client, detail, task, args.save, args.config))
        elif args.action == "create":
            result = {"bug": create_bug(client, account, args.task, args.text, args.reporter, args.assignee,
                                        args.type or "BUG")}
        elif args.action == "note":
            result = append_note(client, args.task, args.id, args.prefix, args.text)
        else:
            result = set_done(client, args.task, args.id, args.followqa)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (LoginError, workspace.WorkspaceError, OSError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1
    except (AttributeError, KeyError, TypeError):
        print(json.dumps({"error": "提单平台返回的数据结构已变化"}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
