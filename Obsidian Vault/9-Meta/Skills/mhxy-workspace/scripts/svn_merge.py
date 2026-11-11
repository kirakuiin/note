#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SVN 合并：把源分支的修订合到当前工作副本，trunk、周期分支和研发分支走同一套流程。

子命令（都输出 JSON）：
  plan      只读。算出要合哪些修订、提交说明该怎么写、有什么挡路。
  run       执行合并。带 --commit 时校验通过就提交；否则停在工作副本等检查。
  continue  冲突由 agent 处理完之后接着做（校验，按 run 时的选择提交或停下）。
  commit    提交已经合好、还没提交的合并。
  abort     撤销没提交的合并，恢复合并前的本地修改。
  status    查看有没有未完成的合并。

两条硬性保证：
- 合并只用 `svn merge`，源地址统一到目标工作副本所在仓库的地址上（不同仓库直接拒绝），
  合并后和提交后各核对一次 svn:mergeinfo；没有记录合并信息的结果不能提交。
- 提交时工作副本里只有这次合并的内容：其他本地修改（如入口文件的受管区段）合并前暂存，结束后放回。

流程、冲突处理原则和授权要求见 references/svn-merge.md。
"""
import argparse
from datetime import datetime
import difflib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from xml.etree import ElementTree

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import precommit  # noqa: E402
import svn_commit  # noqa: E402
import workspace  # noqa: E402

LONG_TIMEOUT = 3600          # merge、update、commit 在大仓库上可能很慢
STATE_DIR = Path(".mhxy-workspace") / "merge"
SIDECAR = re.compile(r"\.(merge-left\.r\d+|merge-right\.r\d+|working|mine|r\d+|prej|rej|orig)$")
BLOCKING_ITEMS = {"added", "deleted", "replaced", "conflicted", "missing", "obstructed", "incomplete"}
TEXT_ENCODINGS = ("utf-8", "gb18030")
CODING_LINE = re.compile(r"^(?P<prefix>[ \t\f]*#.*?coding[:=][ \t]*)(?P<encoding>[-\w.]+)(?P<suffix>.*)$", re.S)
REPLACEMENT = b"\xef\xbf\xbd"


class MergeError(Exception):
    """合并无法继续；消息直接给用户看。"""


# ---------------------------------------------------------------- svn 基础

def svn_result(root, *args, timeout=600):
    completed = precommit.svn_process(root, *args, timeout=timeout)
    return (completed.returncode, precommit.decode_output(completed.stdout),
            precommit.decode_output(completed.stderr))


def svn(root, *args, timeout=600):
    code, out, err = svn_result(root, *args, timeout=timeout)
    if code:
        raise MergeError(f"svn {args[0]} 失败：{(err or out).strip()}")
    return out


def info(root, target="."):
    """读取 URL、仓库根、仓库标识和相对路径。target 可以是工作副本路径或 URL。"""
    entry = ElementTree.fromstring(svn(root, "info", "--xml", target)).find("entry")
    if entry is None:
        raise MergeError(f"读不到 SVN 信息：{target}")
    return {"url": entry.findtext("url") or "", "root": entry.findtext("repository/root") or "",
            "uuid": entry.findtext("repository/uuid") or "", "relative": entry.findtext("relative-url") or "",
            "revision": int(entry.get("revision") or 0)}


def status(root):
    """工作副本里所有非正常状态的条目。path 是相对根目录的正斜杠路径，根目录自己是 "."。"""
    tree = ElementTree.fromstring(svn(root, "status", "--xml", "--ignore-externals", "."))
    entries = []
    for parent in list(tree.findall("target")) + list(tree.findall("changelist")):
        for entry in parent.findall("entry"):
            wc = entry.find("wc-status")
            if wc is None:
                continue
            entries.append({
                "path": (entry.get("path") or ".").replace("\\", "/"),
                "item": wc.get("item") or "", "props": wc.get("props") or "none",
                "tree_conflicted": wc.get("tree-conflicted") == "true", "locked": wc.get("wc-locked") == "true",
                "changelist": parent.get("name") if parent.tag == "changelist" else None})
    return entries


def versioned(entries):
    """有实际改动或冲突的纳管条目。只是待在变更列表里、内容没变的文件（item 为 normal）不算。"""
    return [e for e in entries if e["item"] not in ("unversioned", "external", "ignored", "none", "normal")
            or e["props"] in ("modified", "conflicted") or e["tree_conflicted"]]


def is_conflicted(entry):
    return entry["item"] == "conflicted" or entry["props"] == "conflicted" or entry["tree_conflicted"]


def plain_edit(entry):
    """单纯内容被修改的文件：可以暂存再放回。"""
    return (entry["item"] == "modified" and entry["props"] in ("none", "normal")
            and not entry["tree_conflicted"] and not entry["locked"])


# ---------------------------------------------------------------- 源和修订

def resolve_source(root, source, target):
    """把源统一成目标仓库地址下的 URL。

    源可以是 URL（任何协议）、另一个工作副本的路径，或仓库内的相对路径（如 trunk、branchs/2026_dev/x）。
    协议或主机写法和目标不同也没关系：只取它在仓库里的相对路径，再接到目标的仓库根上。
    这样 svn 认得出是同一个仓库，才会记录 svn:mergeinfo；不是同一个仓库的直接拒绝。
    """
    text = source.strip()
    if "://" in text or (Path(text) / ".svn").is_dir():
        try:
            src = info(root, str(Path(text).resolve()) if "://" not in text else text)
        except MergeError as error:
            raise MergeError(f"读不到源 {source}：{error}") from None
        if src["uuid"] != target["uuid"]:
            raise MergeError(f"源 {source} 和目标不在同一个 SVN 仓库，合并不会记录 svn:mergeinfo，拒绝执行")
        relative = src["relative"]
    else:
        relative = "^/" + text.strip("/")
    url = target["root"] + relative[1:]
    try:
        info(root, url)
    except MergeError:
        raise MergeError(f"源分支不存在：{url}") from None
    if url.rstrip("/") == target["url"].rstrip("/"):
        raise MergeError("源和目标是同一个分支")
    return url


def revision_numbers(text):
    return sorted({int(token.rstrip("*").lstrip("r")) for token in text.split() if token.rstrip("*").lstrip("r").isdigit()})


def mergeinfo(root, kind, source, target, low, high):
    """kind 为 merged 或 eligible；只看 low..high 这一段，避免在老分支上列出全部历史。"""
    return set(revision_numbers(svn(root, "mergeinfo", "--show-revs", kind, "-r", f"{low}:{high}", source, target,
                                    timeout=LONG_TIMEOUT)))


def log_entries(root, source, low, high):
    """low..high 之间源分支上的提交：{修订号: {author, date, message, paths}}，paths 相对源分支根。"""
    base = "/" + info(root, source)["relative"][2:].strip("/")
    tree = ElementTree.fromstring(svn(root, "log", "--xml", "-v", "-r", f"{low}:{high}", source, timeout=LONG_TIMEOUT))
    result = {}
    for entry in tree.findall("logentry"):
        paths = set()
        for node in entry.findall("paths/path"):
            path = node.text or ""
            if path == base or path.startswith(base + "/"):
                paths.add(path[len(base):].lstrip("/") or ".")
        result[int(entry.get("revision"))] = {
            "author": entry.findtext("author") or "", "date": (entry.findtext("date") or "")[:19],
            "message": (entry.findtext("msg") or "").strip(), "paths": sorted(paths)}
    return result


def select_revisions(root, args, source):
    """按参数选出要合的修订，并标出已经合过的。返回 (待合修订的日志, 已合过的修订号列表)。"""
    if args.eligible:
        head = info(root, source)["revision"]
        low, high = args.min_rev or 1, args.max_rev or head
        wanted = sorted(mergeinfo(root, "eligible", source, ".", low, high) - set(args.skip_revs or []))
        if not wanted:
            return {}, []
        logs = log_entries(root, source, wanted[0], wanted[-1])
        return {rev: logs[rev] for rev in wanted if rev in logs}, []
    wanted = sorted(set(args.revs or []))
    if not wanted:
        raise MergeError("没有指定要合的修订：用 --revs 列出，或用 --eligible 合并所有还没合过的")
    logs = log_entries(root, source, wanted[0], wanted[-1])
    missing = [rev for rev in wanted if rev not in logs]
    if missing:
        raise MergeError("这些修订不在源分支上：" + "、".join(f"r{rev}" for rev in missing))
    eligible = mergeinfo(root, "eligible", source, ".", wanted[0], wanted[-1])
    return ({rev: logs[rev] for rev in wanted if rev in eligible}, [rev for rev in wanted if rev not in eligible])


def format_revisions(revs):
    """r1,r2,r5-r8 这样的压缩写法。"""
    parts, start, prev = [], None, None
    for rev in sorted(revs):
        if start is None:
            start = prev = rev
        elif rev == prev + 1:
            prev = rev
        else:
            parts.append(f"r{start}" if start == prev else f"r{start}-r{prev}")
            start = prev = rev
    if start is not None:
        parts.append(f"r{start}" if start == prev else f"r{start}-r{prev}")
    return ",".join(parts)


# ---------------------------------------------------------------- 提交说明

def check_message(message, kind):
    """格式和直接提交完全一样（见 svn-commit.md「格式」）。来源不用写进说明，svn:mergeinfo 里有记录。"""
    first = message.splitlines()[0] if message else ""
    if not re.match(r"^(?:finish )?#[0-9]+\s+\S", first):
        raise MergeError("说明首行必须是 `finish #工单号 工单名：改动描述`（trunk、周期分支）或 "
                         "`#工单号 工单名：改动描述`（研发分支）")
    if "auto commit:" in message.lower():
        raise MergeError("说明里不能出现 `auto commit:`")
    if (kind != "研发分支") != first.startswith("finish "):
        raise MergeError("trunk、周期分支的说明必须以 `finish #工单号` 开头" if kind != "研发分支"
                         else "研发分支的说明不加 finish，以 `#工单号` 开头")


def tracked_tickets(root):
    try:
        tasks = workspace.read_tracking(root / ".mhxy-workspace")[2]["tracked_tasks"]
    except Exception:  # 追踪文件缺失或损坏不影响合并，只是少一个提示
        return []
    return [{"id": str(task.get("id") or task.get("issue_id") or ""), "title": str(task.get("title") or "")}
            for task in tasks if isinstance(task, dict)]


# ---------------------------------------------------------------- 计划

def build_plan(root, args):
    target = info(root)
    try:
        kind = svn_commit.branch_kind(target["url"])
    except ValueError as error:
        raise MergeError(f"目标 {target['url']} 不是分支根目录：{error}") from None
    source = resolve_source(root, args.source, target)
    revisions, already = select_revisions(root, args, source)
    entries = versioned(status(root))
    blockers = [f"{e['path']}（{'锁定' if e['locked'] else '冲突' if is_conflicted(e) else e['item'] + '／属性' + e['props']}）"
                for e in entries if not plain_edit(e)]
    name = source.rstrip("/").rsplit("/", 1)[-1]
    tickets = sorted({t for item in revisions.values() for t in re.findall(r"#(\d{5,})", item["message"].splitlines()[0]
                                                                         if item["message"] else "")})
    warnings = []
    if kind != "研发分支" and len(tickets) > 1:
        warnings.append("这些修订来自多个工单（" + "、".join("#" + t for t in tickets) + "），外放分支建议按工单分开合并、分开提交")
    if already:
        warnings.append("已经合过、这次会跳过：" + format_revisions(already))
    return {
        "source": source, "source_name": name,
        "target": {"root": str(root), "url": target["url"], "kind": kind, "revision": target["revision"]},
        "revisions": [{"revision": rev, "author": item["author"], "date": item["date"],
                       "first_line": item["message"].splitlines()[0] if item["message"] else "",
                       "paths": item["paths"]} for rev, item in revisions.items()],
        "already_merged": already,
        "message": {"format": "finish #工单号 工单名：改动描述" if kind != "研发分支" else "#工单号 工单名：改动描述",
                    "source_tickets": tickets, "tracked_tickets": tracked_tickets(root)},
        "local_changes": [e["path"] for e in entries if plain_edit(e)],
        "blockers": blockers, "warnings": warnings,
    }


# ---------------------------------------------------------------- 状态文件和暂存

def state_path(root):
    return root / STATE_DIR / "state.json"


def load_state(root):
    path = state_path(root)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def save_state(root, state):
    path = state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def clear_state(root):
    state_path(root).unlink(missing_ok=True)


def stash(root, state, keep=()):
    """把单纯内容被修改、且不在 keep 里的文件备份后还原。记录在 state["stash"]。"""
    entries = [e for e in versioned(status(root)) if plain_edit(e) and e["path"] not in keep]
    if not entries:
        return []
    batch = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    base = root / STATE_DIR / "stash" / batch
    for entry in entries:
        local, pristine = base / "local" / entry["path"], base / "pristine" / entry["path"]
        local.parent.mkdir(parents=True, exist_ok=True)
        pristine.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / entry["path"], local)
        svn(root, "revert", entry["path"] + "@")
        shutil.copy2(root / entry["path"], pristine)
        state.setdefault("stash", []).append({"path": entry["path"], "batch": batch, "changelist": entry["changelist"]})
        save_state(root, state)
    return [e["path"] for e in entries]


def three_way(current, pristine, local):
    """把本地修改（local 相对 pristine）合到 current 上；两边改到同一处或没有 git 时返回 None。"""
    git = shutil.which("git")
    if not git:
        return None
    result = subprocess.run([git, "merge-file", "-p", str(current), str(pristine), str(local)], capture_output=True,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return result.stdout if result.returncode == 0 else None


def restore(root, state, skip=()):
    """放回暂存的本地修改。skip 里的路径先不放（合并也改了它们，要等提交之后）。

    返回 {"restored": [...], "remerged": [...], "kept": [{path, backup}], "pending": [...]}。
    remerged：文件在合并或更新里也变了，本地修改已三方合并上去。kept：两边改到同一处，没有覆盖，本地版本留在备份里。
    """
    result = {"restored": [], "remerged": [], "kept": [], "pending": []}
    remaining = []
    for item in state.get("stash", []):
        base = root / STATE_DIR / "stash" / item["batch"]
        local, pristine, path = base / "local" / item["path"], base / "pristine" / item["path"], root / item["path"]
        if item["path"] in skip:
            result["pending"].append(item["path"])
            remaining.append(item)
            continue
        if path.is_file() and path.read_bytes() == pristine.read_bytes():
            shutil.copy2(local, path)
            result["restored"].append(item["path"])
        else:
            merged = three_way(path, pristine, local) if path.is_file() else None
            if merged is None:
                result["kept"].append({"path": item["path"], "backup": str(local), "batch": item["batch"]})
                continue      # 备份保留在原处，不再当作待放回
            path.write_bytes(merged)
            result["remerged"].append(item["path"])
        if item.get("changelist"):
            svn_result(root, "changelist", item["changelist"], item["path"] + "@")
    state["stash"] = remaining
    kept_batches = {k.pop("batch") for k in result["kept"]}
    stash_root = root / STATE_DIR / "stash"
    if stash_root.is_dir():
        active = {item["batch"] for item in remaining} | kept_batches
        for batch in stash_root.iterdir():
            if batch.name not in active:
                shutil.rmtree(batch, ignore_errors=True)
    return result


# ---------------------------------------------------------------- 冲突

def sidecar(path, side):
    matches = sorted(path.parent.glob(path.name + f".{side}*"))
    return matches[0] if matches else None


def decode(data):
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8"), "utf-8-sig"
    for encoding in TEXT_ENCODINGS:
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return None, None


def hunks(base, other):
    matcher = difflib.SequenceMatcher(a=base, b=other, autojunk=False)
    return [(i1, i2, other[j1:j2]) for tag, i1, i2, j1, j2 in matcher.get_opcodes() if tag != "equal"]


def merge_hunks(base, first, second):
    """两组相对同一基准的改动不重叠时合成一份；有重叠（内容不同）返回 None。"""
    merged = []
    for start, end, replacement in [*first, *second]:
        duplicate = False
        for old_start, old_end, old_replacement in merged:
            if (start == end == old_start == old_end) or (start < old_end and old_start < end):
                if (start, end, replacement) == (old_start, old_end, old_replacement):
                    duplicate = True
                    break
                return None
        if not duplicate:
            merged.append((start, end, replacement))
    result, cursor = [], 0
    for start, end, replacement in sorted(merged, key=lambda item: (item[0], item[1])):
        if start < cursor:
            return None
        result += base[cursor:start] + replacement
        cursor = end
    return result + base[cursor:]


def utf8_coding_line(path, text):
    """Python 文件头两行里的编码声明改成 utf-8。"""
    if path.suffix.lower() != ".py":
        return text
    lines = text.splitlines(keepends=True)
    for index in range(min(2, len(lines))):
        match = CODING_LINE.match(lines[index])
        if match:
            lines[index] = match.group("prefix") + "utf-8" + match.group("suffix")
            return "".join(lines)
    return text


def resolve_encoding_conflict(root, relative):
    """源和目标文件编码不同造成的文本冲突：三方内容都能解码、两边改动不重叠时自动合好，统一存成 UTF-8。"""
    path = root / relative
    sides = [sidecar(path, name) for name in ("working", "merge-left", "merge-right")]
    if not path.is_file() or not all(sides):
        return None
    decoded = [decode(side.read_bytes()) for side in sides]
    if any(text is None for text, _ in decoded):
        return None
    (target_text, target_enc), (base_text, _), (source_text, source_enc) = decoded
    if target_enc == source_enc:
        return None     # 不是编码造成的冲突，属于真实的内容冲突
    base = base_text.splitlines(keepends=True)
    merged = merge_hunks(base, hunks(base, target_text.splitlines(keepends=True)),
                         hunks(base, source_text.splitlines(keepends=True)))
    if merged is None:
        return None
    path.write_bytes(utf8_coding_line(path, "".join(merged)).encode("utf-8"))
    svn(root, "resolve", "--accept", "working", relative + "@")
    return f"编码不同造成的冲突已自动合并并存为 UTF-8（目标 {target_enc}，源 {source_enc}）"


def externals(root):
    code, out, _ = svn_result(root, "propget", "svn:externals", "--xml", "-R", ".", timeout=LONG_TIMEOUT)
    if code:
        return {}
    result = {}
    for target in ElementTree.fromstring(out).findall("target"):
        prop = target.find("property")
        if prop is not None:
            result[(target.get("path") or ".").replace("\\", "/")] = prop.text or ""
    return result


def conflicted_properties(root, relative):
    out = svn(root, "info", relative + "@")
    match = re.search(r"^Conflicted Properties:\s*(.+)$", out, re.M)
    return {name.strip() for name in match.group(1).split(",")} if match else set()


def resolve_externals_conflict(root, relative, before):
    """只有 svn:externals 属性冲突时保留目标分支原来的外链（外链不跟着合并走）。"""
    if conflicted_properties(root, relative) != {"svn:externals"}:
        return None
    if relative in before:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, newline="") as handle:
            handle.write(before[relative])
        try:
            svn(root, "propset", "svn:externals", "-F", handle.name, relative + "@")
        finally:
            Path(handle.name).unlink(missing_ok=True)
    else:
        svn(root, "propdel", "svn:externals", relative + "@")
    svn(root, "resolve", "--accept", "working", relative + "@")
    return "svn:externals 属性冲突：保留目标分支原来的外链"


def handle_conflicts(root, state):
    """先自动处理能安全处理的两类冲突，返回剩下需要 agent 处理的冲突清单。"""
    remaining = []
    for entry in versioned(status(root)):
        if not is_conflicted(entry):
            continue
        relative, note = entry["path"], None
        state.setdefault("conflicted", [])
        if relative not in state["conflicted"]:
            state["conflicted"].append(relative)
        if not entry["tree_conflicted"]:
            if entry["props"] == "conflicted" and entry["item"] != "conflicted":
                note = resolve_externals_conflict(root, relative, state.get("externals", {}))
            elif entry["item"] == "conflicted" and entry["props"] != "conflicted":
                note = resolve_encoding_conflict(root, relative)
        if note:
            state.setdefault("auto_resolved", []).append({"path": relative, "how": note})
            continue
        path = root / relative
        remaining.append({
            "path": relative,
            "kind": "树冲突" if entry["tree_conflicted"] else "属性冲突" if entry["item"] != "conflicted" else "文本冲突",
            "files": {name: str(side) for name, side in (("目标分支原内容", sidecar(path, "working")),
                                                          ("共同基准", sidecar(path, "merge-left")),
                                                          ("源分支内容", sidecar(path, "merge-right"))) if side}})
    save_state(root, state)
    return remaining


# ---------------------------------------------------------------- 合并后的校验

def base_content(root, relative):
    completed = precommit.svn_process(root, "cat", "-r", "BASE", relative + "@", timeout=600)
    return completed.stdout if completed.returncode == 0 else None


def compiles(data, name):
    try:
        compile(data, name, "exec")
        return True
    except (SyntaxError, ValueError):
        return False


def verify(root, state):
    """提交前的全部检查。返回 (硬性问题, 需要人看的差异, 这次合并改动的路径)。硬性问题不为空就不能提交。"""
    problems, entries = [], status(root)
    changed = versioned(entries)
    for entry in changed:
        if is_conflicted(entry):
            problems.append(f"还有冲突没处理：{entry['path']}")
    leftovers = [e["path"] for e in entries if e["item"] == "unversioned" and SIDECAR.search(e["path"])]
    if leftovers:
        problems.append("还有冲突留下的临时文件，处理完冲突后删掉：" + "、".join(leftovers[:10]))
    revs = state["revisions"]
    merged = mergeinfo(root, "merged", state["source"], ".", revs[0], revs[-1])
    lost = [rev for rev in revs if rev not in merged]
    if lost:
        problems.append("svn:mergeinfo 没有记录这些修订：" + format_revisions(lost)
                        + "。这次合并结果不能提交，用 abort 撤销后查明原因（不要手工补属性，也不要改用拷贝文件的办法）")
    paths = sorted(e["path"] for e in changed)
    for relative in paths:
        path = root / relative
        if not path.is_file():
            continue
        data = path.read_bytes()
        if any(line.startswith((b"<<<<<<< ", b">>>>>>> ")) for line in data.splitlines()):
            problems.append(f"文件里还有冲突标记：{relative}")
        if REPLACEMENT in data:
            base = base_content(root, relative) or b""
            if data.count(REPLACEMENT) > base.count(REPLACEMENT):
                problems.append(f"文件里出现了乱码替换字符（编码被破坏）：{relative}")
        if relative in state.get("conflicted", []) and path.suffix.lower() == ".py":
            base = base_content(root, relative)
            if base is not None and compiles(base, relative) and not compiles(data, relative):
                problems.append(f"处理冲突后 Python 语法不对了：{relative}")
    source_paths = set(state.get("source_paths", []))
    target_paths = set(paths) - {"."}
    review = []
    if source_paths - target_paths:
        review.append("源修订改了、但合并后目标没有变化的路径（可能目标已有相同内容）：" + "、".join(sorted(source_paths - target_paths)[:20]))
    if target_paths - source_paths:
        review.append("合并后目标多出来的改动（源修订里没有）：" + "、".join(sorted(target_paths - source_paths)[:20]))
    return problems, review, paths


def verify_committed(root, state, revision, target_url):
    """提交后读回日志和合并信息核对。"""
    entry = ElementTree.fromstring(svn(root, "log", "--xml", "-r", str(revision), target_url)).find("logentry")
    actual = ((entry.findtext("msg") if entry is not None else "") or "").replace("\r\n", "\n").rstrip("\n")
    errors = []
    if actual != state["message"].replace("\r\n", "\n").rstrip("\n"):
        errors.append("仓库里的提交说明和确认的不一致")
    revs = state["revisions"]
    merged = mergeinfo(root, "merged", state["source"], target_url, revs[0], revs[-1])
    lost = [rev for rev in revs if rev not in merged]
    if lost:
        errors.append("提交后的分支上 svn:mergeinfo 缺少：" + format_revisions(lost))
    return errors


# ---------------------------------------------------------------- 各阶段

def finish(root, state):
    """合并已落到工作副本、没有未处理的冲突：校验，然后提交或停下等检查。"""
    problems, review, paths = verify(root, state)
    state["merged_paths"] = paths
    result = {"source": state["source"], "revisions": format_revisions(state["revisions"]), "changed": paths,
              "auto_resolved": state.get("auto_resolved", []), "review": review}
    if problems:
        state["stage"] = "invalid" if any("mergeinfo" in p for p in problems) else "conflict"
        save_state(root, state)
        return {**result, "status": "blocked", "problems": problems, "committed": False,
                "next": "abort" if state["stage"] == "invalid" else "处理完上面的问题后运行 continue"}, 2
    if state.get("commit") and not review:
        return do_commit(root, state, result)
    state["stage"] = "merged"
    result["local_changes"] = restore(root, state, skip=set(paths))
    save_state(root, state)
    reason = "合并后的改动和源修订对不上，需要先看一下再提交" if review and state.get("commit") else "还没有提交"
    return {**result, "status": "merged", "committed": False, "reason": reason,
            "next": "检查无误后运行 commit；不要了运行 abort"}, (2 if review and state.get("commit") else 0)


def commit_allowed():
    """调用方（如后台服务）用环境变量 MHXY_NO_COMMIT=1 声明这个会话没有得到提交的批准。"""
    return os.environ.get("MHXY_NO_COMMIT", "") in ("", "0")


def do_commit(root, state, result):
    if not commit_allowed():
        state["stage"] = "merged"
        result["local_changes"] = restore(root, state, skip=set(state["merged_paths"]))
        save_state(root, state)
        return {**result, "status": "merged", "committed": False,
                "reason": "这个会话没有得到提交的批准（MHXY_NO_COMMIT），合并结果留在工作副本等用户提交",
                "next": "把合并结果报告给用户，由用户决定提交"}, 0
    stash(root, state, keep=set(state["merged_paths"]))     # 合并之后才出现的其他本地修改不跟着提交
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", delete=False, newline="") as handle:
        handle.write(state["message"])
    try:
        code, out, err = svn_result(root, "commit", "--encoding", "UTF-8", "-F", handle.name, ".", timeout=LONG_TIMEOUT)
    finally:
        Path(handle.name).unlink(missing_ok=True)
    match = re.search(r"Committed revision (\d+)\.", out) or re.search(r"提交后的版本为 (\d+)", out)
    if code or not match:
        state["stage"] = "merged"
        result["local_changes"] = restore(root, state, skip=set(state["merged_paths"]))
        save_state(root, state)
        return {**result, "status": "commit_failed", "committed": False,
                "error": (err or out).strip() or "没有读到提交后的版本号，先用 svn log 核对是否已经提交，不要重复提交",
                "next": "排除原因后运行 commit 重试"}, 1
    revision = int(match.group(1))
    target_url = info(root)["url"]
    errors = verify_committed(root, state, revision, target_url)
    svn_result(root, "update", "--ignore-externals", ".", timeout=LONG_TIMEOUT)
    result["local_changes"] = restore(root, state)
    clear_state(root)
    return {**result, "status": "committed", "committed": True, "revision": revision,
            "verified": not errors, "errors": errors, "message": state["message"]}, (1 if errors else 0)


def after_merge(root, state):
    conflicts = handle_conflicts(root, state)
    if conflicts:
        state["stage"] = "conflict"
        save_state(root, state)
        return {"status": "conflict", "committed": False, "source": state["source"],
                "revisions": format_revisions(state["revisions"]), "conflicts": conflicts,
                "auto_resolved": state.get("auto_resolved", []),
                "next": "按 svn-merge.md「冲突处理」逐个处理并 svn resolve --accept working，然后运行 continue"}, 2
    return finish(root, state)


def cmd_plan(root, args):
    plan = build_plan(root, args)
    plan["status"] = "blocked" if plan["blockers"] else "nothing_to_merge" if not plan["revisions"] else "planned"
    return plan, (2 if plan["blockers"] else 0)


def cmd_run(root, args):
    if load_state(root):
        raise MergeError("上一次合并还没结束：先用 status 查看，再 continue、commit 或 abort")
    plan = build_plan(root, args)
    if plan["blockers"]:
        return {**plan, "status": "blocked"}, 2
    if not plan["revisions"]:
        return {**plan, "status": "nothing_to_merge"}, 0
    message = Path(args.message_file).read_text(encoding="utf-8-sig")
    check_message(message, plan["target"]["kind"])
    revs = [item["revision"] for item in plan["revisions"]]
    state = {"source": plan["source"], "revisions": revs, "message": message, "commit": bool(args.commit),
             "stage": "merging", "started_at": datetime.now().isoformat(timespec="seconds"),
             "source_paths": sorted({p for item in plan["revisions"] for p in item["paths"]} - {"."})}
    save_state(root, state)
    try:
        stash(root, state)
        svn(root, "update", "--ignore-externals", ".", timeout=LONG_TIMEOUT)
        state["externals"] = externals(root)
        save_state(root, state)
        code, out, err = svn_result(root, "merge", "--accept", "postpone", "-c", ",".join(map(str, revs)),
                                    state["source"], ".", timeout=LONG_TIMEOUT)
    except Exception:
        restore(root, state)
        clear_state(root)
        raise
    if code and not any(is_conflicted(e) for e in versioned(status(root))):
        svn_result(root, "revert", "-R", ".")
        restore(root, state)
        clear_state(root)
        raise MergeError(f"svn merge 失败，工作副本已还原：{(err or out).strip()}")
    return after_merge(root, state)


def need_state(root, *stages):
    state = load_state(root)
    if not state:
        raise MergeError("没有未完成的合并")
    if stages and state["stage"] not in stages:
        hint = {"invalid": "这次合并没有记录 svn:mergeinfo，只能 abort", "merged": "已经合好了，用 commit 提交或 abort 撤销",
                "conflict": "还有冲突要处理，处理完运行 continue"}.get(state["stage"], state["stage"])
        raise MergeError(hint)
    return state


def cmd_continue(root, args):
    return after_merge(root, need_state(root, "conflict", "merging"))


def cmd_commit(root, args):
    state = need_state(root, "merged")
    if args.message_file:
        message = Path(args.message_file).read_text(encoding="utf-8-sig")
        check_message(message, svn_commit.branch_kind(info(root)["url"]))
        state["message"] = message
    problems, review, _ = verify(root, state)
    result = {"source": state["source"], "revisions": format_revisions(state["revisions"]),
              "changed": state["merged_paths"], "auto_resolved": state.get("auto_resolved", []), "review": review}
    if problems:
        save_state(root, state)
        return {**result, "status": "blocked", "problems": problems, "committed": False}, 2
    return do_commit(root, state, result)


def cmd_abort(root, args):
    state = need_state(root)
    merged = set(state.get("merged_paths") or [e["path"] for e in versioned(status(root))])
    stash(root, state, keep=merged)
    added = [e["path"] for e in versioned(status(root)) if e["item"] == "added" and e["path"] in merged]
    svn(root, "revert", "-R", ".", timeout=LONG_TIMEOUT)
    for entry in status(root):       # 还原后，合并带进来的新文件和冲突临时文件会变成未纳管文件
        if entry["item"] == "unversioned" and (entry["path"] in added or SIDECAR.search(entry["path"])):
            path = root / entry["path"]
            shutil.rmtree(path, ignore_errors=True) if path.is_dir() else path.unlink(missing_ok=True)
    local = restore(root, state)
    clear_state(root)
    return {"status": "aborted", "committed": False, "local_changes": local}, 0


def cmd_status(root, args):
    state = load_state(root)
    if not state:
        return {"status": "idle"}, 0
    return {"status": state["stage"], "source": state["source"], "revisions": format_revisions(state["revisions"]),
            "commit_after_merge": state.get("commit", False), "started_at": state.get("started_at"),
            "pending_local_changes": [item["path"] for item in state.get("stash", [])],
            "message": state["message"]}, 0


def main():
    parser = argparse.ArgumentParser(description="SVN 合并（记录 svn:mergeinfo）")
    commands = parser.add_subparsers(dest="command", required=True)

    def add(name, function, selectors=False, help_text=""):
        sub = commands.add_parser(name, help=help_text)
        sub.add_argument("--root", required=True, help="目标分支的工作副本根目录")
        if selectors:
            sub.add_argument("--source", required=True, help="源分支：URL、另一个工作副本的路径，或仓库内相对路径")
            sub.add_argument("--revs", nargs="*", type=lambda text: int(text.lstrip("r")), help="要合的修订号")
            sub.add_argument("--eligible", action="store_true", help="合并源分支上所有还没合过的修订")
            sub.add_argument("--min-rev", type=int)
            sub.add_argument("--max-rev", type=int)
            sub.add_argument("--skip-revs", nargs="*", type=lambda text: int(text.lstrip("r")))
        sub.set_defaults(function=function)
        return sub

    add("plan", cmd_plan, selectors=True, help_text="只读：要合什么、说明怎么写、有什么挡路")
    run = add("run", cmd_run, selectors=True, help_text="执行合并")
    run.add_argument("--message-file", required=True, help="已确认的完整提交说明，UTF-8 文本文件")
    run.add_argument("--commit", action="store_true", help="校验通过后直接提交（需要用户已经批准提交）")
    add("continue", cmd_continue, help_text="冲突处理完之后接着做")
    add("commit", cmd_commit, help_text="提交已经合好的合并").add_argument("--message-file")
    add("abort", cmd_abort, help_text="撤销没提交的合并")
    add("status", cmd_status, help_text="查看未完成的合并")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        root = Path(args.root).resolve()
        if not (root / ".svn").is_dir():
            raise MergeError(f"{root} 不是 SVN 工作副本的根目录")
        result, code = args.function(root, args)
    except (MergeError, precommit.PrecheckError, ValueError, OSError) as error:
        result, code = {"status": "error", "error": str(error), "committed": False}, 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
