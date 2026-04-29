#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_visibility.py — Check vault for visibility boundary violations.

Checks:
  1. Public area files with visibility: private
  2. netease/ files with visibility: public
  3. Public area files containing wikilinks to netease/ paths (Critical)

Usage:
  python check_visibility.py [--vault <path>] [--json]

Output:
  List of visibility violations ordered by severity.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path


VAULT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

PUBLIC_AREAS = ["0-Inbox", "1-Sessions", "2-Wiki", "3-Projects", "4-Journal", "5-Life", "6-Tools", "9-Meta"]
PRIVATE_AREA = "netease"

WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


def parse_frontmatter(text: str) -> dict:
    """Parse YAML frontmatter from markdown text."""
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    fm_text = parts[1].strip()
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
    return fm


def check_visibility(vault_root: Path) -> dict:
    """Run all visibility checks. Returns dict with critical, warning, suggestion lists."""
    results = {"critical": [], "warning": [], "suggestion": []}

    for md_file in vault_root.rglob("*.md"):
        if any(part.startswith(".") for part in md_file.parts):
            continue

        try:
            text = md_file.read_text(encoding="utf-8")
        except Exception:
            continue

        rel = str(md_file.relative_to(vault_root))
        fm = parse_frontmatter(text)
        visibility = fm.get("visibility", "")

        # Determine if file is in public or private area
        top_dir = md_file.relative_to(vault_root).parts[0] if md_file != vault_root else ""
        is_public = top_dir in PUBLIC_AREAS
        is_private = top_dir == PRIVATE_AREA

        # Check 1: Public area file with visibility: private
        if is_public and visibility == "private":
            results["warning"].append({
                "file": rel,
                "issue": "Public area file has visibility: private",
                "fix": "Change visibility to public or move file to netease/",
            })

        # Check 2: Private area file with visibility: public
        if is_private and visibility == "public":
            results["critical"].append({
                "file": rel,
                "issue": "netease/ file has visibility: public",
                "fix": "Change visibility to private",
            })

        # Check 3: Public area file linking to netease/ (Critical)
        if is_public:
            for match in WIKILINK_RE.finditer(text):
                target = match.group(1).strip()
                if target.startswith("netease/") or target.startswith("../netease/"):
                    results["critical"].append({
                        "file": rel,
                        "issue": f"Public file links to netease/: [[{target}]]",
                        "fix": "Remove the cross-boundary reference",
                    })

    return results


def main():
    parser = argparse.ArgumentParser(description="Check vault for visibility violations")
    parser.add_argument("--vault", type=str, default=str(VAULT_ROOT), help="Vault root path")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    vault_root = Path(args.vault).resolve()
    if not vault_root.is_dir():
        print(f"Error: vault root not found: {vault_root}", file=sys.stderr)
        sys.exit(1)

    results = check_visibility(vault_root)

    total = len(results["critical"]) + len(results["warning"]) + len(results["suggestion"])

    if args.json:
        print(json.dumps({"total": total, **results}, ensure_ascii=False, indent=2))
    else:
        if total == 0:
            print("No visibility violations found.")
        else:
            print(f"Found {total} visibility violations:\n")

            if results["critical"]:
                print("## Critical")
                for item in results["critical"]:
                    print(f"  {item['file']}: {item['issue']}")
                    print(f"    -> {item['fix']}")
                print()

            if results["warning"]:
                print("## Warning")
                for item in results["warning"]:
                    print(f"  {item['file']}: {item['issue']}")
                    print(f"    -> {item['fix']}")
                print()

            if results["suggestion"]:
                print("## Suggestion")
                for item in results["suggestion"]:
                    print(f"  {item['file']}: {item['issue']}")
                    print(f"    -> {item['fix']}")


if __name__ == "__main__":
    main()
