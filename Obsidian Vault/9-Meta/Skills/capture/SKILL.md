---
name: capture
description: >
  Capture a single development lesson, pitfall, spec, or short insight into the
  user's Obsidian wiki. Prefer appending to the most relevant existing page;
  create a new page only when no good home exists. Triggers on explicit user
  phrases like "记一下", "归档", "录入 wiki", "capture this", "把这个记到 wiki",
  "追加到 [[页面]]". Do NOT use this skill to archive a full chat or a long
  document (use the `ingest` skill for those). Do NOT use this skill just
  because the user stated a fact — wait until they explicitly ask to save it.
  This skill writes only one targeted piece of content per invocation.
visibility: public
area: meta
---
# Capture Skill

Capture one bite-sized piece of development knowledge (a lesson learned,
a project-specific convention, a gotcha, a short tip) into the user's
Obsidian wiki, with correct classification and link maintenance.

This skill is a lightweight counterpart to `ingest`:

| Skill | Use when |
|---|---|
| `ingest` | There is a whole conversation or a full external document worth archiving. Produces a session file + optional wiki pages. |
| `capture` (this) | There is only a single atomic piece of knowledge worth saving — a lesson, a rule, a trap. Writes straight to wiki. No session file. |

## When to trigger

**Trigger only on explicit user intent.** The user must say something like:

- "这个记一下" / "记到 wiki" / "归档这条"
- "把 X 追加到 [[Y]]"
- "capture this" / "save this lesson" / "log this gotcha"

**Do NOT trigger** when:
- The user just stated a fact in passing and moved on. Wait for an explicit save intent.
- The content is a whole conversation or a long document (>200 chars of prose). Route to `ingest` instead.
- The user is asking a knowledge question ("what do I know about X?"). Route to `query-wiki`.

When in doubt about whether to trigger, ask one short question before acting.

## Vault location

The wiki lives in an Obsidian vault whose path is given by the
`OBSIDIAN_VAULT` environment variable. Read it at the start of each invocation:

- Windows: `%OBSIDIAN_VAULT%`
- macOS/Linux: `$OBSIDIAN_VAULT`

If the variable is unset, stop and ask the user to configure it (e.g.,
`setx OBSIDIAN_VAULT "c:\\path\\to\\vault"` on Windows). Do not guess a path.

All vault-relative paths in this skill resolve against that root.

## Public / private routing

The vault has two regions with a hard separation (see `9-Meta/AGENTS.md` §4):

- **Public**: `<vault>/2-Wiki/` (shared knowledge, eventually git-pushed)
- **Private**: `<vault>/Netease/2-Wiki/` (work-only, never pushed)

Pick the target region BEFORE doing anything else:

1. **CWD heuristic** — if the current working directory is inside a known
   work repository, prefer private.
2. **Content heuristic** — if the content mentions internal project names,
   internal module names, or tags on the red-line list in
   `<vault>/9-Meta/TAGS.md` §3, prefer private.
3. **Otherwise** default to public.
4. **If uncertain**, ask: "录入到公开 wiki (`2-Wiki/`) 还是私有区 (`Netease/2-Wiki/`)？"

The public/private red line is non-negotiable: a public page must never
wikilink or embed a private page. If the user's content would create such
a link, stop and surface it.

## Workflow

### Step 1 — Classify

Given the content, decide where it belongs. Read
`references/classification.md` for the decision procedure in detail. In
short:

1. Read the target region's top-level `_index.md` (`2-Wiki/_index.md` or
   `Netease/2-Wiki/_index.md`) to see existing domains.
2. Match the content to a domain by topic and keywords.
3. Read that domain's `_index.md` and `_MOC.md` to see existing pages.
4. Decide: **append to an existing page** or **create a new page**?
   - Append if the content is a follow-up / addition / new bullet on an
     existing topic.
   - New page if the content is a self-contained concept, lesson, or
     gotcha that has no natural parent page.
5. If creating a new page, pick the right sub-directory (e.g., `UI开发/`,
   `踩坑集/`) by looking at the domain's structure. If no sub-directory
   fits, propose placing the page at the domain root.
   **File name**: match sibling pages' naming style and length — read
   the existing pages in the target directory and follow whatever
   convention is in use (e.g., `模块_具体症状.md`). A new page whose
   filename is markedly longer or differently styled than its siblings
   is a smell.
6. If no domain fits at all, propose creating a new domain directory —
   but require explicit user confirmation, never create a top-level
   directory silently. **When asking, list options neutrally; do not
   mark one as "Recommended"** — the user's judgment on taxonomy is
   better informed than the skill's.

### Step 2 — Draft

Produce a draft **without writing any file yet**. The draft contains:

- **Decision**: `new page` or `append to [[existing page#section]]`
- **Target path** (vault-relative)
- **Frontmatter** (keep it minimal — see next section)
- **Body** (the actual content, in Obsidian Flavored Markdown)
- **Link updates**: which existing pages will gain a back-reference, and
  which `_index.md` / `_MOC.md` / `_log.md` files will be updated
- **Command plan**: the exact `obsidian` CLI commands that will run in
  Step 3 (one per line, in order). This lets the user catch a wrong
  `path=`/`file=` flag or a nonexistent target before anything is
  written.

Before showing the draft, run these checks:

1. **Wikilink targets exist.** Every `[[X]]` that the new body introduces
   must resolve to a real file in the vault. Glob / list to verify. If
   the target doesn't exist, either remove the link or flip the draft to
   also propose creating the missing page (but ask the user first).
2. **Append target structure.** If the decision is "append", read the
   target page and note any existing tables/lists the new fact belongs
   to. Do not add the same fact in two places (e.g., code block AND
   table) — pick the one that matches the page's current structure.
3. **`_log.md` style.** Read a few existing entries in the target
   region's `_log.md` and match their style (headers vs. bullets,
   date format, field order).
4. **Do not invent mechanism.** If the user reported only a symptom,
   keep the body to the symptom + workaround. Never dress up your own
   guess as the cause. When a cause is worth noting at all, prefix it
   with `(推测)` or use a `> [!question] 待验证` callout.
5. **Stay close to the user's wording.** Especially for short gotchas,
   resist the urge to add "usage advice" the user didn't give. Quote
   their framing; only generalize if they explicitly asked you to.

Present the draft to the user. Ask: "这个方案看着对吗？确认我就落盘。"

### Step 3 — Execute (only after confirmation)

Use the `obsidian-cli` skill for every file operation. See the
`obsidian-cli` skill for syntax and the `obsidian-markdown` skill for
content syntax.

Order of operations:

1. **Write/append** the main target file.
2. **Update back-references** — edit the "相关" (Related) section of each
   existing page that the new content cross-references, adding a
   wikilink back to the new page. See `references/link-maintenance.md`.
3. **Update `_index.md`** — if a new page was created, append a line to
   the domain's `_index.md` in the format:
   ```markdown
   - [[Page Name]] — one-line summary (~15 字以内)
   ```
4. **Update `_log.md`** — before appending, read the last few entries
   to match their existing style (headers vs. bullets, date format,
   field order). As a reference template, entries look roughly like:
   ```markdown
   ## [YYYY-MM-DD] capture | <short subject>
   - target: [[page-name]]
   - updated back-refs: [[page-a]], [[page-b]]
   ```
   — but follow the file's current style if it differs.
5. **Verify links** — run `obsidian unresolved total` once; if the count
   increased, report the delta and surface it to the user.

### Step 4 — Report

Tell the user what was written, what was updated, and the unresolved-link
delta (should be 0). Keep it brief.

## Frontmatter minimal policy

Keep frontmatter as short as possible. The rules:

**Always required** (for all knowledge pages):
```yaml
---
area: knowledge
visibility: public     # or private, must match the path
tags:
  - <at least 1 tag>   # from TAGS.md whitelist (see §Tags)
---
```

**Optional** — only include when genuinely useful:
- `status` — include **only if the content's maturity is unclear**
  (e.g., `status: stable` once the user has run the code in prod, or
  `status: draft` when the content is explicitly a guess/TODO). Most
  captured lessons are already stable facts the user has hit —
  prefer omitting `status` over defaulting to `draft`.
- `created` / `updated` — add only if the user wants versioning; skip
  otherwise (the filesystem already tracks mtime).
- `aliases` — only if the page has a common alternate name that would
  appear in wikilinks.

**Do NOT add** custom provenance fields like `source_skill`, `source_repo`,
`source_session`. Frontmatter minimality beats provenance tracking —
provenance can live in the body prose or in `_log.md`.

## Tags policy

Tags are recommended but not required. When assigning tags:

1. **Read the tag vocabulary first**: `<vault>/9-Meta/TAGS.md` (public)
   or the private tag section of `Netease/AGENTS.md` §4 (private).
2. **Only use tags already in the whitelist.** Do not invent tags.
3. **If the needed tag is not in the whitelist**, stop and ask the user:
   "需要 tag `#xxx`，但不在白名单里。要我把它加到 `TAGS.md` 吗？"
4. **If the user confirms a new tag**, add it to `TAGS.md` in the correct
   section (领域 / 类型 / 状态 / 来源 / 红线) BEFORE using it in the
   page. TAGS.md is the single source of truth; pages and vocabulary
   must stay in sync.
5. **Deprecated tags** (marked in TAGS.md `[deprecated]` or §4 历史脏 tag 清理表):
   do not use; substitute the target tag per the cleanup table.

## Link maintenance summary

The wiki's value comes from dense, accurate wikilinks. When capturing:

- The new/updated page SHOULD have a **"## 相关"** section listing 1–2
  wikilinks to directly related pages.
- **`## 相关` must be the last section of the file** (AGENTS.md §5.4).
  Nothing else may come after it. This lets back-ref maintenance use
  cheap `obsidian append` rather than fragile `eval` + string patching.
- Each page wikilinked FROM the new page SHOULD gain a reciprocal
  wikilink back in ITS "## 相关" section — making the relationship
  bidirectional.
- Before appending a back-ref to a target page, `read` it to confirm
  `## 相关` is the last section. If it isn't (legacy page), either
  patch via `eval`, or fix the page to put `## 相关` last as part of
  this capture (±1 hop scope).
- Scope: stay within ±1 hop. Don't recursively update the whole graph.
- See `references/link-maintenance.md` for exact edit patterns.

## What NOT to do

- Do NOT write files before the user confirms the draft.
- Do NOT use generic file tools (`write`, `edit`, `mv`). Every vault
  file operation goes through the `obsidian-cli` skill.
- Do NOT create a wikilink from a public-region page to a
  `Netease/`-region page. If the content seems to require that, stop
  and surface it.
- Do NOT invent tags. Use TAGS.md whitelist, or ask before adding new.
- Do NOT add provenance frontmatter fields. Keep it minimal.
- Do NOT create a new top-level domain directory without explicit user
  confirmation.
- Do NOT invent causes/mechanisms the user didn't provide. Symptom +
  workaround is enough; mark any hypothesis as `(推测)` or surface it
  as a `> [!question]` callout.
- Do NOT recommend one option over another when asking "new domain vs.
  which existing domain". List options neutrally.
- Do NOT claim `unresolved delta = 0` in a draft without actually
  verifying that every new `[[X]]` resolves to an existing file.
- Do NOT trigger this skill for a whole chat or long document — route
  to `ingest` instead.

## References

- `references/classification.md` — classification decision procedure
- `references/link-maintenance.md` — bidirectional wikilink patterns
- External: `obsidian-cli` skill (file ops), `obsidian-markdown` skill
  (OFM syntax), `<vault>/9-Meta/AGENTS.md` (public region rules),
  `<vault>/Netease/AGENTS.md` (private region rules),
  `<vault>/9-Meta/TAGS.md` (tag vocabulary)
