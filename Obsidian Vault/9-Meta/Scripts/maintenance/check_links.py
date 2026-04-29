#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_links.py — Check vault for broken wikilinks.

Parses all .md files, extracts [[wikilinks]], and verifies each target
exists in the vault. Reports broken links with source file and target.

Usage:
  python check_links.py [--vault <path>] [--json]

Output:
  List of broken wikilinks with source file and missing target.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path


VAULT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# Wikilink pattern: [[target]] or [[target|alias]] or [[target#heading]]
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:[|#][^\]]+)?\]\]")


def resolve_wikilink(target: str, source_dir: Path, vault_root: Path) -> Path | None:
    """Resolve a wikilink target to an actual file path. Returns None if not found."""
    target = target.strip()

    # Absolute path from vault root
    if target.startswith("/") or target.startswith("\\"):
        candidate = vault_root / target.lstrip("/\\")
        if candidate.exists():
            return candidate
        # Try with .md extension
        candidate_md = candidate.with_suffix(".md")
        if candidate_md.exists():
            return candidate_md
        return None

    # Relative path from source file's directory
    candidate = (source_dir / target).resolve()
    if candidate.exists():
        return candidate
    candidate_md = candidate.with_suffix(".md")
    if candidate_md.exists():
        return candidate_md

    # Try from vault root
    candidate = (vault_root / target).resolve()
    if candidate.exists():
        return candidate
    candidate_md = candidate.with_suffix(".md")
    if candidate_md.exists():
        return candidate_md

    # Try as note name (search entire vault)
    target_name = target + ".md"
    for f in vault_root.rglob(target_name):
        return f

    return None


def check_links(vault_root: Path) -> list[dict]:
    """Scan all .md files and check wikilinks. Returns list of broken links."""
    broken = []

    for md_file in vault_root.rglob("*.md"):
        if any(part.startswith(".") for part in md_file.parts):
            continue

        try:
            text = md_file.read_text(encoding="utf-8")
        except Exception:
            continue

        source_dir = md_file.parent
        for match in WIKILINK_RE.finditer(text):
            target = match.group(1).strip()
            # Skip external URLs
            if target.startswith("http://") or target.startswith("https://"):
                continue
            # Skip empty
            if not target:
                continue

            resolved = resolve_wikilink(target, source_dir, vault_root)
            if resolved is None:
                broken.append({
                    "source": str(md_file.relative_to(vault_root)),
                    "target": target,
                })

    return broken


def main():
    parser = argparse.ArgumentParser(description="Check vault for broken wikilinks")
    parser.add_argument("--vault", type=str, default=str(VAULT_ROOT), help="Vault root path")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    vault_root = Path(args.vault).resolve()
    if not vault_root.is_dir():
        print(f"Error: vault root not found: {vault_root}", file=sys.stderr)
        sys.exit(1)

    broken = check_links(vault_root)

    if args.json:
        print(json.dumps({"broken": len(broken), "details": broken}, ensure_ascii=False, indent=2))
    else:
        if not broken:
            print("No broken wikilinks found.")
        else:
            print(f"Found {len(broken)} broken wikilinks:\n")
            for link in broken:
                print(f"  {link['source']} -> [[{link['target']}]]")


if __name__ == "__main__":
    main()
