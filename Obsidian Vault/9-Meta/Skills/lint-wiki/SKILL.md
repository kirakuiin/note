---
name: lint-wiki
description: >
  Use when auditing this Obsidian vault for wiki health: broken wikilinks,
  public/private boundary leaks, redline tag leaks, visibility mismatches,
  missing frontmatter, index drift, naming violations, orphan pages, stale
  projects, duplicate topics, or reported lint issues.
visibility: public
area: meta
---
# Lint-Wiki Skill

Run a read-only mechanical audit first. Produce a severity-ordered report.
Modify files only after explicit user confirmation.

Lint protects safety and maintainability. It catches boundary leaks,
metadata drift, broken links, index drift, naming drift, and tag drift. It
does not enforce graph completeness or deep semantic correctness.

## Preconditions

1. Read `OBSIDIAN_VAULT`. If unset, stop and ask user to set it. Do not
   fall back to cwd.
2. Read `9-Meta/AGENTS.md`, `9-Meta/TAGS.md`, and, if present,
   `Netease/AGENTS.md`.
3. Verify Obsidian CLI:
   ```powershell
   obsidian version
   obsidian unresolved total
   ```
   If `obsidian` resolves to `Obsidian.com`, that is OK when commands return
   correctly. Current minimum version: `1.12.7`.
4. Treat `obsidian unresolved total` as current broken-link count. If no prior
   lint report exists, say baseline is "never"; do not invent one.

## Git Isolation

Before applying confirmed lint fixes, isolate the work on a dedicated branch:

1. Inspect dirty state:
   ```powershell
   git -C "<repo-root>" status --short
   ```
2. If unrelated user changes exist, do not stage or modify them. Either keep
   fixes scoped to separate files or stop and ask if the dirty files overlap
   the requested fixes.
3. Create/switch a branch named `codex/lint-wiki-YYYYMMDD` from the current
   branch before making fixes.
4. Run the scan and fixes on that branch only.
5. Commit verified lint fixes on that branch.
6. Merge back to the original branch only after:
   - `python 9-Meta/Scripts/maintenance/lint_wiki.py --vault "$env:OBSIDIAN_VAULT" --json` runs successfully
   - `obsidian unresolved total` does not increase
   - C1-C3 are zero if any Critical fix was attempted
   - `git diff --check` is clean
7. If merge conflicts or overlapping user changes appear, stop and report the
   branch name plus conflict files; do not force merge.

## Region Rules

| Region | Path | Authority | Tag vocab | Required visibility |
|---|---|---|---|---|
| public | everything outside `Netease/` | `9-Meta/AGENTS.md` | `9-Meta/TAGS.md` | `public` |
| private | `Netease/` subtree | `Netease/AGENTS.md` | public vocab + `Netease/AGENTS.md` private vocab | `private` |

Report public and private findings under separate headings. Never mix rows.

## Read-Only Scan

Preferred scanner:

```powershell
python "9-Meta/Scripts/maintenance/lint_wiki.py" --vault "$env:OBSIDIAN_VAULT" --json
```

Use script output as scan data, then format the human report below. The
script is read-only. If script output and Obsidian CLI disagree on broken
links, treat `obsidian unresolved` as source of truth for W1 count.

Skip during full-vault traversal:

- hidden/system entries: `.obsidian/`, `.git/`, `.mypy_cache/`, `.DS_Store`
- binary/assets unless a check explicitly targets them
- retired `_MOC.md` maintenance expectations

Boundary governance docs may describe `Netease/` paths and redline tags as
policy/examples without being reported as C1/C2/S2 leaks:

- `9-Meta/AGENTS.md`, `9-Meta/TAGS.md`, `Netease/AGENTS.md`
- `9-Meta/Skills/**`
- `openspec/**`

Still check those files for basic frontmatter and visibility consistency.

Do not skip root-level non-hidden files or unknown non-hidden dirs; W6 should
report those if they are not allowed by `9-Meta/AGENTS.md`.

### Critical

| ID | Check | Detection |
|---|---|---|
| C1 | Cross-boundary references | Public file wikilinks, embeds, markdown links, or frontmatter values resolve to or mention `Netease/`. Build a note-name/path index so `[[Private Page]]` resolving into `Netease/` is caught, not only literal `Netease/...` strings. |
| C2 | Redline tag leak | Public file has any tag from `TAGS.md` redline section. Match literal entries, explicit redline nested paths, and redline prefixes (`#sdc/*`, `#Arcolab/*`, `#frame-tool/*`, `#战斗/*`, `#战斗系统/*`, `#模块/*`, `#文档/*`). |
| C3 | Visibility mismatch | `visibility` disagrees with path region: `Netease/` must be `private`; all other paths must be `public`. |

### Warning

| ID | Check | Detection |
|---|---|---|
| W1 | Broken wikilinks | Prefer `obsidian unresolved`. Use `total` for count and detailed output for report lines. |
| W2 | Missing frontmatter | Required by current `AGENTS.md`: all files need `area` + `visibility`; `knowledge`/`session`/`project` need `tags` with at least one item; `session` also needs `date` + `topic`; public `journal` needs `date`; public `tool` needs `category`; private `journal` needs `date`; private `reference` should include `source` when inferable. Do not require `status`, `created`, or `updated`. |
| W3 | `## 相关` not last section | Non-index/log page has `## 相关` and any heading or body content after it. |
| W4 | Index drift | Page under `2-Wiki/<domain>/` or `Netease/2-Wiki/<domain>/` missing from that domain `_index.md`, or `_index.md` lists nonexistent page. Ignore `_MOC.md`. |
| W5 | `_index.md` entry format | Domain index entries should be lightweight: `[[Page]] — 一句话摘要`. Do not require duplicated tags/date metadata. |
| W6 | Unknown top-level entry | Public root entry not allowed by `9-Meta/AGENTS.md` plus allowed extras (`Netease/`, `Dashboard.md`, `openspec/`). Ignore hidden/system entries listed above. For private root, apply `Netease/AGENTS.md` allowed structure. |
| W7 | Naming violations | Public sessions: `1-Sessions/YYYY/MM/YYYY-MM-DD-<topic>.md` with optional same-day numeric suffix. Private sessions mirror under `Netease/1-Sessions/`. Private daily notes: `Netease/0-Daily/YYYY/MM/YYYY-MM-DD_日报.md`. Public tools: flat `6-Tools/<类别>-<工具名>.md`. Reserved names: `_index.md`, `_log.md`. |
| W8 | Session structure | Session files missing any required section from `AGENTS.md` Step 6: `## 背景 / 问题`, `## 关键讨论`, `## 结论`, `## 产出物`. |
| W9 | `wiki_pages_touched` validity | Every frontmatter entry resolves to an existing wiki page in the same region or an allowed private-to-public reference. |

### Suggestion

| ID | Check | Detection |
|---|---|---|
| S1 | Orphan pages | Non-index/log wiki pages with zero backlinks. Suggestion only. Missing reciprocal links are not failures. |
| S2 | Wild tag | Tag not in the region whitelist, or nested tag depth exceeds two segments. First consult `TAGS.md` cleanup table; if mapped, suggest exact target. Do not invent new whitelist tags. |
| S3 | Stale active project | Project marked active but no meaningful activity for more than 30 days, only when `status`/activity metadata already exists. Since `status` is no longer required, absence of `status` is not an issue. |
| S4 | Duplicate topics | Same-domain pages with strongly overlapping titles or near-identical opening paragraphs. Flag only; never auto-merge. |

Out of scope: stale-claim detection across sessions/wiki, missing-concept
inference, semantic dedup beyond simple duplicate-topic hints. Route those to
a future deep audit.

## Report Format

```markdown
# Wiki Lint Report — YYYY-MM-DD
- Region(s) scanned: public + private
- Broken-link baseline: <previous N or "never"> → current <N>
- Current unresolved total: <N>

## Critical
### [public] C1 Cross-boundary references
- `path` — problem → suggested fix

## Warning
### [private] W2 Missing frontmatter
- `path` — problem → suggested fix

## Suggestion
### [public] S2 Wild tag
- `path` — problem → suggested fix
```

Rules:

- Show findings in severity order: Critical, Warning, Suggestion.
- Within each severity, split `[public]` and `[private]`.
- Each line includes path, concrete problem, suggested fix.
- If a category has no findings, say `None`.
- Default output is conversation only. Save report only if user asks.

After report, ask:

`哪些需要修复？可回复 "全部"、"只修 Critical"、或具体条目号。`

## Fix Rules

No automatic fixes. Even obvious W2 frontmatter additions require user
confirmation.

After confirmation:

- Frontmatter changes must use `obsidian property:set` /
  `obsidian property:remove`, not raw file writes.
- Content edits, moves, renames, creates, deletes, and wikilink changes must
  go through `obsidian` CLI so Obsidian can update links.
- `lint_wiki.py` is the only maintenance script for lint scans. Do not use
  ad-hoc Python scripts for fixes; confirmed fixes go through Obsidian CLI.
- A pure read-only helper script is acceptable if it modifies nothing.
- Refuse any fix that would create or preserve a public-to-`Netease/` link.

After each fix batch:

1. Run `obsidian unresolved total`; count must not increase.
2. If any Critical item was fixed, re-run C1-C3.
3. Append `_log.md` only for confirmed structural or cross-page fixes:
   `2-Wiki/_log.md` for public, `Netease/2-Wiki/_log.md` for private.
   Do not log read-only lint reports or tiny single-file cleanup.

## Common Pitfalls

- Do not treat root hidden/system entries as W6 violations.
- Do not require `_MOC.md`; it is retired.
- Do not require `status`, `created`, or `updated`.
- Do not trust string-only C1 scans; resolve note names to paths.
- Do not use public tag whitelist for private-only tags.
- Do not merge public/private findings in one list.
