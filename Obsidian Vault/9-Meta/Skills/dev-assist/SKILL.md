---
name: dev-assist
description: >
  Proactively retrieve relevant wiki knowledge while the user is coding,
  debugging, or refactoring — without waiting for an explicit query. Triggers
  on any coding/debugging/refactoring task in Cursor or Claude Code, even
  if the user does not ask "have I solved this before?". The skill runs a
  cheap ripgrep probe first; if nothing matches, it exits silently and does
  not pollute context. If the probe hits, it surfaces up to 3 wiki pages
  as inline references the agent can use to inform its work. Prefer this
  skill over `query-wiki` when the user is in the middle of writing code,
  not asking a knowledge question. Always use this skill when the user
  starts a coding task, even on small refactors — the probe cost is near
  zero and the upside is large.
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

## Workflow

The skill has two layers: a **fast probe** that decides whether to engage,
and a **deep search** that runs only when the probe hits.

### Phase 1: Probe (fast path, terminates ~90% of invocations)

1. **Extract probe tokens** from the current task description, the cwd,
   and any open files. See `references/trigger-keywords.md` for the
   extraction rules — the rules are intentionally regex-based so they
   adapt automatically as the wiki grows; you do not maintain a
   keyword list.

   **Cap at 8 tokens.** If extraction produces more, keep the top 8 by
   strength (rule 1 > rule 2 > rule 3) and earliness in the task
   description. Token count blowup makes ripgrep slow and dilutes
   relevance.

2. **Run ripgrep** against both wiki roots in one pass:

   ```bash
   rg -i -l --type md --no-ignore-vcs \
     -e "<token1>" -e "<token2>" ... \
     "Netease/2-Wiki" "2-Wiki"
   ```

   Notes:
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

3. **Pick top 3 candidates** by combined score
   (probe-token-match-count + domain-weight). Read each candidate's full
   content (or first 50 lines if >200 lines).

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

## Constraints

- **Probe must be cheap.** One ripgrep call, no Obsidian roundtrip in
  Phase 1. If the probe needs >1 second, redesign the token extraction.
- **Output must be terminating.** Do not enter a loop of "found nothing,
  let me try other keywords". Either the probe hits or it doesn't.
- **Max 3 candidates.** Surfacing 5+ pages saturates the agent's context
  and dilutes relevance. Ranking is for narrowing, not for thoroughness.
- **No caching.** Each task re-probes. ripgrep is fast enough; cache
  invalidation across wiki edits is a worse problem than re-running.
- **Do not chain into capture.** If during the coding task the user
  discovers a new lesson worth filing, they will explicitly invoke
  `capture`. dev-assist surfaces; capture files. They are independent.

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
> 约定。
>
> 实操方案待第一次添加 lesson 时确定（`obsidian eval` 精确插入 / 临时
> 脚本 / 手动编辑等都可），不预先杜撰未实测的 CLI 模板。

## 相关

- [[query-wiki]] — 用户主动问问题时用
- [[capture]] — 沉淀新经验回 wiki
- [[obsidian-cli]] — append domain-mapping 行的 CLI 用法
- [[9-Meta/AGENTS]] — 红线政策权威源
