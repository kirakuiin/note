#!/usr/bin/env python3
"""检查并修复共享 skill 目录到 Claude Code、Codex 全局 skill 目录的目录联接。

本 skill 和同目录下的其他 skill（例如笔记库 `9-Meta/Skills/`）共用一份真实文件，
通过 junction 链接进 `~/.claude/skills` 和 `~/.codex/skills`。这些联接曾被外部工具重置，
所以会话开始时（workspace.py context）自动核对并补建。

只处理链接：缺失时新建，指向别处或失效时替换；同名的普通目录或文件一律不动，记为问题。
删除旧链接只移除链接本身，不会删除任何目标目录。
"""
import json
import os
from pathlib import Path
import stat
import sys

SKILL = Path(__file__).resolve().parents[1]


def tool_skill_dirs(home=None):
    """返回已安装工具的全局 skill 目录；工具目录（~/.claude、~/.codex）不存在时跳过。"""
    home = Path(home) if home else Path.home()
    return [home / tool / "skills" for tool in (".claude", ".codex") if (home / tool).is_dir()]


def _is_link(path):
    """路径本身是符号链接或 Windows 目录联接，不跟随目标。"""
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def _same(link, target):
    try:
        return link.resolve(strict=True) == target.resolve(strict=True)
    except OSError:
        return False


def _make_link(link, target):
    if os.name == "nt":
        import _winapi  # CPython 自带；junction 不需要管理员权限，也不受开发者模式影响。
        _winapi.CreateJunction(str(target), str(link))
    else:
        os.symlink(target, link, target_is_directory=True)


def _remove_link(link):
    # Windows 上目录联接和目录符号链接都按目录移除；只删链接，不触及目标。
    (os.rmdir if os.name == "nt" else os.unlink)(link)


def repair(source_root=None, skill_dirs=None):
    """确保 source_root 下每个含 SKILL.md 的子目录都链接进各工具的全局 skill 目录。

    source_root 本身就是某个工具的 skill 目录时（skill 直接安装、没有共享目录）不做任何事。

    Args:
        source_root: 共享 skill 目录，默认是本 skill 的上级目录。
        skill_dirs: 要维护的全局 skill 目录，默认见 tool_skill_dirs。

    Returns:
        {"created": [...], "replaced": [...], "problems": [...]}，列表项为链接路径或问题说明；
        全部正常时三个列表都为空。
    """
    source_root = Path(source_root or SKILL.parent).resolve()
    skill_dirs = [Path(path) for path in (skill_dirs if skill_dirs is not None else tool_skill_dirs())]
    result = {"created": [], "replaced": [], "problems": []}
    if any(_same(directory, source_root) for directory in skill_dirs if directory.exists()):
        return result
    skills = sorted(path for path in source_root.iterdir() if (path / "SKILL.md").is_file())
    for directory in skill_dirs:
        for skill in skills:
            link = directory / skill.name
            try:
                if not os.path.lexists(link):
                    directory.mkdir(parents=True, exist_ok=True)
                    _make_link(link, skill)
                    result["created"].append(str(link))
                elif not _is_link(link):
                    result["problems"].append(f"{link} 是普通目录或文件，未替换为指向 {skill} 的链接")
                elif not _same(link, skill):
                    _remove_link(link)
                    _make_link(link, skill)
                    result["replaced"].append(str(link))
            except OSError as error:
                result["problems"].append(f"{link}：{error}")
    return result


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    result = repair()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["problems"] else 0


if __name__ == "__main__":
    sys.exit(main())
