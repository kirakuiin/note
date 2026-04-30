#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Replace #reference and #language tags with path-appropriate whitelist tags.
#reference -> domain tag based on file location
#language -> #英语
"""

import sys
from pathlib import Path

VAULT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# Path prefix -> replacement tag for #reference
PATH_TO_TAG = {
    "2-Wiki/编程语言": "编程语言",
    "2-Wiki/游戏开发": "游戏开发",
    "2-Wiki/算法与数据结构": "算法与数据结构",
    "2-Wiki/AI与Agent": "AI与Agent",
    "2-Wiki/英语": "英语",
    "2-Wiki/方法论": "方法论",
    "2-Wiki/计科基础": "编程语言",
    "5-Life": "方法论",
    "6-Tools": "工具",
    "9-Meta": "from-doc",
}


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


def get_tags(fm: dict) -> list[str]:
    tags = fm.get("tags")
    if not tags:
        return []
    if isinstance(tags, str):
        return [t.strip() for t in tags.split(",") if t.strip()]
    if isinstance(tags, list):
        return tags
    return []


def set_tags(fm: dict, tags: list[str]):
    fm["tags"] = tags


def rebuild_file(fm: dict, body: str) -> str:
    lines = ["---"]
    for k, v in fm.items():
        if isinstance(v, list):
            lines.append(f"{k}:")
            for item in v:
                lines.append(f"  - {item}")
        else:
            lines.append(f"{k}: {v}")
    lines.append("---")
    return "\n".join(lines) + body


def infer_replacement_tag(file_rel: str) -> str | None:
    """Infer the replacement tag for #reference based on file path."""
    rel = file_rel.replace("\\", "/")
    for prefix, tag in PATH_TO_TAG.items():
        if rel.startswith(prefix):
            return tag
    return None


def main():
    dry_run = "--dry-run" in sys.argv
    changed = 0

    for md_file in VAULT_ROOT.rglob("*.md"):
        if any(part.startswith(".") for part in md_file.parts):
            continue

        try:
            text = md_file.read_text(encoding="utf-8")
        except Exception:
            continue

        fm, body = parse_frontmatter(text)
        tags = get_tags(fm)
        if not tags:
            continue

        new_tags = list(tags)
        modified = False

        # Replace #reference
        if "reference" in new_tags:
            rel = str(md_file.relative_to(VAULT_ROOT))
            replacement = infer_replacement_tag(rel)
            if replacement:
                new_tags = [replacement if t == "reference" else t for t in new_tags]
                modified = True
                if dry_run:
                    print(f"  WOULD: {rel}: reference -> {replacement}")

        # Replace #language -> #英语
        if "language" in new_tags:
            new_tags = ["英语" if t == "language" else t for t in new_tags]
            modified = True
            if dry_run:
                rel = str(md_file.relative_to(VAULT_ROOT))
                print(f"  WOULD: {rel}: language -> 英语")

        if modified and not dry_run:
            set_tags(fm, new_tags)
            new_text = rebuild_file(fm, body)
            md_file.write_text(new_text, encoding="utf-8")
            rel = str(md_file.relative_to(VAULT_ROOT))
            print(f"  CHANGED: {rel}")
            changed += 1

    if dry_run:
        print(f"\nWould change {changed} files.")
    else:
        print(f"\nChanged {changed} files.")


if __name__ == "__main__":
    main()
