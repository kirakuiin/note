#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""正式分支的定向 SVN 提交：默认只读预览，--apply 才添加新文件并提交。

仅接收明确的文件清单和 UTF-8 消息文件；不执行更新、合并、冲突处理或重试。
工作流及授权要求见 references/svn-commit.md。
"""
import argparse
import json
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import quote, unquote
from xml.etree import ElementTree

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import precommit  # noqa: E402
import workspace  # noqa: E402


def run_svn(root, *args):
    """通过 Python 直接调用 svn.exe，返回标准输出字节；失败立即停止。"""
    completed = precommit.svn_process(root, *args)
    if completed.returncode:
        raise precommit.PrecheckError(precommit.decode_output(completed.stderr).strip()
                                     or precommit.decode_output(completed.stdout).strip())
    return completed.stdout


def branch_kind(url):
    """识别 trunk 和 _ship 下的已知周期分支，不按名称子串推断研发分支。"""
    path = workspace.branch_path(url)
    if path == "trunk":
        return "trunk"
    parent, _, name = (path or "").rpartition("/")
    if (re.fullmatch(r"branchs/\d{4}_ship", parent)
            and (name in workspace.PERIODIC_TYPES or workspace.PERIODIC_NAME.fullmatch(name))):
        return "周期分支"
    raise ValueError("本脚本只用于 trunk 和 _ship 下的已知周期分支；研发分支使用 openforge")


def info(root, target):
    """读取目标的 SVN 元数据；@ 后缀避免把文件名中的 @ 当作 peg revision。"""
    entry = ElementTree.fromstring(run_svn(root, "info", "--xml", "--depth", "empty", "./" + target + "@")).find("entry")
    if entry is None:
        raise ValueError(f"无法读取 SVN 元数据：{target}")
    return entry


def prepare(root, paths, message):
    """只读核对分支、说明和每个文件的状态，拒绝目录与跨工作副本目标。

    新文件要求其父目录已被版本控制，预览不会自动 svn add。
    """
    if not paths:
        raise ValueError("必须明确列出待提交文件，不能提交整个工作副本")
    if not re.match(r"^finish #[0-9]+\s+\S", message.splitlines()[0] if message else ""):
        raise ValueError("正式分支说明必须以 `finish #工单号 描述` 开头")
    if "auto commit:" in message.lower():
        raise ValueError("本脚本处理人工提交，不接受 auto commit: 日志")
    root_info = info(root, ".")
    url = root_info.findtext("url")
    kind = branch_kind(url or "")
    wc_root = root_info.findtext("wc-info/wcroot-abspath")
    if not wc_root or Path(wc_root).resolve() != root:
        raise ValueError("--root 必须是工作副本根目录")
    entries, seen = [], set()
    for value in paths:
        requested = Path(value)
        if requested.is_absolute() or requested.drive or ".." in requested.parts:
            raise ValueError(f"路径必须相对工作副本且不能含 ..：{value}")
        path = root / requested
        if path.is_symlink():
            raise ValueError(f"不支持符号链接目标：{value}")
        relative = path.resolve().relative_to(root).as_posix()
        if relative == "." or path.is_dir():
            raise ValueError(f"只允许文件目标，不能递归提交目录：{value}")
        identity = str(path.resolve()).casefold()
        if identity in seen:
            raise ValueError(f"文件清单存在重复路径：{value}")
        seen.add(identity)
        if relative.split("/", 1)[0] in precommit.LOCAL_ONLY | {precommit.DATA_DIRECTORY}:
            raise ValueError(f"本地辅助文件和导表数据不由本脚本提交：{relative}")
        status_xml = run_svn(root, "status", "--xml", "--verbose", "--no-ignore", "--depth", "empty", "./" + relative + "@")
        nodes = ElementTree.fromstring(status_xml).findall(".//entry")
        if len(nodes) != 1 or nodes[0].find("wc-status") is None:
            raise ValueError(f"无法确定文件状态：{relative}")
        status = nodes[0].find("wc-status")
        item, props = status.get("item"), status.get("props")
        if (item in precommit.BLOCKING_ITEMS or props == "conflicted"
                or status.get("tree-conflicted") == "true" or status.get("switched") == "true"):
            raise ValueError(f"文件存在冲突、缺失或切换：{relative}（{item} / {props}）")
        if item == "unversioned":
            if not path.is_file():
                raise ValueError(f"新文件不存在：{relative}")
            node_relative = requested.parent.as_posix()
        elif item in precommit.CHANGED_ITEMS or (item == "normal" and props == "modified"):
            node_relative = relative
        else:
            raise ValueError(f"文件没有可提交改动或被忽略：{relative}（{item} / {props}）")
        node_info = info(root, node_relative)
        expected_url = url if node_relative == "." else url.rstrip("/") + "/" + quote(node_relative, safe="/")
        if (node_info.findtext("wc-info/wcroot-abspath") != wc_root
                or unquote(node_info.findtext("url") or "") != unquote(expected_url)
                or (item != "unversioned" and node_info.get("kind") != "file")):
            raise ValueError(f"目标不属于本分支的文件，或新文件父目录未被版本控制：{relative}")
        entries.append({"path": relative, "status": item, "props": props})
    return {"root": str(root), "branch": {"url": url, "kind": kind}, "message": message,
            "entries": entries, "changed_count": len(entries),
            "will_add": [entry["path"] for entry in entries if entry["status"] == "unversioned"]}


def verify_log(root, url, revision, message, paths):
    """读取指定修订，核验完整日志及实际变更路径集合。"""
    entry = ElementTree.fromstring(run_svn(root, "log", "--xml", "--verbose", "-r", str(revision), url)).find("logentry")
    if entry is None or entry.get("revision") != str(revision):
        raise ValueError(f"无法读取已提交修订 r{revision}")
    if (entry.findtext("msg") or "").replace("\r\n", "\n").rstrip("\n") != message.replace("\r\n", "\n").rstrip("\n"):
        raise ValueError(f"r{revision} 的仓库日志与确认的说明不一致")
    root_info = info(root, ".")
    repository = root_info.findtext("repository/root") or ""
    prefix = unquote(url[len(repository):]).rstrip("/")
    actual = [unquote(node.text or "") for node in entry.findall("paths/path")]
    expected = {prefix + "/" + path for path in paths}
    if len(actual) != len(expected) or set(actual) != expected:
        raise ValueError(f"r{revision} 的实际变更路径与确认的文件清单不一致：{actual}")


def submit(root_arg, paths, message_file, apply=False):
    """预览或执行一次定向提交；返回结果中的 error 表示失败，不能自动重试。

    Returns:
        dict: committed 为 False 表示未提交，None 表示提交结果不明，True 表示已提交。
            verified 单独表示仓库日志与路径核验是否通过；核验失败也不能重复提交。
    """
    result = {"dry_run": not apply, "committed": False, "verified": False}
    try:
        root = Path(root_arg).resolve()
        message = Path(message_file).read_text(encoding="utf-8-sig")
        result.update(prepare(root, paths, message))
        if not apply:
            return result
        targets = ["./" + entry["path"] + "@" for entry in result["entries"]]
        if result["will_add"]:
            run_svn(root, "add", "--depth", "empty", *["./" + path + "@" for path in result["will_add"]])
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, newline="") as handle:
            message_path = Path(handle.name)
            handle.write(message)
        try:
            # 事务发起后的任何通信失败都可能已经提交；留下未知状态，禁止自动重试。
            result["committed"] = None
            output = precommit.decode_output(run_svn(root, "commit", "--depth", "empty", "--encoding", "UTF-8",
                                                     "-F", str(message_path), *targets))
            match = re.search(r"(?:Committed revision|提交后的版本为)\s+([0-9]+)", output)
            if not match:
                raise ValueError(f"无法从 SVN 返回值确认提交修订；先查仓库日志，不能重复提交：{output}")
            result["committed"] = True
            result["revision"] = int(match[1])
        finally:
            message_path.unlink()
        verify_log(root, result["branch"]["url"], result["revision"], message,
                   [entry["path"] for entry in result["entries"]])
        result["verified"] = True
    except (precommit.PrecheckError, OSError, ValueError, ElementTree.ParseError) as error:
        result["error"] = str(error)
    return result


def main():
    """解析参数并输出 UTF-8 JSON；发生失败或提交结果不明时返回非零退出码。"""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="工作副本根目录")
    parser.add_argument("--path", action="append", required=True, help="待提交文件的相对路径，可重复")
    parser.add_argument("--message-file", required=True, help="已确认的完整说明，UTF-8 文本文件")
    parser.add_argument("--apply", action="store_true", help="实际添加新文件并提交；默认只读预览")
    args = parser.parse_args()
    result = submit(args.root, args.path, args.message_file, args.apply)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if "error" in result else 0


if __name__ == "__main__":
    sys.exit(main())
