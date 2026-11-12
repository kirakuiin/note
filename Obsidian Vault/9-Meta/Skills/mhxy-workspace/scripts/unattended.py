#!/usr/bin/env python3
"""无人值守模式的结果文件（规则见 references/unattended.md）。

    unattended.py result --root <项目> --issue-id <工单号> --status <状态> --reason <原因> [...]
    unattended.py show   --root <项目> --issue-id <工单号>

`result` 校验字段后写出 <项目>/.mhxy-workspace/unattended/<工单号>/result.json，供调用方（如
popo-agent-service）读取；`show` 原样读回。结果文件的字段固定：

    issue_id, status, reason, changed_files, commit_message, self_check, report_path, branch, written_at

status 为“待提交”时，改动文件、提交说明、自检结果和报告都必须齐全；“需要你处理”“放弃”只要求原因，
其余有就填、没有为空。“等前一单提交”表示要改的文件被同一工作区另一张未提交的工单占用，必须用
--waiting-for 给出占用它的工单号。只写个人目录，不执行任何 SVN 写操作。

固定字段之后按以下顺序可以多出几个可选字段，不给对应参数时没有：
- waiting_for：只在“等前一单提交”时出现，占用文件的工单号；
- candidates：真机自检里测试执行者上报的候选原语（test 结果的 candidates，格式见 references/cli.md「读取结果」），
  由调用方列给用户确认；
- pm_update：给出 --pm-status 或 --pm-hours 时出现，提交成功后要对易协作工单做的更新
  （约定见 references/task-tracking.md「更新工单」），调用方原样转成 pm_update.py 的参数；
  ai_level 在给了状态时默认“L4 - 全自主Agent”；
- bug_note：popo 工单（工单号 popo-<提单平台单号>）必有、其他工单没有，调用方写到 bug 单上的备注
  （不超过 20 字，一行）。
"""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import workspace  # noqa: E402

DIRECTORY = "unattended"  # 个人目录下的结果目录，每个工单一个子目录。
RESULT_FILE = "result.json"
READY, WAITING = "待提交", "等前一单提交"
STATUSES = (READY, "需要你处理", "放弃", WAITING)
FIELDS = ("issue_id", "status", "reason", "changed_files", "commit_message", "self_check", "report_path",
          "branch", "written_at")
WAIT_FIELD, CANDIDATES_FIELD, PM_FIELD, BUG_FIELD = "waiting_for", "candidates", "pm_update", "bug_note"
OPTIONAL = (WAIT_FIELD, CANDIDATES_FIELD, PM_FIELD, BUG_FIELD)  # 可选字段，只能按这个顺序排在固定字段之后。
BUG_NOTE_MAX = 20   # popo 工单备注正文的字数上限（用户 2026-11-12 定）
PM_KEYS = ("status", "status_from", "ai_level", "hours", "activity", "comments")
DEFAULT_AI_LEVEL = "L4 - 全自主Agent"   # 无人值守会话的工单一律 L4（用户 2026-11-12 定，见 task-tracking.md「更新工单」）
CANDIDATE_KEYS = ("kind", "content", "runs", "note")
CANDIDATE_KINDS = ("preset", "clean_ui", "template", "step")  # 与 codex_cli.py 的 test schema 一致


class ResultError(Exception):
    """可直接呈现的结果校验错误。"""


def text_argument(value, file_path, label):
    """取 --xxx 或 --xxx-file 给出的文本（两者只能给一个），去掉首尾空白；都没给时为空字符串。"""
    if value is not None and file_path is not None:
        raise ResultError(f"{label}不能同时用参数和文件给出")
    if file_path is not None:
        try:
            return workspace.decode_document(Path(file_path).read_bytes())[0].strip()
        except (OSError, workspace.WorkspaceError) as error:
            raise ResultError(f"无法读取{label}文件：{file_path}：{error}") from None
    return (value or "").strip()


def validate_candidates(candidates):
    if not isinstance(candidates, list):
        raise ResultError("候选原语必须是列表")
    for index, item in enumerate(candidates, 1):
        if not isinstance(item, dict) or set(item) != set(CANDIDATE_KEYS):
            raise ResultError(f"第 {index} 条候选原语的字段应为：{'、'.join(CANDIDATE_KEYS)}")
        if item["kind"] not in CANDIDATE_KINDS:
            raise ResultError(f"第 {index} 条候选原语的 kind 只能是：{'、'.join(CANDIDATE_KINDS)}")
        if not isinstance(item["content"], str) or not item["content"].strip():
            raise ResultError(f"第 {index} 条候选原语的 content 不能为空")
        if not isinstance(item["runs"], int) or isinstance(item["runs"], bool) or item["runs"] < 0:
            raise ResultError(f"第 {index} 条候选原语的 runs 必须是非负整数")
        if not isinstance(item["note"], str):
            raise ResultError(f"第 {index} 条候选原语的 note 必须是字符串")


def load_candidates(path):
    """读取候选原语：candidates 列表本身，或含 candidates 字段的 test 结果对象；按固定键序返回。"""
    try:
        data = json.loads(workspace.decode_document(Path(path).read_bytes())[0])
    except (OSError, ValueError, workspace.WorkspaceError) as error:
        raise ResultError(f"无法读取候选原语文件：{path}：{error}") from None
    if isinstance(data, dict):
        if CANDIDATES_FIELD not in data:
            raise ResultError(f"候选原语文件里没有 candidates 字段：{path}")
        data = data[CANDIDATES_FIELD]
    validate_candidates(data)
    return [{key: item[key] for key in CANDIDATE_KEYS} for item in data]


def validate(result):
    """校验结果的字段齐全且互相一致；通过时返回 None。"""
    keys = tuple(result)
    extra = keys[len(FIELDS):]
    if keys[:len(FIELDS)] != FIELDS or extra != tuple(key for key in OPTIONAL if key in extra):
        raise ResultError("结果字段不完整或顺序不符")
    if result["status"] not in STATUSES:
        raise ResultError(f"状态只能是：{'、'.join(STATUSES)}")
    if (result["status"] == WAITING) != (WAIT_FIELD in result):
        raise ResultError(f"状态为{WAITING}时必须用 --waiting-for 给出占用文件的工单号，其他状态不能给")
    popo = workspace.is_popo_key(result["issue_id"])
    if popo != (BUG_FIELD in result):
        raise ResultError("popo 工单必须用 --bug-note 给出备注，其他工单不能给" if popo
                          else "只有 popo 工单（popo- 开头）才能带 --bug-note")
    if BUG_FIELD in result:
        note = result[BUG_FIELD]
        if not isinstance(note, str) or not note or len(note) > BUG_NOTE_MAX or re.search(r"[\r\n]", note):
            raise ResultError(f"--bug-note 要写一行、不超过 {BUG_NOTE_MAX} 个字")
    if WAIT_FIELD in result:
        workspace.validate_issue_key(result[WAIT_FIELD])
        if result[WAIT_FIELD] == result["issue_id"]:
            raise ResultError("--waiting-for 不能是本工单")
    if CANDIDATES_FIELD in result:
        validate_candidates(result[CANDIDATES_FIELD])
    if PM_FIELD in result:
        pm_update = result[PM_FIELD]
        if not isinstance(pm_update, dict) or tuple(pm_update) != PM_KEYS:
            raise ResultError("pm_update 字段不完整或顺序不符")
        if pm_update["status"] is None and pm_update["hours"] is None:
            raise ResultError("pm_update 至少要有状态或工时")
        if (pm_update["hours"] is None) != (pm_update["activity"] is None):
            raise ResultError("工单工时和活动要一起给出")
        if pm_update["hours"] is None and pm_update["comments"]:
            raise ResultError("--pm-comments 要和 --pm-hours 一起使用")
        for key, label in (("status", "工单状态"), ("activity", "工时活动")):
            if pm_update[key] is not None and not str(pm_update[key]).strip():
                raise ResultError(f"{label}不能为空")
        if pm_update["status_from"] is not None and not all(
                name.strip() for name in re.split(r"[,，]", pm_update["status_from"])):
            raise ResultError("--pm-status-from 里有空的状态名")
        hours = pm_update["hours"]
        if hours is not None and (not isinstance(hours, str) or not re.fullmatch(r"\d{1,3}(\.\d{1,2})?", hours)
                                  or float(hours) <= 0):
            raise ResultError("工单工时须大于 0、不超过 999.99，且最多两位小数")
        if pm_update["ai_level"] is not None and pm_update["status"] is None:
            raise ResultError("--pm-ai-level 要和 --pm-status 一起使用")
        if pm_update["status_from"] is not None and pm_update["status"] is None:
            raise ResultError("--pm-status-from 要和 --pm-status 一起使用")
        if result["status"] != "待提交":
            raise ResultError("只有待提交的结果才能带工单更新")
        if popo:
            raise ResultError("popo 工单不更新易协作工单，不能带 --pm-* 参数")
    if not result["reason"]:
        raise ResultError("必须写明原因（待提交时写处理结论，其余写卡在哪里）")
    if result["status"] != "待提交":
        return
    missing = [label for key, label in (("changed_files", "改动文件"), ("commit_message", "提交说明"),
                                        ("self_check", "自检结果"), ("report_path", "报告路径"))
               if not result[key]]
    if missing:
        raise ResultError("状态为待提交时必须提供：" + "、".join(missing))


def result_path(personal, issue_id):
    path = personal / DIRECTORY / issue_id / RESULT_FILE
    workspace.no_links(path)
    return path


def write_result(args):
    root, personal, _ = workspace.paths(args.root, args.global_config)
    workspace.require_initialized(root)
    workspace.validate_issue_key(args.issue_id)
    files = []
    for value in args.file:
        relative = str(value).replace("\\", "/").strip("/")
        if not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ResultError(f"改动文件要写相对项目根目录的路径：{value}")
        if relative not in files:
            files.append(relative)
    report = ""
    if args.report:
        report_path = Path(args.report) if Path(args.report).is_absolute() else root / args.report
        if report_path.is_dir():
            report_path = report_path / "index.html"
        if not report_path.is_file():
            raise ResultError(f"报告不存在：{report_path}")
        report = str(report_path)
    result = dict(zip(FIELDS, (
        args.issue_id, args.status, text_argument(args.reason, args.reason_file, "原因"), files,
        text_argument(args.message, args.message_file, "提交说明"),
        text_argument(args.self_check, args.self_check_file, "自检结果"), report,
        workspace.svn_branch(root), datetime.now().astimezone().isoformat(timespec="seconds"))))
    if args.waiting_for is not None:
        result[WAIT_FIELD] = args.waiting_for.strip().lstrip("#")
    if args.candidates_file is not None:
        result[CANDIDATES_FIELD] = load_candidates(args.candidates_file)
    if args.pm_status is not None or args.pm_hours is not None or args.pm_activity is not None \
            or args.pm_status_from is not None or args.pm_comments:
        ai_level = args.pm_ai_level or (DEFAULT_AI_LEVEL if args.pm_status is not None else None)
        result[PM_FIELD] = dict(zip(PM_KEYS, (args.pm_status, args.pm_status_from, ai_level, args.pm_hours,
                                              args.pm_activity, args.pm_comments)))
    if args.bug_note is not None:
        result[BUG_FIELD] = args.bug_note.strip()
    validate(result)
    path = result_path(personal, args.issue_id)
    workspace.apply_changes([(path, workspace.read_bytes(path), workspace.json_bytes(result))])
    return {"action": "unattended-result", "path": str(path), "result": result}


def show_result(args):
    root, personal, _ = workspace.paths(args.root, args.global_config)
    workspace.require_initialized(root)
    workspace.validate_issue_key(args.issue_id)
    path = result_path(personal, args.issue_id)
    raw = workspace.read_bytes(path)
    if raw is None:
        raise ResultError(f"工单 {args.issue_id} 还没有结果文件：{path}")
    result = workspace.parse_json(raw, path)
    validate(result)
    return {"action": "unattended-result", "path": str(path), "result": result}


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="action", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", default=os.getcwd())
    common.add_argument("--issue-id", required=True)
    common.add_argument("--global-config", default=str(Path.home() / workspace.DIRECTORY / "config.json"))
    writer = commands.add_parser("result", parents=[common], help="校验并写出结果文件")
    writer.add_argument("--status", required=True, help="、".join(STATUSES))
    writer.add_argument("--reason")
    writer.add_argument("--reason-file")
    writer.add_argument("--file", action="append", default=[], help="改动文件（相对项目根目录），可重复")
    writer.add_argument("--message", help="拟定的提交说明")
    writer.add_argument("--message-file")
    writer.add_argument("--self-check", help="自检结果（提交前自检和真机自检的结论）")
    writer.add_argument("--self-check-file")
    writer.add_argument("--report", help="处理报告的目录或 index.html")
    writer.add_argument("--waiting-for", help=f"状态为{WAITING}时必填：占用要改的文件的工单号")
    writer.add_argument("--candidates-file",
                        help="候选原语：test 结果 JSON（取其 candidates）或 candidates 列表本身；没有候选原语时不给")
    writer.add_argument("--pm-status", help="提交后工单要改成的状态（pm_update.py --status）")
    writer.add_argument("--pm-status-from", help="只有当前状态在其中才改（pm_update.py --status-from）")
    writer.add_argument("--pm-ai-level", help="改状态时一起填的 AI Coding Level（pm_update.py --ai-level）；"
                        "给了 --pm-status 而不给它时默认“L4 - 全自主Agent”")
    writer.add_argument("--pm-hours", help="提交后要登记的工时（pm_update.py --hours）")
    writer.add_argument("--pm-activity", help="工时的活动（pm_update.py --activity）")
    writer.add_argument("--pm-comments", default="", help="工时备注（pm_update.py --comments）")
    writer.add_argument("--bug-note", help=f"popo 工单（--issue-id popo-<单号>）必填：写到 bug 单上的备注，"
                        f"不超过 {BUG_NOTE_MAX} 字；待提交写怎么修的，其余写原因")
    commands.add_parser("show", parents=[common], help="读回结果文件")
    args = parser.parse_args(argv)
    try:
        result = write_result(args) if args.action == "result" else show_result(args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ResultError, workspace.WorkspaceError, OSError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
