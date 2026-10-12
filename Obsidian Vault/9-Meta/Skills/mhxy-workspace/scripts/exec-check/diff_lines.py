#!/usr/bin/env python3
"""改动执行检查的目标行：列出工作副本未提交改动中会执行的 Python 行，输出 JSON。

规则见 references/exec-check.md「确定目标行」。只读，不执行任何 SVN 写操作。

用法：python -X utf8 diff_lines.py --root <工作副本根目录> [相对路径 ...]
不给路径时，取 svn status 中修改、新增或替换的 .py 文件（排除个人目录、入口文件和导表数据）。

退出码：0 成功；1 失败（svn 不可用、不是工作副本等）。
"""
import argparse
import difflib
import json
from pathlib import Path
import re
import sys
import types
import warnings

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import precommit  # noqa: E402

CO_OPTIMIZED = 0x1  # 函数（含 lambda、推导式）的代码对象带此标志；模块和类体不带。
# Python 把单独的 CR 也当换行，svn diff 只按 LF 计行；统一按 Python 规则计行，才能和客户端 f_lineno 对上。
NEWLINE = re.compile(r"\r\n|\r|\n")
CHANGED_ITEMS = {"modified", "added", "replaced"}


def split_py_lines(data):
    """按 Python 的换行规则切分 UTF-8 源码字节，返回行列表（第 i 项对应第 i+1 行）。"""
    return NEWLINE.split(data.decode("utf-8"))


def changed_line_numbers(old, new):
    """返回 new 相对 old 新增或修改的行号集合（Python 计行，从 1 开始）。

    Args:
        old: 基线源码字节；新增文件传 b""。
        new: 当前源码字节。
    """
    old_lines = split_py_lines(old) if old else []
    lines = set()
    matcher = difflib.SequenceMatcher(None, old_lines, split_py_lines(new), autojunk=False)
    for tag, _, _, j1, j2 in matcher.get_opcodes():
        if tag in ("replace", "insert"):
            lines.update(range(j1 + 1, j2 + 1))
    return lines


def executable_lines(source, filename):
    """返回函数体内会产生字节码的行号集合。

    不含注释、空行、docstring，也不含模块级和类体语句（它们在导入或热更时执行，不由用例触发）。
    函数的 def 行属于函数自身的代码对象，调用时由追踪器的 call 事件记为已执行。

    Raises:
        SyntaxError: 源码无法编译。
    """
    result = set()

    def walk(code):
        if code.co_flags & CO_OPTIMIZED:
            result.update(line for _, _, line in code.co_lines() if line)
        for const in code.co_consts:
            if isinstance(const, types.CodeType):
                walk(const)

    with warnings.catch_warnings():  # 业务代码里的 SyntaxWarning 与目标行无关，不输出
        warnings.simplefilter("ignore")
        code = compile(source.decode("utf-8"), filename, "exec", dont_inherit=True)
    walk(code)
    return result


def changed_py_files(root):
    """svn status 中待提交的 .py 文件相对路径（/ 分隔）。"""
    files = []
    for entry in precommit.svn_status(root):
        path, first = entry["path"], entry["path"].split("/", 1)[0]
        if (entry["item"] in CHANGED_ITEMS and path.endswith(".py")
                and first not in precommit.LOCAL_ONLY and first != precommit.DATA_DIRECTORY):
            files.append(path)
    return sorted(files)


def base_source(root, rel):
    """返回文件的 BASE 版本字节；新增或未纳入版本控制的文件返回 b""。"""
    try:
        return precommit.run_svn(root, "cat", "-r", "BASE", rel)
    except precommit.PrecheckError:
        return b""


def collect(root, rels):
    """计算各文件的目标行。

    Returns:
        {"files": {相对路径: [行号]}, "total": 行数, "skipped": {相对路径: 原因}}
        没有目标行的文件不出现在 files 中。
    """
    files, skipped = {}, {}
    for rel in rels:
        path = root / rel
        if not path.is_file():
            skipped[rel] = "文件不存在"
            continue
        current = path.read_bytes()
        try:
            lines = sorted(changed_line_numbers(base_source(root, rel), current) & executable_lines(current, str(path)))
        except (SyntaxError, UnicodeDecodeError) as error:
            skipped[rel] = f"无法解析：{error}"
            continue
        if lines:
            files[rel] = lines
    return {"files": files, "total": sum(len(v) for v in files.values()), "skipped": skipped}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", required=True, help="SVN 工作副本根目录")
    parser.add_argument("paths", nargs="*", help="相对路径；省略时取 svn status 中待提交的 .py 文件")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    try:
        rels = [p.replace("\\", "/") for p in args.paths] or changed_py_files(root)
        result = collect(root, rels)
    except precommit.PrecheckError as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
