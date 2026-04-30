# Classification Decision Procedure

When invoked by `capture`, use this procedure to decide where a piece of
content belongs in the wiki.

## Input

- Raw content from the user (a sentence, a paragraph, a code snippet).
- The target region (public `2-Wiki/` or private `Netease/2-Wiki/`) —
  already determined by `capture`'s public/private routing step.

## Output

- A single target location:
  - **Append** to `<region>/<domain>/<page>.md` (optionally at a specific
    `#section`), OR
  - **New page** at `<region>/<domain>/[<subdir>/]<new-page-name>.md`.
- A list of existing pages the new content cross-references (for
  back-reference updates).

## Procedure

### 1. Read the region's top-level index

```
<region>/_index.md
```

Scan the "领域" (Domains) section for existing domain directories and
their one-line descriptions. Pick the best match by topic.

If no domain matches:
- Check if the content is cross-cutting (applies to multiple domains).
  If so, default to the domain whose concepts the content most relies on.
- If genuinely standalone, propose a new domain directory to the user.
  Never create a new top-level domain silently — it crosses into
  `9-Meta/AGENTS.md` §3 territory ("新建顶级目录必须先开 OpenSpec
  change").

### 2. Read the domain's index and MOC

```
<region>/<domain>/_index.md
<region>/<domain>/_MOC.md
```

List out candidate pages whose title or summary overlaps with the new
content. A page is a candidate if:

- The page title is a super-concept of the new content (e.g., new
  content is "Tick 单位是帧" and there is a page "时间与帧率").
- The page title is a sibling concept in the same sub-domain (e.g.,
  both are gotchas in the same module).
- The page title references the same module, class, or function.

### 3. Decide: append or new page

**Prefer append** when any of these hold:
- The content extends a section that already exists in a candidate page
  (e.g., a new log level for `log.*`, a new entry to a command cheatsheet).
- The content is a correction or refinement of a paragraph in an existing page.
- The content is shorter than ~10 lines and has no self-contained concept.

**Prefer new page** when any of these hold:
- The content defines a new concept, trap, or rule that would be searched
  for on its own (e.g., "状态机 _current_status 初值是 None").
- The content is a pitfall worth its own title — titles are the primary
  search keys.
- Appending would bloat the host page past ~300 lines or mix unrelated
  topics.
- The domain has a "踩坑集/" or "lessons/" sub-directory and the content
  fits that category — add a new page there.

### 4. Sub-directory selection (for new pages)

Inspect the domain's structure. Common sub-directory patterns:

| Sub-dir | Put there if content is |
|---|---|
| `踩坑集/` or `lessons/` | A gotcha, pitfall, or "don't do this" lesson |
| `UI开发/` (and similar feature areas) | Scoped to one feature area |
| `<module>/` | Scoped to a specific module or component |
| (no sub-dir) | A general concept or rule that spans the domain |

If none of the existing sub-directories fits AND the domain has >10 pages
at its root, propose a new sub-directory to the user — do not create it
silently.

### 5. Name the new page

- Use a **Chinese short name** that captures the concept (see
  `9-Meta/AGENTS.md` §7).
- Name must read well as a wikilink — prefer standalone nouns or
  name-of-thing patterns over full sentences.
  - ✅ `time_utils_Tick单位是帧`
  - ✅ `confirm_box回调语义反直觉`
  - ❌ `关于 time_utils Tick 函数的一个坑`
- If the name collides with an existing page, disambiguate with a
  domain suffix (see AGENTS §7).

### 6. Identify cross-references

From the candidate pages identified in step 2, select 1–2 that the new
page should wikilink to in its "## 相关" section. Criteria:

- Pick the page that is the closest super-concept or sibling concept.
- Pick the domain's `_index` or `_MOC` only if nothing more specific exists.
- Avoid linking to pages that merely share a tag — shared-tag is not a
  reason to cross-link.

These same pages will receive a back-reference in their "## 相关" section
during `capture`'s execute step.

## Examples

### Example 1 — Append

**Content**: "log.critical 会停服后上报"

- Region: private (mentions internal log levels).
- Domain match: `梦幻西游客户端/` → `Python编码规范.md` has a "日志输出"
  section listing existing log levels.
- Decision: **append to `梦幻西游客户端/Python编码规范.md#6-日志输出`**
  as a new row in the log level table.
- Back-references: none (the page already exists; no new wikilinks created).

### Example 2 — New page, sub-directory

**Content**: "发现 genInsFromUI 传 parent=None 会悄悄挂到 root"

- Region: private.
- Domain match: `梦幻西游客户端/`.
- Candidate pages: `UI开发/Handle与Single基类.md` (super-concept).
- Decision: **new page** at
  `梦幻西游客户端/踩坑集/genInsFromUI传空parent会挂到root.md`
  (it's a gotcha, "踩坑集/" sub-directory fits).
- Back-references:
  - New page's `## 相关` links to `[[../UI开发/Handle与Single基类]]`.
  - `Handle与Single基类.md`'s `## 相关` gains a link to
    `[[踩坑集/genInsFromUI传空parent会挂到root]]`.

### Example 3 — New domain

**Content**: "今天学了 Rust 的 ownership 模型，总结了几条关键点"

- Region: public.
- Domain match: none currently under `2-Wiki/` has Rust.
- Decision: **propose new domain** `2-Wiki/编程语言/` likely exists;
  place as `2-Wiki/编程语言/Rust_ownership.md` (sub-concept under
  existing domain). If `编程语言/` doesn't exist at all, surface to the
  user before creating a new top-level domain.
