# Link Maintenance Patterns

When `capture` creates or updates a page, it must also maintain the
wiki's link graph. Follow these patterns.

## Principle

Keep wikilinks **bidirectional within ±1 hop**:

- When page A wikilinks to page B, page B SHOULD also wikilink back to A
  (unless A is the root index, which may have one-way outbound links).
- Don't recurse further — updating A↔B doesn't require updating B↔C.
- The goal is a navigable graph, not a fully transitive closure.

## Where wikilinks live on a page

A standard wiki page has the following structure:

```markdown
---
<frontmatter>
---
# <Title>

<body sections>

## 相关

- [[page-a]]
- [[page-b]] — optional one-line why
```

The `## 相关` section at the end of the page is the **canonical place
for cross-references**. Add and remove wikilinks here, not in the body
prose.

Exceptions:
- Wikilinks used in-line in body prose (e.g., "详见 `X`" in a table) are
  kept; they don't need a duplicate in `## 相关`.
- `_index.md` has its own structure; see below.

## Pattern 1 — New page created

When `capture` creates a new page N:

1. **N's `## 相关` section** lists 1–2 wikilinks to existing pages
   (selected per `classification.md` step 6).

2. **Each existing page E that N links to** gets its `## 相关` section
   updated:
   - If E already has a `## 相关` section, append a bullet:
     ```markdown
     - [[path/to/N]] — optional why
     ```
   - If E has no `## 相关` section, create one at the end of the body
     (before any trailing metadata).

3. **The domain's `_index.md`** gets a new line in the appropriate
   sub-section (usually the pattern is: one line per page, sorted
   visually or by logical grouping):
   ```markdown
   - [[path/to/N|display name]] — one-line summary (≤15 字)
   ```

## Pattern 2 — Append to existing page

When `capture` appends content to an existing page P:

1. **P's body** gains the new content in the appropriate section (new
   bullet, new row, new paragraph, or new sub-section).

2. **If the appended content introduces a new wikilink** to a page X
   that P didn't previously link to:
   - Add a bullet to P's `## 相关` section if not already there.
   - Update X's `## 相关` with a back-reference to P.

3. **Usually `_index.md` does NOT need updating on append** — the
   existing entry for P stays valid.

   Exception: if the appended content substantially changes what P is
   about, the one-line summary in `_index.md` may need a refresh.

## Pattern 3 — Renaming or moving a page

Out of scope for `capture`. Rename/move is `obsidian-cli`'s job with
`alwaysUpdateLinks: true` handling the heavy lifting. If the user asks
for rename/move, exit this skill and use `obsidian-cli` directly.

## `_log.md` format

Append one block per capture invocation:

```markdown
## [YYYY-MM-DD] capture | <short subject — what was captured>
- target: [[<new or modified page>]]
- updated back-refs: [[page-a]], [[page-b]]
```

If no back-references were touched, omit the second line.

`_log.md` lives in the **region root** (`<region>/_log.md`, where
`<region>` is `2-Wiki/` or `Netease/2-Wiki/`). Do not write `_log.md`
entries inside domain sub-directories unless the domain explicitly has
its own `_log.md`.

## Edit commands (via obsidian-cli)

All edits go through `obsidian-cli`. Common patterns:

| Operation | Command pattern |
|---|---|
| Create new page | `obsidian create path="<rel>" content="..." silent` |
| Append a line | `obsidian append file="<name>" content="..."` |
| Read before edit | `obsidian read file="<name>"` then `obsidian create ... overwrite silent` for rewrites |
| Set a property | `obsidian property:set name="..." value="..." file="..."` |
| Remove a property | `obsidian property:remove name="..." file="..."` |

Always use `silent` when creating files in batch to keep Obsidian from
opening each one.

## Verification

After all edits, run:

```bash
obsidian unresolved total
```

Compare against the pre-capture baseline (capture should remember this).
If the count increased, a wikilink is broken — surface the delta and the
list of new unresolved items to the user. Do not auto-fix; let the user
decide whether to create the missing page, rename the link, or drop it.

## Examples

### Example A — New gotcha page with one back-ref

Captured content creates
`Netease/2-Wiki/梦幻西游客户端/踩坑集/genInsFromUI传空parent会挂到root.md`
with `## 相关` linking to `[[../UI开发/Handle与Single基类]]`.

Edits made:
1. **Create** the new page (with body, frontmatter, `## 相关`).
2. **Append** to
   `Netease/2-Wiki/梦幻西游客户端/UI开发/Handle与Single基类.md` under
   its `## 相关` section:
   ```markdown
   - [[踩坑集/genInsFromUI传空parent会挂到root]]
   ```
3. **Append** to `Netease/2-Wiki/梦幻西游客户端/踩坑集/_index.md`:
   ```markdown
   - [[genInsFromUI传空parent会挂到root]] — parent=None 时 Handle 会静默挂到 root
   ```
4. **Append** to `Netease/2-Wiki/_log.md`:
   ```markdown
   ## [2026-04-30] capture | genInsFromUI 静默挂 root 的坑
   - target: [[genInsFromUI传空parent会挂到root]]
   - updated back-refs: [[Handle与Single基类]]
   ```
5. Verify: `obsidian unresolved total` should be unchanged.

### Example B — Append a log level to existing page

Captured content adds `log.critical` to the log level table in
`Python编码规范.md`.

Edits made:
1. **Read** the page, find the `## 6. 日志输出` section, append a row
   to the table, rewrite with `obsidian create ... overwrite`.
2. No new wikilinks introduced → `## 相关` unchanged.
3. `_index.md` unchanged (summary still accurate).
4. **Append** to `Netease/2-Wiki/_log.md`:
   ```markdown
   ## [2026-04-30] capture | log.critical 日志级别补充
   - target: [[Python编码规范#6-日志输出]]
   ```
5. Verify.
