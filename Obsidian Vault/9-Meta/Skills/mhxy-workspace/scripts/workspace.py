#!/usr/bin/env python3
"""Manage local workspace metadata.

Commands that change configuration or entry files preview unless --apply is set.
`context` and `index` update the spec index directly: membership is recorded by
the script (see plan_index), and index.md is always re-rendered, never hand-edited.
"""
import argparse
import codecs
from datetime import datetime
import getpass
import itertools
import json
import locale
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
from urllib.parse import unquote
from xml.etree import ElementTree

SKILL = Path(__file__).resolve().parents[1]
NAME = "mhxy-workspace"
LEGACY_NAME = "mhxy-workspace-init"
DIRECTORY = ".mhxy-workspace"
BEGIN = f"<!-- {NAME}:begin -->"
END = f"<!-- {NAME}:end -->"
# 必须由用户确认（路径或显式 null）的字段；其余字段可选，缺省视为未配置。
PATH_KEYS = ("pc_client_dir", "ht_client_dir", "engine_dir", "global_resources_dir", "design_config_dir")
SPEC_DIRECTORY = "spec"
INDEX_FILE = "index.md"
INDEX_STATE = "index-state.json"  # 索引收录名单与起点时间，随个人目录一起清理。
INDEX_HEADER = "<!-- 由 workspace.py 自动生成。"
# svn status 中视为“本地有改动”的条目状态；仅用于判断 spec 是否由本人新建或修改。
SVN_LOCAL_CHANGES = {"modified", "added", "unversioned", "replaced", "conflicted"}
# 受管入口文件；它们常受版本控制（AGENTS.md 是团队规范），带有本机路径，不应被提交。
ENTRY_FILES = ("AGENTS.md", "CLAUDE.md")
IGNORE_ON_COMMIT = "ignore-on-commit"  # TortoiseSVN 提交对话框默认不勾选此变更列表中的文件。
INDEX_RECENT_LIMIT = 20  # context 中列出的最近 spec 数量。
# 周期分支的类型、名称与 URL 规则，是唯一来源；references/svn-update.md「选择目标」只引用这里。
# branch.py 用 PERIODIC_NAME 校验检出名称，并按 PERIODIC_TYPES 在 PERIODIC_RESOURCES 中配置资源目录。
PERIODIC_TYPES = ("test", "shiwan", "release", "release2", "release3", "newbie", "sjf", "zlp")
_PERIODIC_NAME = rf"({'|'.join(PERIODIC_TYPES)})_(\d{{4}})_(\d{{2}})_(\d{{2}})"  # 分组：类型、年、月、日。
PERIODIC_NAME = re.compile(rf"^{_PERIODIC_NAME}$")
PERIODIC_BRANCH = re.compile(rf"/wzimage/branchs/\d{{4}}_ship/{_PERIODIC_NAME}/?$")
INDEX_SUMMARY_LIMIT = 60  # 索引中每篇 spec 摘要的最大字符数。
HOOK_FLAG = "--from-hook"  # 标识本 skill 写入 Claude Code 设置的 hooks（context 与 index）。
CODEX_JOBS = "codex-cli"  # codex_cli.py 在个人目录下的任务目录，每个任务一个子目录，含 state.json。
CODEX_ACTIVE = ("starting", "running")  # 仍在运行、清理会破坏其输出的任务状态。
HANDOFF = "handoff"  # 个人目录下的会话交接文件目录（见 references/session.md），新会话接手后删除。


class WorkspaceError(Exception):
    pass


def exists(path):
    return os.path.lexists(path)


def is_link(path):
    """判断路径本身是否为符号链接或 Windows 目录联接，不跟随目标。"""
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def no_links(path):
    """Reject links in the entire lexical path, including Windows junctions."""
    for part in (path, *path.parents):
        if exists(part) and is_link(part):
            raise WorkspaceError(f"拒绝符号链接或 reparse point：{part}")


def absolute(path):
    return Path(os.path.abspath(os.path.expanduser(str(path))))


def read_bytes(path):
    no_links(path)
    if not exists(path):
        return None
    if not path.is_file():
        raise WorkspaceError(f"应为普通文件：{path}")
    return path.read_bytes()


def parse_json(data, label):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"重复键 {key}")
            result[key] = value
        return result
    try:
        value = json.loads(data, object_pairs_hook=unique)
    except (ValueError, UnicodeError) as error:
        raise WorkspaceError(f"JSON 损坏：{label}：{error}") from error
    if not isinstance(value, dict):
        raise WorkspaceError(f"应为 JSON 对象：{label}")
    return value


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def decode_document(data):
    if data is None:
        return "", "utf-8", b"", "\n"
    bom = b""
    encoding = "utf-8"
    for marker, candidate in ((codecs.BOM_UTF8, "utf-8"),
                              (codecs.BOM_UTF16_LE, "utf-16-le"),
                              (codecs.BOM_UTF16_BE, "utf-16-be")):
        if data.startswith(marker):
            bom, encoding = marker, candidate
            break
    try:
        text = data[len(bom):].decode(encoding)
    except UnicodeDecodeError:
        if bom:
            raise WorkspaceError("文档编码损坏")
        encoding = "gb18030"
        try:
            text = data.decode(encoding)
        except UnicodeDecodeError as error:
            raise WorkspaceError("文档编码无法处理") from error
    if "\x00" in text:
        raise WorkspaceError("文档包含 NUL，拒绝作为文本覆盖")
    newline = "\r\n" if "\r\n" in text else "\n"
    return text, encoding, bom, newline


def release(value):
    if not isinstance(value, str) or not re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", value):
        raise WorkspaceError(f"无效发布版本：{value!r}")
    return tuple(map(int, value.split(".")))


def validate_metadata(meta, expected_name=NAME):
    if set(meta) != {"skill", "applied_version", "schema_version"} or meta.get("skill") != expected_name:
        raise WorkspaceError("管理元数据字段或 skill 标识错误")
    release(meta["applied_version"])
    if type(meta["schema_version"]) is not int or meta["schema_version"] not in (1, 2):
        raise WorkspaceError("不支持的结构版本")


def block_info(text):
    names = [name for name in (NAME, LEGACY_NAME) if f"<!-- {name}:" in text]
    if len(names) > 1:
        raise WorkspaceError("新旧受管区段同时存在，请先解决冲突")
    block_name = names[0] if names else NAME
    begin = f"<!-- {block_name}:begin -->"
    ending = f"<!-- {block_name}:end -->"
    if not text.count(begin) and not text.count(ending):
        if f"<!-- {block_name}:" in text:
            raise WorkspaceError("发现异常受管标记")
        return None
    if text.count(begin) != 1 or text.count(ending) != 1 or text.count(f"<!-- {block_name}:") != 2:
        raise WorkspaceError("受管区段重复或标记不完整")
    start, end = text.index(begin), text.index(ending)
    if end < start or (start and text[start - 1] != "\n") or (end and text[end - 1] != "\n"):
        raise WorkspaceError("受管标记顺序或位置异常")
    after_start = start + len(begin)
    if after_start < len(text) and text[after_start] not in "\r\n":
        raise WorkspaceError("开始标记必须独占一行")
    finish = end + len(ending)
    if finish < len(text) and text[finish] not in "\r\n":
        raise WorkspaceError("结束标记必须独占一行")
    matches = re.findall(r"### 管理元数据\s*\r?\n```json\r?\n(.*?)\r?\n```", text[start:finish], re.S)
    if len(matches) != 1:
        raise WorkspaceError("受管区段缺少唯一 JSON 元数据")
    meta = parse_json(matches[0], "管理元数据")
    validate_metadata(meta, block_name)
    return start, finish, meta


METADATA_SECTION = re.compile(r"### 管理元数据\s*\r?\n```json\r?\n.*?\r?\n```", re.S)


def rule_body(block):
    """去掉管理元数据并统一换行，用于判断受管区段的规则内容是否变化（版本号变化不算）。"""
    return METADATA_SECTION.sub("", block.replace("\r\n", "\n"))


def validate_config(config, keys, label):
    if set(config) - set(keys):
        raise WorkspaceError(f"未知配置键：{label}：{sorted(set(config) - set(keys))}")
    for key, value in config.items():
        if key in {"openid_username", "openid_password"}:
            if value is not None and (not isinstance(value, str) or not value or any(c in value for c in "\r\n\x00")):
                raise WorkspaceError(f"{label} 的 {key} 必须是非空字符串或 null")
            if key == "openid_username" and value is not None and not re.fullmatch(r"[A-Za-z0-9_.-]+@corp\.netease\.com", value):
                raise WorkspaceError("openid_username 必须是 CORP 邮箱")
            continue
        if key == "coder_name":
            if value is not None and (not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", value)):
                raise WorkspaceError(f"{label} 的 coder_name 必须是邮箱前缀或 null")
            continue
        if key == "default_devid":
            if value is not None and (not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_]+", value)):
                raise WorkspaceError(f"{label} 的 default_devid 必须是设备 ID 或 null")
            continue
        if value is not None and (not isinstance(value, str) or not value or
                                  not Path(value).is_absolute() or any(c in value for c in "\r\n\x00")):
            raise WorkspaceError(f"{label} 的 {key} 必须是绝对路径或 null")


def paths(root_arg, global_arg):
    root = absolute(root_arg)
    no_links(root)
    if not root.is_dir():
        raise WorkspaceError(f"工作区不存在：{root}")
    root = root.resolve()  # Normalize Windows short names before boundary comparisons.
    personal = root / DIRECTORY
    no_links(personal)
    if exists(personal) and not personal.is_dir():
        raise WorkspaceError(f"个人目录不是目录：{personal}")
    global_config = absolute(global_arg)
    no_links(global_config)
    global_config = global_config.resolve()
    # Never allow the managed directory to contain the home-level configuration,
    # even when a testing override points elsewhere.
    for protected in (global_config, absolute(Path.home() / DIRECTORY / "config.json").resolve()):
        if protected == personal or personal in protected.parents:
            raise WorkspaceError("个人目录与用户级配置重叠")
    return root, personal, global_config


def ensure_writable(path):
    """拒绝只读的目标文件（svn:needs-lock 未加锁或被手动设为只读），不自行去掉只读属性。"""
    if exists(path) and not path.stat().st_mode & stat.S_IWRITE:
        raise WorkspaceError(f"目标文件只读（可能是 svn:needs-lock 未加锁或被手动设为只读），"
                             f"请先确认并解除只读后重试：{path}")


def atomic_write(path, data):
    no_links(path)
    ensure_writable(path)
    descriptor, name = tempfile.mkstemp(prefix=".mhxy-write-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if exists(path):
            # 目标已确认可写，复制权限位不会让临时文件变成只读。
            os.chmod(temporary, stat.S_IMODE(path.stat().st_mode))
        os.replace(temporary, path)
    except BaseException:
        # 清理失败不能掩盖原始错误；临时文件可能被设成只读，先恢复可写再删除。
        try:
            if exists(temporary):
                os.chmod(temporary, stat.S_IREAD | stat.S_IWRITE)
                temporary.unlink()
        except OSError:
            pass
        raise


def apply_changes(changes):
    """Each change is (path, original bytes or None, desired bytes)."""
    completed, created_dirs = [], []
    try:
        for path, old, new in changes:
            if read_bytes(path) != old:
                raise WorkspaceError(f"检测到并发修改：{path}")
            ensure_writable(path)  # 写入任何文件之前先发现只读目标。
        for path, old, new in changes:
            missing = []
            parent = path.parent
            while not exists(parent):
                missing.append(parent)
                parent = parent.parent
            for directory in reversed(missing):
                no_links(directory)
                directory.mkdir()
                created_dirs.append(directory)
            if read_bytes(path) != old:
                raise WorkspaceError(f"检测到并发修改：{path}")
            atomic_write(path, new)
            completed.append((path, old, new))
    except Exception as error:
        failures = []
        for path, old, new in reversed(completed):
            try:
                if read_bytes(path) != new:
                    raise WorkspaceError("回滚前检测到并发修改")
                if old is None:
                    path.unlink()
                else:
                    atomic_write(path, old)
            except Exception as rollback_error:
                failures.append(f"{path}: {rollback_error}")
        for directory in reversed(created_dirs):
            try:
                directory.rmdir()
            except OSError:
                pass
        detail = "; 回滚失败：" + "; ".join(failures) if failures else "; 本轮文件变更已恢复"
        raise WorkspaceError(f"更新失败：{error}{detail}") from error


def apply_settings(values, assignments, option):
    result = dict(values)
    for assignment in assignments:
        key, separator, value = assignment.partition("=")
        if not separator:
            raise WorkspaceError(f"{option} 应为 键=值 或 键=null")
        if key == "openid_password" and value != "null":
            raise WorkspaceError("密码通过 config --prompt-password 隐藏输入，不放在命令行参数中")
        if key == "openid_username" and result.get(key) != (None if value == "null" else value):
            result.pop("openid_password", None)  # An old password must not follow an account change.
        result[key] = None if value == "null" else value
    return result


def effective_values(global_values, local):
    """Merge non-secret overrides and derive the coder without duplicating state."""
    if set(local) & {"openid_username", "openid_password"}:
        raise WorkspaceError("OpenID 账密仅允许存放在用户级配置")
    values = {**global_values, **local}
    if not values.get("coder_name") and values.get("openid_username"):
        values["coder_name"] = values["openid_username"].split("@", 1)[0]
    return values


def masked_config(values):
    """Return a display-only configuration; never disclose the saved password."""
    return {key: ("***" if value is not None else None) if key == "openid_password" else value
            for key, value in values.items()}


def load_config(root_arg, global_arg):
    """Read effective settings without creating workspace files; internal use only."""
    root, personal, global_path = paths(root_arg, global_arg)
    defaults = parse_json((SKILL / "config/defaults.json").read_bytes(), "配置模板")
    values = []
    for path in (global_path, personal / "config.json"):
        data = read_bytes(path)
        value = parse_json(data, path) if data is not None else {}
        validate_config(value, defaults, path)
        values.append(value)
    return effective_values({**defaults, **values[0]}, values[1])


def configure_global(global_arg, assignments=(), password=None, apply=False):
    """Update only the user configuration, preserving unrelated settings."""
    path = absolute(global_arg)
    old = read_bytes(path)
    values = parse_json(old, path) if old is not None else {}
    values = apply_settings(values, assignments, "--set-global")
    if password is not None:
        values["openid_password"] = password
    defaults = parse_json((SKILL / "config/defaults.json").read_bytes(), "配置模板")
    validate_config(values, defaults, path)
    new = json_bytes(values)
    changes = [(path, old, new)] if old != new else []
    if apply:
        apply_changes(changes)
    return {"action": "config", "applied": apply, "changes": [str(item[0]) for item in changes],
            "effective_config": masked_config(effective_values({**defaults, **values}, {}))}


def sync(root_arg, global_arg, assignments=(), apply=False, skill=SKILL, local_assignments=()):
    root, personal, global_config = paths(root_arg, global_arg)
    metadata = parse_json((skill / "config/version.json").read_bytes(), "发布版本")
    validate_metadata(metadata)
    if metadata["schema_version"] != 2:
        raise WorkspaceError("当前模板要求结构版本 2")
    defaults = parse_json((skill / "config/defaults.json").read_bytes(), "配置模板")
    changes, warnings = [], []

    def propose(path, old, new):
        if old != new:
            changes.append((path, old, new))

    original_global = read_bytes(global_config)
    global_values = parse_json(original_global, global_config) if original_global is not None else {}
    global_values = apply_settings(global_values, assignments, "--set-global")
    validate_config(global_values, defaults, global_config)
    local_path = personal / "config.json"
    original_local = read_bytes(local_path)
    local = parse_json(original_local, local_path) if original_local is not None else {}
    local = apply_settings(local, local_assignments, "--set-local")
    validate_config(local, defaults, local_path)
    missing = sorted(set(PATH_KEYS) - set(global_values))
    effective = effective_values({**defaults, **global_values}, local)
    for key, value in effective.items():
        if key in PATH_KEYS and value is not None and not Path(value).is_dir():
            warnings.append(f"{key} 目录当前不可用，保留原值：{value}")
    if original_global is None or assignments:
        if original_global is None or parse_json(original_global, global_config) != global_values:
            propose(global_config, original_global, json_bytes(global_values))
    if original_local is None or (local_assignments and parse_json(original_local, local_path) != local):
        propose(local_path, original_local, json_bytes(local))

    # AGENTS.md 承载完整规则（Codex 读取）；CLAUDE.md 只放元数据和 @AGENTS.md 导入
    # （Claude Code 读取），规则保持唯一来源。CLAUDE.md 区段完全由 AGENTS.md 派生，
    # 因此不再要求两者元数据一致，只保留拒绝降级；旧版写入的完整区段在此被替换。
    documents = []
    for filename, template_name in zip(ENTRY_FILES, ("managed-block.md", "claude-block.md")):
        path = root / filename
        old = read_bytes(path)
        text, encoding, bom, newline = decode_document(old)
        info = block_info(text)
        if info and release(info[2]["applied_version"]) > release(metadata["applied_version"]):
            raise WorkspaceError(f"拒绝降级：{path}")
        if old is not None and encoding != "utf-8":
            warnings.append(f"{filename} 的编码是 {encoding.upper()}，Codex 和 Claude Code 按 UTF-8 读取，"
                            "可能读不到或读错规则；sync 保留原编码，建议用户自行转换为 UTF-8")
        documents.append((path, old, text, encoding, bom, newline, info, template_name))

    variables = {
        "metadata": json.dumps(metadata, ensure_ascii=False, indent=2),
        "references_dir": (skill.resolve() / "references").as_posix(),
        "workspace_script": (skill.resolve() / "scripts/workspace.py").as_posix(),
    }
    entry_changed = False
    for path, old, text, encoding, bom, newline, info, template_name in documents:
        template = (skill / "assets" / template_name).read_text(encoding="utf-8").rstrip("\n")
        block = re.sub(r"\{\{(\w+)\}\}", lambda match: variables[match[1]], template)
        rendered = block.replace("\n", newline)
        if path.name == ENTRY_FILES[0]:
            entry_changed = not info or rule_body(text[info[0]:info[1]]) != rule_body(rendered)
        if info:
            new_text = text[:info[0]] + rendered + text[info[1]:]
        else:
            separator = "" if not text else (newline if text.endswith("\n") else newline * 2)
            new_text = text + separator + rendered + newline
        propose(path, old, bom + new_text.encode(encoding))
    for change in plan_index(root, personal)[0]:
        propose(*change)
    hook = claude_hook_change(root, skill.resolve() / "scripts/workspace.py")
    if hook:
        propose(*hook)
    if apply and missing:
        raise WorkspaceError(f"用户级配置缺少已确认字段：{', '.join(missing)}；未使用项可显式设置 null")
    changelist = []
    if apply:
        apply_changes(changes)
        # 文件写入后再判断：首次创建的入口文件未纳入版本控制，不需要处理。
        changelist, changelist_warnings = plan_ignore_on_commit(root)
        changelist_warnings += apply_ignore_on_commit(root, changelist)
    else:
        changelist, changelist_warnings = plan_ignore_on_commit(root)
    warnings += changelist_warnings
    # 当前会话里已加载的是旧入口规则；明确提示，避免 agent 凭印象认为规则没变。
    # 只比较去掉管理元数据后的规则内容，单纯的版本号变化不提示。
    notice = ("入口规则（AGENTS.md 受管区段）有变化：" + ("应用后" if not apply else "")
              + "请重新读取该区段，并向用户说明新增或变化的规则；当前会话已加载的是旧版本。") if entry_changed else ""
    return {"action": "sync", "applied": apply, "root": str(root),
            "changes": [str(item[0]) for item in changes], "missing_fields": missing,
            "entry_rules_changed": entry_changed, "notice": notice,
            "ignore_on_commit": changelist,
            "optional_fields_to_confirm": sorted({"openid_username", "openid_password"} - set(global_values)) if original_global is None else [],
            "effective_config": masked_config(effective), "warnings": warnings}


def spec_summary(path):
    """提取一篇 spec 的标题（首个标题行）和摘要（首个正文行）。

    跳过开头的 YAML front matter、代码块、表格、分隔线和 HTML 注释；去掉列表符号和
    粗体／行内代码标记。无法按 UTF-8／UTF-16／GB18030 解码时以文件名为标题。
    """
    try:
        text = decode_document(path.read_bytes())[0]
    except (WorkspaceError, OSError):
        return path.stem, "（无法识别编码）"
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":  # front matter
        closing = next((i for i, line in enumerate(lines[1:], 1) if line.strip() == "---"), None)
        lines = lines[closing + 1:] if closing else lines
    title, summary, fenced = None, "", False
    for raw in lines:
        line = raw.strip()
        if line.startswith(("```", "~~~")):
            fenced = not fenced
            continue
        if fenced or not line or line.startswith(("|", "<!--", "---", "***", "===")) or "-*- coding" in line:
            continue
        heading = re.fullmatch(r"#{1,6}\s+(.*?)\s*#*", line)
        if heading:
            title = title or heading[1]
            continue
        summary = re.sub(r"^(?:[-*+>]\s+|\d+[.)]\s+)", "", line).replace("**", "").replace("`", "").strip()
        if summary:
            break
    if len(summary) > INDEX_SUMMARY_LIMIT:
        summary = summary[:INDEX_SUMMARY_LIMIT] + "…"
    return title or path.stem, summary


def spec_relative(root, value):
    """把用户、hook 或 svn 给出的路径规范为 `spec/...md`；不是 spec/ 下的 Markdown 时返回 None。

    Windows 下按不区分大小写比较根目录，跳过隐藏路径段。
    """
    path = Path(os.path.realpath(root / Path(value)))  # 也还原 Windows 上的实际大小写
    try:
        rel = Path(os.path.relpath(path, root))
    except ValueError:  # 不同盘符
        return None
    parts = rel.parts
    if (len(parts) < 2 or parts[0].lower() != SPEC_DIRECTORY
            or not rel.name.lower().endswith(".md") or any(part.startswith(".") for part in parts[1:])):
        return None
    return "/".join((SPEC_DIRECTORY, *parts[1:]))


def spec_files(path):
    """返回 path（文件或目录）下的 Markdown 文件；不跟随链接，跳过隐藏项，不存在时为空。"""
    if not exists(path) or is_link(path):
        return []
    if path.is_file():
        return [path]
    found = []
    for directory, dirnames, filenames in os.walk(path):
        base = Path(directory)
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and not is_link(base / d)]
        found += [base / name for name in filenames
                  if not name.startswith(".") and name.lower().endswith(".md") and not is_link(base / name)]
    return found


def decode_output(data):
    """解码 svn 的非 XML 输出：先按 UTF-8 严格解码，失败再按系统区域编码（中文 Windows 为 GBK）。

    UTF-8 字节恰好也是合法 GBK 的情况很常见，反之很少，因此先试 UTF-8。
    """
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode(locale.getpreferredencoding(False) or "utf-8", "replace")


def svn_merge_pending(root, tree):
    """判断工作副本是否有未提交的 svn:mergeinfo 变更（svn merge 之后、提交之前）。

    检查项目根目录，以及 spec 状态中属性有改动的条目；只读。查询失败时视为没有。
    """
    targets = ["."]
    for entry in tree.iter("entry"):
        status = entry.find("wc-status")
        if entry.get("path") and status is not None and status.get("props") == "modified":
            targets.append(entry.get("path"))
    try:
        completed = subprocess.run(["svn", "diff", "--properties-only", "--depth", "empty", "--non-interactive",
                                    *targets], cwd=root, capture_output=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return False
    return not completed.returncode and b"svn:mergeinfo" in completed.stdout


def svn_local_changes(root):
    """返回 (状态, spec/ 下本地有改动的 Markdown 相对路径集合)。

    本地有改动指修改、新增、未纳入版本控制等；未纳入版本控制的目录展开为其中的文件。
    状态为 `ok`；svn 不可用、不是工作副本或超时时为 `unavailable`；有未提交的合并
    （svn:mergeinfo 有改动）时为 `merge_pending`，此时合并进来的他人 spec 也显示为本地
    改动，无法区分，集合为空。后两种情况调用方跳过这一收录来源，不视为错误。只读。
    """
    if not (root / SPEC_DIRECTORY).is_dir():
        return "ok", set()
    try:
        completed = subprocess.run(["svn", "status", "--xml", "--non-interactive", SPEC_DIRECTORY],
                                   cwd=root, capture_output=True, timeout=20)
        if completed.returncode or b"155007" in completed.stderr:  # 非工作副本时只有警告、退出码为 0
            return "unavailable", set()
        tree = ElementTree.fromstring(completed.stdout)
    except (OSError, subprocess.SubprocessError, ElementTree.ParseError):
        return "unavailable", set()
    if svn_merge_pending(root, tree):
        return "merge_pending", set()
    changed = set()
    for entry in tree.iter("entry"):
        status = entry.find("wc-status")
        if not entry.get("path") or status is None or status.get("item") not in SVN_LOCAL_CHANGES:
            continue
        for path in spec_files(root / entry.get("path")):
            rel = spec_relative(root, path)
            if rel:
                changed.add(rel)
    return "ok", changed


def classify_branch(url):
    """按仓库 URL 判断分支类型：`trunk`、`周期分支` 或 `研发分支`。"""
    if PERIODIC_BRANCH.search(url):
        return "周期分支"
    if re.search(r"/wzimage/trunk/?$", url):
        return "trunk"
    return "研发分支"


def branch_path(url):
    """返回仓库相对路径（URL 中 `wzimage/` 之后的部分，如 `branchs/2026_dev/x`、`trunk`）。

    覆盖率网站和 coverage-task 登记都用这个格式；无法识别时返回 None。
    """
    match = re.search(r"/wzimage/(.+?)/?$", url)
    # svn info 返回的 URL 是 URI 编码的，网站和日志里的路径是解码后的
    return unquote(match.group(1)) if match else None


def svn_branch(root):
    """只读读取工作副本的仓库 URL 并分类；svn 不可用或不是工作副本时返回 None。

    每次现场读取、不落盘，因此不受个人目录清理影响。`path` 见 branch_path。
    """
    try:
        completed = subprocess.run(["svn", "info", "--show-item", "url", "--non-interactive", "."],
                                   cwd=root, capture_output=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    url = decode_output(completed.stdout).strip()
    if completed.returncode or not url:
        return None
    return {"url": url, "name": unquote(url.rstrip("/").rsplit("/", 1)[-1]), "path": branch_path(url),
            "kind": classify_branch(url)}


def svn_changelist(root, name):
    """只读查询文件所在的 SVN 变更列表。

    Returns:
        变更列表名；不在任何列表中时为空字符串；未纳入版本控制（含目录不是工作副本）时为 None。

    Raises:
        WorkspaceError: svn 不可用或其他查询失败。
    """
    try:
        completed = subprocess.run(["svn", "info", "--show-item", "changelist", "--non-interactive", name],
                                   cwd=root, capture_output=True, timeout=20)
    except (OSError, subprocess.SubprocessError) as error:
        raise WorkspaceError(f"svn 不可用：{error}") from None
    if completed.returncode:
        if b"W155010" in completed.stderr or b"E155007" in completed.stderr:  # 未纳入版本控制／不是工作副本
            return None
        raise WorkspaceError(decode_output(completed.stderr).strip() or "svn info 失败")
    return decode_output(completed.stdout).strip()


def plan_ignore_on_commit(root):
    """找出需要放入 ignore-on-commit 变更列表的入口文件，并给出无法处理的原因。

    只处理受版本控制的 ENTRY_FILES：已在该列表中的跳过；在用户自己的其他变更列表中的
    不移动，只给出警告。svn 不可用时整体跳过并给出警告。

    Returns:
        (待加入的文件名列表, 警告列表)。
    """
    pending, warnings = [], []
    for name in ENTRY_FILES:
        if not exists(root / name):
            continue
        try:
            current = svn_changelist(root, name)
        except WorkspaceError as error:
            return [], [f"未能把入口文件加入 {IGNORE_ON_COMMIT}：{error}"]
        if current == "":
            pending.append(name)
        elif current not in (None, IGNORE_ON_COMMIT):
            warnings.append(f"{name} 已在变更列表 {current} 中，未移入 {IGNORE_ON_COMMIT}")
    return pending, warnings


def apply_ignore_on_commit(root, names):
    """把文件加入 ignore-on-commit 变更列表（只改本地工作副本元数据，不影响服务器）。

    Returns:
        警告列表；失败不抛出，因为配置文件此时已经写入。
    """
    if not names:
        return []
    try:
        completed = subprocess.run(["svn", "changelist", IGNORE_ON_COMMIT, "--non-interactive", *names],
                                   cwd=root, capture_output=True, timeout=20)
    except (OSError, subprocess.SubprocessError) as error:
        return [f"未能把 {', '.join(names)} 加入 {IGNORE_ON_COMMIT}：{error}"]
    if completed.returncode:
        detail = decode_output(completed.stderr).strip()
        return [f"未能把 {', '.join(names)} 加入 {IGNORE_ON_COMMIT}：{detail}"]
    return []


def read_index_state(personal):
    """读取索引收录状态；缺失时以当前时间为起点新建，名单为空。

    从 0.2.x 升级时，旧版手写索引里登记过的 spec 路径会迁入名单，避免丢失。

    Returns:
        (状态文件路径, 原始字节或 None, 状态)。状态含 since（带时区的 ISO 时间）、
        specs（收录名单）和 excluded（用户移出、不再自动收录的名单），路径都相对项目根。
        0.3.18 及之前写入的状态没有 excluded，按空名单读取。

    Raises:
        WorkspaceError: 状态文件损坏。
    """
    path = personal / INDEX_STATE
    old = read_bytes(path)
    if old is not None:
        state = parse_json(old, path)
        state.setdefault("excluded", [])
        if (set(state) != {"since", "specs", "excluded"}
                or not all(isinstance(state[key], list) and all(isinstance(item, str) for item in state[key])
                           for key in ("specs", "excluded"))):
            raise WorkspaceError(f"索引状态结构无效：{path}")
        try:
            datetime.fromisoformat(state["since"]).timestamp()
        except (TypeError, ValueError):
            raise WorkspaceError(f"索引状态起点时间无效：{path}") from None
        return path, old, state
    specs = []
    legacy = read_bytes(personal / INDEX_FILE)
    if legacy is not None:
        text = decode_document(legacy)[0]
        if not text.startswith(INDEX_HEADER):
            specs = re.findall(r"^\s*-\s*(spec/.+?\.md)\s*[：:]", text, re.M)
    return path, None, {"since": datetime.now().astimezone().isoformat(timespec="seconds"),
                        "specs": specs, "excluded": []}


def render_index(since, entries):
    """把收录条目渲染为索引 Markdown；同样的名单和 spec 内容总是得到相同字节。"""
    lines = [INDEX_HEADER + "收录名单见 index-state.json；手工修改本文件会被覆盖。 -->",
             f"收录 {since} 之后新建或修改的 spec，共 {len(entries)} 篇。按组名（spec/ 一级子目录）、标题或摘要搜索定位。", ""]
    for group, items in itertools.groupby(entries, key=lambda entry: entry[0]):
        items = list(items)
        lines.append(f"# {group or 'spec 根目录'}（{len(items)}）")
        lines.extend(f"- {path}：{title}" + (f" — {summary}" if summary else "") for _, path, title, summary in items)
        lines.append("")
    return "\n".join(lines).encode("utf-8")


def mtime(path):
    """返回文件修改时间；文件已不存在（例如刚被删除或改名）时返回 None。"""
    try:
        return path.stat().st_mtime
    except FileNotFoundError:
        return None


def plan_index(root, personal, add=(), remove=(), scan=True, written=()):
    """计算新的收录名单与索引内容，只返回变更，不写入。

    名单只增不减。新增来源：
    - add：用户手动收录，不受起点限制，同时从排除名单中去掉；
    - written：hook 报告刚写入的 spec，不受起点限制；
    - scan 时“起点之后修改、且 svn 显示本地有改动”的 spec。svn update 拉下的他人 spec
      在本地无改动，因此不会被收录；有未提交的合并时跳过这一来源（见 svn_local_changes）。
    remove 中的条目移出名单并记入排除名单，written 和 scan 不会再收录它们。文件已不存在的
    条目从两个名单中移出。

    Returns:
        (changes, stats, entries)。changes 可交给 apply_changes；entries 为按组排序的
        [(组名, 路径, 标题, 摘要)]。
    """
    state_path, old_state, state = read_index_state(personal)
    since = datetime.fromisoformat(state["since"]).timestamp()
    excluded = (set(state["excluded"]) | set(remove)) - set(add)
    members = set(state["specs"]) | set(add) | (set(written) - excluded)
    svn = "skipped"
    if scan:
        svn, changed = svn_local_changes(root)
        members |= {rel for rel in changed - excluded if (mtime(root / rel) or 0) > since}

    def present(rel):
        return (root / rel).is_file() and not is_link(root / rel)
    members = sorted(rel for rel in members - excluded if present(rel))
    excluded = sorted(rel for rel in excluded if present(rel))
    entries = sorted((Path(rel).parts[1] if len(Path(rel).parts) > 2 else "", rel, *spec_summary(root / rel))
                     for rel in members)
    index_path = personal / INDEX_FILE
    new_state = {"since": state["since"], "specs": members, "excluded": excluded}
    candidates = ((state_path, old_state, json_bytes(new_state)),
                  (index_path, read_bytes(index_path), render_index(state["since"], entries)))
    changes = [change for change in candidates if change[1] != change[2]]
    stats = {"path": f"{DIRECTORY}/{INDEX_FILE}", "specs": len(members), "since": state["since"], "svn": svn}
    return changes, stats, entries


def refresh_index(root, personal, add=(), remove=(), scan=True, written=()):
    """按 plan_index 更新收录名单和索引，无变化不写入；返回 (统计信息, entries)。"""
    changes, stats, entries = plan_index(root, personal, add, remove, scan, written)
    apply_changes(changes)
    return {**stats, "updated": bool(changes)}, entries


def require_initialized(root):
    """只有 sync 能初始化工作区；其他会写个人目录的命令要求根目录 AGENTS.md 已有受管区段。

    防止从子目录传 `--root "."` 时在错误的位置新建 `.mhxy-workspace/`。

    Raises:
        WorkspaceError: AGENTS.md 不存在、无法解码或没有受管区段。
    """
    if block_info(decode_document(read_bytes(root / ENTRY_FILES[0]))[0]) is None:
        raise WorkspaceError(f"{root} 不是已初始化的工作区（AGENTS.md 中没有 {NAME} 受管区段）；"
                             "请把 --root 指向项目根目录，或先按 SKILL.md 初始化")


def query_index(root_arg, global_arg, terms=(), add=(), remove=(), limit=50):
    """刷新索引，可同时手动收录或移出 spec，再按关键词（全部命中、不区分大小写）匹配。

    Raises:
        WorkspaceError: 工作区未初始化；add／remove 的路径不是 spec/ 下的 Markdown，
            或要收录的文件不存在。
    """
    root, personal, _ = paths(root_arg, global_arg)
    require_initialized(root)
    normalized = {}
    for label, values in (("add", add), ("remove", remove)):
        normalized[label] = []
        for value in values:
            rel = spec_relative(root, value)
            if rel is None or (label == "add" and not (root / rel).is_file()):
                raise WorkspaceError(f"不是已存在的 spec/ 下 Markdown 文件：{value}")
            normalized[label].append(rel)
    stats, entries = refresh_index(root, personal, normalized["add"], normalized["remove"])
    needles = [term.lower() for term in terms if term.strip()]
    matches = [f"{path}：{title}" + (f" — {summary}" if summary else "")
               for group, path, title, summary in entries
               if all(n in f"{group} {path} {title} {summary}".lower() for n in needles)]
    return {"index": stats, "matches": matches[:limit], "truncated": len(matches) > limit}


def record_hook_write(root_arg, global_arg, payload):
    """Claude Code PostToolUse hook：工具刚写入 spec/ 下的 Markdown 时收录该文件。

    其他文件直接忽略；用户移出过的 spec 不再收录。只更新名单和索引，不运行 svn。
    """
    tool_input = payload.get("tool_input") if isinstance(payload, dict) else None
    file_path = tool_input.get("file_path") if isinstance(tool_input, dict) else None
    if not isinstance(file_path, str):
        return
    root, personal, _ = paths(root_arg, global_arg)
    rel = spec_relative(root, file_path)
    if rel and (root / rel).is_file():
        require_initialized(root)
        refresh_index(root, personal, scan=False, written=[rel])


def context(root_arg, global_arg):
    """会话开始时一次性加载：当前分支、脱敏配置、追踪工单、覆盖率身份、最近的 spec 和遗留的交接文件。

    各部分独立读取，某部分失败只记入 problems，不影响其余部分。不创建配置或追踪文件；
    索引状态缺失（首次或清理后）时以当前时间为起点新建空名单。branch 为 None 表示
    svn 不可用或不是工作副本。

    Raises:
        WorkspaceError: 工作区未初始化（见 require_initialized），此时不写入任何文件。
    """
    root, personal, _ = paths(root_arg, global_arg)
    require_initialized(root)
    result, problems = {"root": str(root), "branch": svn_branch(root)}, []
    try:
        result["effective_config"] = masked_config(load_config(root_arg, global_arg))
    except (WorkspaceError, OSError) as error:
        problems.append(f"配置：{error}")
    try:
        tracking = read_tracking(personal)[2]
        result["tracked_tasks"] = tracking["tracked_tasks"]
        result["coverage_tasks"] = tracking["coverage_tasks"]
    except (WorkspaceError, OSError) as error:
        problems.append(f"追踪：{error}")
    try:
        stats, entries = refresh_index(root, personal)
        recent = sorted(entries, key=lambda entry: mtime(root / entry[1]) or 0, reverse=True)
        stats["recent"] = [f"{path}：{title}" for _, path, title, _ in recent[:INDEX_RECENT_LIMIT]]
        result["index"] = stats
    except (WorkspaceError, OSError) as error:
        problems.append(f"索引：{error}")
    try:
        handoffs = personal / HANDOFF
        no_links(handoffs)
        files = sorted(handoffs.glob("*.md")) if handoffs.is_dir() else []
        result["handoffs"] = [{"path": str(path), "modified": datetime.fromtimestamp(path.stat().st_mtime)
                               .astimezone().isoformat(timespec="seconds")} for path in files]
    except (WorkspaceError, OSError) as error:
        problems.append(f"交接文件：{error}")
    result["problems"] = problems
    return result


def claude_hook_change(root, script):
    """生成在工作区 .claude/settings.local.json 中登记本 skill hooks 的变更。

    - SessionStart：会话开始、恢复、清空和上下文压缩后运行 `context`，把结果注入上下文。
    - PostToolUse（Write/Edit/MultiEdit）：写入 spec/ 下的 Markdown 后立即收录进索引。

    只增改命令中带 HOOK_FLAG 的本 skill 条目，保留其他设置；已是最新时返回 None。
    """
    path = root / ".claude" / "settings.local.json"
    old = read_bytes(path)
    settings = parse_json(old, path) if old is not None else {}
    hooks = settings.get("hooks", {})
    if not isinstance(hooks, dict):
        raise WorkspaceError(f"无法识别的 hooks 结构：{path}")
    prefix = f'python "{script.as_posix()}"'
    root_arg = f'--root "{root.as_posix()}" {HOOK_FLAG}'
    desired = {
        "SessionStart": {"hooks": [{"type": "command", "command": f"{prefix} context {root_arg}", "timeout": 30}]},
        "PostToolUse": {"matcher": "Write|Edit|MultiEdit",
                        "hooks": [{"type": "command", "command": f"{prefix} index {root_arg}", "timeout": 30}]},
    }

    def is_ours(hook):
        command = str(hook.get("command", "")) if isinstance(hook, dict) else ""
        return HOOK_FLAG in command and "workspace.py" in command

    new_hooks = dict(hooks)
    for event, ours in desired.items():
        entries = hooks.get(event, [])
        if not isinstance(entries, list):
            raise WorkspaceError(f"无法识别的 hooks 结构：{path}")
        # 只移除本 skill 的命令对象；用户的命令与之同在一个条目时保留该条目和用户命令。
        # 新条目放在第一次出现本 skill 命令的位置，没有出现过时追加到末尾。
        updated, position = [], None
        for entry in entries:
            commands = entry.get("hooks") if isinstance(entry, dict) else None
            kept = [hook for hook in commands if not is_ours(hook)] if isinstance(commands, list) else None
            if kept is None or len(kept) == len(commands):
                updated.append(entry)
                continue
            if position is None:
                position = len(updated)
            if kept:
                updated.append({**entry, "hooks": kept})
        updated.insert(len(updated) if position is None else position, ours)
        new_hooks[event] = updated
    if new_hooks == hooks:
        return None
    return path, old, json_bytes({**settings, "hooks": new_hooks})


def validate_coverage(task):
    """校验已经核实存在的远端覆盖率身份，不代表本轮通过。"""
    if set(task) != {"task_name", "branch", "redmine_id", "coder_name", "created"} or task["created"] is not True:
        raise WorkspaceError("覆盖率任务字段无效")
    for key in ("task_name", "branch", "redmine_id", "coder_name"):
        if not isinstance(task[key], str) or not task[key] or any(c in task[key] for c in "\r\n\x00`"):
            raise WorkspaceError(f"覆盖率任务字段无效：{key}")
    validate_issue_id(task["redmine_id"])


def validate_issue_id(issue_id):
    """工单号同时用作目录名，只接受正整数字符串。"""
    if not isinstance(issue_id, str) or not re.fullmatch(r"[1-9][0-9]*", issue_id):
        raise WorkspaceError("工单号必须为正整数")


def issue_entry(issue_id, title):
    """生成不含正文的工单定位信息，路径始终相对于项目根目录。"""
    validate_issue_id(issue_id)
    if not isinstance(title, str) or not title.strip() or any(c in title for c in "\r\n\x00"):
        raise WorkspaceError("工单标题必须为非空单行文本")
    return {"issue_id": issue_id, "title": title,
            "description_path": f"{DIRECTORY}/tasks/{issue_id}/issue.md"}


def read_tracking(personal):
    """读取本地追踪状态；缺失表示空状态，不隐式创建文件。"""
    path = personal / "tracking.json"
    old = read_bytes(path)
    value = parse_json(old, path) if old is not None else {"tracked_tasks": [], "coverage_tasks": []}
    if set(value) != {"tracked_tasks", "coverage_tasks"} or any(
            not isinstance(value[key], list) for key in value):
        raise WorkspaceError("tracking.json 结构无效")
    seen = set()
    for task in value["tracked_tasks"]:
        if not isinstance(task, dict) or task != issue_entry(task.get("issue_id"), task.get("title")):
            raise WorkspaceError("追踪工单字段无效")
        if task["issue_id"] in seen:
            raise WorkspaceError("追踪工单重复")
        seen.add(task["issue_id"])
    identities = set()
    for task in value["coverage_tasks"]:
        if not isinstance(task, dict):
            raise WorkspaceError("覆盖率任务字段无效")
        validate_coverage(task)
        identity = (task["redmine_id"], task["branch"])
        if identity in identities:
            raise WorkspaceError("同工单同分支的覆盖率身份重复")
        identities.add(identity)
    return path, old, value


def save_tracking(path, old, value, action, apply):
    """无差异不写入；沿用文件并发检查和失败恢复。"""
    new = json_bytes(value)
    changes = [(path, old, new)] if old != new else []
    if apply:
        apply_changes(changes)
    return {"action": action, "applied": apply, "tracking": value,
            "changes": [str(item[0]) for item in changes]}


def track_tasks(root_arg, global_arg, issue_ids, replace=False, remove=False, apply=False):
    """从脚本查询清单追加或替换用户选中的工单；取消追踪不删除正文。"""
    root, personal, _ = paths(root_arg, global_arg)
    if not issue_ids:
        raise WorkspaceError("请指定至少一个 --issue-id")
    for issue_id in issue_ids:
        validate_issue_id(issue_id)
    path, old, value = read_tracking(personal)
    if remove:
        value["tracked_tasks"] = [t for t in value["tracked_tasks"] if t["issue_id"] not in issue_ids]
    else:
        index_path = personal / "tasks/index.json"
        raw = read_bytes(index_path)
        if raw is None:
            raise WorkspaceError("请先获取当前任务，生成本地工单清单")
        index = parse_json(raw, index_path)
        if not isinstance(index.get("tasks"), list):
            raise WorkspaceError("工单清单缺少 tasks 列表")
        available = {}
        for item in index["tasks"]:
            if not isinstance(item, dict):
                raise WorkspaceError("工单清单条目无效")
            entry = issue_entry(item.get("issue_id"), item.get("title"))
            if item != entry:
                raise WorkspaceError("工单清单条目无效")
            available[entry["issue_id"]] = entry
        selected = {} if replace else {t["issue_id"]: t for t in value["tracked_tasks"]}
        for issue_id in issue_ids:
            if issue_id not in available or read_bytes(root / available[issue_id]["description_path"]) is None:
                raise WorkspaceError(f"工单 {issue_id} 不在当前清单或正文缺失，请重新获取")
            selected[issue_id] = available[issue_id]
        value["tracked_tasks"] = list(selected.values())
    return save_tracking(path, old, value, "untrack" if remove else "track", apply)


def record_coverage_task(root_arg, global_arg, task, apply=False):
    """按工单和分支登记覆盖率身份，仅写个人目录，不更新入口文件。"""
    validate_coverage(task)
    _, personal, _ = paths(root_arg, global_arg)
    path, old, value = read_tracking(personal)
    value["coverage_tasks"] = [t for t in value["coverage_tasks"]
                               if (t["redmine_id"], t["branch"]) != (task["redmine_id"], task["branch"])]
    value["coverage_tasks"].append(task)
    value["coverage_tasks"].sort(key=lambda t: (t["redmine_id"], t["branch"]))
    return save_tracking(path, old, value, "coverage-task", apply)


def busy_codex_jobs(personal):
    """返回不能清理的 codex-cli 任务：仍在运行（starting／running），或 test 任务的设备尚未 release。

    没有或无法读取 state.json 时状态未知，也算在内，由用户核实后再清理。
    """
    jobs = personal / CODEX_JOBS
    no_links(jobs)
    if not jobs.is_dir():
        return []
    busy = []
    for job in sorted(jobs.iterdir()):
        state_path = job / "state.json"
        try:
            raw = read_bytes(state_path)
            if raw is None:
                busy.append(f"{job.name}（没有 state.json，可能正在创建或创建时中断：确认没有 codex_cli.py 进程"
                            "在使用它、全机设备锁目录 %LOCALAPPDATA%\\mhxy-cli-testing\\locks 中没有指向它的锁后，"
                            "手动删除该任务目录）")
                continue
            state = parse_json(raw, state_path)
        except (WorkspaceError, OSError) as error:
            busy.append(f"{job.name}（state.json 无法读取：{error}）")
            continue
        status = state.get("status")
        if isinstance(status, str) and status.startswith(CODEX_ACTIVE):
            busy.append(f"{job.name}（{status}）")
        elif state.get("kind") == "test" and state.get("released") is not True:
            busy.append(f"{job.name}（test 任务尚未 release）")
    return busy


def clean(root_arg, global_arg, apply=False):
    """清空个人目录；codex-cli 有未结束或未 release 的任务时拒绝，不删除任何内容。"""
    root, personal, global_config = paths(root_arg, global_arg)
    if not exists(personal):
        return {"action": "clean", "applied": apply, "target": str(personal), "entries": []}
    busy = busy_codex_jobs(personal)
    if busy:
        raise WorkspaceError("codex-cli 还有未结束或未 release 的任务，请先等待完成、取消或 release 后再清理："
                             + "、".join(busy))
    identity = personal.stat()
    items = []

    def scan(directory):
        for path in sorted(directory.iterdir()):
            no_links(path)
            if not path.is_relative_to(personal):
                raise WorkspaceError(f"越界路径：{path}")
            info = path.lstat()
            if stat.S_ISDIR(info.st_mode):
                scan(path)
            elif not stat.S_ISREG(info.st_mode):
                raise WorkspaceError(f"拒绝特殊文件：{path}")
            items.append((path, info))

    scan(personal)  # Complete preflight before any deletion.
    entries = [str(path.relative_to(personal)) for path in sorted(personal.iterdir())]
    if apply:
        try:
            for path, before in items:
                no_links(personal)
                current_root = personal.stat()
                if (identity.st_dev, identity.st_ino) != (current_root.st_dev, current_root.st_ino):
                    raise WorkspaceError("个人目录身份发生变化")
                no_links(path)
                now = path.lstat()
                if (before.st_dev, before.st_ino, before.st_mode) != (now.st_dev, now.st_ino, now.st_mode):
                    raise WorkspaceError(f"待清理对象已变化：{path}")
                if stat.S_ISDIR(now.st_mode):
                    path.rmdir()
                else:
                    if (before.st_size, before.st_mtime_ns) != (now.st_size, now.st_mtime_ns):
                        raise WorkspaceError(f"待清理文件已变化：{path}")
                    path.unlink()
            if any(personal.iterdir()):
                raise WorkspaceError("清理期间出现新文件")
        except Exception as error:
            raise WorkspaceError(f"清理中止，可能已部分清理：{error}") from error
    return {"action": "clean", "applied": apply, "target": str(personal), "entries": entries}


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("sync", "context", "index", "clean", "coverage-task", "config",
                                           "show-config", "track", "untrack"))
    parser.add_argument("--query", action="append", default=[], help="index：按关键词过滤，可重复，全部命中")
    parser.add_argument("--add", action="append", default=[], help="index：手动收录 spec，可重复")
    parser.add_argument("--remove", action="append", default=[], help="index：移出 spec，可重复")
    parser.add_argument(HOOK_FLAG, dest="from_hook", action="store_true",
                        help="context／index：由 Claude Code hook 调用（context 输出注入格式，index 从 stdin 读取写入事件）")
    parser.add_argument("--issue-id", action="append", default=[])
    parser.add_argument("--replace", action="store_true", help="替换追踪列表；默认追加")
    parser.add_argument("--prompt-password", action="store_true")
    parser.add_argument("--task-name")
    parser.add_argument("--branch", help="coverage-task：仓库相对路径（如 branchs/2026_dev/x），省略时从 svn 推断")
    parser.add_argument("--redmine-id")
    parser.add_argument("--coder-name")
    parser.add_argument("--root", default=os.getcwd())
    parser.add_argument("--global-config", default=str(Path.home() / DIRECTORY / "config.json"))
    parser.add_argument("--set-global", action="append", default=[])
    parser.add_argument("--set-local", action="append", default=[])
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        if args.replace and args.action != "track":
            raise WorkspaceError("--replace 仅用于 track")
        if args.issue_id and args.action not in ("track", "untrack"):
            raise WorkspaceError("--issue-id 仅用于 track 或 untrack")
        if args.action not in ("sync", "config") and (args.set_global or args.set_local):
            raise WorkspaceError("此操作不接受 --set-global 或 --set-local")
        if args.action != "config" and args.prompt_password:
            raise WorkspaceError("--prompt-password 仅用于 config")
        if args.action == "config" and args.set_local:
            raise WorkspaceError("config 仅更新用户级配置")
        if (args.query or args.add or args.remove) and args.action != "index":
            raise WorkspaceError("--query、--add、--remove 仅用于 index")
        if args.from_hook and args.action not in ("context", "index"):
            raise WorkspaceError(f"{HOOK_FLAG} 仅用于 context 或 index")
        if args.action == "index" and args.from_hook:
            # 写入后的 hook 不得干扰工具调用：静默处理，失败也以 0 退出。
            try:
                payload = json.loads(sys.stdin.buffer.read().decode("utf-8-sig") or "{}")
                record_hook_write(args.root, args.global_config, payload)
            except Exception:  # noqa: BLE001
                pass
            return 0
        if args.action == "context" and args.from_hook:
            # hook 不得阻断会话：任何失败都作为文本注入，并以 0 退出。
            try:
                text = json.dumps(context(args.root, args.global_config), ensure_ascii=False, indent=2)
            except Exception as error:  # noqa: BLE001
                text = json.dumps({"problems": [f"context 失败：{error}"]}, ensure_ascii=False)
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": "mhxy-workspace context（会话开始时由 hook 自动运行，本会话无需再运行）：\n" + text,
            }}, ensure_ascii=False))
            return 0
        if args.action == "context":
            result = context(args.root, args.global_config)
        elif args.action == "index":
            result = query_index(args.root, args.global_config, args.query, args.add, args.remove)
        elif args.action == "sync":
            result = sync(args.root, args.global_config, args.set_global, args.apply,
                          local_assignments=args.set_local)
        elif args.action == "show-config":  # 兼容 0.2.x 入口；新入口统一使用 context。
            result = {"effective_config": masked_config(load_config(args.root, args.global_config))}
        elif args.action == "config":
            password = None
            if args.prompt_password:
                if not args.apply:
                    raise WorkspaceError("--prompt-password 需要同时加 --apply，否则输入的密码不会保存")
                # Claude Code 等命令工具的 stdin 可能是 NUL（Windows 下是字符设备，isatty 为真），
                # getpass 会一直等待；stderr 不是终端时同样视为没有交互终端。
                if not (sys.stdin.isatty() and sys.stderr.isatty()):
                    raise WorkspaceError("隐藏输入密码需要交互终端")
                password = getpass.getpass("OpenID password (save to user config): ")
            result = configure_global(args.global_config, args.set_global, password, args.apply)
            password = None
        elif args.action == "coverage-task":
            require_initialized(paths(args.root, args.global_config)[0])
            branch =args.branch or (svn_branch(Path(args.root)) or {}).get("path")
            if not branch:
                raise WorkspaceError("无法从 svn 推断分支，请用 --branch 传仓库相对路径（如 branchs/2026_dev/x）")
            result = record_coverage_task(args.root, args.global_config,
                {"task_name": args.task_name, "branch": branch,
                 "redmine_id": args.redmine_id, "coder_name": args.coder_name, "created": True}, args.apply)
        elif args.action in ("track", "untrack"):
            require_initialized(paths(args.root, args.global_config)[0])
            result =track_tasks(args.root, args.global_config, args.issue_id,
                                 args.replace, args.action == "untrack", args.apply)
        else:
            result = clean(args.root, args.global_config, args.apply)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (WorkspaceError, OSError, UnicodeError, KeyError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
