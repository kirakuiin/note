---
name: lint-wiki
description: >
  Audit an Obsidian vault for wiki health issues such as broken wikilinks,
  public/private boundary leaks, redline tag leaks, visibility mismatches,
  missing frontmatter, index drift, naming violations, orphan pages, and stale
  project pages. Use when the user asks to lint the wiki, check wiki health,
  find broken links, validate frontmatter, audit the vault, or fix reported
  wiki lint issues.
visibility: public
area: meta
---
# Lint-Wiki Skill

Inspect the vault for health issues, produce a severity-ordered report,
fix only after user confirmation.

Lint protects safety and mechanical maintainability. It should catch broken
links, boundary leaks, invalid metadata, and missing lightweight indexes; it
should not try to make the wiki graph perfect.

## When to use this skill

**Explicit:** "lint the wiki", "check wiki health", "find broken links",
"validate frontmatter", "audit vault".

**Auto-trigger:** after any operation affecting >=10 vault files, after
restructuring/file moves, before archiving an OpenSpec change, or if
>30 days since last lint.

## Vault location

Vault root comes from the `OBSIDIAN_VAULT` env var (Windows:
`%OBSIDIAN_VAULT%`, Unix: `$OBSIDIAN_VAULT`). If unset, stop and ask the
user to set it (e.g., `setx OBSIDIAN_VAULT "c:\\path\\to\\vault"`). Do
not guess, do not fall back to pwd. All paths in this skill resolve
against that root.

## Region routing

The vault has two regions with distinct rules:

| Region | Path | Authority | Tag vocab | visibility |
|---|---|---|---|---|
| Public | not under `Netease/` | `9-Meta/AGENTS.md` | `9-Meta/TAGS.md` | `public` |
| Private | under `Netease/` | `Netease/AGENTS.md` | private vocab in `Netease/AGENTS.md` §4 | `private` |

Before scanning, read **both** AGENTS.md files (if `Netease/` exists)
so each file is checked against its own vocab. Report region-tagged
issues separately — never merge public + private rows
(AGENTS.md §4 audit rule).

## Workflow

### Phase 1: Run all checks (read-only)

#### 🔴 Critical (security/privacy)

| # | Check | Detection |
|---|---|---|
| C1 | Cross-boundary references | Public file wikilinks/embeds/frontmatter pointing to a `Netease/` path |
| C2 | Redline tag leak | Public file has any tag in TAGS.md §3 — match literal entries (§3.1–§3.4 + §3.5 explicit nested paths) AND prefix patterns (`#sdc/*`, `#Arcolab/*`, `#frame-tool/*`, `#战斗/*`, `#战斗系统/*`, `#模块/*`, `#文档/*`) |
| C3 | Visibility mismatch | `visibility` field disagrees with path region (Netease/ → must be `private`; else `public`) |

#### 🟠 Warning (data integrity)

| # | Check | Detection |
|---|---|---|
| W1 | Broken wikilinks | `obsidian unresolved` |
| W2 | Missing frontmatter | Per-area requirements from AGENTS.md §5.1: knowledge (`tags`>=1), session (`tags`>=1, `date`, `topic`), project (`tags`>=1), journal (`date`), tool (`category`); private files additionally need `visibility: private` |
| W3 | `## 相关` not last section | Any non-index/log page where `## 相关` exists with content or another heading after it (breaks the cheap append protocol — AGENTS.md §5.4) |
| W4 | Index drift | Page in `2-Wiki/<domain>/` not listed in domain `_index.md`, or `_index.md` lists a nonexistent page |
| W5 | `_index.md` entry format | Lines should be lightweight: `[[Page]] — 一句话摘要`; do not require duplicated tags/date metadata |
| W6 | Unknown top-level dir | Any vault root entry not in AGENTS.md §3 whitelist + allowed extras (`Netease/`, `Dashboard.md`, `openspec/`) — new top-level dirs require an OpenSpec change |
| W7 | Naming violations | Session: `1-Sessions/YYYY/MM/YYYY-MM-DD-<topic>.md` (or `-N` suffix for same-day repeats); `6-Tools/`: flat `<类别>-<工具名>.md`; reserved fixed names: `_index.md` / `_log.md` |
| W8 | Session structure | `1-Sessions/` files missing any of `## 背景` / `## 关键讨论` / `## 结论` / `## 产出物` (AGENTS.md §9 Step 6) |
| W9 | `wiki_pages_touched` validity | Each entry in a session's `wiki_pages_touched` must resolve to an existing wiki page |

#### 🟡 Suggestion (quality)

| # | Check | Detection |
|---|---|---|
| S1 | Orphan pages | Non-index/log pages with zero `obsidian backlinks` |
| S2 | Wild tag | Tag not in the region's whitelist. **Always look up TAGS.md §4 cleanup table first** — if there's a mapped target, suggest it; only fall back to "closest match" when no §4 entry exists. Also enforce TAGS.md §1: nested tag's top-level segment must be in the whitelist and tag depth must be at most two (`#top` or `#top/sub`) |
| S3 | Duplicate topics | Same-domain pages with strongly overlapping titles or near-identical first paragraphs (flag only — never auto-merge) |

### Phase 2: Produce the report

```markdown
# Wiki Lint Report — YYYY-MM-DD
- Region(s) scanned: public + private (or just one)
- Broken-link baseline: <prev N> → current <N> (delta <±N>)
- Last lint: <date or "never">

## 🔴 Critical
### [public] C1 Cross-boundary references
- `path` — issue → suggested fix

### [private] C2 ...

## 🟠 Warning
### [public] W3 ...

## 🟡 Suggestion
### [public] S2 ...
```

Each line: file path, problem, suggested fix. Public and private rows
go under separate sub-headings.

### Phase 3: Confirmation

Present the report. Ask:
"哪些需要修复？可回复 '全部'、'只修 Critical'、或具体条目号。"

**Auto-fix without asking** — only if all true:
1. Issue is W2 (missing frontmatter)
2. Fix is field **addition**, never a value change
3. Default values: `area` inferred from path; `visibility` = `private`
   if path under `Netease/` else `public`; `tags: []` only when no whitelist
   tag can be inferred safely. Empty tags
   remain a warning for user follow-up; do not pretend the tag requirement is
   fully fixed.

All other fixes require explicit confirmation, including any value
change, file move, or content edit.

### Phase 4: Execute fixes

**Frontmatter changes** SHALL go through `obsidian property:set` /
`property:remove`, never raw `edit`/`write`. AGENTS.md §8.3.1 puts
frontmatter outside the edit-tool exception (even for auto-fixes).

**Content / file ops** (move, rename, create, delete, body edits
involving wikilinks) SHALL go through `obsidian-cli`. Obsidian's
link auto-update (`alwaysUpdateLinks: true`) only fires through the cli.

After each fix batch:
1. Run `obsidian unresolved total`; verify count is ≤ baseline.
2. If a Critical fix was applied, re-run C1+C2+C3 to confirm closure.
3. Refuse to write any fix that would create a public→private wikilink.

### Phase 5: Log + persist baseline (mandatory)

1. Append to `2-Wiki/_log.md` (or `Netease/2-Wiki/_log.md` for private):
   ```markdown
   ## [YYYY-MM-DD] lint | <one-line summary>
   - critical: <N> | warning: <N> | suggestion: <N>
   - fixed: <N> across <M> files
   - unresolved delta: <±N>
   ```
2. Save the full report to
   `1-Sessions/YYYY/MM/YYYY-MM-DD-lint-report.md`
   (or `Netease/1-Sessions/...` for private). Always — the next lint
   diffs against this baseline.

## Check reference

| # | Check | Severity | Auto-fix? |
|---|---|---|---|
| C1 | Cross-boundary refs | Critical | No |
| C2 | Redline tag leak (incl. §3.5 prefixes) | Critical | No |
| C3 | Visibility mismatch | Critical | No |
| W1 | Broken wikilinks | Warning | No |
| W2 | Missing frontmatter | Warning | Yes (defaults only, via cli) |
| W3 | `## 相关` not last section | Warning | No |
| W4 | Index drift | Warning | No |
| W5 | `_index.md` entry format | Warning | No |
| W6 | Unknown top-level dir | Warning | No |
| W7 | Naming violations | Warning | No |
| W8 | Session structure | Warning | No |
| W9 | `wiki_pages_touched` validity | Warning | No |
| S1 | Orphan pages | Suggestion | No |
| S2 | Wild tag (consult TAGS.md §4 first) | Suggestion | No |
| S3 | Stale project | Suggestion | No |
| S4 | Duplicate topics | Suggestion | No |

## Important constraints

- **Read-only until confirmed.** Phase 1-2 modify nothing; `_log.md`
  append happens only in Phase 5.
- **Region authority.** Public files follow `9-Meta/AGENTS.md` +
  `9-Meta/TAGS.md`; private files follow `Netease/AGENTS.md` + its
  internal vocab. Mixing the two is a bug.
- **Frontmatter via cli.** Even auto-fixes use `obsidian property:set`,
  not raw edits.
- **Cli for vault file ops.** No `mv`, `write`, `xcopy` for
  `.md`/`.base`/`.canvas`.
- **TAGS.md §4 cleanup table is authoritative for wild-tag renames.**
  Don't invent "closest match" when an exact target exists.
- **Boundary scope.** C1, C2, C3 are Critical. Refuse to write a fix
  that would create or preserve a public→private link.
- **No MOC maintenance.** `_MOC.md` is retired from the maintenance path.
  Do not require it, recreate it, update it, or report its absence as drift.
- **No graph-completeness enforcement.** Missing reciprocal backlinks are not
  lint failures. Orphans, duplicates, and stale pages stay Suggestions.
- **Out of scope (route to a future `deep-audit` skill):** stale-claim
  detection across sessions/wiki, missing-concept inference, deep
  semantic dedup. Lint stays mechanical.
