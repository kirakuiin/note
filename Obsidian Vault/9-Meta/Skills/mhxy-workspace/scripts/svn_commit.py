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

COMMIT_TIMEOUT = 3600  # 大文件提交可能很慢，与 branch.py 的 SVN_TIMEOUT 一致。
# 事务在本地检查、服务端校验或 pre-commit 钩子阶段被拒绝、确定没有生效的错误码：工作副本被锁、不是工作副本、
# 节点不存在、版本过旧、冲突、仓库路径不存在／已存在、事务冲突、钩子拒绝、非法目标。
# 只有错误输出中的错误码全部属于此列时才报告 committed: false；超时、连接中断和其他错误一律视为结果不明。
REJECTED_CODES = {"E155004", "E155007", "E155010", "E155011", "E155015", "E160013", "E160020", "E160024",
                  "E160028", "E165001", "E170004", "E200009"}
DIRECTORY_ERROR = "只允许文件目标；新目录、目录属性修改和目录删除由用户自行提交"


def run_svn(root, *args):
    """通过 Python 直接调用 svn.exe，返回标准输出字节；失败立即停止。"""
    completed = precommit.svn_process(root, *args)
    if completed.returncode:
        raise precommit.PrecheckError(precommit.decode_output(completed.stderr).strip()
                                     or precommit.decode_output(completed.stdout).strip())
    return completed.stdout


def commit_process(root, *args):
    """运行 svn commit，使用较长的超时；结果由 run_commit 解释。"""
    return precommit.svn_process(root, "commit", *args, timeout=COMMIT_TIMEOUT)


def branch_kind(url):
    """只接受 trunk 和带日期的周期分支，判定规则复用 workspace.classify_branch，不按名称子串推断研发分支。"""
    kind = workspace.classify_branch(url)
    if kind in ("trunk", "周期分支"):
        return kind
    raise ValueError("本脚本只用于 trunk 和周期分支（<类型>_YYYY_MM_DD）；研发分支使用 openforge")


def info(root, target):
    """读取目标的 SVN 元数据；@ 后缀避免把文件名中的 @ 当作 peg revision。"""
    entry = ElementTree.fromstring(run_svn(root, "info", "--xml", "--depth", "empty", "./" + target + "@")).find("entry")
    if entry is None:
        raise ValueError(f"无法读取 SVN 元数据：{target}")
    return entry


def node_status(root, relative):
    """返回单个节点的 (wc-status 元素, 变更列表名)；svn 没有给出该节点状态时返回 (None, None)。"""
    tree = ElementTree.fromstring(run_svn(root, "status", "--xml", "--verbose", "--no-ignore", "--depth", "empty",
                                          "./" + relative + "@"))
    nodes = []
    for parent in list(tree.iter("target")) + list(tree.iter("changelist")):
        changelist = parent.get("name") if parent.tag == "changelist" else None
        nodes += [(entry.find("wc-status"), changelist) for entry in parent.findall("entry")]
    if len(nodes) != 1 or nodes[0][0] is None:
        return None, None
    return nodes[0]


def check_ancestors(root, relative):
    """从上往下检查目标的每级上级目录都已提交到仓库。

    上级目录是新目录时 `--depth empty` 提交必然失败（E200009）；位于未纳管目录中时 svn 查不到文件状态。
    这两种情况和目录删除一样，交给用户自己提交。
    """
    parts = relative.split("/")[:-1]
    for depth in range(1, len(parts) + 1):
        ancestor = "/".join(parts[:depth])
        status, _ = node_status(root, ancestor)
        item = status.get("item") if status is not None else None
        if item == "normal":
            continue
        if item == "unversioned":
            raise ValueError(f"{relative} 位于未纳入版本控制的目录 {ancestor}/ 中；新目录由用户自行提交")
        if item in ("added", "replaced"):
            raise ValueError(f"{relative} 的上级目录 {ancestor}/ 是尚未提交的新目录；新目录由用户自行提交")
        if item == "deleted":
            raise ValueError(f"{relative} 的上级目录 {ancestor}/ 已被删除；目录删除由用户自行提交")
        raise ValueError(f"{relative} 的上级目录 {ancestor}/ 状态为 {item}，不能定向提交")


def prepare(root, paths, message):
    """只读核对分支、说明和每个文件的状态，拒绝目录、跨工作副本目标和 ignore-on-commit 中的文件。

    新文件要求其各级上级目录都已提交到仓库，预览不会自动 svn add。
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
            raise ValueError(f"{DIRECTORY_ERROR}：{value}")
        identity = str(path.resolve()).casefold()
        if identity in seen:
            raise ValueError(f"文件清单存在重复路径：{value}")
        seen.add(identity)
        if relative.split("/", 1)[0] in precommit.LOCAL_ONLY | {precommit.DATA_DIRECTORY}:
            raise ValueError(f"本地辅助文件和导表数据不由本脚本提交：{relative}")
        check_ancestors(root, relative)
        status, changelist = node_status(root, relative)
        if status is None:
            raise ValueError(f"无法确定文件状态：{relative}")
        if changelist == workspace.IGNORE_ON_COMMIT:
            raise ValueError(f"{relative} 在 {workspace.IGNORE_ON_COMMIT} 变更列表中（提交时默认排除），不由本脚本提交；"
                             "确需提交时由用户先移出该列表")
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
        if node_info.findtext("wc-info/wcroot-abspath") != wc_root:
            raise ValueError(f"目标位于其他工作副本（如外链）中，不由本脚本提交：{relative}")
        if item != "unversioned" and node_info.get("kind") != "file":
            raise ValueError(f"{DIRECTORY_ERROR}：{relative}")
        if unquote(node_info.findtext("url") or "") != unquote(expected_url):
            raise ValueError(f"目标已切换或不属于本分支：{relative}")
        entries.append({"path": relative, "status": item, "props": props, "changelist": changelist})
    return {"root": str(root), "branch": {"url": url, "kind": kind}, "message": message,
            "entries": entries, "changed_count": len(entries),
            "will_add": [entry["path"] for entry in entries if entry["status"] == "unversioned"]}


def run_commit(root, targets, message_path):
    """执行一次提交，返回 (committed, revision, error)；committed 的含义见 submit。"""
    try:
        completed = commit_process(root, "--depth", "empty", "--encoding", "UTF-8", "-F", str(message_path), *targets)
    except precommit.SvnTimeout:
        return None, None, "提交超时，结果不明，可能需要 cleanup；先只读查询仓库日志确认是否已提交，不能重复提交"
    except precommit.PrecheckError as error:
        return False, None, str(error)  # svn 无法启动，没有发起提交。
    output = precommit.decode_output(completed.stdout)
    match = re.search(r"(?:Committed revision|提交后的版本为)\s+([0-9]+)", output)
    if match:
        # 已有新修订号就算已提交；post-commit 钩子等告警不改变这一事实，交给后续日志核验。
        return True, int(match[1]), None
    detail = (precommit.decode_output(completed.stderr).strip() or output.strip()
              or f"svn commit 退出码 {completed.returncode}")
    if not completed.returncode:
        return None, None, f"无法从 SVN 返回值确认提交修订；先查仓库日志，不能重复提交：{detail}"
    codes = set(re.findall(r"\bE\d{6}\b", detail))
    if codes and codes <= REJECTED_CODES:
        return False, None, f"提交被拒绝，没有生效：{detail}"
    return None, None, f"提交结果不明；先只读查询仓库日志确认是否已提交，不能重复提交：{detail}"


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
        dict: committed 为 False 表示未提交（含提交被拒绝），None 表示提交结果不明，True 表示已提交。
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
            committed, revision, error = run_commit(root, targets, message_path)
        finally:
            # 提交结果已定，临时文件被占用删不掉也不能改变 committed。
            try:
                message_path.unlink()
            except OSError:
                pass
        result["committed"] = committed
        if error:
            raise ValueError(error)
        result["revision"] = revision
        try:
            precommit.forget_reviewed(root, [entry["path"] for entry in result["entries"]])
        except (workspace.WorkspaceError, OSError) as error:
            # 已经提交成功，review 记录更新失败只作提醒。
            result["warnings"] = [f"review 记录未能删除已提交的文件：{error}"]
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
