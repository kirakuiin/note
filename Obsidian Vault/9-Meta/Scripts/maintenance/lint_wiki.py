#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only wiki lint scanner for the Obsidian vault.

This script produces structured findings only. It never modifies files.
Fixes must go through user confirmation and Obsidian CLI.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


SKIP_NAMES = {".obsidian", ".git", ".mypy_cache", "__pycache__", ".DS_Store"}
PUBLIC_ROOTS = {
    "0-Inbox",
    "1-Sessions",
    "2-Wiki",
    "3-Projects",
    "4-Journal",
    "5-Life",
    "6-Tools",
    "9-Meta",
}
PUBLIC_ALLOWED_ROOTS = PUBLIC_ROOTS | {"Netease", "Dashboard.md", "openspec"}
PRIVATE_ALLOWED_ROOTS = {
    "0-Daily",
    "1-Sessions",
    "2-Wiki",
    "3-Projects",
    "4-Reference",
    "Assets",
    "AGENTS.md",
}
PUBLIC_AREA_BY_ROOT = {
    "0-Inbox": "inbox",
    "1-Sessions": "session",
    "2-Wiki": "knowledge",
    "3-Projects": "project",
    "4-Journal": "journal",
    "5-Life": "life",
    "6-Tools": "tool",
    "9-Meta": "meta",
}
PRIVATE_AREA_BY_ROOT = {
    "0-Daily": "journal",
    "1-Sessions": "session",
    "2-Wiki": "knowledge",
    "3-Projects": "project",
    "4-Reference": "reference",
}

WIKILINK_RE = re.compile(r"!?\[\[([^\]]+)\]\]")
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
INLINE_TAG_RE = re.compile(r"(?<![\w/])#([A-Za-z0-9_\-/\u4e00-\u9fff]+)")
HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def relpath(path: Path, vault_root: Path) -> str:
    return path.relative_to(vault_root).as_posix()


def should_skip(path: Path, vault_root: Path) -> bool:
    try:
        parts = path.relative_to(vault_root).parts
    except ValueError:
        return True
    return any(part in SKIP_NAMES or part.startswith(".") for part in parts)


def markdown_files(vault_root: Path) -> list[Path]:
    return sorted(
        path
        for path in vault_root.rglob("*.md")
        if path.is_file() and not should_skip(path, vault_root)
    )


def read_markdown(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text

    fm: dict[str, Any] = {}
    current_key: str | None = None
    for raw in parts[1].splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("-") and current_key:
            value = stripped[1:].strip().strip("\"'")
            existing = fm.setdefault(current_key, [])
            if not isinstance(existing, list):
                existing = [existing]
                fm[current_key] = existing
            existing.append(value)
            continue
        if ":" in stripped:
            key, value = stripped.split(":", 1)
            key = key.strip()
            value = value.strip().strip("\"'")
            fm[key] = [] if value == "" else value
            current_key = key
    return fm, parts[2]


def flatten_values(value: Any) -> list[str]:
    if isinstance(value, dict):
        out: list[str] = []
        for item in value.values():
            out.extend(flatten_values(item))
        return out
    if isinstance(value, list):
        out = []
        for item in value:
            out.extend(flatten_values(item))
        return out
    return [str(value)]


def normalize_tag(tag: str) -> str:
    return tag.strip().strip("#").strip()


def tags_from_fm(fm: dict[str, Any]) -> list[str]:
    raw = fm.get("tags", [])
    if isinstance(raw, str):
        raw_tags = [part.strip() for part in raw.split(",")]
    elif isinstance(raw, list):
        raw_tags = [str(part).strip() for part in raw]
    else:
        raw_tags = []
    return [normalize_tag(tag) for tag in raw_tags if normalize_tag(tag)]


def all_tags(text: str, fm: dict[str, Any]) -> list[str]:
    tags = tags_from_fm(fm)
    tags.extend(normalize_tag(match.group(1)) for match in INLINE_TAG_RE.finditer(text))
    return sorted(set(tag for tag in tags if tag))


def strip_code_spans(text: str) -> str:
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    text = re.sub(r"`[^`\n]*`", "", text)
    text = re.sub(r"\[[^\]]+\]\([^)]+\)", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    return text


def extract_code_tags(line: str) -> list[str]:
    return [normalize_tag(tag) for tag in re.findall(r"`(#[^`]+)`", line)]


def load_tag_rules(vault_root: Path) -> dict[str, Any]:
    public_whitelist: set[str] = set()
    private_whitelist: set[str] = set()
    redline_literals: set[str] = set()
    redline_prefixes: set[str] = set()
    cleanup: dict[str, str] = {}

    tags_path = vault_root / "9-Meta" / "TAGS.md"
    section = ""
    if tags_path.exists():
        for line in read_markdown(tags_path).splitlines():
            if line.startswith("## 2."):
                section = "whitelist"
            elif line.startswith("## 3."):
                section = "redline"
            elif line.startswith("## 4."):
                section = "cleanup"
            elif line.startswith("## "):
                section = ""

            code_tags = extract_code_tags(line)
            if section == "whitelist":
                public_whitelist.update(code_tags)
            elif section == "redline":
                if "合法" in line:
                    continue
                for tag in code_tags:
                    if tag.endswith("/*"):
                        redline_prefixes.add(tag[:-2])
                    else:
                        redline_literals.add(tag)
            elif section == "cleanup" and "|" in line:
                tags = extract_code_tags(line)
                if len(tags) >= 2:
                    cleanup[tags[0]] = tags[1]

    private_path = vault_root / "Netease" / "AGENTS.md"
    if private_path.exists():
        in_private_table = False
        for line in read_markdown(private_path).splitlines():
            if "4.2" in line and "白名单" in line:
                in_private_table = True
            elif line.startswith("### ") and in_private_table:
                in_private_table = False
            if in_private_table:
                private_whitelist.update(extract_code_tags(line))

    return {
        "public_whitelist": public_whitelist,
        "private_whitelist": public_whitelist | private_whitelist | redline_literals,
        "redline_literals": redline_literals,
        "redline_prefixes": redline_prefixes,
        "cleanup": cleanup,
    }


def is_private_rel(rel: str) -> bool:
    return rel == "Netease/AGENTS.md" or rel.startswith("Netease/")


def region_for(rel: str) -> str:
    return "private" if is_private_rel(rel) else "public"


def infer_area(rel: str) -> str | None:
    parts = rel.split("/")
    if not parts:
        return None
    if parts[0] == "Netease" and len(parts) > 1:
        return PRIVATE_AREA_BY_ROOT.get(parts[1])
    return PUBLIC_AREA_BY_ROOT.get(parts[0])


def build_note_index(files: list[Path], vault_root: Path) -> dict[str, list[str]]:
    index: dict[str, list[str]] = defaultdict(list)
    for path in files:
        rel = relpath(path, vault_root)
        no_ext = rel[:-3] if rel.endswith(".md") else rel
        keys = {path.stem.lower(), no_ext.lower()}
        for key in keys:
            index[key].append(rel)
    return index


def clean_link_target(raw: str) -> str:
    target = raw.split("|", 1)[0].split("#", 1)[0].strip()
    return target[:-3] if target.endswith(".md") else target


def resolve_target(target: str, source: Path, vault_root: Path, index: dict[str, list[str]]) -> str | None:
    target = clean_link_target(target).replace("\\", "/").lstrip("/")
    if not target:
        return None

    candidates: list[Path] = []
    if "/" in target:
        candidates.extend([vault_root / target, source.parent / target])
    else:
        for rel in index.get(target.lower(), []):
            return rel

    for candidate in candidates:
        md = candidate if candidate.suffix == ".md" else candidate.with_suffix(".md")
        try:
            if md.exists() and md.is_file() and md.resolve().is_relative_to(vault_root.resolve()):
                return relpath(md, vault_root)
        except ValueError:
            continue
    if "/" in target:
        suffix = "/" + target.lower()
        matches = [
            rel
            for key, rels in index.items()
            if key.endswith(suffix)
            for rel in rels
        ]
        if len(matches) == 1:
            return matches[0]
    return None


def make_issue(severity: str, issue_id: str, region: str, path: str, problem: str, suggestion: str) -> dict[str, str]:
    return {
        "severity": severity,
        "id": issue_id,
        "region": region,
        "path": path,
        "problem": problem,
        "suggestion": suggestion,
    }


def check_required_frontmatter(rel: str, fm: dict[str, Any]) -> list[str]:
    area = fm.get("area") or infer_area(rel)
    missing: list[str] = []
    for field in ("area", "visibility"):
        if not fm.get(field):
            missing.append(field)
    if rel.startswith("9-Meta/Templates/"):
        return missing
    if Path(rel).name in {"_index.md", "_log.md"}:
        return missing
    if area in {"knowledge", "session", "project"} and not tags_from_fm(fm):
        missing.append("tags")
    if area == "session":
        for field in ("date", "topic"):
            if not fm.get(field):
                missing.append(field)
    if area == "journal" and not fm.get("date"):
        missing.append("date")
    if area == "tool" and not fm.get("category"):
        missing.append("category")
    if area == "reference" and not fm.get("source"):
        missing.append("source")
    return missing


def related_not_last(body: str) -> bool:
    match = re.search(r"^##\s+相关\s*$", body, flags=re.MULTILINE)
    if not match:
        return False
    tail = body[match.end() :].strip()
    if not tail:
        return False
    return bool(re.search(r"^##\s+", tail, flags=re.MULTILINE))


def check_session_sections(rel: str, body: str) -> list[str]:
    if Path(rel).name in {"_index.md", "_log.md"}:
        return []
    if "/1-Sessions/" not in f"/{rel}" and not rel.startswith("1-Sessions/"):
        return []
    headings = set(HEADING_RE.findall(body))
    required = ["背景 / 问题", "关键讨论", "结论", "产出物"]
    return [heading for heading in required if heading not in headings]


def is_tag_authority_file(rel: str) -> bool:
    return rel in {"9-Meta/TAGS.md", "Netease/AGENTS.md"}


def is_boundary_governance_file(rel: str) -> bool:
    return (
        rel in {"9-Meta/AGENTS.md", "9-Meta/TAGS.md", "Netease/AGENTS.md"}
        or rel.startswith("9-Meta/Skills/")
        or rel.startswith("openspec/")
    )


def is_tag_governance_exempt_file(rel: str) -> bool:
    return is_tag_authority_file(rel) or is_boundary_governance_file(rel) or rel.startswith("9-Meta/Excalidraw/")


def is_link_placeholder_target(target: str) -> bool:
    return "{{" in target or "}}" in target or "'" in target or '"' in target or target.startswith("[")


def scan_vault(vault_root: Path) -> dict[str, Any]:
    vault_root = vault_root.resolve()
    files = markdown_files(vault_root)
    index = build_note_index(files, vault_root)
    tag_rules = load_tag_rules(vault_root)
    issues: list[dict[str, str]] = []
    incoming: Counter[str] = Counter()

    for path in files:
        rel = relpath(path, vault_root)
        region = region_for(rel)
        text = read_markdown(path)
        fm, body = parse_frontmatter(text)
        scan_text = strip_code_spans(text)
        scan_body = strip_code_spans(body)

        expected_visibility = "private" if region == "private" else "public"
        if fm.get("visibility") and fm.get("visibility") != expected_visibility:
            issues.append(
                make_issue(
                    "critical",
                    "C3",
                    region,
                    rel,
                    f"visibility is {fm.get('visibility')!r}; expected {expected_visibility!r}",
                    f"Set visibility to {expected_visibility} via obsidian property:set.",
                )
            )

        missing = check_required_frontmatter(rel, fm)
        if missing:
            issues.append(
                make_issue(
                    "warning",
                    "W2",
                    region,
                    rel,
                    "missing frontmatter field(s): " + ", ".join(missing),
                    "Add missing properties after confirmation via obsidian property:set.",
                )
            )

        if region == "public" and not is_boundary_governance_file(rel):
            values = "\n".join(flatten_values(fm))
            if "Netease/" in scan_text or "Netease/" in values:
                issues.append(
                    make_issue(
                        "critical",
                        "C1",
                        region,
                        rel,
                        "mentions Netease/ in public file",
                        "Remove or move the reference behind the private boundary.",
                    )
                )

        for match in WIKILINK_RE.finditer(scan_text):
            target = clean_link_target(match.group(1))
            if is_link_placeholder_target(target):
                continue
            suffix = Path(target).suffix.lower()
            if suffix and suffix != ".md":
                continue
            resolved = resolve_target(target, path, vault_root, index)
            if resolved:
                incoming[resolved] += 1
                if (
                    region == "public"
                    and is_private_rel(resolved)
                    and not is_boundary_governance_file(rel)
                ):
                    issues.append(
                        make_issue(
                            "critical",
                            "C1",
                            region,
                            rel,
                            f"wikilink [[{target}]] resolves to Netease/ path {resolved}",
                            "Remove the cross-boundary wikilink.",
                        )
                    )
            elif target and not target.startswith(("http://", "https://")):
                issues.append(
                    make_issue(
                        "warning",
                        "W1",
                        region,
                        rel,
                        f"broken wikilink [[{target}]]",
                        "Create the target page or update the link.",
                    )
                )

        for match in MARKDOWN_LINK_RE.finditer(scan_text):
            target = match.group(1).replace("\\", "/")
            if region == "public" and "Netease/" in target and not is_boundary_governance_file(rel):
                issues.append(
                    make_issue(
                        "critical",
                        "C1",
                        region,
                        rel,
                        f"markdown link points to private path {target}",
                        "Remove the cross-boundary markdown link.",
                    )
                )

        for tag in [] if is_tag_governance_exempt_file(rel) else tags_from_fm(fm):
            whitelist = (
                tag_rules["private_whitelist"]
                if region == "private"
                else tag_rules["public_whitelist"]
            )
            if region == "public" and (
                tag in tag_rules["redline_literals"]
                or any(tag.startswith(prefix + "/") for prefix in tag_rules["redline_prefixes"])
            ):
                issues.append(
                    make_issue(
                        "critical",
                        "C2",
                        region,
                        rel,
                        f"public file uses redline tag #{tag}",
                        "Remove tag or move note into Netease/ if it is private.",
                    )
                )
            if tag in tag_rules["cleanup"]:
                suggestion = f"Replace #{tag} with #{tag_rules['cleanup'][tag]}."
            elif "/" in tag:
                top = tag.split("/", 1)[0]
                suggestion = "Use a whitelisted top-level tag and at most one nested segment."
                if region == "private" and any(tag.startswith(prefix + "/") for prefix in tag_rules["redline_prefixes"]):
                    continue
                if top in whitelist and tag.count("/") <= 1:
                    continue
            elif tag in whitelist:
                continue
            else:
                suggestion = "Ask whether to add this tag to the whitelist or replace it."
            issues.append(make_issue("suggestion", "S2", region, rel, f"wild tag #{tag}", suggestion))

        if related_not_last(scan_body) and Path(rel).name not in {"_index.md", "_log.md"}:
            issues.append(
                make_issue(
                    "warning",
                    "W3",
                    region,
                    rel,
                    "`## 相关` is not the last section",
                    "Move `## 相关` to the end after confirmation.",
                )
            )

        missing_sections = check_session_sections(rel, scan_body)
        if missing_sections:
            issues.append(
                make_issue(
                    "warning",
                    "W8",
                    region,
                    rel,
                    "missing session section(s): " + ", ".join(missing_sections),
                    "Add required session sections.",
                )
            )

    # W6 root structure checks.
    for child in vault_root.iterdir():
        if child.name in SKIP_NAMES or child.name.startswith("."):
            continue
        if child.name not in PUBLIC_ALLOWED_ROOTS:
            issues.append(
                make_issue(
                    "warning",
                    "W6",
                    "public",
                    child.name,
                    "unknown public top-level entry",
                    "Add to AGENTS.md via spec change or move into an allowed directory.",
                )
            )
    netease = vault_root / "Netease"
    if netease.exists():
        for child in netease.iterdir():
            if child.name in SKIP_NAMES or child.name.startswith("."):
                continue
            if child.name not in PRIVATE_ALLOWED_ROOTS:
                issues.append(
                    make_issue(
                        "warning",
                        "W6",
                        "private",
                        f"Netease/{child.name}",
                        "unknown private top-level entry",
                        "Add to Netease/AGENTS.md or move into an allowed directory.",
                    )
                )

    # S1 simple orphan pass.
    for path in files:
        rel = relpath(path, vault_root)
        name = path.name
        if "/2-Wiki/" not in f"/{rel}" or name in {"_index.md", "_log.md"}:
            continue
        if incoming[rel] == 0:
            issues.append(
                make_issue(
                    "suggestion",
                    "S1",
                    region_for(rel),
                    rel,
                    "wiki page has zero simple backlinks",
                    "Review whether this should be linked, indexed, or left as an orphan.",
                )
            )

    severity_order = {"critical": 0, "warning": 1, "suggestion": 2}
    issues.sort(key=lambda item: (severity_order[item["severity"]], item["region"], item["id"], item["path"]))
    summary = Counter(issue["severity"] for issue in issues)
    return {
        "vault": str(vault_root),
        "summary": {
            "critical": summary["critical"],
            "warning": summary["warning"],
            "suggestion": summary["suggestion"],
            "total": len(issues),
        },
        "issues": issues,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Wiki Lint Report",
        f"- Vault: `{report['vault']}`",
        f"- Findings: {report['summary']['total']} "
        f"(critical {report['summary']['critical']}, warning {report['summary']['warning']}, "
        f"suggestion {report['summary']['suggestion']})",
        "",
    ]
    for severity in ("critical", "warning", "suggestion"):
        lines.append(f"## {severity.title()}")
        items = [issue for issue in report["issues"] if issue["severity"] == severity]
        if not items:
            lines.append("- None")
            lines.append("")
            continue
        for region in ("public", "private"):
            region_items = [issue for issue in items if issue["region"] == region]
            if not region_items:
                continue
            lines.append(f"### [{region}]")
            for issue in region_items:
                lines.append(
                    f"- `{issue['path']}` [{issue['id']}] — {issue['problem']} → {issue['suggestion']}"
                )
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only lint scan for this Obsidian vault")
    parser.add_argument("--vault", type=Path, required=True, help="Vault root path")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args(argv)

    report = scan_vault(args.vault)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
