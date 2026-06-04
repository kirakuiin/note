#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scan_frontmatter.py — Scan vault .md files for frontmatter completeness.

Checks each .md file for required frontmatter fields based on its area:
  - All files: area, visibility
  - knowledge (2-Wiki/): tags, status
  - session (1-Sessions/): tags, date, topic
  - project (3-Projects/): tags, status
  - journal (4-Journal/): date
  - meta (9-Meta/): (no extra required)

Usage:
  python scan_frontmatter.py [--vault <path>] [--fix] [--json]

Output:
  Table of files with missing fields. With --fix, auto-fills safe defaults.
  With --json, outputs JSON for programmatic consumption.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path


# --- Configuration ---

VAULT_ROOT = Path(__file__).resolve().parent.parent.parent.parent  # 9-Meta/Scripts/maintenance -> vault root

REQUIRED_FIELDS = {
    "all": ["area", "visibility"],
    "knowledge": ["tags", "status"],
    "session": ["tags", "date", "topic"],
    "project": ["tags", "status"],
    "journal": ["date"],
    "meta": [],
}

AREA_PATH_MAP = {
    "2-Wiki": "knowledge",
    "1-Sessions": "session",
    "3-Projects": "project",
    "4-Journal": "journal",
    "9-Meta": "meta",
    "0-Inbox": "all",
    "5-Life": "all",
    "6-Tools": "all",
}

SAFE_DEFAULTS = {
    "area": None,  # must be inferred
    "visibility": None,  # must be inferred from path (public vs private)
    "status": "archived",  # user decision: all migrated notes are archived
    "tags": [],  # will be inferred from path
    "date": None,  # must be provided
    "topic": "",
}

# Path prefix -> default tags (must be in TAGS.md whitelist)
PATH_TAG_MAP = {
    "2-Wiki/编程语言": ["编程语言"],
    "2-Wiki/游戏开发": ["游戏开发"],
    "2-Wiki/算法与数据结构": ["算法与数据结构"],
    "2-Wiki/AI与Agent": ["AI与Agent"],
    "2-Wiki/英语": ["英语"],
    "2-Wiki/方法论": ["方法论"],
    "2-Wiki/计科基础": ["编程语言"],  # fallback: 计科基础不在白名单，归入编程语言
    "1-Sessions": ["from-session"],
    "3-Projects": ["项目"],
    "4-Journal": ["from-session"],  # fallback: journal 不在白名单
    "5-Life": ["方法论"],  # fallback: life 不在白名单
    "6-Tools": ["工具"],
    "0-Inbox": ["速查"],  # fallback
}


# --- Frontmatter parsing (stdlib only, no PyYAML dependency) ---

def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parse YAML frontmatter from markdown text. Returns (frontmatter_dict, body)."""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    fm_text = parts[1].strip()
    body = parts[2]
    fm = {}
    for line in fm_text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            fm[key] = value
    return fm, body


def infer_area(file_path: Path, vault_root: Path) -> str:
    """Infer area from file path relative to vault root."""
    try:
        rel = file_path.relative_to(vault_root)
    except ValueError:
        return "unknown"
    parts = rel.parts
    if len(parts) >= 1:
        top = parts[0]
        for prefix, area in AREA_PATH_MAP.items():
            if top == prefix:
                return area
    return "unknown"


def get_required_fields(area: str) -> list[str]:
    """Get required fields for a given area."""
    fields = list(REQUIRED_FIELDS.get("all", []))
    fields.extend(REQUIRED_FIELDS.get(area, []))
    return fields


# --- Main scan logic ---

def scan_vault(vault_root: Path) -> list[dict]:
    """Scan all .md files and return list of issues."""
    issues = []
    for md_file in vault_root.rglob("*.md"):
        # Skip hidden dirs and template placeholders
        if any(part.startswith(".") for part in md_file.parts):
            continue
        if md_file.name.startswith("_"):
            continue  # _index.md and _log.md are meta files

        try:
            text = md_file.read_text(encoding="utf-8")
        except Exception:
            continue

        fm, _ = parse_frontmatter(text)
        area = fm.get("area") or infer_area(md_file, vault_root)
        required = get_required_fields(area)

        missing = [f for f in required if f not in fm or not fm[f]]
        if missing:
            issues.append({
                "file": str(md_file.relative_to(vault_root)),
                "area": area,
                "missing": missing,
                "current": {k: fm.get(k) for k in required},
            })

    return issues


def auto_fix(issues: list[dict], vault_root: Path, only_fields: list[str] | None = None) -> list[dict]:
    """Auto-fill missing frontmatter with safe defaults. Returns list of fixes applied.
    If only_fields is provided, only fix those fields (skip others)."""
    fixes = []
    for issue in issues:
        file_path = vault_root / issue["file"]
        text = file_path.read_text(encoding="utf-8")
        fm, body = parse_frontmatter(text)

        for field in issue["missing"]:
            if only_fields and field not in only_fields:
                continue
            default = SAFE_DEFAULTS.get(field)
            if field == "area":
                # Infer area from path
                default = infer_area(file_path, vault_root)
            elif field == "visibility":
                # Infer visibility from path: netease/ -> private, else public
                default = "private" if issue["file"].startswith("netease") else "public"
            elif field == "tags":
                # Infer tags from path prefix
                rel = issue["file"].replace("\\", "/")
                default = []
                for prefix, tags in PATH_TAG_MAP.items():
                    if rel.startswith(prefix):
                        default = list(tags)
                        break
            if default is not None:
                fm[field] = default
                fixes.append({"file": issue["file"], "field": field, "value": default})

        # Reconstruct file
        fm_lines = ["---"]
        for k, v in fm.items():
            if isinstance(v, list):
                fm_lines.append(f"{k}:")
                for item in v:
                    fm_lines.append(f"  - {item}")
            else:
                fm_lines.append(f"{k}: {v}")
        fm_lines.append("---")
        new_text = "\n".join(fm_lines) + body
        file_path.write_text(new_text, encoding="utf-8")

    return fixes


def main():
    parser = argparse.ArgumentParser(description="Scan vault for missing frontmatter")
    parser.add_argument("--vault", type=str, default=str(VAULT_ROOT), help="Vault root path")
    parser.add_argument("--fix", action="store_true", help="Auto-fill missing fields with safe defaults")
    parser.add_argument("--fields", type=str, default=None, help="Comma-separated list of fields to fix (e.g. 'area,visibility'). If omitted, fix all.")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    vault_root = Path(args.vault).resolve()
    if not vault_root.is_dir():
        print(f"Error: vault root not found: {vault_root}", file=sys.stderr)
        sys.exit(1)

    issues = scan_vault(vault_root)

    if args.fix:
        only_fields = args.fields.split(",") if args.fields else None
        fixes = auto_fix(issues, vault_root, only_fields=only_fields)
        if args.json:
            print(json.dumps({"fixed": len(fixes), "details": fixes}, ensure_ascii=False, indent=2))
        else:
            print(f"Fixed {len(fixes)} missing fields across {len(issues)} files:")
            for fix in fixes:
                print(f"  {fix['file']}: +{fix['field']} = {fix['value']}")
    else:
        if args.json:
            print(json.dumps({"issues": len(issues), "details": issues}, ensure_ascii=False, indent=2))
        else:
            if not issues:
                print("All files have complete frontmatter.")
            else:
                print(f"Found {len(issues)} files with missing frontmatter:\n")
                for issue in issues:
                    print(f"  {issue['file']} ({issue['area']}): missing {', '.join(issue['missing'])}")


if __name__ == "__main__":
    main()
