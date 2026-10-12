#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import difflib
import json
import locale
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import tokenize
import xml.etree.ElementTree as ET
from dataclasses import dataclass


STATUS_BLOCKERS = set("ADMRC!~L")
TICKET_PREFIX_PATTERN = (
    r"(?:(?:finish|finished|finishes|refs?|fix|fixed|fixes|close|closed|closes|"
    r"resolve|resolved|resolves)\s+)?#\S+\s+"
)
FIRST_LINE_PREFIX = re.compile(rf"^({TICKET_PREFIX_PATTERN})(.*)$", re.IGNORECASE)
FIRST_LINE_TAG = re.compile(rf"^({TICKET_PREFIX_PATTERN})\[([^\]]+)\](.*)$", re.IGNORECASE)
PYTHON_CODING_TEXT_RE = re.compile(
    r"^(?P<prefix>[ \t\f]*#.*?coding[:=][ \t]*)(?P<encoding>[-\w.]+)(?P<suffix>.*)$",
    re.IGNORECASE,
)
DEFAULT_AUTHOR_ALLOWLIST = frozenset(
    {
        "xuxuming",
        "gzzhanglei",
        "gzgongchao",
        "sunzhenpeng",
        "wanjinsen",
        "huangqingzhen",
        "yangchanghua",
    }
)
AUTHOR_ALIASES = {
    "xuxuiming": "xuxuming",
}
DEFAULT_IGNORED_AUTHORS = frozenset(
    {
        "grp.xyqpatch",
    }
)


class SvnRebaseError(RuntimeError):
    pass


@dataclass
class RevisionGroup:
    revs: list[int]
    author: str
    msg: str


@dataclass
class RevisionPlanItem:
    rev: int
    author: str
    msg: str
    summary: list[str]
    is_revert: bool
    revert_targets: list[int]
    classification: str
    reason: str


REVERT_KEYWORDS = (
    "回退",
    "回滚",
    "撤销",
    "revert",
    "rollback",
    "backout",
)
RELEASE_HOLD_PATTERNS = (
    re.compile(r"不回\s*(?:全服|trunk)", re.IGNORECASE),
    re.compile(r"不\s*回\s*(?:全服|trunk)", re.IGNORECASE),
    re.compile(r"不\s*(?:全服|trunk)", re.IGNORECASE),
    re.compile(r"不\s*上\s*(?:全服|trunk)", re.IGNORECASE),
    re.compile(r"不\s*转\s*(?:全服|trunk)", re.IGNORECASE),
    re.compile(r"不\s*合\s*(?:全服|trunk)", re.IGNORECASE),
    re.compile(r"无需\s*merge\s*回\s*(?:全服|trunk)", re.IGNORECASE),
    re.compile(r"连续\s*(?:\d+|[一二三四五六七八九十两]+|N|n)\s*周\s*外测"),
)
REVISION_REF_PATTERN = re.compile(
    r"(?:\br|revision(?:s)?\s*|修订\s*)(\d{5,})",
    re.IGNORECASE,
)
TICKET_ID_PATTERN = re.compile(r"#\d+")
MERGED_FROM_TRUNK_PATTERN = re.compile(
    r"^\s*Merged\s+revision(?:\(s\)|s)?\s+[\dr,\-\s]+from\s+.+(?:/|\\)trunk\b",
    re.IGNORECASE,
)
AUTO_COMMIT_LOG_RE = re.compile(r"auto\s*commit\s*:", re.IGNORECASE)
ROBOT_AUTO_COMMIT_LINE_RE = re.compile(r"^\s*auto\s*commit\s*:", re.IGNORECASE)
ROBOT_AUTO_COMMIT_PREFIX_RE = re.compile(
    r"^\s*auto\s*commit\s*:\s*"
    r"(?:Merged\s+(?:revisions?)?\s*[\dr,\-\s]*\(?[^)]*\)?\s*(?:from\s+\S+)?\s*:?\s*)?",
    re.IGNORECASE,
)
FORMAL_BRANCH_SHIP_RE = re.compile(r"\d{4}_ship", re.IGNORECASE)
TEST_BRANCH_NAME_RE = re.compile(r"^test", re.IGNORECASE)
COMPLIANT_FORMAL_LOG_RE = re.compile(
    r"^(?:(?:finish|finished|refs|ref)\s*#\d+\s+\S|#热更\s+\S)",
    re.IGNORECASE,
)
LEADING_TICKET_PREFIX_RE = re.compile(
    r"^(?:(?:finish|finished|refs|ref|fix|fixed|fixes|close|closed|closes|"
    r"resolve|resolved|resolves)\s+)?#\d+\s*",
    re.IGNORECASE,
)
LEADING_LOG_KEYWORD_RE = re.compile(
    r"^(?:finish|finished|refs|ref|fix|fixed|fixes|close|closed|closes|"
    r"resolve|resolved|resolves)\s+(?=#\S)",
    re.IGNORECASE,
)
LEADING_TICKET_TOKEN_RE = re.compile(r"^#\S+\s*")
LEADING_AUTHOR_TAG_RE = re.compile(r"^\[[^\]]*\]\s*")
FORMAL_LOG_KEYWORDS = ("refs", "finish")
HOTFIX_TICKET_TOKENS = frozenset({"热更", "热更新", "紧急热更", "hotfix"})


def candidate_output_encodings() -> list[str]:
    preferred = locale.getpreferredencoding(False)
    values = [
        os.environ.get("SVN_MERGE_SVN_ENCODING", ""),
        "utf-8",
        "gbk",
        "cp936",
        "mbcs" if os.name == "nt" else "",
        preferred,
    ]
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def decode_svn_output(data: bytes | str) -> str:
    if isinstance(data, str):
        return data
    encodings = candidate_output_encodings()
    for encoding in encodings:
        try:
            return data.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return data.decode(encodings[-1] if encodings else "utf-8", errors="replace")


def run_svn(args: list[str], cwd: str | None = None, check: bool = True) -> str:
    timeout = int(os.environ.get("SVN_MERGE_SVN_TIMEOUT_SEC", "1800"))
    try:
        completed = subprocess.run(
            ["svn", "--non-interactive", *args],
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=None if timeout <= 0 else timeout,
        )
    except subprocess.TimeoutExpired as exc:
        partial = exc.stdout or ""
        partial = decode_svn_output(partial)
        raise SvnRebaseError(
            f"svn {' '.join(args)} 超过 {timeout} 秒仍未完成。\n"
            "请结束残留的 svn.exe 进程，回滚目标工作副本，"
            "删除冲突临时文件，然后从当前重放项重新执行合并。\n"
            f"部分输出：\n{partial}"
        )
    if check and completed.returncode != 0:
        raise SvnRebaseError(
            f"svn {' '.join(args)} 执行失败，退出码 {completed.returncode}\n"
            f"{decode_svn_output(completed.stdout)}"
        )
    return decode_svn_output(completed.stdout)


def run_svn_result(args: list[str], cwd: str | None = None) -> tuple[int, str]:
    timeout = int(os.environ.get("SVN_MERGE_SVN_TIMEOUT_SEC", "1800"))
    try:
        completed = subprocess.run(
            ["svn", "--non-interactive", *args],
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=None if timeout <= 0 else timeout,
        )
    except subprocess.TimeoutExpired as exc:
        partial = exc.stdout or ""
        partial = decode_svn_output(partial)
        raise SvnRebaseError(
            f"svn {' '.join(args)} 超过 {timeout} 秒仍未完成。\n"
            "请结束残留的 svn.exe 进程，回滚目标工作副本，"
            "删除冲突临时文件，然后从当前重放项重新执行合并。\n"
            f"部分输出：\n{partial}"
        )
    return completed.returncode, decode_svn_output(completed.stdout)


def run_svn_bytes(args: list[str], cwd: str | None = None, check: bool = True) -> bytes:
    timeout = int(os.environ.get("SVN_MERGE_SVN_TIMEOUT_SEC", "1800"))
    try:
        completed = subprocess.run(
            ["svn", "--non-interactive", *args],
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=None if timeout <= 0 else timeout,
        )
    except subprocess.TimeoutExpired as exc:
        partial = exc.stdout or b""
        raise SvnRebaseError(
            f"svn {' '.join(args)} 超过 {timeout} 秒仍未完成。\n"
            "请结束残留的 svn.exe 进程，回滚目标工作副本，"
            "删除冲突临时文件，然后从当前重放项重新执行合并。\n"
            f"部分输出：\n{decode_svn_output(partial)}"
        )
    if check and completed.returncode != 0:
        raise SvnRebaseError(
            f"svn {' '.join(args)} 执行失败，退出码 {completed.returncode}\n"
            f"{decode_svn_output(completed.stdout)}"
        )
    return completed.stdout


def parse_rev_list(text: str | None) -> set[int]:
    if not text:
        return set()
    values: set[int] = set()
    for part in text.split(","):
        item = part.strip()
        if not item:
            continue
        if item.startswith("r"):
            item = item[1:]
        values.add(int(item))
    return values


def parse_author_list(text: str | None) -> set[str]:
    if not text:
        return set()
    return {
        canonical_author_token(part)
        for part in text.split(",")
        if part.strip()
    }


def normalize_author(author: str, keep_domain: bool) -> str:
    author = author.strip()
    if not keep_domain and "@" in author:
        author = author.split("@", 1)[0]
    return AUTHOR_ALIASES.get(author.lower(), author)


def canonical_author_token(author: str) -> str:
    author = author.strip()
    if "@" in author:
        author = author.split("@", 1)[0]
    return AUTHOR_ALIASES.get(author.lower(), author.lower())


def build_author_allowlist(source_author: str) -> set[str]:
    allowlist = set(DEFAULT_AUTHOR_ALLOWLIST)
    if source_author.strip():
        allowlist.add(canonical_author_token(source_author))
    return allowlist


def normalize_path_prefix(path: str) -> str:
    return path.replace("\\", "/").rstrip("/")


def source_branch_tag(source_url: str) -> str:
    branch_name = normalize_path_prefix(source_url).rsplit("/", 1)[-1]
    match = re.match(r"^(?P<tag>.+?)_\d{4}_\d{2}_\d{2}$", branch_name)
    if match:
        return match.group("tag")
    return branch_name


def format_auto_commit_revisions(revs: list[int]) -> str:
    if len(revs) == 1:
        return f"revision {revs[0]}"
    return "revisions " + ",".join(str(rev) for rev in revs)


def prepend_auto_commit_line(message: str, revs: list[int], author: str, source_url: str) -> str:
    line = (
        f"auto commit:Merged {format_auto_commit_revisions(revs)}"
        f"({author}) from {source_branch_tag(source_url)}"
    )
    if not message:
        return line + "\n"
    suffix = "" if message.endswith(("\n", "\r")) else "\n"
    return line + "\n" + message + suffix


@dataclass
class LogPolicyOptions:
    target_kind: str = "other"
    weekly_maintenance: bool = False
    log_ticket: str | None = None
    log_keyword: str | None = None
    log_text: str | None = None
    log_extra: str | None = None

    @property
    def target_formal(self) -> bool:
        return self.target_kind != "other"

    @property
    def is_release(self) -> bool:
        return self.target_kind == "release"

    @property
    def robot_auto_commit_allowed(self) -> bool:
        return self.weekly_maintenance

    def effective_keyword(self) -> str:
        if self.log_keyword:
            return self.log_keyword.strip().lower()
        return "finish" if self.log_ticket else "refs"


def classify_target_branch(target_url: str) -> str:
    path = normalize_path_prefix(target_url)
    name = path.rsplit("/", 1)[-1]
    if name.lower() == "trunk":
        return "trunk"
    if FORMAL_BRANCH_SHIP_RE.search(path):
        if TEST_BRANCH_NAME_RE.match(name):
            return "test"
        return "release"
    return "other"


def build_log_policy(args: argparse.Namespace, target_url: str) -> LogPolicyOptions:
    return LogPolicyOptions(
        target_kind=classify_target_branch(target_url),
        weekly_maintenance=bool(getattr(args, "weekly_maintenance", False)),
        log_ticket=(getattr(args, "log_ticket", None) or None),
        log_keyword=(getattr(args, "log_keyword", None) or None),
        log_text=(getattr(args, "log_text", None) or None),
        log_extra=(getattr(args, "log_extra", None) or None),
    )


def strip_robot_log_lines(lines: list[str]) -> tuple[list[str], list[str]]:
    kept: list[str] = []
    removed: list[str] = []
    for line in lines:
        if ROBOT_AUTO_COMMIT_LINE_RE.match(line):
            removed.append(line)
        else:
            kept.append(line)
    return kept, removed


def normalize_log_ticket(value: str | None) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    bare = text.lstrip("#").strip()
    if bare in HOTFIX_TICKET_TOKENS:
        return bare
    match = re.search(r"#(\d+)", text) or re.search(r"(\d{4,})", text)
    if match:
        return match.group(1)
    match = re.search(r"#(\S+)", text)
    if match:
        return match.group(1)
    return bare


def derive_first_line_description(text: str) -> str:
    value = (text or "").strip()
    author_tag = ""
    for _ in range(4):
        previous = value
        match = ROBOT_AUTO_COMMIT_PREFIX_RE.match(value)
        if match:
            value = value[match.end() :].strip()
        match = LEADING_LOG_KEYWORD_RE.match(value)
        if match:
            value = value[match.end() :].strip()
        match = LEADING_TICKET_TOKEN_RE.match(value)
        if match:
            value = value[match.end() :].strip()
        match = LEADING_AUTHOR_TAG_RE.match(value)
        if match:
            if not author_tag:
                author_tag = match.group(0).strip()
            value = value[match.end() :].strip()
        if value == previous:
            break
    if not value:
        return ""
    return f"{author_tag}{value}" if author_tag else value


def derive_log_description(first_line: str, body_lines: list[str]) -> str:
    description = derive_first_line_description(first_line)
    if description:
        return description
    for line in body_lines:
        if not TICKET_ID_PATTERN.search(line):
            continue
        description = derive_first_line_description(line)
        if description:
            return description
    return ""


def default_provenance_text(source_url: str, revs: list[int]) -> str:
    revision_text = "r" + ",".join(str(rev) for rev in revs)
    return f"merge from {source_branch_tag(source_url)} {revision_text}"


def report_log_policy_violation(
    policy: LogPolicyOptions,
    reason: str,
    first_line: str,
    message: str,
    group_label: str,
    strict: bool,
) -> None:
    candidates = sorted(set(TICKET_ID_PATTERN.findall(message)))
    details = [
        f"目标分支提交日志不合规（{group_label}）：{reason}",
        f"当前首行：{first_line}",
        "规范：目标分支为正式分支（URL 含 <年份>_ship，或分支为 trunk）时，提交日志必须关联 redmine 单号，"
        "首行形如 `finish #321998 描述` 或 `refs #321998 描述`，单号后面的描述不能省略；"
        "紧急热更来不及建单时可用 `#热更 描述`。",
        "禁止在提交日志里使用 `auto commit:`：该关键词只保留给公共账号自动提交，本技能中仅周维护版本合并的"
        "机器人调用例外（--weekly-maintenance，目标可以是 trunk、外测分支或 <年份>_ship 下的任一外放分支）。",
    ]
    if policy.log_ticket is None:
        details.append(
            "处理：在命令中追加 --log-ticket <单号> 和 --log-text <描述>（只给单号不够，描述不能省略）后重跑，"
            "可按需配合 --log-keyword finish|refs、--log-extra <附加内容>；确需跳过的修订用 --skip-revs。"
        )
    elif not (policy.log_text or "").strip():
        details.append(
            "处理：追加 --log-text <描述> 后重跑（或确认源日志里存在带单号、带描述的日志行）；"
            "只给 --log-ticket 不足以生成合规日志。"
        )
    else:
        details.append(
            f"处理：检查 --log-ticket {policy.log_ticket} 与 --log-text/--log-extra 取值，"
            "或改用 --skip-revs 跳过该修订。"
        )
    if candidates:
        details.append("源日志中检测到的候选单号：" + "、".join(candidates[:5]))
    text = "\n".join(details)
    if strict:
        raise SvnRebaseError(text)
    print("TARGET_LOG_POLICY_VIOLATION " + text.replace("\n", " | "))


def enforce_commit_log_policy(
    message: str,
    policy: LogPolicyOptions,
    *,
    revs: list[int],
    source_url: str,
    group_label: str = "",
    strict: bool = True,
) -> str:
    label = group_label or format_revision_group(revs)
    lines = message.splitlines()
    if not lines:
        lines = [""]
    raw_first = lines[0]
    first_line = raw_first.strip()
    if policy.target_formal and not policy.robot_auto_commit_allowed:
        body, removed_robot_lines = strip_robot_log_lines(lines[1:])
    else:
        body, removed_robot_lines = lines[1:], []
    first_line_has_auto_commit = bool(AUTO_COMMIT_LOG_RE.search(first_line))
    keyword = policy.effective_keyword()
    ticket = normalize_log_ticket(policy.log_ticket)
    hotfix = ticket in HOTFIX_TICKET_TOKENS if ticket else False
    final_first = raw_first
    notes: list[str] = []
    changed = False

    auto_commit_blocked = first_line_has_auto_commit and not policy.robot_auto_commit_allowed
    if auto_commit_blocked and not ticket:
        if policy.is_release:
            reason = "外放正式分支禁止使用 auto commit: 日志，必须使用 finish/refs #维护单号。"
        else:
            reason = "auto commit: 日志只允许公共账号自动提交（周维护版本合并机器人，--weekly-maintenance）使用。"
        report_log_policy_violation(policy, reason, first_line, message, label, strict)
    elif (policy.target_formal or auto_commit_blocked) and not (
        policy.robot_auto_commit_allowed and first_line_has_auto_commit
    ):
        if hotfix:
            if not COMPLIANT_FORMAL_LOG_RE.match(first_line) or not first_line.startswith("#热更"):
                description = (policy.log_text or "").strip() or derive_log_description(first_line, body)
                if not description:
                    report_log_policy_violation(
                        policy,
                        "热更日志缺少描述：`#热更` 后面必须写描述。",
                        first_line,
                        message,
                        label,
                        strict,
                    )
                else:
                    final_first = f"#热更 {description}"
                    notes.append(f"TARGET_LOG_HOTFIX_APPLIED {label} first_line={final_first}")
                    changed = True
        elif ticket:
            expected_prefix = f"{keyword} #{ticket}"
            already_applied = first_line.startswith(expected_prefix) and first_line[
                len(expected_prefix) :
            ].strip()
            if not already_applied:
                description = (policy.log_text or "").strip() or derive_log_description(first_line, body)
                extra = (policy.log_extra or "").strip()
                if not extra and (removed_robot_lines or first_line_has_auto_commit):
                    extra = default_provenance_text(source_url, revs)
                if not description:
                    report_log_policy_violation(
                        policy,
                        "只有单号没有描述：`--log-ticket` 必须同时给出描述。",
                        first_line,
                        message,
                        label,
                        strict,
                    )
                else:
                    final_first = " ".join(
                        part for part in (expected_prefix, description, extra) if part
                    )
                    notes.append(
                        f"TARGET_LOG_TICKET_APPLIED {label} ticket=#{ticket} keyword={keyword} "
                        f"first_line={final_first}"
                    )
                    changed = True
                    if (
                        not first_line_has_auto_commit
                        and TICKET_ID_PATTERN.search(first_line)
                        and f"#{ticket}" not in first_line
                    ):
                        body = [raw_first, *body]
                        notes.append(f"TARGET_LOG_SOURCE_LINE_KEPT {label} {first_line}")
        elif not COMPLIANT_FORMAL_LOG_RE.match(first_line):
            prefix_match = LEADING_TICKET_PREFIX_RE.match(first_line)
            if prefix_match and first_line[prefix_match.end() :].strip():
                final_first = f"{keyword} {first_line}"
                notes.append(f"TARGET_LOG_KEYWORD_ADDED {label} keyword={keyword} first_line={final_first}")
                changed = True
            else:
                report_log_policy_violation(
                    policy,
                    "首行没有可识别的 `finish #单号 描述` / `refs #单号 描述`（单号和描述缺一不可）。",
                    first_line,
                    message,
                    label,
                    strict,
                )

    if removed_robot_lines:
        changed = True

    if policy.target_formal and not policy.robot_auto_commit_allowed:
        kept_mentions = [
            line for line in (final_first, *body) if AUTO_COMMIT_LOG_RE.search(line)
        ]
        if kept_mentions:
            print(
                f"TARGET_LOG_AUTO_COMMIT_TEXT_WARNING {label} 提交日志仍有 auto commit: 字样："
                + " | ".join(kept_mentions[:3])
            )

    for note in notes:
        print(note)
    if removed_robot_lines and policy.target_formal:
        print(
            f"TARGET_LOG_ROBOT_LINE_REMOVED {label} 移除 {len(removed_robot_lines)} 行机器人 auto commit: 日志"
        )

    if not changed:
        return message
    final_message = "\n".join([final_first, *body])
    if message.endswith("\n"):
        final_message += "\n"
    return final_message


def normalize_summarize_line(line: str, prefix: str) -> str | None:
    if not line.strip():
        return None
    status = line[0]
    if status not in {"A", "M", "D"}:
        return None
    match = re.match(r"^(..?)\s+(?P<path>.+)$", line)
    if not match:
        return None
    item_path = normalize_path_prefix(match.group("path").strip())
    prefix_norm = normalize_path_prefix(prefix)
    if item_path.startswith(prefix_norm + "/"):
        item_path = item_path[len(prefix_norm) + 1 :]
    elif item_path == prefix_norm:
        item_path = "."
    return f"{status} {item_path}"


def summarize_diff(prefix: str, svn_args: list[str]) -> list[str]:
    raw = run_svn(svn_args).splitlines()
    items = {
        item
        for item in (normalize_summarize_line(line, prefix) for line in raw)
        if item is not None
    }
    return sorted(items)


def has_conflict_output(text: str) -> bool:
    return bool(
        re.search(r"(^|\r?\n)C\s", text)
        or "Summary of conflicts:" in text
        or "Tree conflict" in text
    )


def has_only_property_conflicts(text: str) -> bool:
    if not has_conflict_output(text):
        return False
    return bool(
        re.search(r"Property conflicts:\s*[1-9]\d*", text)
        and not re.search(r"Text conflicts:\s*[1-9]\d*", text)
        and not re.search(r"Tree conflicts:\s*[1-9]\d*", text)
    )


def get_info_xml(target: str) -> ET.Element:
    xml_bytes = run_svn_bytes(["info", "--xml", target])
    return ET.fromstring(decode_svn_output(xml_bytes))


def get_target_url(target_wc: str) -> str:
    root = get_info_xml(target_wc)
    url = root.findtext(".//entry/url")
    if not url:
        raise SvnRebaseError(f"无法从工作副本推导目标 URL：{target_wc}")
    return url


def get_log_entry(source_url: str, rev: int) -> tuple[str, str]:
    xml_bytes = run_svn_bytes(["log", "--xml", "--incremental", "-r", str(rev), source_url])
    root = ET.fromstring(decode_svn_output(xml_bytes))
    entry = root if root.tag == "logentry" else root.find("./logentry")
    if entry is None:
        raise SvnRebaseError(f"无法解析 {source_url} 的 r{rev} SVN 日志")
    author = entry.findtext("author") or ""
    msg = entry.findtext("msg") or ""
    return author, msg


def should_ignore_author(author: str, ignored_authors: set[str]) -> bool:
    return canonical_author_token(author) in ignored_authors


def filter_revisions_by_ignored_authors(
    source_url: str,
    revisions: list[int],
    ignored_authors: set[str],
) -> list[int]:
    if not ignored_authors:
        return revisions

    kept: list[int] = []
    for rev in revisions:
        author, msg = get_log_entry(source_url, rev)
        if should_ignore_author(author, ignored_authors):
            first_line = msg.splitlines()[0] if msg else ""
            print(
                f"SKIP_IGNORED_AUTHOR r{rev} 作者={author} 日志={first_line}",
                file=sys.stderr,
            )
            continue
        kept.append(rev)
    return kept


def build_ignored_authors(args: argparse.Namespace) -> set[str]:
    ignored_authors: set[str] = set()
    if not getattr(args, "include_robot_commits", False):
        ignored_authors.update(DEFAULT_IGNORED_AUTHORS)
    ignored_authors.update(parse_author_list(getattr(args, "ignore_authors", "")))
    return ignored_authors


def first_line_has_author_token(first_line: str, author_allowlist: set[str]) -> bool:
    match = FIRST_LINE_TAG.match(first_line)
    if not match:
        return False
    return canonical_author_token(match.group(2)) in author_allowlist


def normalize_first_line_author_token(first_line: str, keep_author_domain: bool) -> str:
    match = FIRST_LINE_TAG.match(first_line)
    if not match:
        return first_line
    normalized = normalize_author(match.group(2), keep_author_domain)
    if normalized == match.group(2):
        return first_line
    return f"{match.group(1)}[{normalized}]{match.group(3)}"


def get_merge_history_authors(source_url: str, rev: int) -> list[str]:
    xml_bytes = run_svn_bytes(["log", "-g", "--xml", "--incremental", "-r", str(rev), source_url])
    root = ET.fromstring(decode_svn_output(xml_bytes))
    entry = root if root.tag == "logentry" else root.find("./logentry")
    if entry is None:
        return []

    authors: list[str] = []
    for nested in list(entry.iter("logentry"))[1:]:
        author = (nested.findtext("author") or "").strip()
        if author:
            authors.append(author)
    return authors


def infer_merge_history_author(
    source_url: str,
    rev: int,
    source_author: str,
    keep_author_domain: bool,
) -> str | None:
    authors = get_merge_history_authors(source_url, rev)
    if not authors:
        return None

    seen: set[str] = set()
    unique: list[str] = []
    for author in authors:
        token = canonical_author_token(author)
        if token in seen:
            continue
        seen.add(token)
        unique.append(normalize_author(author, keep_author_domain))

    if len(unique) == 1:
        return unique[0]
    return None


def resolve_commit_author(
    source_url: str,
    source_author: str,
    source_msg: str,
    rev: int,
    keep_author_domain: bool,
    infer_merge_history_author_enabled: bool,
) -> str:
    first_line = source_msg.splitlines()[0] if source_msg else ""
    author_allowlist = build_author_allowlist(source_author)
    if first_line_has_author_token(first_line, author_allowlist):
        match = FIRST_LINE_TAG.match(first_line)
        if match:
            return normalize_author(match.group(2), keep_author_domain)

    if infer_merge_history_author_enabled:
        inferred = infer_merge_history_author(source_url, rev, source_author, keep_author_domain)
        if inferred:
            return inferred

    return normalize_author(source_author, keep_author_domain)


def build_commit_message(
    source_url: str,
    source_msg: str,
    source_author: str,
    revs: list[int],
    preserve_log_through: int | None,
    preserve_log_revs: set[int],
    keep_author_domain: bool,
    weekly_maintenance: bool,
    infer_merge_history_author_enabled: bool,
) -> str:
    first_rev = revs[0]
    if first_rev in preserve_log_revs:
        return source_msg
    if preserve_log_through is not None and first_rev <= preserve_log_through:
        return source_msg

    lines = source_msg.splitlines(keepends=True)
    if not lines:
        author = normalize_author(source_author, keep_author_domain)
        if weekly_maintenance:
            return prepend_auto_commit_line(source_msg, revs, author, source_url)
        return source_msg

    first_line = lines[0].rstrip("\r\n")
    newline = lines[0][len(first_line) :]

    author_allowlist = build_author_allowlist(source_author)
    author = resolve_commit_author(
        source_url,
        source_author,
        source_msg,
        first_rev,
        keep_author_domain,
        infer_merge_history_author_enabled,
    )
    if weekly_maintenance:
        return prepend_auto_commit_line(source_msg, revs, author, source_url)

    if first_line.lower().startswith("merged revision"):
        return source_msg

    if not first_line_has_author_token(first_line, author_allowlist):
        match = FIRST_LINE_PREFIX.match(first_line)
        if match:
            first_line = f"{match.group(1)}[{author}]{match.group(2)}"
        else:
            first_line = f"[{author}]{first_line}"
    else:
        first_line = normalize_first_line_author_token(first_line, keep_author_domain)

    lines[0] = first_line + newline
    return "".join(lines)


def verify_clean_working_copy(target_wc: str) -> None:
    output = run_svn(["status", target_wc])
    blockers: list[str] = []
    warnings: list[str] = []
    for line in output.splitlines():
        if not line:
            continue
        if line.startswith("Performing status on external item"):
            continue
        code = line[0]
        if code in STATUS_BLOCKERS:
            blockers.append(line)
        elif code == "?":
            warnings.append(line)
    if warnings:
        print("警告：忽略目标工作副本中的未版本控制路径：", file=sys.stderr)
        for line in warnings:
            print(f"  {line}", file=sys.stderr)
    if blockers:
        raise SvnRebaseError(
            "目标工作副本存在版本控制内的本地修改或锁：\n" + "\n".join(blockers)
        )


def get_eligible_revisions(
    source_url: str,
    target_wc: str,
    min_rev: int | None,
    max_rev: int | None,
    skip_revs: set[int],
    ignored_authors: set[str],
) -> list[int]:
    output = run_svn(["mergeinfo", "--show-revs", "eligible", source_url, target_wc])
    revisions: list[int] = []
    for line in output.splitlines():
        line = line.strip()
        if not line.startswith("r"):
            continue
        rev = int(line[1:])
        if min_rev is not None and rev < min_rev:
            continue
        if max_rev is not None and rev > max_rev:
            continue
        if rev in skip_revs:
            continue
        revisions.append(rev)
    return filter_revisions_by_ignored_authors(source_url, revisions, ignored_authors)


def format_revision_group(revs: list[int]) -> str:
    if len(revs) == 1:
        return f"r{revs[0]}"
    if revs == list(range(revs[0], revs[-1] + 1)):
        return f"r{revs[0]}-r{revs[-1]} ({len(revs)} revs)"
    return ",".join(f"r{rev}" for rev in revs)


def revision_group_file_stem(revs: list[int]) -> str:
    if len(revs) == 1:
        return f"r{revs[0]}"
    return f"r{revs[0]}_r{revs[-1]}"


def build_revision_merge_args(revs: list[int]) -> list[str]:
    return ["-c", ",".join(str(rev) for rev in revs)]


def summarize_source_revision_group(source_url: str, revs: list[int]) -> list[str]:
    items: set[str] = set()
    for rev in revs:
        items.update(summarize_diff(source_url, ["diff", "--summarize", "-c", str(rev), source_url]))
    return sorted(items)


def revision_property_names(source_url: str, rev: int) -> set[str]:
    raw = run_svn(["diff", "--properties-only", "-c", str(rev), source_url])
    return {
        match.group(1).strip()
        for match in re.finditer(r"^(?:Added|Modified|Deleted):\s+([^\r\n]+)", raw, re.MULTILINE)
    }


def is_externals_only_revision(source_url: str, rev: int, summary: list[str]) -> bool:
    if summary:
        return False
    property_names = revision_property_names(source_url, rev)
    return bool(property_names) and property_names == {"svn:externals"}


def first_log_line(msg: str) -> str:
    return msg.splitlines()[0] if msg else ""


def first_line_ticket_id(msg: str) -> str | None:
    match = TICKET_ID_PATTERN.search(first_log_line(msg))
    return match.group(0) if match else None


def same_revision_group_log(left_msg: str, right_msg: str) -> bool:
    left_ticket = first_line_ticket_id(left_msg)
    right_ticket = first_line_ticket_id(right_msg)
    if left_ticket and right_ticket:
        return left_ticket == right_ticket
    return first_log_line(left_msg) == first_log_line(right_msg)


def is_revert_message(msg: str) -> bool:
    lower_first_line = first_log_line(msg).lower()
    return any(keyword in lower_first_line for keyword in REVERT_KEYWORDS)


def release_hold_reason(msg: str) -> str | None:
    for pattern in RELEASE_HOLD_PATTERNS:
        match = pattern.search(msg)
        if match:
            return f"日志包含不应回 trunk 的发布提醒：{match.group(0)}"
    return None


def merged_from_trunk_reason(msg: str) -> str | None:
    first_line = first_log_line(msg)
    if MERGED_FROM_TRUNK_PATTERN.search(first_line):
        return "首行日志显示该提交是从 trunk 同步到外测分支的 merge commit，周维护回 trunk 默认跳过"
    return None


def parse_revert_targets(msg: str) -> list[int]:
    targets: list[int] = []
    seen: set[int] = set()
    for match in REVISION_REF_PATTERN.finditer(msg):
        rev = int(match.group(1))
        if rev in seen:
            continue
        seen.add(rev)
        targets.append(rev)
    return targets


def extract_ticket_ids(msg: str) -> set[str]:
    return {match.group(0) for match in TICKET_ID_PATTERN.finditer(msg)}


def parse_summary_item(item: str) -> tuple[str, str]:
    status, path = item.split(" ", 1)
    return status, path


def m_file_paths(summary: list[str]) -> set[str] | None:
    paths: set[str] = set()
    for item in summary:
        status, path = parse_summary_item(item)
        if status != "M" or path == ".":
            return None
        paths.add(path)
    return paths


def summary_paths(summary: list[str]) -> set[str]:
    return {parse_summary_item(item)[1] for item in summary}


def parse_externals_propget_xml(text: str) -> dict[str, str]:
    root = ET.fromstring(text)
    values: dict[str, str] = {}
    for target in root.findall("./target"):
        path = target.get("path")
        if not path:
            continue
        prop = target.find("./property[@name='svn:externals']")
        if prop is not None:
            values[normalize_path_prefix(path)] = prop.text or ""
    return values


def snapshot_target_externals(target_wc: str) -> dict[str, str]:
    try:
        raw = run_svn(["propget", "svn:externals", "--xml", "-R", target_wc])
    except SvnRebaseError:
        return {}
    return parse_externals_propget_xml(raw)


def conflicted_paths(target_wc: str) -> list[str]:
    output = run_svn(["status", "--ignore-externals", target_wc])
    paths: list[str] = []
    for line in output.splitlines():
        if not line or len(line) < 8:
            continue
        if "C" in line[:7]:
            paths.append(line[7:].strip())
    return paths


def conflicted_property_names(path: str) -> set[str]:
    output = run_svn(["info", path])
    match = re.search(r"^Conflicted Properties:\s*(.+)$", output, re.MULTILINE)
    if not match:
        return set()
    return {item.strip() for item in match.group(1).split(",") if item.strip()}


def restore_target_externals(path: str, externals_before: dict[str, str]) -> None:
    key = normalize_path_prefix(path)
    if key not in externals_before:
        run_svn(["propdel", "svn:externals", path])
        return
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, newline="") as handle:
        handle.write(externals_before[key])
        prop_file = pathlib.Path(handle.name)
    try:
        run_svn(["propset", "svn:externals", "-F", str(prop_file), path])
    finally:
        prop_file.unlink(missing_ok=True)


def resolve_external_property_conflicts(target_wc: str, externals_before: dict[str, str]) -> bool:
    paths = conflicted_paths(target_wc)
    if not paths:
        return False
    for path in paths:
        if conflicted_property_names(path) != {"svn:externals"}:
            return False
    for path in paths:
        restore_target_externals(path, externals_before)
        run_svn(["resolve", "--accept", "working", path])
        print(f"AUTO_RESOLVE_EXTERNALS_CONFLICT 保留目标分支 svn:externals: {path}")
    return True


def first_existing_conflict_side(path: pathlib.Path, side: str) -> pathlib.Path | None:
    matches = sorted(path.parent.glob(path.name + f".{side}*"))
    return matches[0] if matches else None


def detect_text_encoding(data: bytes) -> str | None:
    if data.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    for encoding in ("utf-8", "gb18030", "gbk", "cp936"):
        try:
            data.decode(encoding)
            return encoding
        except UnicodeDecodeError:
            continue
    return None


def changed_line_hunks(base: list[str], other: list[str]) -> list[tuple[int, int, list[str]]]:
    matcher = difflib.SequenceMatcher(a=base, b=other, autojunk=False)
    hunks: list[tuple[int, int, list[str]]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        hunks.append((i1, i2, other[j1:j2]))
    return hunks


def merge_non_overlapping_hunks(
    base: list[str],
    target_hunks: list[tuple[int, int, list[str]]],
    source_hunks: list[tuple[int, int, list[str]]],
) -> list[str] | None:
    merged_hunks: list[tuple[int, int, list[str]]] = []
    for hunk in [*target_hunks, *source_hunks]:
        start, end, replacement = hunk
        overlapped = False
        for idx, (old_start, old_end, old_replacement) in enumerate(merged_hunks):
            same_insert_pos = start == end == old_start == old_end
            interval_overlap = start < old_end and old_start < end
            if same_insert_pos or interval_overlap:
                if start == old_start and end == old_end and replacement == old_replacement:
                    overlapped = True
                    break
                return None
        if not overlapped:
            merged_hunks.append(hunk)

    result: list[str] = []
    cursor = 0
    for start, end, replacement in sorted(merged_hunks, key=lambda item: (item[0], item[1])):
        if start < cursor:
            return None
        result.extend(base[cursor:start])
        result.extend(replacement)
        cursor = end
    result.extend(base[cursor:])
    return result


def normalize_python_coding_to_utf8(path: pathlib.Path, text: str) -> str:
    if path.suffix.lower() != ".py":
        return text
    try:
        detected_encoding, _ = tokenize.detect_encoding(
            iter(text.encode("utf-8").splitlines(keepends=True)).__next__
        )
    except (SyntaxError, UnicodeDecodeError):
        detected_encoding = None
    if not detected_encoding:
        return text

    lines = text.splitlines(keepends=True)
    for idx in range(min(2, len(lines))):
        match = PYTHON_CODING_TEXT_RE.match(lines[idx])
        if match:
            lines[idx] = (
                match.group("prefix")
                + "utf-8"
                + match.group("suffix")
            )
            return "".join(lines)
    return text


def auto_resolve_encoding_conflict_file(path_text: str) -> bool:
    path = pathlib.Path(path_text)
    if not path.exists() or not path.is_file():
        return False
    target_side = first_existing_conflict_side(path, "working")
    base_side = first_existing_conflict_side(path, "merge-left")
    source_side = first_existing_conflict_side(path, "merge-right")
    if not target_side or not base_side or not source_side:
        return False

    try:
        target_data = target_side.read_bytes()
        base_data = base_side.read_bytes()
        source_data = source_side.read_bytes()
    except OSError:
        return False

    target_encoding = detect_text_encoding(target_data)
    base_encoding = detect_text_encoding(base_data)
    source_encoding = detect_text_encoding(source_data)
    if not target_encoding or not base_encoding or not source_encoding:
        return False
    if target_encoding == source_encoding:
        return False

    try:
        target_text = target_data.decode(target_encoding)
        base_text = base_data.decode(base_encoding)
        source_text = source_data.decode(source_encoding)
    except UnicodeDecodeError:
        return False

    base_lines = base_text.splitlines(keepends=True)
    target_lines = target_text.splitlines(keepends=True)
    source_lines = source_text.splitlines(keepends=True)
    target_hunks = changed_line_hunks(base_lines, target_lines)
    source_hunks = changed_line_hunks(base_lines, source_lines)
    merged_lines = merge_non_overlapping_hunks(base_lines, target_hunks, source_hunks)
    if merged_lines is None:
        return False

    resolved_text = normalize_python_coding_to_utf8(path, "".join(merged_lines))
    resolved_data = resolved_text.encode("utf-8")

    path.write_bytes(resolved_data)
    run_svn(["resolve", "--accept", "working", str(path)])
    print(
        f"AUTO_RESOLVE_ENCODING_CONFLICT {path} "
        f"output_encoding=utf-8 target_encoding={target_encoding} source_encoding={source_encoding}"
    )
    return True


def resolve_encoding_conflicts(target_wc: str) -> bool:
    paths = conflicted_paths(target_wc)
    if not paths:
        return False
    resolved_any = False
    unresolved: list[str] = []
    for path in paths:
        try:
            prop_conflicts = conflicted_property_names(path)
        except SvnRebaseError:
            prop_conflicts = set()
        if prop_conflicts:
            unresolved.append(path)
            continue
        if auto_resolve_encoding_conflict_file(path):
            resolved_any = True
        else:
            unresolved.append(path)
    if unresolved:
        if resolved_any:
            print("AUTO_RESOLVE_ENCODING_CONFLICT_PARTIAL_UNRESOLVED " + ",".join(unresolved))
        return False
    return resolved_any


def infer_revert_targets_from_candidates(
    item: RevisionPlanItem,
    candidates: list[RevisionPlanItem],
) -> list[int]:
    item_tickets = extract_ticket_ids(item.msg)
    item_paths = summary_paths(item.summary)
    if not item_tickets or not item_paths:
        return []

    matches: list[int] = []
    for candidate in candidates:
        if candidate.rev >= item.rev:
            continue
        if candidate.author != item.author:
            continue
        if not (item_tickets & extract_ticket_ids(candidate.msg)):
            continue
        if not (item_paths & summary_paths(candidate.summary)):
            continue
        matches.append(candidate.rev)
    if len(matches) == 1:
        return matches
    return []


def svn_cat_url_at(url: str, rev: int | str) -> bytes:
    return run_svn_bytes(["cat", "-r", str(rev), url])


def source_child_url(source_url: str, path: str) -> str:
    return f"{source_url.rstrip('/')}/{path}"


def target_child_url(target_url: str, path: str) -> str:
    return f"{target_url.rstrip('/')}/{path}"


def is_neutralized_pair(
    source_url: str,
    target_url: str,
    original_rev: int,
    revert_rev: int,
    summaries: dict[int, list[str]],
) -> tuple[bool, str]:
    original_paths = m_file_paths(summaries.get(original_rev, []))
    revert_paths = m_file_paths(summaries.get(revert_rev, []))
    if not original_paths or not revert_paths:
        return False, "只自动跳过纯文件修改的回退对"
    if original_paths != revert_paths:
        return False, "原始提交和回退提交的文件集合不一致"

    for path in sorted(original_paths):
        try:
            before_original = svn_cat_url_at(source_child_url(source_url, path), original_rev - 1)
            after_revert = svn_cat_url_at(source_child_url(source_url, path), revert_rev)
            target_current = svn_cat_url_at(target_child_url(target_url, path), "HEAD")
        except SvnRebaseError as exc:
            return False, f"无法读取 {path} 的三方内容：{exc}"

        if before_original != after_revert:
            return False, f"{path} 在回退后不等于原始提交前"
        if target_current != before_original:
            return False, f"{path} 的目标当前内容不等于原始提交前"

    return True, "原始提交和回退提交在 test 内完全抵消，且目标当前未包含该改动"


def build_revision_plan(
    source_url: str,
    target_url: str,
    revisions: list[int],
    auto_skip_neutralized_reverts: bool,
) -> list[RevisionPlanItem]:
    revision_set = set(revisions)
    entries: dict[int, tuple[str, str]] = {
        rev: get_log_entry(source_url, rev)
        for rev in revisions
    }
    summaries = {
        rev: summarize_source_revision_group(source_url, [rev])
        for rev in revisions
    }
    plan = [
        RevisionPlanItem(
            rev=rev,
            author=entries[rev][0],
            msg=entries[rev][1],
            summary=summaries[rev],
            is_revert=is_revert_message(entries[rev][1]),
            revert_targets=parse_revert_targets(entries[rev][1]),
            classification="INCLUDE",
            reason="普通候选修订",
        )
        for rev in revisions
    ]
    by_rev = {item.rev: item for item in plan}

    for item in plan:
        trunk_merge_reason = merged_from_trunk_reason(item.msg)
        if trunk_merge_reason:
            item.classification = "SKIP"
            item.reason = trunk_merge_reason
            continue
        hold_reason = release_hold_reason(item.msg)
        if hold_reason:
            item.classification = "SKIP"
            item.reason = hold_reason
            continue
        if is_externals_only_revision(source_url, item.rev, item.summary):
            item.classification = "SKIP"
            item.reason = "纯 svn:externals 外链属性修改，周维护默认保留目标分支外链"
            continue
        if not item.is_revert:
            continue
        if not item.revert_targets:
            item.revert_targets = infer_revert_targets_from_candidates(item, plan)
        if not item.revert_targets:
            item.classification = "REVIEW"
            item.reason = "疑似回退/回滚提交，但日志中无法解析被回退修订"
            continue

        candidate_targets = [rev for rev in item.revert_targets if rev in revision_set and rev < item.rev]
        if not candidate_targets:
            item.classification = "REVIEW"
            item.reason = "疑似回退/回滚提交，但被回退修订不在本轮候选中"
            continue

        neutralized_targets: list[int] = []
        review_reasons: list[str] = []
        for target_rev in candidate_targets:
            ok, reason = is_neutralized_pair(
                source_url,
                target_url,
                target_rev,
                item.rev,
                summaries,
            )
            if ok:
                neutralized_targets.append(target_rev)
            else:
                review_reasons.append(f"r{target_rev}: {reason}")

        if neutralized_targets and auto_skip_neutralized_reverts:
            item.classification = "SKIP"
            item.reason = (
                "自动跳过回退提交；抵消 "
                + ",".join(f"r{rev}" for rev in neutralized_targets)
            )
            for target_rev in neutralized_targets:
                target_item = by_rev[target_rev]
                if target_item.classification == "INCLUDE":
                    target_item.classification = "SKIP"
                    target_item.reason = f"被 r{item.rev} 在 test 内完全抵消"
            continue

        item.classification = "REVIEW"
        if neutralized_targets:
            item.reason = (
                "识别到可抵消提交对，但未启用自动跳过："
                + ",".join(f"r{rev}" for rev in neutralized_targets)
            )
        else:
            item.reason = "疑似回退/回滚提交，需要人工确认；" + "；".join(review_reasons)

    return plan


def write_revision_plan_reports(
    plan: list[RevisionPlanItem],
    risk_report: str | None,
    plan_json: str | None,
) -> None:
    if risk_report:
        path = pathlib.Path(risk_report)
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = ["# Weekly Maintenance Revision Plan", ""]
        for classification in ("INCLUDE", "SKIP", "REVIEW"):
            lines.append(f"## {classification}")
            matched = [item for item in plan if item.classification == classification]
            if not matched:
                lines.append("")
                lines.append("(none)")
                lines.append("")
                continue
            for item in matched:
                first_line = first_log_line(item.msg)
                targets = ",".join(f"r{rev}" for rev in item.revert_targets) or "-"
                lines.append(
                    f"- r{item.rev} | author={item.author} | "
                    f"targets={targets} | reason={item.reason} | log={first_line}"
                )
            lines.append("")
        path.write_text("\n".join(lines), encoding="utf-8", newline="\n")

    if plan_json:
        path = pathlib.Path(plan_json)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = [
            {
                "rev": item.rev,
                "author": item.author,
                "first_line": first_log_line(item.msg),
                "summary": item.summary,
                "is_revert": item.is_revert,
                "revert_targets": item.revert_targets,
                "classification": item.classification,
                "reason": item.reason,
            }
            for item in plan
        ]
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
            newline="\n",
        )


def print_revision_plan(plan: list[RevisionPlanItem]) -> None:
    print("WEEKLY_PLAN_BEGIN")
    for classification in ("INCLUDE", "SKIP", "REVIEW"):
        print(f"{classification}_BEGIN")
        for item in plan:
            if item.classification != classification:
                continue
            first_line = first_log_line(item.msg)
            targets = ",".join(f"r{rev}" for rev in item.revert_targets) or "-"
            print(
                f"r{item.rev} | 作者={item.author} | "
                f"回退目标={targets} | 原因={item.reason} | 日志={first_line}"
            )
        print(f"{classification}_END")
    print("WEEKLY_PLAN_END")


def group_revisions_by_author_and_log(source_url: str, revisions: list[int]) -> list[RevisionGroup]:
    groups: list[RevisionGroup] = []
    current: RevisionGroup | None = None

    for rev in revisions:
        author, msg = get_log_entry(source_url, rev)
        if (
            current is not None
            and author == current.author
            and same_revision_group_log(msg, current.msg)
        ):
            current.revs.append(rev)
            continue

        current = RevisionGroup([rev], author, msg)
        groups.append(current)

    return groups


def verify_committed_log(target_url: str, commit_rev: int, expected_msg: str) -> None:
    _, actual_msg = get_log_entry(target_url, commit_rev)

    def normalize(text: str) -> str:
        return text.replace("\r\n", "\n").rstrip("\n")

    if normalize(actual_msg) != normalize(expected_msg):
        raise SvnRebaseError(
            f"提交日志校验失败：目标修订 r{commit_rev}\n"
            f"期望：\n{expected_msg}\n实际：\n{actual_msg}"
        )


def update_target(target_wc: str) -> None:
    print(run_svn(["update", "--ignore-externals", target_wc]), end="")


def iter_versioned_changed_paths(target_wc: str) -> list[pathlib.Path]:
    output = run_svn(["status", "--ignore-externals", target_wc])
    paths: list[pathlib.Path] = []
    for line in output.splitlines():
        if not line:
            continue
        if line[0] in "?XI":
            continue
        path = pathlib.Path(line[8:].strip())
        if path.exists() and path.is_file():
            paths.append(path)
    return paths


def precommit_sanity_check(target_wc: str) -> None:
    root = pathlib.Path(target_wc)
    conflict_temps: list[str] = []
    for pattern in ("*.merge-left.*", "*.merge-right.*", "*.working", "*.mine", "*.rej", "*.orig"):
        conflict_temps.extend(str(path) for path in root.rglob(pattern))
    if conflict_temps:
        raise SvnRebaseError(
            "提交前仍存在冲突临时文件：\n" + "\n".join(conflict_temps[:50])
        )

    conflict_markers: list[str] = []
    replacement_files: list[str] = []
    mixed_eol: list[str] = []
    bom_files: list[str] = []
    text_suffixes = {
        ".c",
        ".cc",
        ".cpp",
        ".h",
        ".hpp",
        ".py",
        ".lua",
        ".txt",
        ".md",
        ".cmake",
        ".xml",
        ".json",
        ".fbs",
    }
    for path in iter_versioned_changed_paths(target_wc):
        data = path.read_bytes()
        replacement_count = data.count(b"\xef\xbf\xbd")
        base_replacement_count = 0
        if replacement_count:
            try:
                base_data = run_svn_bytes(["cat", "-r", "BASE", str(path)])
                base_replacement_count = base_data.count(b"\xef\xbf\xbd")
            except SvnRebaseError:
                base_replacement_count = 0
        if replacement_count > base_replacement_count:
            replacement_files.append(str(path))
        elif replacement_count:
            print(
                f"PRECOMMIT_EXISTING_REPLACEMENT_BYTES {path} "
                f"count={replacement_count} base_count={base_replacement_count}"
            )
        if path.suffix.lower() in text_suffixes:
            if any(line.startswith((b"<<<<<<<", b"=======", b">>>>>>>")) for line in data.splitlines()):
                conflict_markers.append(str(path))
        if data.startswith(b"\xef\xbb\xbf"):
            bom_files.append(str(path))
        crlf = data.count(b"\r\n")
        lf_only = data.count(b"\n") - crlf
        if crlf and lf_only:
            mixed_eol.append(f"{path} CRLF={crlf} LF_ONLY={lf_only}")

    if conflict_markers:
        raise SvnRebaseError(
            "提交前仍存在冲突标记：\n" + "\n".join(conflict_markers)
        )
    if replacement_files:
        raise SvnRebaseError(
            "提交前仍存在新增的 UTF-8 replacement bytes：\n" + "\n".join(replacement_files)
        )
    if bom_files:
        print("PRECOMMIT_BOM_FILES_BEGIN")
        for item in bom_files:
            print(item)
        print("PRECOMMIT_BOM_FILES_END")
    if mixed_eol:
        print("PRECOMMIT_MIXED_EOL_BEGIN")
        for item in mixed_eol:
            print(item)
        print("PRECOMMIT_MIXED_EOL_END")


def replay_revision_group(
    source_url: str,
    target_wc: str,
    target_url: str,
    log_policy: LogPolicyOptions,
    group: RevisionGroup,
    preserve_log_through: int | None,
    preserve_log_revs: set[int],
    keep_author_domain: bool,
    weekly_maintenance: bool,
    infer_merge_history_author: bool,
    message_dir: str | None,
    auto_resolve_external_conflicts: bool,
    commit: bool,
) -> int | None:
    group_label = format_revision_group(group.revs)
    first_rev = group.revs[0]
    print(f"开始处理 {group_label}")

    merge_rev_args = build_revision_merge_args(group.revs)
    externals_before = snapshot_target_externals(target_wc) if auto_resolve_external_conflicts else {}
    dry_run_code, dry_run = run_svn_result(["merge", "--dry-run", *merge_rev_args, source_url, target_wc])
    print(dry_run, end="")
    dry_run_has_conflict = has_conflict_output(dry_run)
    if dry_run_code != 0 and not dry_run_has_conflict:
        raise SvnRebaseError(
            f"svn merge --dry-run {' '.join(merge_rev_args)} {source_url} {target_wc} "
            f"执行失败，退出码 {dry_run_code}\n{dry_run}"
        )
    if dry_run_has_conflict:
        if auto_resolve_external_conflicts and has_only_property_conflicts(dry_run):
            print(f"{group_label} 的 dry-run 仅检测到属性冲突，尝试自动保留目标分支 svn:externals")
        elif "Text conflicts:" in dry_run or re.search(r"(^|\r?\n)\s*C\s+", dry_run):
            print(
                f"DRY_RUN_ENCODING_CONFLICT_RECHECK {group_label} "
                "dry-run 检测到文本冲突，继续真实 merge 以尝试编码冲突自动解决"
            )
        elif len(group.revs) > 1:
            print(
                f"DRY_RUN_GROUP_CONFLICT_RECHECK {group_label} "
                "多修订组 dry-run 可能未模拟前置修订落地，继续用真实 merge 复核"
            )
        else:
            raise SvnRebaseError(f"{group_label} 的 dry-run 检测到冲突")

    merge_code, merge_output = run_svn_result(["merge", *merge_rev_args, source_url, target_wc])
    print(merge_output, end="")
    merge_has_conflict = has_conflict_output(merge_output)
    if merge_code != 0 and not merge_has_conflict:
        raise SvnRebaseError(
            f"svn merge {' '.join(merge_rev_args)} {source_url} {target_wc} "
            f"执行失败，退出码 {merge_code}\n{merge_output}"
        )
    if merge_has_conflict:
        if not (
            (
                auto_resolve_external_conflicts
                and has_only_property_conflicts(merge_output)
                and resolve_external_property_conflicts(target_wc, externals_before)
            )
            or resolve_encoding_conflicts(target_wc)
        ):
            raise SvnRebaseError(f"{group_label} 的真实合并检测到冲突")

    source_summary = summarize_source_revision_group(source_url, group.revs)
    target_summary = summarize_diff(target_wc, ["diff", "--summarize", target_wc])
    if source_summary != target_summary:
        raise SvnRebaseError(
            f"{group_label} 合并后的文件摘要与源修订不一致\n"
            f"源侧：\n" + "\n".join(source_summary) + "\n"
            f"目标侧：\n" + "\n".join(target_summary)
        )

    commit_msg = build_commit_message(
        source_url,
        group.msg,
        group.author,
        group.revs,
        preserve_log_through,
        preserve_log_revs,
        keep_author_domain,
        weekly_maintenance,
        infer_merge_history_author,
    )
    commit_msg = enforce_commit_log_policy(
        commit_msg,
        log_policy,
        revs=group.revs,
        source_url=source_url,
        group_label=group_label,
    )
    if message_dir:
        msg_root = pathlib.Path(message_dir)
        msg_root.mkdir(parents=True, exist_ok=True)
        msg_path = msg_root / f"svn-merge-message-{revision_group_file_stem(group.revs)}.txt"
        msg_path.write_text(commit_msg, encoding="utf-8", newline="")
        delete_msg_file = False
    else:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, newline="") as handle:
            msg_path = pathlib.Path(handle.name)
            handle.write(commit_msg)
        delete_msg_file = True

    try:
        print("COMMIT_MESSAGE_BEGIN")
        print(commit_msg, end="" if commit_msg.endswith("\n") else "\n")
        print("COMMIT_MESSAGE_END")
        print(f"提交消息文件 {msg_path}")
        precommit_sanity_check(target_wc)
        if not commit:
            print(f"MERGE_READY_FOR_REVIEW {group_label} 未提交")
            return None
        commit_output = run_svn(
            ["commit", "--encoding", "UTF-8", target_wc, "-F", str(msg_path)]
        )
        print(commit_output, end="")
    finally:
        if delete_msg_file:
            msg_path.unlink(missing_ok=True)

    match = re.search(r"Committed revision (\d+)\.", commit_output)
    if not match:
        raise SvnRebaseError(f"无法解析 {group_label} 对应的新提交修订号")
    commit_rev = int(match.group(1))
    verify_committed_log(target_url, commit_rev, commit_msg)
    print(f"提交日志校验通过：源 {group_label} -> 目标 r{commit_rev}")
    return commit_rev


def write_message(args: argparse.Namespace) -> int:
    if args.preserve_log_through is not None and not args.allow_preserve_log_through:
        raise SvnRebaseError(
            "--preserve-log-through 会原样保留源日志并绕过作者插入。"
            "明确例外请优先使用 --preserve-log-revs；只有确实需要原始源日志时，"
            "才添加 --allow-preserve-log-through。"
        )
    author, source_msg = get_log_entry(args.source_url, args.rev)
    message = build_commit_message(
        args.source_url,
        source_msg,
        author,
        [args.rev],
        args.preserve_log_through,
        parse_rev_list(args.preserve_log_revs),
        args.keep_author_domain,
        args.weekly_maintenance,
        args.infer_merge_history_author,
    )
    if args.out:
        pathlib.Path(args.out).write_text(message, encoding="utf-8", newline="")
    else:
        sys.stdout.write(message)
    return 0


def print_eligible(args: argparse.Namespace) -> int:
    revisions = get_eligible_revisions(
        args.source_url,
        args.target_wc,
        args.min_rev,
        args.max_rev,
        parse_rev_list(args.skip_revs),
        build_ignored_authors(args),
    )
    for rev in revisions:
        print(f"r{rev}")
    return 0


def replay(args: argparse.Namespace) -> int:
    if args.preserve_log_through is not None and not args.allow_preserve_log_through:
        raise SvnRebaseError(
            "--preserve-log-through 会原样保留源日志并绕过作者插入。"
            "明确例外请优先使用 --preserve-log-revs；只有确实需要原始源日志时，"
            "才添加 --allow-preserve-log-through。"
        )
    skip_revs = parse_rev_list(args.skip_revs)
    preserve_log_revs = parse_rev_list(args.preserve_log_revs)
    ignored_authors = build_ignored_authors(args)

    if args.eligible:
        revisions = get_eligible_revisions(
            args.source_url,
            args.target_wc,
            args.min_rev,
            args.max_rev,
            skip_revs,
            ignored_authors,
        )
    else:
        revisions = [int(rev[1:] if rev.startswith("r") else rev) for rev in args.revs]
        revisions = [rev for rev in revisions if rev not in skip_revs]
        revisions = filter_revisions_by_ignored_authors(args.source_url, revisions, ignored_authors)

    if not revisions:
        print("没有选择任何修订。")
        return 0

    if args.weekly_maintenance or args.classify_reverts:
        target_url = args.target_url or get_target_url(args.target_wc)
        auto_skip = (
            args.auto_skip_neutralized_reverts
            if args.auto_skip_neutralized_reverts is not None
            else args.weekly_maintenance
        )
        plan = build_revision_plan(
            args.source_url,
            target_url,
            revisions,
            auto_skip,
        )
        write_revision_plan_reports(plan, args.risk_report, args.plan_json)
        print_revision_plan(plan)

        review_items = [item for item in plan if item.classification == "REVIEW"]
        if review_items and not args.plan_only:
            details = "\n".join(
                f"r{item.rev}: {item.reason}"
                for item in review_items
            )
            raise SvnRebaseError(
                "周维护计划中存在 REVIEW 修订，不能自动真实合并。\n"
                "请人工确认后用 --skip-revs 绕过，或单独指定 --revs 处理。\n"
                + details
            )

        revisions = [
            item.rev
            for item in plan
            if item.classification == "INCLUDE"
        ]
        if not revisions:
            print("周维护分类后没有需要合入的 INCLUDE 修订。")
            return 0

    revision_groups = group_revisions_by_author_and_log(args.source_url, revisions)

    target_url = args.target_url or get_target_url(args.target_wc)
    log_policy = build_log_policy(args, target_url)
    print(
        f"TARGET_BRANCH_KIND {log_policy.target_kind} "
        f"formal={'yes' if log_policy.target_formal else 'no'} url={target_url}"
    )

    def group_commit_message(group: RevisionGroup) -> str:
        return build_commit_message(
            args.source_url,
            group.msg,
            group.author,
            group.revs,
            args.preserve_log_through,
            preserve_log_revs,
            args.keep_author_domain,
            args.weekly_maintenance,
            args.infer_merge_history_author,
        )

    projected_messages: dict[tuple[int, ...], str] = {}
    for group in revision_groups:
        projected_messages[tuple(group.revs)] = enforce_commit_log_policy(
            group_commit_message(group),
            log_policy,
            revs=group.revs,
            source_url=args.source_url,
            group_label=format_revision_group(group.revs),
            strict=not args.plan_only,
        )

    if args.plan_only:
        for group in revision_groups:
            first_line = first_log_line(group.msg)
            target_first_line = first_log_line(projected_messages[tuple(group.revs)])
            marker = "修订组" if len(group.revs) > 1 else "修订"
            print(
                f"{marker} {format_revision_group(group.revs)} | "
                f"作者={group.author} | 日志={first_line} | 目标日志首行={target_first_line}"
            )
        return 0

    if not args.commit and len(revision_groups) > 1:
        raise SvnRebaseError(
            "默认 replay 不提交，只支持一个修订组，避免未提交改动影响后续修订摘要校验。\n"
            "请拆分为单组 replay 并逐组检查，或在确认需要自动逐组提交时显式传 --commit。"
        )

    verify_clean_working_copy(args.target_wc)
    update_target(args.target_wc)
    auto_resolve_external_conflicts = (
        args.auto_resolve_external_conflicts
        if args.auto_resolve_external_conflicts is not None
        else args.weekly_maintenance
    )

    processed: list[str] = []
    for group in revision_groups:
        commit_rev = replay_revision_group(
            args.source_url,
            args.target_wc,
            target_url,
            log_policy,
            group,
            args.preserve_log_through,
            preserve_log_revs,
            args.keep_author_domain,
            args.weekly_maintenance,
            args.infer_merge_history_author,
            args.message_dir,
            auto_resolve_external_conflicts,
            args.commit,
        )
        if commit_rev is None:
            processed.append(f"OK {format_revision_group(group.revs)} -> 工作副本（未提交）")
        else:
            processed.append(f"OK {format_revision_group(group.revs)} -> r{commit_rev}")
            update_target(args.target_wc)

    print("PROCESS_SUMMARY_BEGIN")
    for line in processed:
        print(line)
    print("PROCESS_SUMMARY_END")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="逐个重放 SVN 修订，并保留 svn:mergeinfo。",
        add_help=False,
    )
    parser.add_argument("-h", "--help", action="help", help="显示帮助信息并退出。")
    subparsers = parser.add_subparsers(dest="command", required=True)

    eligible = subparsers.add_parser("eligible", help="列出 eligible 修订。", add_help=False)
    eligible.add_argument("-h", "--help", action="help", help="显示帮助信息并退出。")
    eligible.add_argument("--source-url", required=True)
    eligible.add_argument("--target-wc", required=True)
    eligible.add_argument("--min-rev", type=int)
    eligible.add_argument("--max-rev", type=int)
    eligible.add_argument("--skip-revs", default="")
    eligible.add_argument("--ignore-authors", default="")
    eligible.add_argument("--include-robot-commits", action="store_true")
    eligible.set_defaults(func=print_eligible)

    message = subparsers.add_parser("message", help="生成单个修订的提交消息。", add_help=False)
    message.add_argument("-h", "--help", action="help", help="显示帮助信息并退出。")
    message.add_argument("--source-url", required=True)
    message.add_argument("--rev", required=True, type=int)
    message.add_argument("--preserve-log-through", type=int)
    message.add_argument("--preserve-log-revs", default="")
    message.add_argument("--allow-preserve-log-through", action="store_true")
    message.add_argument("--keep-author-domain", action="store_true")
    message.add_argument("--weekly-maintenance", action="store_true")
    message.add_argument("--infer-merge-history-author", action="store_true")
    message.add_argument("--out")
    message.set_defaults(func=write_message)

    replay_cmd = subparsers.add_parser("replay", help="把修订重放到目标分支。", add_help=False)
    replay_cmd.add_argument("-h", "--help", action="help", help="显示帮助信息并退出。")
    replay_cmd.add_argument("--source-url", required=True)
    replay_cmd.add_argument("--target-wc", required=True)
    replay_cmd.add_argument("--target-url")
    replay_cmd.add_argument("--eligible", action="store_true")
    replay_cmd.add_argument("--revs", nargs="*", default=[])
    replay_cmd.add_argument("--min-rev", type=int)
    replay_cmd.add_argument("--max-rev", type=int)
    replay_cmd.add_argument("--skip-revs", default="")
    replay_cmd.add_argument("--ignore-authors", default="")
    replay_cmd.add_argument("--include-robot-commits", action="store_true")
    replay_cmd.add_argument("--preserve-log-through", type=int)
    replay_cmd.add_argument("--preserve-log-revs", default="")
    replay_cmd.add_argument("--allow-preserve-log-through", action="store_true")
    replay_cmd.add_argument("--keep-author-domain", action="store_true")
    replay_cmd.add_argument("--weekly-maintenance", action="store_true")
    replay_cmd.add_argument("--classify-reverts", action="store_true")
    replay_cmd.add_argument(
        "--auto-skip-neutralized-reverts",
        dest="auto_skip_neutralized_reverts",
        action="store_true",
        default=None,
    )
    replay_cmd.add_argument(
        "--no-auto-skip-neutralized-reverts",
        dest="auto_skip_neutralized_reverts",
        action="store_false",
    )
    replay_cmd.add_argument("--infer-merge-history-author", action="store_true")
    replay_cmd.add_argument(
        "--auto-resolve-external-conflicts",
        dest="auto_resolve_external_conflicts",
        action="store_true",
        default=None,
    )
    replay_cmd.add_argument(
        "--no-auto-resolve-external-conflicts",
        dest="auto_resolve_external_conflicts",
        action="store_false",
    )
    replay_cmd.add_argument("--message-dir")
    replay_cmd.add_argument(
        "--log-ticket",
        default=None,
        help="正式分支提交日志关联的单号，如 321998；填 热更 时生成 `#热更 描述`。",
    )
    replay_cmd.add_argument(
        "--log-keyword",
        dest="log_keyword",
        default=None,
        choices=list(FORMAL_LOG_KEYWORDS),
        help="正式分支提交日志关键词；缺省 refs，与 --log-ticket 同时使用时缺省 finish。",
    )
    replay_cmd.add_argument(
        "--log-text",
        default=None,
        help="正式分支提交日志的描述文本；缺省从源日志推导。",
    )
    replay_cmd.add_argument(
        "--log-extra",
        default=None,
        help="正式分支提交日志的附加内容，如 `merge from trunk r2685000`。",
    )
    replay_cmd.add_argument(
        "--commit",
        action="store_true",
        help="合并校验通过后提交；默认仅保留工作副本改动供人工检查。",
    )
    replay_cmd.add_argument("--risk-report")
    replay_cmd.add_argument("--plan-json")
    replay_cmd.add_argument("--plan-only", action="store_true")
    replay_cmd.set_defaults(func=replay)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except SvnRebaseError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
