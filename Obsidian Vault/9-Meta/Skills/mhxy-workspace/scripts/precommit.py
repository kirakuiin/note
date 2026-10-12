#!/usr/bin/env python3
"""提交前自检：只读检查工作副本的待提交内容，输出 JSON。

规则说明见 references/svn-commit.md「提交前自检」，本脚本只做其中可确定判断的部分：
提交范围分类、冲突与缺失、Python 编码和语法、新增行中的调试残留。不执行任何 SVN 写操作。

退出码：0 没有阻断问题；2 有阻断问题；1 自检本身失败（如 svn 不可用）。
"""
import argparse
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
LEFTOVERS = ((re.compile(r"\bpdb\b|\bbreakpoint\(\)"), "调试断点"),
             (re.compile(r"^\s*print\("), "新增 print"),
             (re.compile(r"mh_at_[0-9a-f]{32}"), "写死的设备 ID"))
LIST_LIMIT = 50  # 每类路径最多列出的数量，避免输出过长。


class PrecheckError(Exception):
    """自检无法完成（svn 不可用、不是工作副本等）。"""


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
        PrecheckError: svn 不可用或超时。
    """
    try:
        return subprocess.run(["svn", *map(str, args), "--non-interactive"], cwd=cwd,
                              capture_output=True, timeout=timeout)
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


def classify(entries):
    """把状态条目分为待提交、排除、未纳入版本控制、属性改动和阻断问题。"""
    result = {"commit": [], "excluded_local_only": [], "excluded_data": [], "unversioned": [],
              "property_changes": [], "blocking": []}
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
        elif item == "unversioned":
            result["unversioned"].append(path)
        elif item in CHANGED_ITEMS:
            result["commit"].append(f"{path}（{item}）")
        elif entry["props"] == "modified":
            result["commit"].append(f"{path}（属性修改）")
        if entry["props"] == "modified" and first not in LOCAL_ONLY:
            result["property_changes"].append(path)
    return result


def source_files(root, entries):
    """需要检查编码和语法的源码：待提交的修改／新增文件，以及未纳入版本控制的源码。"""
    files = []
    for entry in entries:
        first = entry["path"].split("/", 1)[0]
        if first in LOCAL_ONLY or first == DATA_DIRECTORY or entry["item"] not in ("modified", "added", "replaced", "unversioned"):
            continue
        path = root / entry["path"]
        candidates = path.rglob("*") if path.is_dir() else [path]
        files += [p for p in candidates if p.is_file() and p.suffix in SOURCE_SUFFIXES]
    return sorted(set(files))


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
        completed = subprocess.run([sys.executable, "-B", str(tool), "--root", ".", "--expect-utf8", "--compile", *relative],
                                   cwd=root, capture_output=True, timeout=300)
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


def added_lines(root, entry):
    """返回本次新增的行：修改的文件取 svn diff 的新增行，新文件取全文。"""
    path = root / entry["path"]
    if entry["item"] in ("added", "unversioned"):
        if not path.is_file():
            return []
        return workspace.decode_document(path.read_bytes())[0].splitlines()
    diff = workspace.decode_document(run_svn(root, "diff", "--internal-diff", entry["path"]))[0]
    return [line[1:] for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++")]


def check_leftovers(root, entries):
    """扫描待提交源码新增行中的疑似调试残留，只返回警告。"""
    warnings = []
    for entry in entries:
        first = entry["path"].split("/", 1)[0]
        if (first in LOCAL_ONLY or first == DATA_DIRECTORY or not entry["path"].endswith(SOURCE_SUFFIXES)
                or entry["item"] not in ("modified", "added", "replaced", "unversioned")):
            continue
        for line in added_lines(root, entry):
            for pattern, label in LEFTOVERS:
                if pattern.search(line):
                    warnings.append(f"{entry['path']}：{label}：{line.strip()[:80]}")
    return warnings


def precheck(root_arg):
    """执行全部自检并返回结果字典（见模块说明）。"""
    root = Path(root_arg).resolve()
    entries = svn_status(root)
    result = classify(entries)
    blocking, warnings, method = check_sources(root, source_files(root, entries))
    result["blocking"] += blocking
    result["warnings"] = warnings + check_leftovers(root, entries)
    if result["property_changes"]:
        result["warnings"].append("有属性改动（可能是外链更新）：建议与代码分开提交，并在说明末尾加 [NO MERGE]")
    if result["excluded_data"]:
        result["warnings"].append("导表数据默认不提交，已从待提交清单排除，请自行处理")
    for key in ("commit", "excluded_local_only", "excluded_data", "unversioned", "property_changes", "warnings"):
        if len(result[key]) > LIST_LIMIT:
            result[key] = result[key][:LIST_LIMIT] + [f"……另有 {len(result[key]) - LIST_LIMIT} 项未列出"]
    return {"root": str(root), "branch": workspace.svn_branch(root), "source_check": method, **result}


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    try:
        result = precheck(args.root)
    except (PrecheckError, OSError, ElementTree.ParseError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2 if result["blocking"] else 0


if __name__ == "__main__":
    sys.exit(main())
