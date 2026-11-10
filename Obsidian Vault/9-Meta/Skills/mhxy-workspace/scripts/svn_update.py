#!/usr/bin/env python3
"""更新 SVN 工作副本（规则见 references/svn-update.md），输出 JSON。

    svn_update.py --root <项目> [--code-only] [--clean-blockers] [--dry-run]

更新 <项目>（代码工作副本）和它上层的 ../_test（资源，保持当前 URL）。周期分支尽量切到下一个维护周。
挡住更新的内容自动处理，处理前先备份到 <项目>/.mhxy-workspace/backups/<时间>/（保留最近 5 次）：
- 默认：本地修改备份成 patch；更新产生冲突的文件采用服务器版本；挡住新增文件的未纳管文件挪进备份目录；
  工作副本被锁时 cleanup。不冲突的本地修改保留。
- --clean-blockers：备份后把全部本地修改 revert，再更新或切换（维护流程用）。
入口文件、.claude、.mhxy-workspace 和其余未纳管文件两种方式都不动。不提交，不创建或删除分支。
退出码：0 全部成功；2 部分完成（外链失败、仍有冲突、资源目录失败等）；1 代码工作副本失败或参数错误。
"""
import argparse
from datetime import date, datetime, timedelta
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
from xml.etree import ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
import precommit  # noqa: E402
import workspace  # noqa: E402

SVN_TIMEOUT = 3600  # update、switch、cleanup、status：资源工作副本很大，可能很慢。
INFO_TIMEOUT = 120
BACKUPS = "backups"  # 个人目录下的备份目录，每次运行一个 <YYYYMMDD-HHMMSS> 子目录。
BACKUP_NAME = re.compile(r"^\d{8}-\d{6}$")
BACKUP_KEEP = 5
RESOURCE = "_test"
CHANGED_ITEMS = {"modified", "added", "deleted", "replaced", "conflicted", "obstructed", "incomplete"}
NOT_FOUND_CODES = {"E200009", "W160013", "E160013"}  # svn list：目录在远端不存在（不是网络或权限失败）。
OBSTRUCTION_RETRIES = 20


class UpdateError(Exception):
    """可直接呈现的更新错误。"""


def svn(cwd, *args, timeout=SVN_TIMEOUT):
    try:
        return precommit.svn_process(cwd, *args, timeout=timeout)
    except precommit.SvnTimeout as error:
        raise UpdateError(f"{error}；命令可能仍未完成，先检查工作副本状态再决定是否重试") from None
    except precommit.PrecheckError as error:
        raise UpdateError(str(error)) from None


def output(completed):
    return precommit.decode_output(completed.stdout) + "\n" + precommit.decode_output(completed.stderr)


def error_text(completed, action):
    return precommit.decode_output(completed.stderr).strip() or f"svn {action} 失败，退出码 {completed.returncode}"


def error_codes(completed):
    return set(re.findall(r"\b[EW]\d{6}\b", precommit.decode_output(completed.stderr)))


def peg(path):
    """路径含 @ 时末尾补 @，避免被 svn 当作 peg 版本。"""
    return f"{path}@" if "@" in str(path) else str(path)


def wc_info(directory):
    """返回工作副本的 {"url", "branch", "revision"}；不是工作副本时抛 UpdateError。"""
    completed = svn(directory, "info", "--xml", ".", timeout=INFO_TIMEOUT)
    if completed.returncode:
        raise UpdateError(error_text(completed, "info"))
    entry = ElementTree.fromstring(completed.stdout).find("entry")
    url = entry.findtext("url")
    return {"url": url, "branch": url.rstrip("/").rsplit("/", 1)[-1], "revision": int(entry.get("revision"))}


def wc_status(directory):
    """主工作副本（不含外链）的状态条目：path、item、props、tree_conflict、locked。"""
    completed = svn(directory, "status", "--xml", "--ignore-externals", ".")
    if completed.returncode or b"155007" in completed.stderr:
        raise UpdateError(error_text(completed, "status"))
    entries = []
    for entry in ElementTree.fromstring(completed.stdout).iter("entry"):
        status = entry.find("wc-status")
        if status is None:
            continue
        entries.append({"path": entry.get("path", "").replace("\\", "/"), "item": status.get("item"),
                        "props": status.get("props"), "tree_conflict": status.get("tree-conflicted") == "true",
                        "locked": status.get("wc-locked") == "true"})
    return entries


def local_only(path):
    """入口文件和本地辅助目录由 sync 维护，不参与 revert 和挡路处理。"""
    return path.split("/", 1)[0] in precommit.LOCAL_ONLY


def is_changed(entry):
    return entry["item"] in CHANGED_ITEMS or entry["props"] in ("modified", "conflicted") or entry["tree_conflict"]


def is_conflicted(entry):
    return entry["item"] == "conflicted" or entry["props"] == "conflicted" or entry["tree_conflict"]


def unversioned_files(directory, entries):
    """未纳管的文件集合（未纳管目录展开为其中的文件），不含本地辅助文件；不跟随链接。"""
    found = set()
    for entry in entries:
        if entry["item"] != "unversioned" or local_only(entry["path"]):
            continue
        path = directory / entry["path"]
        if workspace.is_link(path):
            continue
        if path.is_dir():
            for base, dirnames, filenames in os.walk(path):
                dirnames[:] = [name for name in dirnames if not workspace.is_link(Path(base) / name)]
                found |= {(Path(base) / name).relative_to(directory).as_posix() for name in filenames}
        else:
            found.add(entry["path"])
    return found


def next_maintenance_day(today):
    """本地日期之后最近的周二；周二当天取下周二。"""
    return today + timedelta(days=(1 - today.weekday()) % 7 or 7)


def list_branches(directory, url):
    """列出远端目录下的子目录名；目录不存在时为空列表，其他失败抛 UpdateError（不当作分支不存在）。"""
    completed = svn(directory, "list", url, timeout=INFO_TIMEOUT)
    if completed.returncode:
        if error_codes(completed) & NOT_FOUND_CODES:
            return []
        raise UpdateError(f"无法列出远端分支 {url}：{error_text(completed, 'list')}")
    return [line.strip().rstrip("/") for line in precommit.decode_output(completed.stdout).splitlines() if line.strip()]


def choose_target(directory, url, today):
    """按 svn-update.md「选择目标」决定代码工作副本的目标 URL。

    Returns:
        (目标 URL, 说明)。不是周期分支时目标就是当前 URL。
    """
    match = workspace.PERIODIC_BRANCH.search(url)
    if not match:
        return url, "不是周期分支，保持当前分支"
    kind, current = match[1], date(int(match[2]), int(match[3]), int(match[4]))
    prefix = url[:url.rindex("/branchs/")] + "/branchs"
    target_day = next_maintenance_day(today)
    published = {}
    for year in range(current.year, max(target_day.year, current.year) + 1):
        for name in list_branches(directory, f"{prefix}/{year}_ship"):
            found = workspace.PERIODIC_NAME.match(name)
            if found and found[1] == kind:
                try:
                    published[date(int(found[2]), int(found[3]), int(found[4]))] = f"{prefix}/{year}_ship/{name}"
                except ValueError:
                    continue
    candidates = [day for day in published if current <= day <= target_day]
    wanted = f"{kind}_{target_day:%Y_%m_%d}"
    if not candidates:
        return url, f"目标维护周分支 {wanted} 尚未发布，也没有更新的已发布分支，保持当前分支"
    chosen = max(candidates)
    if chosen == target_day:
        return published[chosen], f"目标维护周 {wanted}"
    if chosen == current:
        return url, f"目标维护周分支 {wanted} 尚未发布，保持当前分支"
    return published[chosen], f"目标维护周分支 {wanted} 尚未发布，切到已发布的最新分支 {published[chosen].rsplit('/', 1)[-1]}"


class Backup:
    """一次运行的备份目录，用到时才创建；save 复制、take 挪走，都保持相对路径。"""

    def __init__(self, personal, stamp):
        self.base = personal / BACKUPS / stamp
        self.used = False

    def directory(self, name):
        target = self.base / name
        workspace.no_links(target)
        target.mkdir(parents=True, exist_ok=True)
        self.used = True
        return target

    def write_patch(self, name, data):
        (self.directory(name) / "local-changes.patch").write_bytes(data)

    def save(self, name, directory, relative):
        """把本地文件或目录原样存一份。已存过的不覆盖（先存的是更原始的本地状态）；本地不存在时没有可存的。

        Raises:
            UpdateError: 路径是链接，无法可靠备份；调用方据此放弃对它的后续处理。
            OSError: 复制失败。
        """
        source = directory / relative
        if not os.path.lexists(source):
            return
        if workspace.is_link(source):
            raise UpdateError(f"{relative} 是符号链接或目录联接，无法备份，未处理")
        target = self.directory(name) / "files" / relative
        if os.path.lexists(target):
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target, symlinks=True, ignore=shutil.ignore_patterns(".svn"))
        else:
            shutil.copy2(source, target)

    def take(self, name, directory, relative):
        """把本地文件或目录挪进备份；同名备份已存在时另取名字，不覆盖。"""
        source = directory / relative
        target = self.directory(name) / "files" / relative
        number = 2
        while os.path.lexists(target):
            target = target.with_name(f"{Path(relative).name}.{number}")
            number += 1
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))


def remove(path):
    def retry(function, target, *_):
        os.chmod(target, stat.S_IWRITE)
        function(target)
    if path.is_dir() and not workspace.is_link(path):
        if sys.version_info >= (3, 12):
            shutil.rmtree(path, onexc=retry)
        else:
            shutil.rmtree(path, onerror=retry)
    elif os.path.lexists(path):
        os.chmod(path, stat.S_IWRITE)
        path.unlink()


def prune_backups(personal):
    """只保留最近 BACKUP_KEEP 次备份；只删名称符合时间格式的普通目录。"""
    base = personal / BACKUPS
    if not base.is_dir() or workspace.is_link(base):
        return
    old = sorted(item for item in base.iterdir()
                 if BACKUP_NAME.match(item.name) and item.is_dir() and not workspace.is_link(item))[:-BACKUP_KEEP]
    for item in old:
        remove(item)


def resolve_conflicts(directory, name, entries, backup, handled, errors):
    """把冲突条目解决为服务器版本：先备份本地文件，文本／属性冲突取 theirs-full，树冲突还原本地一侧。

    每个条目都是“备份成功 → 逐步检查退出码”，任何一步失败就放弃该条目（留作冲突，由调用方报告），不再继续
    还原或删除。入口文件和本地辅助目录的树冲突不处理；它们的文本冲突照常取服务器版本，受管区段由 update 重新写回。
    """
    def checked(action, *args):
        completed = svn(directory, action, *args)
        if completed.returncode:
            raise UpdateError(error_text(completed, action))

    for entry in entries:
        if not is_conflicted(entry):
            continue
        path = entry["path"]
        try:
            if entry["tree_conflict"] and local_only(path):
                raise UpdateError("入口文件或本地辅助目录的树冲突不自动处理，请手动解决")
            backup.save(name, directory, path)
            if entry["tree_conflict"]:
                checked("revert", "--depth", "infinity", peg(path))
                checked("resolve", "--accept", "working", "--depth", "infinity", peg(path))
                leftover = [item for item in wc_status(directory)
                            if item["path"] == path and item["item"] == "unversioned"]
                if leftover:  # 服务器一侧已删除或换成别的条目，本地留下的内容已在备份里
                    remove(directory / path)
                checked("update", "--accept", "postpone", "--force", peg(path))
            else:
                checked("resolve", "--accept", "theirs-full", peg(path))
            handled["conflicts_resolved"].append(path)
        except (UpdateError, OSError) as error:
            errors.append(f"处理冲突 {path} 失败：{error}")


def run_update(directory, name, command, backup, handled):
    """执行 update／switch；工作副本被锁时 cleanup 后重试，文件和目录互相挡路时把本地一侧挪进备份后重试。

    Returns:
        (是否成功, 外链失败说明列表, 错误文本或 None)
    """
    cleaned = False
    for _ in range(OBSTRUCTION_RETRIES):
        completed = svn(directory, *command)
        codes = error_codes(completed)
        if not completed.returncode:
            return True, [], None
        if "E155004" in codes and not cleaned:
            cleanup = svn(directory, "cleanup")
            if cleanup.returncode:
                return False, [], error_text(cleanup, "cleanup")
            handled["cleanup"] = cleaned = True
            continue
        text = precommit.decode_output(completed.stderr)
        blocked = re.search(r"E155000: [^'\n]*'([^'\n]+)'", text) if "E155000" in codes else None
        target = Path(blocked[1]) if blocked else None
        if target is not None:  # 按词法路径判断是否在工作副本内，不跟随链接
            target = Path(os.path.abspath(target if target.is_absolute() else directory / target))
        if target is not None and os.path.lexists(target) and target.is_relative_to(directory) and target != directory:
            relative = target.relative_to(directory).as_posix()
            if workspace.is_link(target):
                return False, [], f"挡住更新的 {relative} 是符号链接或目录联接，请手动处理后重试"
            if not local_only(relative):
                backup.take(name, directory, relative)
                handled["moved_unversioned"].append(relative)
                continue
        failures = [line.strip() for line in text.splitlines() if "W205011" in line or "E205011" in line]
        if {code for code in codes if code.startswith("E")} == {"E205011"}:  # 只有外链失败，主工作副本已更新
            return True, failures or ["外链处理失败"], None
        return False, [], text.strip() or f"svn {command[0]} 失败，退出码 {completed.returncode}"
    return False, [], "挡路文件过多，已停止重试"


def update_working_copy(directory, name, target, backup, clean_blockers, dry_run, today=None):
    """更新一个工作副本并返回结果条目；target 为 None 时保持当前 URL（代码工作副本由 choose_target 决定）。"""
    handled = {"cleanup": False, "reverted": [], "conflicts_resolved": [], "moved_unversioned": []}
    result = {"name": name, "path": str(directory), "before": None, "target": None, "after": None,
              "operation": None, "status": "failed", "handled": handled, "conflicts": [],
              "external_failures": [], "errors": [], "notes": []}
    try:
        result["before"] = before = wc_info(directory)
        if target is None:
            target_url, reason = before["url"], "保持当前分支"
        else:
            target_url, reason = choose_target(directory, before["url"], today or date.today())
        result["target"] = {"url": target_url, "branch": target_url.rstrip("/").rsplit("/", 1)[-1], "reason": reason}
        switching = target_url != before["url"]
        result["operation"] = "switch" if switching else "update"
        entries = wc_status(directory)
        changed = sorted(entry["path"] for entry in entries if is_changed(entry))
        result["local_changes"] = len(changed)
        if dry_run:
            result["status"] = "planned"
            result["locked"] = any(entry["locked"] for entry in entries)
            return result
        if any(entry["locked"] for entry in entries):
            completed = svn(directory, "cleanup")
            if completed.returncode:
                raise UpdateError(error_text(completed, "cleanup"))
            handled["cleanup"] = True
            entries = wc_status(directory)
        if changed:
            diff = svn(directory, "diff", ".")
            if diff.stdout.strip():
                backup.write_patch(name, diff.stdout)
        resolve_conflicts(directory, name, entries, backup, handled, result["errors"])
        if clean_blockers:
            targets = [entry["path"] for entry in wc_status(directory)
                       if is_changed(entry) and not local_only(entry["path"]) and entry["path"] not in ("", ".")]
            for path in targets:  # 全部备份成功后才开始还原；任何一份备份失败就中止本工作副本
                backup.save(name, directory, path)
            # 父目录在前：还原新增目录时连同其中的条目一起还原
            for path in sorted(targets):
                if any(path.startswith(done + "/") for done in handled["reverted"]):
                    continue
                completed = svn(directory, "revert", "--depth", "infinity", peg(path))
                if completed.returncode:
                    raise UpdateError(error_text(completed, "revert"))
                handled["reverted"].append(path)
            if any(is_changed(entry) and entry["path"] in ("", ".") for entry in entries):
                result["notes"].append("工作副本根目录自身有属性改动，未还原")
        loose_before = unversioned_files(directory, wc_status(directory))
        command = (["switch", "--ignore-ancestry", target_url, "."] if switching else ["update", "."])
        ok, externals, error = run_update(directory, name, [*command, "--force", "--accept", "postpone"],
                                          backup, handled)
        result["external_failures"] = externals
        if not ok:
            raise UpdateError(error)
        # --force 让挡住新增文件的未纳管文件原地变成“已纳管且有修改”：挪进备份，换成服务器版本。
        after_entries = wc_status(directory)
        still_loose = unversioned_files(directory, after_entries)
        modified = {entry["path"] for entry in after_entries if entry["item"] in ("modified", "conflicted")}
        for path in sorted((loose_before - still_loose) & modified):
            try:
                backup.save(name, directory, path)
            except (UpdateError, OSError) as error:
                result["errors"].append(f"挡路文件 {path} 备份失败，保留本地内容：{error}")
                continue
            completed = svn(directory, "revert", peg(path))
            if completed.returncode:
                result["errors"].append(f"挡路文件 {path} 换成服务器版本失败：{error_text(completed, 'revert')}")
            else:
                handled["moved_unversioned"].append(path)
        resolve_conflicts(directory, name, wc_status(directory), backup, handled, result["errors"])
        result["after"] = after = wc_info(directory)
        result["conflicts"] = sorted(entry["path"] for entry in wc_status(directory) if is_conflicted(entry))
        if after["url"] != target_url:
            result["errors"].append(f"更新后分支不是目标分支：{after['url']}")
        if result["errors"]:
            result["status"] = "failed"
        elif result["conflicts"] or externals:
            result["status"] = "partial"
        else:
            result["status"] = "updated"
    except (UpdateError, OSError, ElementTree.ParseError) as error:
        result["errors"].append(str(error))
        try:
            result["after"] = wc_info(directory)
        except UpdateError:
            pass
    return result


def has_block(root):
    try:
        return workspace.block_info(workspace.decode_document(workspace.read_bytes(root / "AGENTS.md"))[0]) is not None
    except (workspace.WorkspaceError, OSError):
        return False


def update(root_arg, global_arg, code_only=False, clean_blockers=False, dry_run=False, today=None, stamp=None):
    root, personal, _ = workspace.paths(root_arg, global_arg)
    workspace.require_initialized(root)
    backup = Backup(personal, stamp or datetime.now().strftime("%Y%m%d-%H%M%S"))
    copies = [update_working_copy(root, root.name, "choose", backup, clean_blockers, dry_run, today)]
    entry_resolved = set(copies[0]["handled"]["conflicts_resolved"]) & set(workspace.ENTRY_FILES)
    if not dry_run and (entry_resolved or not has_block(root)):
        # 入口文件冲突后采用了服务器版本，受管区段随之丢失：重新写入
        try:
            workspace.sync(root, global_arg, apply=True)
            copies[0]["notes"].append("入口文件采用服务器版本后受管区段丢失，已重新写入")
        except (workspace.WorkspaceError, OSError) as error:
            copies[0]["errors"].append(f"入口文件的受管区段在更新中丢失且未能重新写入，请重新 sync：{error}")
            copies[0]["status"] = "failed"
    skipped = None
    if not code_only:
        resource = root.parent / RESOURCE
        if resource.is_dir() and (resource / ".svn").is_dir():
            copies.append(update_working_copy(resource, RESOURCE, None, backup, clean_blockers, dry_run))
        else:
            skipped = f"{resource} 不存在或不是独立的工作副本，跳过资源更新"
    if not dry_run:
        prune_backups(personal)
    code = copies[0]["status"]
    statuses = {item["status"] for item in copies}
    status = ("planned" if dry_run else "failed" if code == "failed"
              else "success" if statuses == {"updated"} else "partial")
    result = {"action": "svn-update", "dry_run": dry_run, "mode": "clean-blockers" if clean_blockers else "default",
              "status": status, "backup_dir": str(backup.base) if backup.used else None, "working_copies": copies}
    if skipped:
        result["resource_skipped"] = skipped
    return result


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=os.getcwd(), help="代码工作副本（项目根目录）")
    parser.add_argument("--global-config", default=str(Path.home() / workspace.DIRECTORY / "config.json"))
    parser.add_argument("--code-only", action="store_true", help="不更新 ../_test")
    parser.add_argument("--clean-blockers", action="store_true", help="备份后把全部本地修改 revert 再更新")
    parser.add_argument("--dry-run", action="store_true", help="只报告当前和目标分支、本地改动数量，不做任何修改")
    args = parser.parse_args(argv)
    try:
        result = update(args.root, args.global_config, args.code_only, args.clean_blockers, args.dry_run)
    except (UpdateError, workspace.WorkspaceError, OSError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return {"success": 0, "planned": 0, "partial": 2}.get(result["status"], 1)


if __name__ == "__main__":
    sys.exit(main())
