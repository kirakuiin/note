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
    "visibility": "public",
    "status": "draft",
    "tags": [],
    "date": None,  # must be provided
    "topic": "",
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
            continue  # _index.md, _MOC.md, _log.md are meta files

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


def auto_fix(issues: list[dict], vault_root: Path) -> list[dict]:
    """Auto-fill missing frontmatter with safe defaults. Returns list of fixes applied."""
    fixes = []
    for issue in issues:
        file_path = vault_root / issue["file"]
        text = file_path.read_text(encoding="utf-8")
        fm, body = parse_frontmatter(text)

        for field in issue["missing"]:
            default = SAFE_DEFAULTS.get(field)
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
        new_text = "\n".join(fm_lines) + "\n" + body
        file_path.write_text(new_text, encoding="utf-8")

    return fixes


def main():
    parser = argparse.ArgumentParser(description="Scan vault for missing frontmatter")
    parser.add_argument("--vault", type=str, default=str(VAULT_ROOT), help="Vault root path")
    parser.add_argument("--fix", action="store_true", help="Auto-fill missing fields with safe defaults")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    vault_root = Path(args.vault).resolve()
    if not vault_root.is_dir():
        print(f"Error: vault root not found: {vault_root}", file=sys.stderr)
        sys.exit(1)

    issues = scan_vault(vault_root)

    if args.fix:
        fixes = auto_fix(issues, vault_root)
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
