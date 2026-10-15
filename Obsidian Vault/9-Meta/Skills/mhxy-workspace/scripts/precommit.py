#!/usr/bin/env python3
"""提交前自检：只读检查工作副本的待提交内容，输出 JSON。

规则说明见 references/svn-commit.md「提交前自检」，本脚本只做其中可确定判断的部分：
提交范围分类、冲突与缺失、Python 编码和语法、新增行中的调试残留、review 之后的改动。不执行任何 SVN 写操作。
--mark-reviewed 只记录 review 指纹到个人目录，不做自检。

退出码：0 没有阻断问题；2 有阻断问题；1 自检本身失败（如 svn 不可用）。
"""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from xml.etree import ElementTree

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import workspace  # noqa: E402

# 不应提交的本地文件（首段路径）；与 svn-commit.md「提交前自检」表中 excluded_local_only 的说明一致，修改时两处同步。
LOCAL_ONLY = {workspace.DIRECTORY, ".claude", *workspace.ENTRY_FILES}
DATA_DIRECTORY = "data"  # 导表数据，默认不提交，由用户自己处理。
CHANGED_ITEMS = {"modified", "added", "replaced", "deleted"}
BLOCKING_ITEMS = {"conflicted", "missing", "obstructed", "incomplete"}
SOURCE_SUFFIXES = (".py", ".tmpl")  # 与项目编码检查工具的默认扫描范围一致。
ENCODING_TOOL = "tools/check_py_source_encoding.py"
# 新增行中的疑似调试残留：(模式, 说明)。只给警告，由主线程判断是否属于正常代码。
# Mock／追踪器只认 game-debugging.md「Mock 与验证」和 exec-check 的注入写法，不误报普通的回调赋值。
LEFTOVERS = ((re.compile(r"\bpdb\b|\bbreakpoint\(\)"), "调试断点"),
             (re.compile(r"^\s*print\("), "新增 print"),
             (re.compile(r"mh_at_[0-9a-f]{32}"), "写死的设备 ID"),
             (re.compile(r"\b(?:sys|threading)\.(?:settrace|setprofile)\s*\("), "追踪器残留"),
             (re.compile(r"\b(?:exec_check_start|error_watch_start|error_watch_finish)\b|_error_watch_collector"),
              "自检模板残留"),
             (re.compile(r"\bunittest\.mock\b|^\s*(?:from\s+mock\s+import|import\s+mock\b)|\bmock\.patch\b"
                         r"|\bpatch\.object\(|\bMagicMock\b"), "Mock 残留"),
             # 用 lambda *a, **k 整体替换模块或类的属性；self.／cls. 上的赋值是正常写法，不算。
             (re.compile(r"^\s*(?!self\.|cls\.)[A-Za-z_]\w*(?:\.\w+)+\s*=\s*lambda\s*\*"
                         r"|\bsetattr\([^,]+,[^,]+,\s*lambda\b"), "疑似 monkey patch"),
             (re.compile(r"^\s*_*orig(?:inal)?_\w*\s*=\s*(?!self\.|cls\.)[A-Za-z_]\w*(?:\.\w+)+\s*$"),
              "疑似 Mock 保存的原函数"))
LIST_LIMIT = 50  # 每类路径最多列出的数量，避免输出过长。
REVIEW_MARK = "review-mark.json"  # 位于个人目录，记录 review 通过时各文件的指纹。


class PrecheckError(Exception):
    """自检无法完成（svn 不可用、不是工作副本等）。"""


class SvnTimeout(PrecheckError):
    """svn 命令超时：命令可能仍在执行或已部分生效，调用方不能把它当作“svn 不可用”。"""


def decode_output(data):
    """解码 svn 输出：先按 UTF-8，失败再按 GB18030（中文 Windows 上 svn 的提示用系统代码页）。"""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("gb18030", "replace")


def svn_process(cwd, *args, timeout=120):
    """运行 svn（自动加 --non-interactive），返回 CompletedProcess，由调用方判断退出码和输出。

    其他脚本需要自己解释失败原因时用它；只关心成功输出时用 run_svn。

    Raises:
        SvnTimeout: 超过 timeout 秒未结束。
        PrecheckError: svn 不可用。
    """
    try:
        return subprocess.run(["svn", *map(str, args), "--non-interactive"], cwd=cwd,
                              capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise SvnTimeout(f"svn {args[0] if args else ''} 超过 {timeout} 秒未结束") from None
    except (OSError, subprocess.SubprocessError) as error:
        raise PrecheckError(f"svn 不可用：{error}") from None


def run_svn(root, *args, timeout=120):
    """在工作副本根目录运行只读 svn 命令并返回标准输出字节；失败时抛出 PrecheckError。"""
    completed = svn_process(root, *args, timeout=timeout)
    if completed.returncode:
        raise PrecheckError(decode_output(completed.stderr).strip() or f"svn {args[0]} 失败")
    if b"155007" in completed.stderr:  # 非工作副本时 svn status 只给警告且退出码为 0，不能当作“没有改动”
        raise PrecheckError(f"不是 SVN 工作副本：{root}")
    return completed.stdout


def svn_status(root):
    """返回主工作副本（不含外链）的状态条目列表。

    Returns:
        [{"path": 相对路径（/ 分隔）, "item": 状态, "props": 属性状态,
          "tree_conflict": bool, "changelist": 变更列表名或 None}]
    """
    tree = ElementTree.fromstring(run_svn(root, "status", "--xml", "--ignore-externals", "."))
    entries = []
    for parent in list(tree.iter("target")) + list(tree.iter("changelist")):
        changelist = parent.get("name") if parent.tag == "changelist" else None
        for entry in parent.findall("entry"):
            status = entry.find("wc-status")
            if status is None:
                continue
            entries.append({"path": entry.get("path", "").replace("\\", "/"), "item": status.get("item"),
                            "props": status.get("props"), "tree_conflict": status.get("tree-conflicted") == "true",
                            "changelist": changelist})
    return entries


def in_scope(entry):
    """条目是否属于可能提交的范围：不是本地辅助文件、导表数据，也不在 ignore-on-commit 变更列表中。"""
    first = entry["path"].split("/", 1)[0]
    return (first not in LOCAL_ONLY and first != DATA_DIRECTORY
            and entry.get("changelist") != workspace.IGNORE_ON_COMMIT)


def classify(entries):
    """把状态条目分为待提交、排除、未纳入版本控制、属性改动和阻断问题。"""
    result = {"commit": [], "excluded_local_only": [], "excluded_data": [], "ignore_on_commit": [],
              "unversioned": [], "property_changes": [], "blocking": []}
    for entry in entries:
        path, item = entry["path"], entry["item"]
        first = path.split("/", 1)[0]
        if item in ("external", "ignored", "normal", "none") and entry["props"] not in ("modified", "conflicted"):
            continue
        if item in BLOCKING_ITEMS or entry["tree_conflict"] or entry["props"] == "conflicted":
            result["blocking"].append(f"{path}：状态为 {item}{'（树冲突）' if entry['tree_conflict'] else ''}，先解决再提交")
            continue
        if first in LOCAL_ONLY:
            result["excluded_local_only"].append(path)
        elif first == DATA_DIRECTORY:
            result["excluded_data"].append(path)
        elif entry.get("changelist") == workspace.IGNORE_ON_COMMIT:
            result["ignore_on_commit"].append(f"{path}（{item if item in CHANGED_ITEMS else '属性修改'}）")
            continue
        elif item == "unversioned":
            result["unversioned"].append(path)
        elif item in CHANGED_ITEMS:
            result["commit"].append(f"{path}（{item}）")
        elif entry["props"] == "modified":
            result["commit"].append(f"{path}（属性修改）")
        if entry["props"] == "modified" and first not in LOCAL_ONLY:
            result["property_changes"].append(path)
    return result


def source_targets(root, entries):
    """待检查的源码：[(路径, 状态)]。包括待提交的修改／新增文件，以及未纳入版本控制的源码（含未纳管目录中的）。

    编码检查和调试残留扫描共用这份清单，范围保持一致。已加入版本控制的目录中，子文件各自是独立的状态条目。
    """
    targets = {}
    for entry in entries:
        if not in_scope(entry) or entry["item"] not in ("modified", "added", "replaced", "unversioned"):
            continue
        path = root / entry["path"]
        candidates = path.rglob("*") if entry["item"] == "unversioned" and path.is_dir() else [path]
        for candidate in candidates:
            if candidate.is_file() and candidate.suffix in SOURCE_SUFFIXES:
                targets[candidate] = entry["item"]
    return sorted(targets.items())


def source_files(root, entries):
    """需要检查编码和语法的源码文件（见 source_targets）。"""
    return [path for path, _ in source_targets(root, entries)]


def check_sources(root, files):
    """检查编码与语法。项目有编码检查工具时以它为准（--expect-utf8 --compile），否则用内置检查。

    Returns:
        (阻断问题, 警告, 使用的检查方式)
    """
    blocking, warnings = [], []
    if not files:
        return blocking, warnings, "无需检查"
    relative = [p.relative_to(root).as_posix() for p in files]
    for path, rel in zip(files, relative):
        data = path.read_bytes()
        if b"\r\n" in data and data.replace(b"\r\n", b"").count(b"\n"):
            warnings.append(f"{rel}：混用 CRLF 和 LF 换行")
    tool = root / ENCODING_TOOL
    if tool.is_file():
        try:
            completed = subprocess.run([sys.executable, "-B", str(tool), "--root", ".", "--expect-utf8", "--compile",
                                        *relative], cwd=root, capture_output=True, timeout=300)
        except subprocess.TimeoutExpired:
            raise PrecheckError(f"{ENCODING_TOOL} 超过 300 秒未结束") from None
        output = completed.stdout.decode("utf-8", "replace").splitlines()
        issues = [line for line in output if line.strip() and not line.startswith("OK")]
        if completed.returncode:
            blocking += issues or [f"{ENCODING_TOOL} 返回 {completed.returncode}"]
        else:
            warnings += issues
        return blocking, warnings, ENCODING_TOOL
    for path, rel in zip(files, relative):
        data = path.read_bytes()
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            blocking.append(f"{rel}：不是有效的 UTF-8（{error.reason}，位置 {error.start}）")
            continue
        header = re.search(r"coding[:=]\s*([-\w.]+)", "\n".join(text.splitlines()[:2]))
        if header and header[1].lower().replace("_", "-") not in ("utf-8", "utf8"):
            blocking.append(f"{rel}：编码声明为 {header[1]}，应为 utf-8")
        if path.suffix == ".py":
            try:
                compile(text, rel, "exec", dont_inherit=True)
            except SyntaxError as error:
                blocking.append(f"{rel}:{error.lineno}：语法错误：{error.msg}")
    return blocking, warnings, "内置检查（项目没有编码检查工具）"


def decode_line(data):
    """解码单行或单个文件：先 UTF-8，失败再按 GB18030（兼容系统代码页 cp936），无法解码的字节替换掉。"""
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("gb18030", "replace")


def diff_added_lines(data):
    """从 svn diff 的原始字节中取出新增行。

    svn diff 的文件头（Index:、---、+++）用系统代码页输出，内容行是文件原始字节（通常 UTF-8），
    整段解码会因编码混用而失败，因此逐行解码。只把 @@ 块内以 + 开头的行算作新增；
    Index: 或 Property changes on: 开始新的头部，属性块（## 开头）中的行不算源码新增。
    """
    lines, in_hunk = [], False
    for raw in data.splitlines():
        if raw.startswith((b"Index: ", b"Property changes on: ")):
            in_hunk = False
        elif raw.startswith(b"@@"):
            in_hunk = True
        elif in_hunk and raw.startswith(b"+"):
            lines.append(decode_line(raw[1:]))
    return lines


def added_lines(root, relative, item):
    """返回本次新增的行：修改的文件取 svn diff 的新增行，新文件取全文。"""
    path = root / relative
    if item in ("added", "unversioned"):
        return decode_line(path.read_bytes()).splitlines() if path.is_file() else []
    return diff_added_lines(run_svn(root, "diff", "--internal-diff", relative))


def check_leftovers(root, entries):
    """扫描待提交源码新增行中的疑似调试残留，只返回警告；范围与编码检查相同（见 source_targets）。"""
    warnings = []
    for path, item in source_targets(root, entries):
        relative = path.relative_to(root).as_posix()
        for line in added_lines(root, relative, item):
            for pattern, label in LEFTOVERS:
                if pattern.search(line):
                    warnings.append(f"{relative}：{label}：{line.strip()[:80]}")
    return warnings


def review_fingerprints(root, entries):
    """可能提交的各文件指纹：{相对路径: "状态/属性状态:内容 sha256"}。

    范围与 classify 列出的改动相同（不含本地辅助文件、导表数据和 ignore-on-commit）；
    未纳管目录展开为其中的文件，已删除或缺失的文件内容记为 "-"。
    """
    result = {}
    for entry in entries:
        item, props = entry["item"], entry.get("props")
        if not in_scope(entry) or (item in ("external", "ignored", "normal", "none")
                                   and props not in ("modified", "conflicted")):
            continue
        path = root / entry["path"]
        if item == "unversioned" and path.is_dir():
            files = [(p, p.relative_to(root).as_posix()) for p in path.rglob("*") if p.is_file()]
        else:
            files = [(path, entry["path"])]
        for file, relative in files:
            digest = hashlib.sha256(file.read_bytes()).hexdigest() if file.is_file() else "-"
            result[relative] = f"{item}/{props}:{digest}"
    return result


def mark_reviewed(root_arg):
    """记录 review 通过时的指纹到个人目录的 review-mark.json，覆盖旧记录。"""
    root = Path(root_arg).resolve()
    workspace.require_initialized(root)  # 不在未初始化的目录里新建个人目录
    files = review_fingerprints(root, svn_status(root))
    marked_at = datetime.now().astimezone().isoformat(timespec="seconds")
    path = root / workspace.DIRECTORY / REVIEW_MARK
    workspace.apply_changes([(path, workspace.read_bytes(path),
                              workspace.json_bytes({"marked_at": marked_at, "files": files}))])
    return {"root": str(root), "review_mark": marked_at, "files": len(files), "path": str(path)}


def review_delta(root, entries):
    """与 review 记录比较：返回 (记录时间或 None, review 后变化的文件, 警告)。

    变化包括内容或状态不同、记录后新出现的改动，以及记录中有、现在已没有改动的文件。
    """
    path = root / workspace.DIRECTORY / REVIEW_MARK
    try:
        raw = workspace.read_bytes(path)
        if raw is None:
            return None, [], []
        mark = workspace.parse_json(raw, path)
        if not isinstance(mark.get("marked_at"), str) or not isinstance(mark.get("files"), dict):
            raise workspace.WorkspaceError(f"结构无效：{path}")
    except (workspace.WorkspaceError, OSError) as error:
        return None, [], [f"review 记录无法读取，按没有记录处理：{error}"]
    current, old = review_fingerprints(root, entries), mark["files"]
    changed = sorted(name for name in current.keys() | old.keys() if current.get(name) != old.get(name))
    return mark["marked_at"], changed, []


def precheck(root_arg):
    """执行全部自检并返回结果字典（见模块说明）。"""
    root = Path(root_arg).resolve()
    entries = svn_status(root)
    result = classify(entries)
    blocking, warnings, method = check_sources(root, source_files(root, entries))
    result["blocking"] += blocking
    result["warnings"] = warnings + check_leftovers(root, entries)
    result["review_mark"], result["changed_since_review"], mark_warnings = review_delta(root, entries)
    result["warnings"] += mark_warnings
    if result["property_changes"]:
        result["warnings"].append("有属性改动（可能是外链更新）：建议与代码分开提交，并在说明末尾加 [NO MERGE]")
    if result["excluded_data"]:
        result["warnings"].append("导表数据默认不提交，已从待提交清单排除，请自行处理")
    for key in ("commit", "excluded_local_only", "excluded_data", "ignore_on_commit", "unversioned", "property_changes",
                "changed_since_review", "warnings"):
        if len(result[key]) > LIST_LIMIT:
            result[key] = result[key][:LIST_LIMIT] + [f"……另有 {len(result[key]) - LIST_LIMIT} 项未列出"]
    return {"root": str(root), "branch": workspace.svn_branch(root), "source_check": method, **result}


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--mark-reviewed", action="store_true",
                        help="只记录当前改动的 review 指纹（写 .mhxy-workspace/review-mark.json），不做自检")
    args = parser.parse_args()
    try:
        if args.mark_reviewed:
            print(json.dumps(mark_reviewed(args.root), ensure_ascii=False, indent=2))
            return 0
        result = precheck(args.root)
    except (PrecheckError, workspace.WorkspaceError, OSError, ElementTree.ParseError,
            subprocess.SubprocessError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2 if result["blocking"] else 0


if __name__ == "__main__":
    sys.exit(main())
