---
name: ingest
description: >
  Ingest a conversation or document into the vault. Creates a session file in
  1-Sessions/YYYY/MM/ and optionally extracts knowledge into 2-Wiki/ pages.
  Use this skill whenever the user asks to archive, summarize, ingest, or
  capture a conversation, chat, document, article, or meeting. Also use when
  the user says "save this", "record this", "write this up", "make a note of
  this", or similar capture intents.
---

# Ingest Skill

Turn a conversation or document into a structured session record, and
optionally extract lasting knowledge into wiki pages.

## When to use this skill

- User says "archive this conversation", "summarize this chat", "ingest this"
- User pastes a document/article and wants it digested
- User says "save this", "record this", "write this up", "make a note of this"
- After a session that produced new insights, decisions, or wiki pages

Do NOT trigger on: casual "remember this" (too vague), single-line facts
(better as direct wiki edits), or when the user is actively mid-discussion.

## Workflow

### Phase 1: Determine scope

1. **Ask public or private**: "Save to public vault or netease/ private area?"
   Default to public unless the content references work projects, internal
   systems, or sensitive data.
2. **Ask for topic**: If the user hasn't provided one, propose a 5-15 word
   topic based on the conversation. Let the user confirm or edit.
3. **Identify source type**: conversation (this chat) or external document
   (user pasted content). This affects the session file structure.

### Phase 2: Write the session file

Create the file at `<vault>/1-Sessions/YYYY/MM/YYYY-MM-DD-<topic>.md`
(or `netease/1-Sessions/...` for private).

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

After writing the session file, scan the conversation for knowledge that
deserves a permanent wiki page. Ask yourself:

- Was a new concept defined or explained?
- Was a technique/pattern/method demonstrated?
- Was a comparison or synthesis across multiple topics made?
- Was a bug/trap documented with a solution?
- Did the user explicitly ask to create a wiki page?

If nothing qualifies, skip to Phase 5 with `wiki_pages_touched: []`.

### Phase 4: Propose and execute wiki updates

1. **List proposed changes**: "I found X items worth saving to wiki:
   - New page: [[概念名]] — <one-line description>
   - Update: [[已有页面]] — <what to add>"
2. **Wait for user confirmation**. User can accept all, pick some, or reject.
3. **Execute confirmed changes**:
   - New pages: `obsidian create` with `wiki-page` template, write to
     `2-Wiki/<domain>/` matching the appropriate TAGS.md domain tag
   - Updates: `obsidian append` or `obsidian read` + edit + write back
   - Update `_index.md` in the affected wiki directory
   - Append to `2-Wiki/_log.md` (or netease equivalent)
4. **Backfill**: Update the session file's `wiki_pages_touched` with
   wikilinks to all affected pages.

### Phase 5: Log and verify

1. Append to `2-Wiki/_log.md` (or netease equivalent):
   ```markdown
   ## [YYYY-MM-DD] ingest | <topic>
   - session: [[1-Sessions/YYYY/MM/YYYY-MM-DD-<topic>]]
   - touched: [[page1]], [[page2]]
   ```
2. Run `obsidian unresolved` to verify no broken links were introduced.
3. Report summary to user: "Session saved. X wiki pages created/updated."

## Important constraints

- **Session files are concise records, not transcripts.** 200-800 words.
  If the conversation was very long, capture only the highlights.
- **Never write wiki pages without user confirmation.** The session file
  itself can be created without confirmation (it's just a record), but
  wiki modifications must be approved.
- **Respect the public/private boundary.** Private content goes to
  `netease/1-Sessions/`, public to `1-Sessions/`. Never cross-reference
  between them.
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
