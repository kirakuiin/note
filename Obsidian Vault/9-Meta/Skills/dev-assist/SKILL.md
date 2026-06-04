---
name: dev-assist
description: >
  Use when Codex is about to write, debug, refactor, review, or otherwise
  touch source code, including coding tasks based on specs, pasted errors,
  or requested implementation changes.
visibility: public
area: meta
---
# Dev-Assist Skill

Surface relevant wiki knowledge to the agent **at the start of any coding
task**, so accumulated lessons, conventions, and gotchas inform new code
automatically rather than only when the user thinks to ask.

This skill is the **proactive** counterpart to `query-wiki`:

| Skill | Trigger model | When to use |
|---|---|---|
| `query-wiki` | User asks a knowledge question | "What do I know about X?" |
| `dev-assist` (this) | User starts a coding task | Any coding/debug/refactor work |
| `capture` | User says "记一下 …" | Filing a new lesson back |

## When to trigger

**Auto-trigger on any coding-related task**, including:

- Writing new code (functions, classes, modules)
- Debugging an error or unexpected behavior
- Refactoring or renaming
- Reviewing code the user pasted
- Implementing a feature based on a spec

**Do NOT trigger on:**

- Pure knowledge questions ("what is a closure") — that's `query-wiki`
- **Trivial** doc edits (typo fix, version bump, single-line README change) —
  no wiki context needed, just edit
- Vault maintenance (Obsidian operations on `.md` files) — use the relevant
  Obsidian skills directly

**Do trigger on substantive doc writing.** Writing a new technical note,
synthesizing a multi-section spec, or drafting a wiki page IS knowledge
work and benefits from wiki context — even though the output is `.md`.
Edge case: dev-assist surfaces wiki for the writer; per the write-side
red line below, the resulting public-region note must not link Netease
paths even if private wiki content was used as reference.

The trigger is intentionally aggressive. The probe step is cheap (single
ripgrep). The cost of a false trigger is one ripgrep call; the cost of
missing a relevant lesson is a repeated mistake. We bias toward the cheap
side.

## Vault location

The wiki lives in an Obsidian vault whose path is given by the
`OBSIDIAN_VAULT` environment variable. Read it at the start of each invocation:

- Windows: `%OBSIDIAN_VAULT%`
- macOS/Linux: `$OBSIDIAN_VAULT`

If the variable is unset, stop and ask the user to configure it (e.g.,
`setx OBSIDIAN_VAULT "c:\\path\\to\\vault"` on Windows). Do not guess a path.

All vault-relative paths in this skill resolve against that root.

## Workflow

The skill has two layers: a **fast probe** that decides whether to engage,
and a **deep search** that runs only when the probe hits.

### Phase 1: Probe (fast path, terminates ~90% of invocations)

0. **Resolve vault root and construct absolute search paths.** Read
   `OBSIDIAN_VAULT` env var, then build absolute paths for the two
   wiki roots: `$OBSIDIAN_VAULT/Netease/2-Wiki` and
   `$OBSIDIAN_VAULT/2-Wiki`.

   **Hard rule — search target is the vault, never the project:**
   - ❌ Do NOT Glob, Grep, or ripgrep the current project directory
   - ❌ Do NOT explore cwd files to "understand the codebase first"
   - ❌ Do NOT run `ls`, `tree`, or any filesystem listing in cwd
   - ✅ The ONE AND ONLY search target is the Obsidian vault
   - ✅ Token extraction below reads from the task description string,
     the cwd path string, and the open-file path strings — it does
     NOT mean opening or reading those files

   If the vault roots don't exist on disk (e.g., `2-Wiki` is missing),
   search whichever exists. If neither exists, output
   `> dev-assist: vault wiki 根目录不存在，已跳过` and stop.

1. **Extract probe tokens** from the current task description, the cwd
   path string, and any open file path strings. See
   `references/trigger-keywords.md` for the extraction rules — the
   rules are intentionally regex-based so they adapt automatically as
   the wiki grows; you do not maintain a keyword list.

   **Cap at 8 tokens.** If extraction produces more, keep the top 8 by
   strength (rule 1 > rule 2 > rule 3) and earliness in the task
   description. Token count blowup makes ripgrep slow and dilutes
   relevance.

2. **Run ripgrep** against both wiki roots in one pass, using the
   absolute paths from step 0:

   ```bash
   rg -i -l --type md --no-ignore-vcs \
     --glob '!_log.md' --glob '!_index.md' \
     -e "<token1>" -e "<token2>" ... \
     "$OBSIDIAN_VAULT/Netease/2-Wiki" "$OBSIDIAN_VAULT/2-Wiki"
   ```

   Notes:
   - `--glob '!_log.md' --glob '!_index.md'` excludes
     meta files from probe results. These files aggregate keywords from
     their subtrees and produce false hits in almost every probe. They
     are NOT knowledge pages. `_index.md` is still read in Phase 2 for
     subtree navigation — excluding it here does not affect that step.
   - `--no-ignore-vcs` is required because `Netease/` is in `.gitignore`
     but is a valid search target (private wiki content can inform any
     coding task — see "Write-side red line" below)
   - `-l` returns only filenames; we count hits, we don't read content yet
   - Quote tokens that contain Chinese or special chars
   - **Windows binary path**: `rg` may not be on `PATH` after winget install;
     full path is typically `%LOCALAPPDATA%\Microsoft\WinGet\Packages\BurntSushi.ripgrep.MSVC_*\ripgrep-*\rg.exe`.
     If `rg` fails as a bare command, try the full path or restart the shell.
   - **Path output normalize**: ripgrep on Windows returns paths with mixed
     separators (e.g., `Netease/2-Wiki\梦幻西游客户端\xxx.md`). Before
     passing to `obsidian-cli` `path=` parameter, **convert all `\` to `/`**
     (obsidian-cli only accepts forward slashes — see `obsidian-cli` skill).

3. **Decide:**
   - **0 hits** → output one line: `> dev-assist: wiki 中无相关条目，已跳过` and stop
   - **1+ hits** → continue to Phase 2

### Phase 2: Deep search (slow path)

1. **Read the deepest `_index.md` for each hit subtree.** Group probe
   hits by their containing wiki subtree, then for each subtree read the
   **deepest** `_index.md` covering all hits in that subtree (de-duplicate;
   read each `_index.md` at most once).

   Example: probe hits `Netease/2-Wiki/梦幻西游客户端/UI开发/foo.md` and
   `Netease/2-Wiki/梦幻西游客户端/踩坑集/bar.md` →
   read `Netease/2-Wiki/梦幻西游客户端/_index.md` (covers both subtrees),
   not the two child `_index.md` files separately.

   Why deepest-covering: parent `_index.md` describes child page roles
   in their relative context (e.g., "踩坑集 — 高频坑：confirm_box…"),
   which is more useful than reading a top-level "私有区结构化知识库" index.

2. **Apply domain weighting.** Detect the user's current domain from cwd
   (see `references/domain-mapping.md` for explicit regex patterns +
   fallback inference). Pages **under the matching wiki subtree** get
   +2 to relevance score; others get +0. The matching wiki subtree
   granularity is whatever `domain-mapping.md` declares (typically a
   top-level domain like `梦幻西游客户端/`, not a sub-area like
   `UI开发/` — finer-grained narrowing comes from ripgrep hits on file
   names, not from the mapping). This is **only** used for ranking —
   we do not exclude any region from search.

3. **Pick top 3 candidates** by combined score. Scoring per candidate:

   | Signal | Weight | Rationale |
   |---|---|---|
   | **Filename contains token** | +3 per token | Page title matching a probe token is the strongest relevance signal (e.g., token `confirm_box` → file `confirm_box回调语义反直觉.md`) |
   | **Content contains token** | +1 per token | Body mention — weaker because common terms appear in many pages |
   | **Domain weight** | +2 | cwd matches domain-mapping entry (see step 2) |

   **Noise guard before final ranking**: if one short English token (≤6
   chars, e.g. `Single`, `Handle`, `Panel`) accounts for >50% of probe hits,
   treat it as noisy. For that token, count filename matches as +1 total and
   content matches as +0. Drop candidates that only match noisy tokens and have
   no domain weight unless fewer than 3 candidates remain.

   **Tie-breaking**: among equal scores, prefer pages under `踩坑集/`
   (pitfall pages are actionable), then shorter filenames (more focused).

   Read each top-3 candidate's full content (or first 50 lines if
   >200 lines).

4. **Synthesize a one-line relevance note** per candidate explaining why
   the page matters to the current task.

### Phase 3: Surface results

Output a single callout block, **before** doing any other work on the
user's task. Use **single-line per candidate** to avoid Obsidian rendering
ambiguity (multi-line list items inside callouts can collapse or split
unpredictably depending on theme):

```markdown
> [!info] dev-assist · 相关 wiki
> - **[[页面名 1]]** — <≤30 字相关性> · <从页面提取的关键 1 句>
> - **[[页面名 2]]** — <…> · <…>
> - **[[页面名 3]]** — <…> · <…>
```

Then proceed with the user's actual task, **using the wiki content as
context**. Do not ask "do you want me to read these?" — surfacing them
inline IS the value.

## Write-side red line

Reading any wiki region is allowed (`Netease/` included). **Writing** has
a hard rule from `9-Meta/AGENTS.md`:

> Public-region files must not wikilink, embed, or frontmatter-reference
> any path under `Netease/`.

Practical implication for dev-assist:

- ✅ **Read** Netease wiki to inform code in any cwd
- ✅ **Inject** Netease wiki content into the agent's context
- ❌ **Write** Netease paths or wikilinks into public-region files
  (code comments, public docs, public wiki pages)
- If the user's coding task is in a public-region directory and the
  most relevant wiki page is in `Netease/`, you may use the lesson but
  must **paraphrase** the content rather than citing the Netease path.
  When in doubt, ask the user.

## Self-maintenance: prompt the user when domain mapping is incomplete

If the probe runs in a cwd that doesn't match any entry in
`references/domain-mapping.md`:

- Functionality is **not affected** — full-library ripgrep still works
- After the result callout, append a one-line prompt:

  ```markdown
  > [!tip] dev-assist · 建议
  > 当前 cwd `<path>` 不在 domain-mapping 中。若此项目会长期使用，
  > 建议加一行映射以提升相关性排序（可让我帮你 append）。
  ```

- If the user agrees, append a row to `domain-mapping.md`. Note that
  naive `obsidian append` will land **after** the table (the table is
  followed by other sections); see `references/domain-mapping.md`'s own
  "append 一行的标准操作" section for the up-to-date method —
  responsibility for the actual mechanism lives in that file, not here.

## Self-maintenance: record retrieval misses

If, during or after a coding task, the user points out a relevant wiki page
that dev-assist did not surface, or the agent later finds one manually, record
a compact miss lesson in `## Lessons` before `## 相关`:

```markdown
> [!note] L-<next> (YYYY-MM-DD · miss)
> Task: `<short user wording>`; missed: [[page]]; cause: <token/noise/domain/capture-keywords>; action: <rule/page/mapping update or none>.
```

Use `obsidian eval` to insert the lesson before `## 相关`; do not use
`obsidian append`. If the fix is obvious but changes another skill/reference
or wiki page, ask before applying it. Misses usually map to one of four fixes:
add/adjust token extraction, add domain mapping, improve page title/first
paragraph keywords via `capture`, or tune noise scoring.

## Constraints

- **Search target is the vault, never the local project.** Do not Glob,
  Grep, `ls`, or ripgrep the current working directory. The probe's one
  ripgrep call targets `$OBSIDIAN_VAULT` only. Exploring the project
  directory before or alongside the vault search defeats the purpose of
  a cheap probe and pollutes context with irrelevant local results.
- **Probe must be cheap.** One ripgrep call, no Obsidian roundtrip in
  Phase 1. If the probe needs >1 second, redesign the token extraction.
- **Output must be terminating.** Do not enter a loop of "found nothing,
  let me try other keywords". Either the probe hits or it doesn't.
- **Max 3 candidates.** Surfacing 5+ pages saturates the agent's context
  and dilutes relevance. Ranking is for narrowing, not for thoroughness.
- **No caching.** Each task re-probes. ripgrep is fast enough; cache
  invalidation across wiki edits is a worse problem than re-running.
- **Do not chain into capture automatically.** dev-assist surfaces prior
  knowledge; capture files new knowledge. If a coding task reveals a durable
  new lesson, finish the task and mention one concise "适合 capture" suggestion.
  Run `capture` only after the user explicitly asks to save it.

## Example

**User:** "我要给这个 panel 加个状态机切换"
*(cwd = `D:/workspace/trunk/mhimage/scripts/ui/some_panel/`)*

**Probe:**
- Tokens extracted from prompt + cwd: `panel`、`状态机`、`mhimage`
  - 注：`panel` 是短英文边缘案例（单独可能噪声），但在描述中与`状态机`
    共现 → 按 `trigger-keywords.md` L-1 规则保留
- ripgrep hits（按 token 命中数排序）：`UIStateGroupComponent状态机.md`,
  `状态机_current_status初值是None.md`, `状态机默认态是空串不是default.md`,
  `Handle与Single基类.md`

**Domain weight:** cwd `D:/workspace/trunk/mhimage/scripts/ui/some_panel/`
matches mapping pattern `D:/workspace/.*/mhimage/`
→ pages under `Netease/2-Wiki/梦幻西游客户端/` get +2

**Surfaced output:**

```markdown
> [!info] dev-assist · 相关 wiki
> - **[[UIStateGroupComponent状态机]]** — 状态机控件用法权威页 · 通过状态名 → 子节点显隐切换
> - **[[状态机_current_status初值是None]]** — 初始化坑 · 未 set_status 前不要直接读 _current_status
> - **[[状态机默认态是空串不是default]]** — 默认态命名约定 · 配置里默认态是 ""（空串）而非 "default"
```

然后才开始为用户实现需求。

## Reference files

- `references/trigger-keywords.md` — Token extraction rules for Phase 1
  probe. Self-adapting; no manual updates needed when wiki grows.
- `references/domain-mapping.md` — cwd path patterns → wiki subdirectory
  mappings for Phase 2 ranking. Append-only; updated only when the user
  starts working in a new project.

## Lessons (append-only)

(Empty — populated as the skill is used in real coding tasks; each
real-world hit/miss is a candidate lesson.)

> [!important] 维护守则
> 本节插入新 lesson 时**不要用 `obsidian append`** —— append 落到文件
> 末尾，会跑到 `## 相关` 之后，破坏 AGENTS.md §5.4 "`## 相关` 必须末节"
> 约定。使用 `obsidian eval` 读取全文，把新 lesson 插入到 `\n## 相关`
> 标记之前；若标记不存在，先停下报告，不要猜插入位置。

## 相关

- [[9-Meta/Skills/query-wiki/SKILL|query-wiki]] — 用户主动问问题时用
- [[9-Meta/Skills/capture/SKILL|capture]] — 沉淀新经验回 wiki
- [[9-Meta/Skills/obsidian-cli/SKILL|obsidian-cli]] — append domain-mapping 行的 CLI 用法
- [[9-Meta/AGENTS]] — 红线政策权威源
