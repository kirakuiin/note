# -*- coding: utf-8 -*-
"""PopoMgr 提单平台工单查询 CLI（只读）

用法示例：
    python cli\\popo.py tasks --person 黎靖宇
    python cli\\popo.py issues --person 黎靖宇 --task-id 6a8cf791049cbe0026bd93e3
    python cli\\popo.py show 291258 --images        # 截图存到系统临时目录
    python cli\\popo.py search 全屏战斗
"""
import argparse
import io
import json
import os
import sys
import tempfile

SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SKILL_ROOT)

from src.client import PopoClient, download_issue_images, render_issue  # noqa: E402
from src.config import ISSUE_STATUSES, ISSUE_TYPES, detect_person  # noqa: E402

# Windows 控制台默认 GBK，工单内容和报错提示里有大量中文，不强制 UTF-8 会乱码
for _name in ("stdout", "stderr"):
    _stream = getattr(sys, _name)
    if hasattr(_stream, "buffer"):
        setattr(sys, _name, io.TextIOWrapper(_stream.buffer, encoding="utf-8",
                                             errors="replace", line_buffering=True))


def _dump(data):
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def _person(args, client):
    """解析要查谁的单：显式 --person 优先，否则默认「本人」

    自动识别时把账号和来源打出来，避免查了半天才发现查的是别人（或没查到人）。
    """
    if args.person:
        return args.person
    person, source = detect_person()
    if not person:
        raise SystemExit("没能识别出本人账号，请加 --person，或设置环境变量 POPO_USER")
    account = client.resolve_person(person)
    if not account:
        raise SystemExit(
            "按%s推断出的「%s」在平台上查不到。\n"
            "请用 --person 指定账号或中文名，或设置环境变量 POPO_USER" % (source, person)
        )
    # 走 stderr：--json 时不能污染 stdout，否则下游解析会失败
    print("# 默认按「指派给本人」筛选：%s（%s，来自%s）" % (client.display_name(account), account, source),
          file=sys.stderr)
    return account


def _image_dir(path, issue_id):
    """决定截图落盘位置

    截图是一次性排查材料，默认放系统临时目录。落在 skill 目录或 SVN 工作副本里，
    会污染代码库、还容易被误提交，所以这里直接拦掉。
    """
    if not path:
        return os.path.join(tempfile.gettempdir(), "popo_images", str(issue_id))
    target = os.path.abspath(path)
    try:
        inside_skill = os.path.commonpath([target, SKILL_ROOT]) == SKILL_ROOT
    except ValueError:  # 不同盘符
        inside_skill = False
    if inside_skill:
        raise SystemExit(
            "不要把截图下载到 skill 目录（%s）。\n"
            "省略路径即可用临时目录，或显式指定，例如：--images %s"
            % (SKILL_ROOT, os.path.join(tempfile.gettempdir(), "popo_images", str(issue_id)))
        )
    return target


def cmd_tasks(client, args):
    tasks = client.list_person_tasks(_person(args, client), status=args.status)
    if args.json:
        return _dump(tasks)
    if not tasks:
        print("没有查到任务（换 --status all 试试，或确认人员写法）")
        return
    print("| 任务ID | 任务名 | 状态 | 我的工单 | 待处理 | 最近工单时间 |")
    print("|---|---|---|---|---|---|")
    for task in tasks:
        print("| %s | %s | %s | %d | %d | %s |" % (
            task["task_id"], task["task_name"], task["task_status"],
            task["issue_count"], task["open_count"], task.get("last_ctime", "")))


def cmd_issues(client, args):
    result = client.list_issues(
        person=None if args.all_assignees else _person(args, client),
        task_id=args.task_id,
        status=args.status,
        issue_type=args.type,
        priority=args.priority,
        limit=args.limit,
        detail=args.detail,
    )
    if args.json:
        return _dump(result)
    print("人员: %s | 任务: %s | 状态: %s | 共 %d 条" % (
        result["person"] or "全部", result["task_name"] or result["task_id"] or "全部",
        result["status"], result["total"]))
    print()
    if not result["issues"]:
        print("没有符合条件的工单（--status all 可以看全部状态）")
        return
    print("| 单号 | 类型 | 状态 | 优先 | 指派 | 提单时间 | 标题 |")
    print("|---|---|---|---|---|---|---|")
    for issue in result["issues"]:
        subject = (issue.get("subject") or "").replace("\r", " ").replace("\n", " ")
        if len(subject) > 60:
            subject = subject[:60] + "…"
        print("| %s | %s | %s | %s | %s | %s | %s |" % (
            issue.get("readable_id"), issue.get("type", ""), issue.get("status", ""),
            issue.get("priority", ""), issue.get("assignee_name", ""), issue.get("ctime", ""), subject))
    if args.detail:
        for issue in result["issues"]:
            print("\n" + "-" * 60 + "\n")
            print(render_issue(issue, with_meta=True))


def cmd_show(client, args):
    issue = client.get_issue(args.issue_id)
    if not issue:
        raise SystemExit("找不到工单 #%s（确认单号是 popo 上显示的单号）" % args.issue_id)

    image_map = {}
    if args.images is not None:
        image_map = download_issue_images(issue, _image_dir(args.images, args.issue_id))

    if args.json:
        issue["local_images"] = image_map
        issue["content"] = render_issue(issue, with_meta=True, with_history=args.history, image_map=image_map)
        return _dump(issue)

    print(render_issue(issue, with_meta=True, with_history=args.history, image_map=image_map))
    if image_map:
        print("\n## 截图本地副本")
        for url, local in image_map.items():
            print("- %s\n  <- %s" % (local, url))
    elif args.images is not None:
        print("\n这个工单没有截图（纯文字描述，属正常情形）")


def cmd_search(client, args):
    tasks = client.search_tasks(args.keyword, status=args.status, limit=args.limit)
    if args.json:
        return _dump(tasks)
    if not tasks:
        print("没搜到任务（--status all 可以搜已关闭的）")
        return
    print("| 任务ID | 任务名 | 状态 | 创建时间 |")
    print("|---|---|---|---|")
    for task in tasks:
        print("| %s | %s | %s | %s |" % (task["task_id"], task["task_name"], task["task_status"], task["ctime"]))


def cmd_images(client, args):
    issue = client.get_issue(args.issue_id)
    if not issue:
        raise SystemExit("找不到工单 #%s" % args.issue_id)
    mapping = download_issue_images(issue, _image_dir(args.out, args.issue_id))
    if not mapping:
        print("这个工单没有截图")
        return
    if args.json:
        return _dump(mapping)
    for url, local in mapping.items():
        print("%s\t<- %s" % (local, url))


def build_parser():
    parser = argparse.ArgumentParser(description="PopoMgr 提单平台工单查询（只读）")
    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="输出 JSON 而不是表格/Markdown")

    p_tasks = sub.add_parser("tasks", parents=[common], help="列出某人有工单的制作内容（任务）")
    p_tasks.add_argument("--person", help="账号或中文名；默认是本人（POPO_USER 或当前登录用户）")
    p_tasks.add_argument("--status", default="open", choices=["open", "closed", "all"], help="任务状态，默认进行中")
    p_tasks.set_defaults(func=cmd_tasks)

    p_issues = sub.add_parser("issues", parents=[common], help="列出工单（按人 / 任务 / 状态过滤）")
    p_issues.add_argument("--person", help="账号或中文名；默认只看指派给本人的单")
    p_issues.add_argument("--all-assignees", action="store_true",
                          help="取消「指派给本人」这个默认过滤（配合 --task-id 看整个任务）")
    p_issues.add_argument("--task-id", help="限定任务 ID（tasks/search 命令可以查到）")
    p_issues.add_argument("--status", default="open",
                          help="open=待处理(新建/描述不清/完成转回)，all=全部，或写具体状态：%s" % "/".join(ISSUE_STATUSES))
    p_issues.add_argument("--type", help="工单类型：%s" % "/".join(ISSUE_TYPES))
    p_issues.add_argument("--priority", help="优先级 P0/P1/P2/P3")
    p_issues.add_argument("--limit", type=int, default=50, help="最多返回多少条，默认 50")
    p_issues.add_argument("--detail", action="store_true", help="同时打印每条工单的正文、重现步骤、截图链接")
    p_issues.set_defaults(func=cmd_issues)

    p_show = sub.add_parser("show", parents=[common], help="读取单个工单的完整内容")
    p_show.add_argument("issue_id", type=int, help="工单号，如 291258")
    p_show.add_argument("--images", nargs="?", const="", default=None,
                        help="下载截图并在正文里替换为本地路径；不带路径时存到系统临时目录（推荐）。"
                             "禁止指向 skill 目录内")
    p_show.add_argument("--history", action="store_true", help="附带状态流转记录")
    p_show.set_defaults(func=cmd_show)

    p_search = sub.add_parser("search", parents=[common], help="按关键词搜制作内容（任务）")
    p_search.add_argument("keyword", help="任务名关键词，如 全屏战斗")
    p_search.add_argument("--status", default="open", choices=["open", "closed", "all"], help="任务状态，默认进行中")
    p_search.add_argument("--limit", type=int, default=20)
    p_search.set_defaults(func=cmd_search)

    p_images = sub.add_parser("images", parents=[common], help="只下载某个工单的截图")
    p_images.add_argument("issue_id", type=int)
    p_images.add_argument("--out", help="保存目录；默认系统临时目录下的 popo_images\\<单号>。禁止指向 skill 目录内")
    p_images.set_defaults(func=cmd_images)

    return parser


def main():
    args = build_parser().parse_args()
    client = PopoClient()
    try:
        args.func(client, args)
    except LookupError as exc:
        raise SystemExit(str(exc))
    finally:
        client.close()


if __name__ == "__main__":
    main()
