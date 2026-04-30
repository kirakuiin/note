#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
replace_tags.py ¡ª Batch replace frontmatter tags in vault .md files.

Usage:
  python replace_tags.py --old <old_tag> --new <new_tag> [--dry-run] [--vault <path>]
"""

import argparse
import sys
from pathlib import Path

VAULT_ROOT = Path(__file__).resolve().parent.parent.parent.parent


def parse_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    fm_text = parts[1].strip()
    body = parts[2]
    fm = {}
    current_key = None
    for line in fm_text.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" in stripped and not stripped.startswith("-"):
            key, _, value = stripped.partition(":")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            fm[key] = value
            current_key = key
        elif stripped.startswith("-") and current_key:
            val = stripped[1:].strip().strip('"').strip("'")
            if isinstance(fm.get(current_key), list):
                fm[current_key].append(val)
            elif fm.get(current_key):
                fm[current_key] = [fm[current_key], val]
            else:
                fm[current_key] = [val]
    return fm, body


def replace_tag_in_file(file_path: Path, old_tag: str, new_tag: str, dry_run: bool) -> bool:
    """Replace old_tag with new_tag in file's frontmatter tags. Returns True if changed."""
    try:
        text = file_path.read_text(encoding="utf-8")
    except Exception:
        return False

    fm, body = parse_frontmatter(text)
    tags = fm.get("tags")
    if not tags:
        return False

    if isinstance(tags, str):
        tags_list = [t.strip() for t in tags.split(",") if t.strip()]
    elif isinstance(tags, list):
        tags_list = tags
    else:
        return False

    if old_tag not in tags_list:
        return False

    new_tags = [new_tag if t == old_tag else t for t in tags_list]

    if dry_run:
        print(f"  WOULD CHANGE: {file_path.relative_to(VAULT_ROOT)}")
        print(f"    {old_tag} -> {new_tag}")
        return True

    # Reconstruct frontmatter
    fm["tags"] = new_tags
    lines = ["---"]
    for k, v in fm.items():
        if isinstance(v, list):
            lines.append(f"{k}:")
            for item in v:
                lines.append(f"  - {item}")
        else:
            lines.append(f"{k}: {v}")
    lines.append("---")
    new_text = "\n".join(lines) + body
    file_path.write_text(new_text, encoding="utf-8")
    print(f"  CHANGED: {file_path.relative_to(VAULT_ROOT)}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Batch replace frontmatter tags")
    parser.add_argument("--old", type=str, required=True, help="Old tag to replace")
    parser.add_argument("--new", type=str, required=True, help="New tag")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no changes")
    parser.add_argument("--vault", type=str, default=str(VAULT_ROOT), help="Vault root path")
    args = parser.parse_args()

    vault_root = Path(args.vault).resolve()
    changed = 0
    for md_file in vault_root.rglob("*.md"):
        if any(part.startswith(".") for part in md_file.parts):
            continue
        if replace_tag_in_file(md_file, args.old, args.new, args.dry_run):
            changed += 1

    if args.dry_run:
        print(f"\nWould change {changed} files.")
    else:
        print(f"\nChanged {changed} files.")


if __name__ == "__main__":
    main()
