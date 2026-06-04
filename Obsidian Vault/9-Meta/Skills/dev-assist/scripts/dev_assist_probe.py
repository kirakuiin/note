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
DEFAULT_RULES_PATH = Path(__file__).resolve().parents[1] / "references" / "probe-rules.json"
CHINESE_RE = re.compile(r"[\u4e00-\u9fff]+")
SNAKE_RE = re.compile(r"\b[a-z_][a-z0-9_]{2,}\b")
CAMEL_RE = re.compile(r"\b[A-Z][a-zA-Z0-9]{2,}\b")


def load_rules(path: Path | None = None) -> dict:
    rules_path = path or DEFAULT_RULES_PATH
    with rules_path.open("r", encoding="utf-8") as file:
        rules = json.load(file)

    rules.setdefault("synonym_groups", [])
    rules.setdefault("phrase_stopwords", [])
    rules.setdefault("phrase_boost_terms", [])
    rules.setdefault("noise_tokens", [])
    return rules


def _add(
    candidates: list[tuple[int, int, str]],
    seen: set[str],
    noise: set[str],
    strength: int,
    token: str,
) -> None:
    token = token.strip()
    if not token or token in seen:
        return
    if token in noise or token.lower() in noise:
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


def _extract_code_tokens(
    text: str,
    candidates: list[tuple[int, int, str]],
    seen: set[str],
    noise: set[str],
    strength: int,
) -> None:
    for match in SNAKE_RE.finditer(text):
        _add(candidates, seen, noise, strength, match.group(0))
    for match in CAMEL_RE.finditer(text):
        token = match.group(0)
        if len(token) <= 6:
            strength -= 1
        _add(candidates, seen, noise, strength, token)


def _split_chinese_phrase(run: str, stopwords: list[str]) -> list[str]:
    if not stopwords:
        return [run]

    pattern = "|".join(re.escape(word) for word in sorted(stopwords, key=len, reverse=True))
    return [part for part in re.split(pattern, run) if part]


def _extract_chinese_phrases(
    text: str,
    candidates: list[tuple[int, int, str]],
    seen: set[str],
    noise: set[str],
    rules: dict,
) -> list[str]:
    phrases: list[str] = []
    stopwords = rules.get("phrase_stopwords", [])
    synonym_triggers = {
        term
        for group in rules.get("synonym_groups", [])
        for term in group.get("trigger_terms", group.get("terms", []))
    }
    phrase_boost_terms = set(rules.get("phrase_boost_terms", []))

    for match in CHINESE_RE.finditer(text):
        for phrase in _split_chinese_phrase(match.group(0), stopwords):
            if not 3 <= len(phrase) <= 12:
                continue
            phrases.append(phrase)
            boost = 8 if any(term in phrase for term in synonym_triggers | phrase_boost_terms) else 0
            _add(candidates, seen, noise, 74 + min(len(phrase), 8) + boost, phrase)

    return phrases


def _apply_synonyms(
    text: str,
    phrases: list[str],
    candidates: list[tuple[int, int, str]],
    seen: set[str],
    noise: set[str],
    rules: dict,
) -> None:
    for group in rules.get("synonym_groups", []):
        terms = group.get("terms", [])
        triggers = group.get("trigger_terms", terms)
        contextual_only = set(group.get("contextual_only", []))

        if not any(term in text for term in triggers):
            continue

        for term in terms:
            if term not in contextual_only:
                _add(candidates, seen, noise, 84, term)

        for phrase in phrases:
            if len(phrase) < 6:
                continue
            for source in terms:
                if source not in phrase:
                    continue
                for target in contextual_only:
                    expanded = phrase.replace(source, target)
                    if expanded != phrase:
                        _add(candidates, seen, noise, 88, expanded)


def extract_tokens(task: str, cwd: str = "", open_files: Iterable[str] = (), rules: dict | None = None) -> list[str]:
    """Extract up to eight probe tokens from task text and path strings."""
    rules = rules or load_rules()
    noise = {str(token).lower() for token in rules.get("noise_tokens", [])}
    candidates: list[tuple[int, int, str]] = []
    seen: set[str] = set()

    _extract_code_tokens(task, candidates, seen, noise, 100)
    phrases = _extract_chinese_phrases(task, candidates, seen, noise, rules)
    _apply_synonyms(task, phrases, candidates, seen, noise, rules)

    path_text = " ".join(_path_parts([cwd, *open_files]))
    _extract_code_tokens(path_text, candidates, seen, noise, 40)

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


def run_probe(
    task: str,
    cwd: str = "",
    open_files: Iterable[str] = (),
    vault: Path | None = None,
    rules_path: Path | None = None,
) -> dict:
    if vault is None:
        vault_value = os.environ.get("OBSIDIAN_VAULT")
        if not vault_value:
            return {"status": "no_vault_env", "tokens": [], "hits": []}
        vault = Path(vault_value)

    rules = load_rules(rules_path)
    tokens = extract_tokens(task, cwd=cwd, open_files=open_files, rules=rules)
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
    parser.add_argument("--rules", default=str(DEFAULT_RULES_PATH), help="Probe rules JSON path.")
    args = parser.parse_args(argv)

    vault = Path(args.vault) if args.vault else None
    result = run_probe(args.task, cwd=args.cwd, open_files=args.open_file, vault=vault, rules_path=Path(args.rules))
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
