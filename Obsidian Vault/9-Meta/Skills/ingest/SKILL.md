---
name: ingest
description: >
  Turn a conversation, chat, pasted article, or external document into a concise
  optional Obsidian session record, then optionally propose extracting durable
  knowledge into wiki pages. Use when the user asks to archive, ingest,
  summarize, save, record, or write up a whole conversation, long discussion,
  external document, or multi-page decision trail rather than a single atomic
  fact.
visibility: public
area: meta
---
# Ingest Skill

Turn a conversation or document into an optional structured session record,
and optionally extract lasting knowledge into wiki pages.

## When to use this skill

- User says "archive this conversation", "summarize this chat", "ingest this"
- User pastes a long document/article and wants it digested
- User says "save this", "record this", "write this up", or "make a note of this"
  where "this" clearly refers to a whole conversation, long document,
  multi-page change, or decision trail
- The user explicitly asks to record a session that produced new insights,
  decisions, or wiki pages

Do NOT trigger on: casual "remember this" (too vague), single-line facts
(route to `capture`), one bug/gotcha/rule (route to `capture`), or when
the user is actively mid-discussion.

## Vault location

The wiki lives in an Obsidian vault whose path is given by the
`OBSIDIAN_VAULT` environment variable. Read it at the start of each invocation:

- Windows: `%OBSIDIAN_VAULT%`
- macOS/Linux: `$OBSIDIAN_VAULT`

If the variable is unset, stop and ask the user to configure it (e.g.,
`setx OBSIDIAN_VAULT "c:\\path\\to\\vault"` on Windows). Do not guess a
path, and do not fall back to the current working directory — this skill
is often invoked from an unrelated project directory.

All vault-relative paths in this skill (e.g., `<vault>/1-Sessions/...`,
`2-Wiki/...`, `Netease/1-Sessions/...`) resolve against that root.

## Workflow

### Phase 1: Determine scope

1. **Ask public or private**: "Save to public vault or Netease/ private area?"
   Default to public unless the content references work projects, internal
   systems, or sensitive data.
2. **Ask for topic**: If the user hasn't provided one, propose a 5-15 word
   topic based on the conversation. Let the user confirm or edit.
3. **Identify source type**: conversation (this chat) or external document
   (user pasted content). This affects the session file structure.
4. **Decide whether to create a session file**. Create one by default for
   long conversations/documents, multi-page wiki updates, important decisions,
   tradeoffs, disputes, or explicit user requests. Do not create a session for
   one reusable fact/gotcha/rule even if the wording is >200 characters; route
   that to `capture`. Conversely, a short exchange can still need `ingest` if
   the decision trail or source context matters.

### Phase 2: Write the session file when needed

If Phase 1 decides a session is needed, create the file at
`<vault>/1-Sessions/YYYY/MM/YYYY-MM-DD-<topic>.md` (or
`Netease/1-Sessions/...` for private). If no session is needed, skip to
Phase 3 and handle the durable knowledge with `capture`.

Use `obsidian create` with the `session` template if available, otherwise
construct the file manually. Keep it concise — 200-800 words.

**Required frontmatter:**
```yaml
---
area: session
visibility: public  # or private
date: YYYY-MM-DD
topic: "<short title>"
tags:
  - <relevant tags from TAGS.md>
wiki_pages_touched: []
---
```

**Body structure (keep each section brief):**

```markdown
## 背景
<1-2 sentences: what prompted this, source if external doc>

## 关键讨论
<Bullet points only. No narrative. Capture decisions, insights, disagreements.
3-8 bullets is ideal.>

## 结论
<1-3 sentences: what was decided or learned>

## 产出物
<Wikilinks to created/updated wiki pages, or "无" if none>

## 后续
<Optional. Unfinished items, open questions. Omit if empty.>
```

**Rules for conciseness:**
- Bullet points, not paragraphs
- One idea per bullet
- Skip "the user said / the agent replied" framing — just capture the content
- If the conversation was long, only capture what's worth revisiting later
- External document source: note the URL/title in 背景, attach raw text only
  if the user explicitly asks

### Phase 3: Detect wiki-worthy knowledge

After writing the session file (if any), scan the conversation or document for
knowledge that deserves a permanent wiki page. Ask yourself:

- Was a new concept defined or explained?
- Was a technique/pattern/method demonstrated?
- Was a comparison or synthesis across multiple topics made?
- Was a bug/trap documented with a solution?
- Did the user explicitly ask to create a wiki page?

If nothing qualifies and a session was created, skip to Phase 5 with
`wiki_pages_touched: []`. If no session was created and nothing qualifies,
write nothing.

### Phase 4: Propose and execute wiki updates

1. **List proposed capture items**: "I found X items worth saving to wiki:
   - Capture: `概念名` — <new page or append target, one-line description>
   - Capture: `已有页面` — <what to add>"
2. **Wait for user confirmation**. User can accept all, pick some, or reject.
3. **Execute confirmed changes using `capture`'s write rules**:
   - classify target region/domain/page
   - create or append the main knowledge page
   - update `_index.md` only for newly created pages
   - add reciprocal backlinks only for strong relationships or explicit
     user request
   - update `_log.md` in the target region only when the ingest creates
     a session, creates wiki pages, or updates multiple existing pages
   - run `obsidian unresolved`
4. **Backfill when a session exists**: Update the session file's
   `wiki_pages_touched` with wikilinks to all affected pages.

### Phase 5: Log and verify

1. If a session was created, or the ingest touched multiple wiki pages,
   append a compact batch entry to `2-Wiki/_log.md` (or Netease
   equivalent):
   ```markdown
   ## [YYYY-MM-DD] ingest | <topic>
   - session: [[1-Sessions/YYYY/MM/YYYY-MM-DD-<topic>]]
   - touched: [[page1]], [[page2]]
   ```
   Skip `_log.md` for small direct captures that only append one fact to
   one existing page.
2. Run `obsidian unresolved` to verify no broken links were introduced.
3. Report summary to user: "Session saved. X wiki pages created/updated." If
   no session was created, report only the wiki pages created/updated.

## Important constraints

- **Session files are optional concise records, not transcripts.** 200-800 words.
  If the conversation was very long, capture only the highlights.
- **Never write wiki pages without user confirmation.** The session file
  itself can be created without confirmation (it's just a record), but
  wiki modifications must be approved.
- **Do not create a session for single atomic knowledge.** Route single
  lessons, gotchas, rules, compact specs, and small append requests to
  `capture`; use `ingest` when source context or decisions need traceability.
- **Respect the public/private boundary.** Private content goes to
  `Netease/1-Sessions/` / `Netease/2-Wiki/`, public to `1-Sessions/` /
  `2-Wiki/`. Public-region files must never wikilink, embed, or
  frontmatter-reference `Netease/` paths. Private-region files may link to
  public wiki pages when useful. If one ingest spans both regions, split
  outputs by region and report them separately.
- **Tags must come from `9-Meta/TAGS.md`.** Read the tag vocabulary before
  assigning tags. If a needed tag isn't in the whitelist, ask the user
  before using it.
- **Use obsidian-cli for all file operations.** Never use `mv`, `write`,
  or direct file tools for vault files.
- **Use Obsidian Flavored Markdown** for all vault content. Session files
  and wiki pages must use wikilinks (`[[...]]`), callouts (`> [!note]`),
  embeds (`![[...]]`), and proper YAML frontmatter. See `obsidian-markdown`
  skill for full syntax reference.

## Templates reference

- `9-Meta/Templates/session.md` — session file template (if exists)
- `9-Meta/Templates/wiki-page.md` — wiki page template (if exists)
- `9-Meta/TAGS.md` — tag vocabulary (read before assigning tags)
