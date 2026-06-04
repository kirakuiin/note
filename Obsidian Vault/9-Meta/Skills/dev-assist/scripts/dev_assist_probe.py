#!/usr/bin/env python3
"""Phase-1 probe for the dev-assist skill."""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable


MAX_TOKENS = 8
SPELL_ACTIONS = ("施放", "施法", "释放", "使用")
CHINESE_PRIORITY_TERMS = (
    "战斗外",
    "战斗内",
    "法术",
    "技能",
    "白名单",
    "快捷栏",
    "属性面板",
    "模式",
    "机制",
    "链路",
    "流程",
    "入口",
    "字段",
    "状态",
    "配置",
    "按钮",
)
CHINESE_RE = re.compile(r"[\u4e00-\u9fff]+")
SNAKE_RE = re.compile(r"\b[a-z_][a-z0-9_]{2,}\b")
CAMEL_RE = re.compile(r"\b[A-Z][a-zA-Z0-9]{2,}\b")
LOW_VALUE_CODE_TOKENS = {
    "class",
    "false",
    "for",
    "function",
    "if",
    "method",
    "module",
    "return",
    "true",
    "var",
    "while",
}


def _add(candidates: list[tuple[int, int, str]], seen: set[str], strength: int, token: str) -> None:
    token = token.strip()
    if not token or token in seen:
        return
    if token.lower() in LOW_VALUE_CODE_TOKENS:
        return
    seen.add(token)
    candidates.append((strength, len(candidates), token))


def _path_parts(paths: Iterable[str]) -> list[str]:
    parts: list[str] = []
    for raw in paths:
        for part in re.split(r"[\\/]+", raw):
            if not part or part.endswith(":"):
                continue
            parts.append(Path(part).stem)
    return parts


def _extract_code_tokens(text: str, candidates: list[tuple[int, int, str]], seen: set[str], strength: int) -> None:
    for match in SNAKE_RE.finditer(text):
        _add(candidates, seen, strength, match.group(0))
    for match in CAMEL_RE.finditer(text):
        token = match.group(0)
        if len(token) <= 6:
            strength -= 1
        _add(candidates, seen, strength, token)


def _extract_chinese_tokens(text: str, candidates: list[tuple[int, int, str]], seen: set[str]) -> None:
    for term in CHINESE_PRIORITY_TERMS:
        if term in text:
            _add(candidates, seen, 80, term)

    if any(action in text for action in SPELL_ACTIONS):
        if "战斗外" in text and "法术" in text:
            _add(candidates, seen, 90, "战斗外法术使用")
        if "战斗外" in text and "技能" in text:
            _add(candidates, seen, 90, "战斗外技能使用")
        if "法术" in text:
            _add(candidates, seen, 84, "法术使用")
        if "技能" in text:
            _add(candidates, seen, 84, "技能使用")
        for action in ("施放", "施法", "释放"):
            _add(candidates, seen, 85, action)

    for match in CHINESE_RE.finditer(text):
        run = match.group(0)
        if len(run) < 2:
            continue
        for suffix in ("白名单", "链路", "流程", "机制", "模式"):
            idx = run.find(suffix)
            if idx > 0:
                start = max(0, idx - 4)
                _add(candidates, seen, 70, run[start : idx + len(suffix)])


def extract_tokens(task: str, cwd: str = "", open_files: Iterable[str] = ()) -> list[str]:
    """Extract up to eight probe tokens from task text and path strings."""
    candidates: list[tuple[int, int, str]] = []
    seen: set[str] = set()

    _extract_code_tokens(task, candidates, seen, 100)
    _extract_chinese_tokens(task, candidates, seen)

    path_text = " ".join(_path_parts([cwd, *open_files]))
    _extract_code_tokens(path_text, candidates, seen, 40)

    ranked = sorted(candidates, key=lambda item: (-item[0], item[1]))
    return [token for _, _, token in ranked[:MAX_TOKENS]]


def wiki_roots(vault: Path) -> list[Path]:
    roots = [vault / "Netease" / "2-Wiki", vault / "2-Wiki"]
    return [root for root in roots if root.exists()]


def find_rg() -> str | None:
    found = shutil.which("rg")
    if found:
        return found

    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return None

    pattern = str(
        Path(local_app_data)
        / "Microsoft"
        / "WinGet"
        / "Packages"
        / "BurntSushi.ripgrep.MSVC_*"
        / "ripgrep-*"
        / "rg.exe"
    )
    matches = glob.glob(pattern)
    return matches[0] if matches else None


def run_probe(task: str, cwd: str = "", open_files: Iterable[str] = (), vault: Path | None = None) -> dict:
    if vault is None:
        vault_value = os.environ.get("OBSIDIAN_VAULT")
        if not vault_value:
            return {"status": "no_vault_env", "tokens": [], "hits": []}
        vault = Path(vault_value)

    tokens = extract_tokens(task, cwd=cwd, open_files=open_files)
    if not tokens:
        return {"status": "no_tokens", "tokens": [], "hits": []}

    roots = wiki_roots(vault)
    if not roots:
        return {"status": "no_roots", "tokens": tokens, "hits": []}

    rg = find_rg()
    if not rg:
        return {"status": "rg_not_found", "tokens": tokens, "hits": []}

    cmd = [
        rg,
        "-i",
        "-l",
        "--type",
        "md",
        "--no-ignore-vcs",
        "--glob",
        "!_log.md",
        "--glob",
        "!_index.md",
    ]
    for token in tokens:
        cmd.extend(["-e", token])
    cmd.extend(str(root) for root in roots)

    completed = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if completed.returncode not in (0, 1):
        return {
            "status": "rg_error",
            "tokens": tokens,
            "hits": [],
            "stderr": completed.stderr.strip(),
        }

    hits = [line.strip().replace("\\", "/") for line in completed.stdout.splitlines() if line.strip()]
    return {"status": "hits" if hits else "no_hits", "tokens": tokens, "hits": hits}


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Run the dev-assist Phase-1 wiki probe.")
    parser.add_argument("--task", required=True, help="Current user task text.")
    parser.add_argument("--cwd", default=os.getcwd(), help="Current workspace path string.")
    parser.add_argument("--open-file", action="append", default=[], help="Open file path string. Repeatable.")
    parser.add_argument("--vault", default=os.environ.get("OBSIDIAN_VAULT"), help="Obsidian vault root.")
    args = parser.parse_args(argv)

    vault = Path(args.vault) if args.vault else None
    result = run_probe(args.task, cwd=args.cwd, open_files=args.open_file, vault=vault)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
