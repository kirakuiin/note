---
name: query-wiki
description: >
  Answer questions by searching and synthesizing the vault wiki. Reads
  _index.md to find candidate pages, drills into relevant content, and
  produces cited answers. Use this skill whenever the user asks a
  knowledge question that might be answered by the wiki — "what do I
  know about X", "have I studied Y", "compare A and B", "what's the
  best practice for Z", or any question where the answer likely lives
  in 2-Wiki/ or 1-Sessions/. Also use when the user says "search my
  notes", "check my wiki", "look up", "find in vault".
---

# Query-Wiki Skill

Answer questions from the vault wiki with citations, and identify when
answers are worth filing back as permanent wiki pages.

## When to use this skill

**Auto-trigger on knowledge questions:**
- "What do I know about X?"
- "Have I studied Y before?"
- "Compare A and B"
- "What's the best practice for Z?"
- "How does X work?" (when X is a topic the user has studied)
- "What was that thing about ...?"

**Explicit triggers:**
- "Search my notes for ..."
- "Check the wiki for ..."
- "Look up ... in my vault"

**Do NOT trigger on:**
- Procedural questions ("how do I open this file")
- Current-state questions ("what's the weather")
- Questions clearly about netease work (those go to netease side)
- Questions the user clearly intends to answer from the web, not the vault

## Workflow

### Phase 1: Determine scope

1. **Classify the query**:
   - **Public domain** (general knowledge, learning, personal): search only
     `2-Wiki/` and `1-Sessions/` public side
   - **Work domain** (netease projects, internal systems): search both
     `netease/2-Wiki/`, `netease/1-Sessions/`, and public side
   - **Unclear**: ask the user "Should I search public wiki only, or
     include netease work notes?"

2. **If the query is ambiguous**, ask one clarifying question before
   searching. Don't spend more than one exchange on clarification.

### Phase 2: Search and read

1. **Read `_index.md` first.** Start with `2-Wiki/_index.md` (and
   `netease/2-Wiki/_index.md` if work domain). Scan for pages matching
   the query by title, tag, or description.

2. **Identify candidate pages.** Pick up to 5 most relevant pages based
   on title match, tag match, and description relevance.

3. **Read candidates.** Read each candidate page. If a page is long
   (>200 lines), read the first 50 lines first, then decide whether
   to read more.

4. **Expand if needed.** If the top 5 pages don't contain the answer:
   - Search `1-Sessions/` for related session files (use `obsidian search`
     or grep for keywords)
   - Check `_MOC.md` files in relevant `2-Wiki/<domain>/` directories
   - If still nothing, report "wiki doesn't have this yet"

### Phase 3: Synthesize and answer

**All answers must use Obsidian Flavored Markdown** — the same syntax
used throughout the vault. This means:

- **Wikilinks** for all page references: `[[Page Name]]` or
  `[[Page Name|display text]]`
- **Callouts** for highlights, warnings, or key takeaways:
  `> [!note]` / `> [!warning]` / `> [!tip]`
- **Embeds** when showing content from another page: `![[Page#section]]`
- **Frontmatter** when the answer is filed as a wiki page (via ingest)

1. **Direct answer**: If one page answers the question, quote or
   summarize it, and cite: `详见 [[Page Name]]`

2. **Multi-page synthesis**: If the answer spans multiple pages,
   structure the response:
   ```markdown
   ## <Question>
   <Synthesized answer, 1-3 paragraphs>

   > [!note] 参考页面
   > - [[Page 1]] — <what this page contributed>
   > - [[Page 2]] — <what this page contributed>
   ```

3. **No answer found**: Say clearly "Wiki 中没有相关内容", and ask:
   "要我帮你研究这个问题并把答案沉淀到 wiki 吗？"

### Phase 4: Evaluate filing value

After answering, check if the answer itself is worth filing as a new
wiki page. Apply these criteria (any one is sufficient):

- The answer **synthesized ≥2 pages** into a new comparison or insight
- The answer **defined a new concept** not yet in the wiki
- The answer is a **list/summary/index** the user explicitly asked for

If yes, say: "这个回答综合了多个页面的内容，值得作为新 wiki 页面归档。要我走 ingest 流程存下来吗？"

If the user says yes, **hand off to the ingest skill** — do not create
wiki pages directly from query-wiki.

**Do NOT suggest filing for:**
- Simple fact lookups ("what does X mean" answered by one page)
- Questions where the answer is just a quote from a single page
- Trivial queries with no lasting value

## Search strategies

**By tag**: If the query mentions a domain, map it to TAGS.md:
- "算法" / "data structure" → search for `#算法与数据结构`
- "Python" / "async" → search for `#编程语言`
- "game dev" / "Unity" → search for `#游戏开发`

**By keyword**: Use `obsidian search` for full-text search when
_index.md doesn't yield enough candidates.

**By session**: If the query is about "what did I discuss/decide about X",
search `1-Sessions/` for topic matches in filenames and frontmatter.

## Important constraints

- **Respect public/private boundary.** Public queries must not read
  netease/ files. If a public query accidentally touches work topics,
  stop and ask.
- **Cite with wikilinks.** Every claim from the wiki must have a
  `[[wikilink]]` so the user can verify.
- **Don't fabricate.** If the wiki doesn't have the answer, say so.
  Don't fill gaps with general knowledge unless the user explicitly
  asks for that.
- **Filing is ingest's job.** Query-wiki identifies filing opportunities
  but hands off to the ingest skill for actual wiki page creation.
- **Read TAGS.md** before searching by tag to ensure correct tag names.
- **Use Obsidian Flavored Markdown** for all output. Wikilinks (`[[...]]`),
  callouts (`> [!note]`), and embeds (`![[...]]`) are the vault's native
  syntax. Answers that will be filed as wiki pages must include proper
  YAML frontmatter. See `obsidian-markdown` skill for full syntax reference.
