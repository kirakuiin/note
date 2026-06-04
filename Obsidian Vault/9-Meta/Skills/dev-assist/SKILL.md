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

Surface relevant wiki knowledge **before coding work** so prior lessons,
conventions, and pitfalls inform the implementation.

## Trigger

Use for substantive coding, debugging, refactoring, review, feature work, or
technical spec writing. Skip pure knowledge questions, trivial doc edits, and
vault maintenance.

## Vault

Read `OBSIDIAN_VAULT` at invocation start. If unset, stop and ask the user to
configure it. Search only:

- `$OBSIDIAN_VAULT/Netease/2-Wiki`
- `$OBSIDIAN_VAULT/2-Wiki`

Never search, list, glob, or inspect the current project before the wiki probe.

## Workflow

### Phase 1: Probe

Call the bundled script; do not hand-write tokens or `rg` commands.

```bash
python "$OBSIDIAN_VAULT/9-Meta/Skills/dev-assist/scripts/dev_assist_probe.py" \
  --task "<current user task text>" \
  --cwd "<current cwd path string>" \
  --open-file "<open file path string, repeat as needed>"
```

The script does one vault-only ripgrep pass, caps tokens at 8, excludes
`_log.md` and `_index.md`, captures UTF-8 output, and normalizes paths to `/`.
Retrieval rules live in `references/probe-rules.json`.

Interpret JSON:

- `hits` → continue to Phase 2.
- `no_hits` / `no_tokens` / `no_roots` → output
  `> dev-assist: wiki 中无相关条目，已跳过` and stop.
- `no_vault_env` / `rg_not_found` / `rg_error` → report the skip briefly.

Do not add `_index.md` navigation rescue unless this skill is explicitly
updated to support it.

### Phase 2: Rank And Read

Group hits by subtree and read the deepest covering `_index.md` for context.
Rank candidates by:

| Signal | Weight |
|---|---:|
| Filename contains probe token | +3 |
| Content contains probe token | +1 |
| cwd domain maps to the wiki subtree | +2 |

Use `references/domain-mapping.md` for cwd → wiki subtree weighting. If no
mapping matches, continue without domain weight.

Noise guard: if one short English token (≤6 chars) accounts for more than half
of hits, downgrade that token and drop candidates that only match it unless too
few candidates remain.

Pick top 3. Read each full page, or first 50 lines if over 200 lines. On
Windows, read wiki files with UTF-8 (`Get-Content -Encoding UTF8`); if output is
mojibake, rerun with UTF-8 before judging relevance.

### Phase 3: Surface

Before doing the coding task, output:

```markdown
> [!info] dev-assist · 相关 wiki
> - **[[页面名 1]]** — <≤30 字相关性> · <关键一句>
> - **[[页面名 2]]** — <≤30 字相关性> · <关键一句>
> - **[[页面名 3]]** — <≤30 字相关性> · <关键一句>
```

Then proceed using the surfaced wiki context. Do not ask whether to read them.

## Write-Side Red Line

Reading `Netease/` is allowed. Writing Netease paths or wikilinks into public
region files is forbidden by `9-Meta/AGENTS.md`. If coding in a public region,
paraphrase private lessons instead of citing private paths.

## Self-Maintenance

If cwd has no domain mapping, after the result callout add:

```markdown
> [!tip] dev-assist · 建议
> 当前 cwd `<path>` 不在 domain-mapping 中。若此项目会长期使用，建议加一行映射以提升相关性排序。
```

If the user identifies a relevant wiki page that dev-assist missed, record a
compact lesson before `## 相关`:

```markdown
> [!note] L-<next> (YYYY-MM-DD · miss)
> Task: `<short wording>`; missed: [[page]]; cause: <token/noise/domain/keywords>; action: <rule/page/mapping update or none>.
```

If changing retrieval behavior, update `scripts/test_probe.py`, then
`references/probe-rules.json` or the generic extractor, and run the focused
probe tests.

## Constraints

- Vault-only Phase 1; never search the project.
- Probe is one script call and must terminate.
- Surface at most 3 pages.
- No caching.
- Do not chain into `capture` unless the user explicitly asks to save a lesson.

## References

- `scripts/dev_assist_probe.py` — deterministic Phase 1 probe.
- `references/probe-rules.json` — configurable synonyms, stopwords, noise, boosts.
- `references/trigger-keywords.md` — compact probe maintenance guide.
- `references/domain-mapping.md` — cwd → wiki subtree ranking weights.

## Lessons

> [!note] L-1 (2026-06-04 · miss)
> Task: `搜打撤模式下，战斗外法术施放要走 infosdc 里面的法术白名单`; missed: `战斗外师门法术使用链路`; cause: exact wording mismatch and Windows mojibake; action: add script-backed probe, contextual synonym expansion, UTF-8 read rule, page aliases.

> [!note] L-2 (2026-06-04 · review)
> First script version overfit by hardcoding business terms in Python; action: keep Python generic and move synonyms/stopwords/noise/boosts to `probe-rules.json`.

## 相关

- [[9-Meta/Skills/query-wiki/SKILL|query-wiki]]
- [[9-Meta/Skills/capture/SKILL|capture]]
- [[9-Meta/Skills/obsidian-cli/SKILL|obsidian-cli]]
- [[9-Meta/AGENTS]]
