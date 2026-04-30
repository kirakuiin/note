---
name: lint-wiki
description: >
visibility: public
area: meta
---
# Lint-Wiki Skill

Inspect the vault for 12 categories of health issues and produce a
structured report ordered by severity. Fixes happen only after user
confirmation.

## When to use this skill

**Explicit triggers:**
- "lint the wiki", "check wiki health", "inspect vault"
- "find broken links", "validate frontmatter"
- "audit wiki", "run wiki checks"

**Auto-trigger on:**
- After any operation affecting >=10 files (ingest, migration, restructure)
- After directory restructuring or file moves
- Before archiving an OpenSpec change
- Monthly health check (if >30 days since last lint)

## Workflow

### Phase 1: Run all checks

Execute all 12 checks. For each, collect affected files and issue
descriptions. Do NOT modify any files during this phase.

**Check 1: Broken wikilinks**
- Run `obsidian unresolved` to get all broken links
- For each broken link, note the source file and the target that doesn't exist

**Check 2: Orphan pages**
- List all .md files excluding `_index.md`, `_MOC.md`, `_log.md`
- For each, check if any other file wikilinks to it (use `obsidian backlinks`)
- Pages with zero backlinks are orphans

**Check 3: Missing frontmatter**
- Scan each .md file for required fields: `area`, `visibility`
- Knowledge pages (under `2-Wiki/`) additionally require: `tags`, `status`
- Session pages (under `1-Sessions/`) additionally require: `tags`, `date`, `topic`

**Check 4: Visibility mismatch**
- Public area files (`2-Wiki/`, `1-Sessions/`, etc.) with `visibility: private`
- `Netease/` files with `visibility: public`

**Check 5: Cross-boundary references**
- Public area files containing wikilinks to `Netease/` paths
- This is a Critical security issue

**Check 6: Index drift**
- Pages in `2-Wiki/<domain>/` not listed in that domain's `_index.md`
- Pages listed in `_index.md` that no longer exist

**Check 7: Duplicate topics**
- Compare titles and content of pages within the same domain
- Flag pairs with >70% title similarity or overlapping content

**Check 8: Stale claims**
- Compare conclusions in old session files against current wiki pages
- Flag where a session's conclusion contradicts current wiki content

**Check 9: Missing concepts**
- Scan wiki pages for terms mentioned >=3 times across files that lack
  their own page
- Flag as "concept missing a page"

**Check 10: Stale projects**
- Check `3-Projects/` for pages with `status: active` but `updated` >30 days ago

**Check 11: Wild tags (out-of-vocabulary)**
- Scan all frontmatter `tags` fields
- Flag any tag not in `9-Meta/TAGS.md` whitelist
- For each wild tag, suggest the closest whitelist match
- If `TAGS.md` doesn't exist, skip this check and note "TAGS.md missing"

**Check 12: Redline tag leaks (Critical)**
- Scan public area files for any tag listed in TAGS.md §3 redline
- This is a Critical privacy issue
- If `TAGS.md` doesn't exist, skip this check

### Phase 2: Produce the report

Structure the report by severity:

```markdown
# Wiki Lint Report — YYYY-MM-DD

## 🔴 Critical
<Issues that pose security or privacy risks>

### Check 5: Cross-boundary references
- `public-file.md` links to `Netease/secret.md` → remove or move reference

### Check 12: Redline tag leaks
- `2-Wiki/game-dev.md` uses `#arcolab` → remove or move file to Netease/

## 🟠 Warning
<Issues that break navigation or data integrity>

### Check 1: Broken wikilinks (N found)
- `file-a.md` → `[[missing-page]]` (target not found)

### Check 3: Missing frontmatter (N found)
- `file-b.md`: missing `tags`, `status`

### Check 6: Index drift (N found)
- `2-Wiki/AI/new-page.md` not in `_index.md`

## 🟡 Suggestion
<Issues that affect quality but not function>

### Check 2: Orphan pages (N found)
- `orphan-page.md` has no incoming links

### Check 7: Duplicate topics
- `page-a.md` and `page-b.md` cover similar ground

...
```

Each issue line must include: file path, problem description, and
suggested fix.

### Phase 3: Wait for user confirmation

Present the report and ask: "哪些需要修复？可以回复'全部修复'、'只修 Critical'、或指定具体条目。"

**Exception — auto-fix allowed without confirmation:**
- Adding missing frontmatter with default values:
  - `area`: infer from file path
  - `visibility: public` (for public area files)
  - `status: draft` (for new pages)
  - `tags: []` (empty, user fills later)
- These are safe defaults that don't change content semantics.

### Phase 4: Execute fixes

For each confirmed fix:
1. Use `obsidian-cli` for all file modifications
2. After each batch of fixes, run `obsidian unresolved` to verify no
   new broken links were introduced
3. Append to `2-Wiki/_log.md`:
   ```markdown
   ## [YYYY-MM-DD] lint-fix | <summary>
   - fixed: <N> issues across <M> files
   ```

### Phase 5: Archive report (optional)

If the user requests, save the report to:
`1-Sessions/YYYY/MM/YYYY-MM-DD-lint-report.md`

## Check reference

| # | Check | Severity | Auto-fix? |
|---|-------|----------|-----------|
| 1 | Broken wikilinks | Warning | No |
| 2 | Orphan pages | Suggestion | No |
| 3 | Missing frontmatter | Warning | Yes (defaults only) |
| 4 | Visibility mismatch | Critical | No |
| 5 | Cross-boundary refs | Critical | No |
| 6 | Index drift | Warning | No |
| 7 | Duplicate topics | Suggestion | No |
| 8 | Stale claims | Suggestion | No |
| 9 | Missing concepts | Suggestion | No |
| 10 | Stale projects | Suggestion | No |
| 11 | Wild tags | Suggestion | No |
| 12 | Redline tag leaks | Critical | No |

## Important constraints

- **Read-only until confirmed.** Phase 1-2 must not modify any files
  (except `_log.md` append for lint execution record).
- **Use obsidian-cli for all fixes.** Never use `mv`, `write`, or
  direct file tools for vault files.
- **Use Obsidian Flavored Markdown** for the report and any filed
  content. Wikilinks, callouts, and proper frontmatter throughout.
- **Respect public/private boundary.** When checking cross-boundary
  references, treat any wikilink to `Netease/` from public area as
  Critical.
- **TAGS.md is the authority for checks 11-12.** If TAGS.md is missing,
  skip those checks and note it in the report header.
- **Verify after fixes.** Run `obsidian unresolved` after each batch
  of modifications.
