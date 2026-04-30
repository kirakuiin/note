---
area: knowledge
visibility: public
status: stable
created: 2026-04-29
updated: 2026-04-30
tags:
  - meta
---
# Wiki 操作日志

> Append-only。每次 ingest session / 大批 wiki 修改后追加一条。

---

## [2026-04-30] migration | restructure-vault-as-llm-wiki Phase 4 收尾

**Change:** [[9-Meta/openspec/changes/archive/2026-04-30-restructure-vault-as-llm-wiki/proposal|restructure-vault-as-llm-wiki]]

**操作摘要：**
- 5.2 修复 4 处公开区断链（`5-Life/桌游/_index` 新建、`agent-schema/spec` 路径修正、`C Sharp 知识点`→`CSharp`、`Move Method`→`搬移函数`）
- 5.3 本日志文件创建
- 5.4 各顶级目录 `_index.md` 补全条目
- 5.5 Dashboard.md 知识地图入口更新

**受影响页面：**
- `5-Life/桌游/_index.md`（新建）
- `5-Life/_index.md`
- `9-Meta/Skills/_index.md`
- `2-Wiki/编程语言/Effective CSharp.md`
- `2-Wiki/编程语言/重构/封装集合.md`
- `2-Wiki/_log.md`（本文件）
- `Dashboard.md`

**验证：** unresolved 37 → 33（-4），零新增失链。

---

## [2026-04-29] migration | restructure-vault-as-llm-wiki Phase 0-3 完成

**Change:** [[9-Meta/openspec/changes/archive/2026-04-30-restructure-vault-as-llm-wiki/proposal|restructure-vault-as-llm-wiki]]

**操作摘要：**
- Phase 0: 骨架搭建（7 顶级目录 + 6 领域子目录 + AGENTS.md + TAGS.md + README.md）
- Phase 1: 核心 agent 资产（3 skills + 7 templates + 3 scripts + Dashboard.md）
- Phase 2: 内容迁移（Batch A-G，含资产目录收编，零失链）
- Phase 3: Frontmatter 规范化（area/visibility/tags/status 批量补齐）

**回滚锚点：** pre-phase-1 / post-batch-A / post-batch-B / post-batch-C-low / post-batch-C / post-batch-D / post-batch-E / post-batch-F / post-batch-G / post-asset-consolidation

**验证：** unresolved 36（与 baseline 持平），check_links 291（+2 孤儿，非真断链），git 全 R 无 D+A。

---

## [2026-04-30] migration | restructure-vault-as-llm-wiki Phase 6 + 验收完成（即将归档）

**Change:** [[9-Meta/openspec/changes/archive/2026-04-30-restructure-vault-as-llm-wiki/proposal|restructure-vault-as-llm-wiki]]

**操作摘要：**
- Phase 6 私有区对齐（task 6.1/6.2/6.3）：netease/ 下新建 4 个空骨架目录（`1-Sessions/` `2-Wiki/` `3-Projects/` `4-Reference/`，含 `_index.md`，历史 `daily/` `work/` 不动）；落地 `netease/AGENTS.md` 私有区专属 schema（10 节、10322 bytes UTF-8）；公开区 `9-Meta/AGENTS.md` §4 追加"私有区独立 AGENTS.md"子节 + 强制切换规则表
- Phase 7 验收（task 7.1/7.2/7.3/7.4/7.5）：`openspec validate --strict` 通过；lint 业务性 Critical = 0（保留 1 处已知例外：公开区 `9-Meta/AGENTS.md` → `[[netease/AGENTS]]` 是 spec 强制的合规跨指针）；用户人工巡检 Dashboard → MOC → wiki 页导航顺畅 ✓

**受影响文件：**
- `netease/1-Sessions/_index.md` `netease/2-Wiki/_index.md` `netease/3-Projects/_index.md` `netease/4-Reference/_index.md`（新建）
- `netease/AGENTS.md`（新建）
- `9-Meta/AGENTS.md`（追加 §"私有区独立 AGENTS.md"）
- `9-Meta/openspec/changes/archive/2026-04-30-restructure-vault-as-llm-wiki/tasks.md`（标记 6.1-7.5 完成）

**验证：** unresolved 33 → 33（零新增）；`openspec validate --strict` PASS。

**主 specs 同步策略**（task 7.5 决策）：

本 change 是 vault 历史上**第一个** OpenSpec change，`9-Meta/openspec/specs/` 当前为空。归档时按 OpenSpec 标准流程，本 change 的 7 个 capability spec（`agent-schema` / `note-frontmatter` / `session-ingestion` / `vault-structure` / `wiki-conventions` / `wiki-lint` / `wiki-query`）将**全量 SYNC** 到 `9-Meta/openspec/specs/`，作为这些 capability 的初始权威版本。后续修订需开新 change 通过 ADDED/MODIFIED/REMOVED 增量。

---

## [2026-04-30] verify-followup | 6-Tools frontmatter 规范化（W1 收尾）

**Change:** [[9-Meta/openspec/changes/archive/2026-04-30-restructure-vault-as-llm-wiki/proposal|restructure-vault-as-llm-wiki]] 验收报告 W1 修复

**操作摘要：**
- `/opsx:verify` 报出 WARNING W1：13 个 `6-Tools/*.md` frontmatter 全部为 `area: all`（非法值）+ 空 `tags:` + 缺 `category` 字段，违反 `note-frontmatter` spec 三条要求
- 按 vault-structure spec 命名约定 `<类别>-<工具名>.md` 反推 category，按 TAGS.md §2.5 + §3.5 规则使用 `工具/<工具名>` 嵌套 tag
- 13 文件 × 3 字段 = 39 次 `obsidian property:set`（area=tool, category=<类别>, tags=[工具/<工具>, 可选附加]）

**字段映射：**

| 文件 | category | tags |
|---|---|---|
| `AI-ClaudeCode.md` | `AI` | `工具/ClaudeCode`, `AI与Agent` |
| `AI-Cursor.md` | `AI` | `工具/Cursor`, `AI与Agent` |
| `Obsidian插件-Dataview.md` | `Obsidian插件` | `工具/Dataview` |
| `学习-Anki.md` | `学习` | `工具/Anki` |
| `排版-LaTeX.md` | `排版` | `工具/LaTeX` |
| `标记语言-Markdown.md` | `标记语言` | `工具/Markdown` |
| `测试-NUnit.md` | `测试` | `工具/NUnit`, `编程语言` |
| `版本控制-Git.md` | `版本控制` | `工具/Git` |
| `版本控制-SVN.md` | `版本控制` | `工具/SVN` |
| `笔记-Obsidian.md` | `笔记` | `工具/Obsidian` |
| `系统-Windows.md` | `系统` | `工具/Windows` |
| `编辑器-Emacs.md` | `编辑器` | `工具/Emacs` |
| `编辑器-VSCode.md` | `编辑器` | `工具/VSCode` |

**验证：**
- 全部 13 文件 UTF-8 strict 通过 ✅
- `obsidian unresolved` 33 → 33 零新增失链 ✅
- `scan_frontmatter.py` 在 `6-Tools/` 下 0 命中（之前 13 处 missing tags 全部消失）✅
- `check_visibility.py` 5 处 Critical 维持不变（仍是已知 `[[netease/AGENTS]]` 例外，无新增）✅
- 文件保留原有附加字段（如 `Obsidian插件-Dataview.md` 的 `source-link`、`测试-NUnit.md` 的 `unity_type`）

**关于本次属于哪个 change：** 严格说这是 verify 阶段发现的偏差，task 4.2「批量补 frontmatter」当时遗漏了 `6-Tools/`（脚本可能因这些文件已有 frontmatter 而走"只补缺失"分支跳过）。本次修复未新开 change，直接以 follow-up 形式记录到本 log，不影响 `restructure-vault-as-llm-wiki` 的 archive。


**下一步：** 执行 `openspec archive restructure-vault-as-llm-wiki`（用 `openspec-archive-change` skill），归档过程会自动完成 specs 同步并把 change 目录移入 `archive/`。

---

## [2026-04-30] archive | restructure-vault-as-llm-wiki 归档完成

**Change:** [[9-Meta/openspec/changes/archive/2026-04-30-restructure-vault-as-llm-wiki/proposal|restructure-vault-as-llm-wiki]] → archived

**操作摘要：**
- `openspec archive restructure-vault-as-llm-wiki -y` 一键归档（非 manual mv）
- Change 目录从 `9-Meta/openspec/changes/restructure-vault-as-llm-wiki/` → `9-Meta/openspec/changes/archive/2026-04-30-restructure-vault-as-llm-wiki/`
- 7 个 capability spec **全量 SYNC** 到 `9-Meta/openspec/specs/`（vault 历史第一次 sync，共 32 requirements 全部以 `+ added` 形式落地）：

| Capability | spec.md 大小 | 加 requirements |
|---|---|---|
| `agent-schema` | 9907 B | + 7 |
| `note-frontmatter` | 4574 B | + 4 |
| `session-ingestion` | 4298 B | + 4 |
| `vault-structure` | 7721 B | + 5 |
| `wiki-conventions` | 5036 B | + 5 |
| `wiki-lint` | 4576 B | + 4 |
| `wiki-query` | 3446 B | + 3 |

**验证：**
- `openspec list` → "No active changes found" ✅
- 7 capability `openspec validate <name> --strict` → 全部 PASS ✅
- 7 spec.md 文件 UTF-8 strict → 全 OK ✅
- `obsidian unresolved` 33 → 34（净 +1 失链）：
  - 修复了 `2-Wiki/_log.md` 中 4 个 `[[changes/restructure-vault-as-llm-wiki/proposal]]` → `[[changes/archive/2026-04-30-restructure-vault-as-llm-wiki/proposal]]`
  - 修复了 `9-Meta/Skills/_index.md` 中 2 个 `[[changes/.../specs/agent-schema/spec]]` → `[[specs/agent-schema/spec]]`（重定向到主 specs，因为归档后主 specs 才是权威源）
  - 残留 1 处 `9-Meta/Skills/query-wiki/.../answer.md` 中的 `note-frontmatter/spec` 失链——位于 skill eval 历史输出中，按惯例不回改 eval 历史快照，列为已知失链

**关于根目录 `openspec/` 重复**（验证报告 SUGGESTION S1）：
- 本次归档只动了 `9-Meta/openspec/`（CLI 从 `9-Meta/` 目录运行）
- 根级重复 `openspec/` 现仍含旧的 `restructure-vault-as-llm-wiki/`（未归档）和空 `specs/`，与 `9-Meta/openspec/` 状态完全分叉
- 待用户决定后续清理（删根级 / 留作历史 / 其他）

**主 specs 自此成为 vault 内 OpenSpec 体系的权威源**。后续修订必须新开 change 通过 ADDED/MODIFIED/REMOVED 增量。


---

## [2026-04-30] convention | `## 相关` 必须是文件最末节

**Change:** 新增 `9-Meta/AGENTS.md` §5.4 + `capture` skill §Link maintenance

**理由：** 反向链接维护依赖 `obsidian append`（只能加到文件尾）；若 `## 相关` 在末节，append 一行 wikilink 即等价于在 Related 列表加一条；否则必须 fallback 到脆弱的 `obsidian eval` 拼串。

**全库抽查结果：**
- 私有区 `Netease/2-Wiki/梦幻西游客户端/` 20/20 全部合规（顺手修了 `confirm_box回调语义反直觉.md` 的截断，见私有 _log）
- 公开区 `2-Wiki/` 317 页中 44 页不合规（14%，历史债）

**待办：** 公开区 44 页不在本次 scope 内修；留给未来的 wiki-lint skill 或 cleanup change 批量处理。合规检测脚本可参考：

```powershell
Get-ChildItem -Recurse '2-Wiki' -Filter *.md | Where-Object { $_.Name -notmatch '^_' } | ForEach-Object {
  $h2s = Get-Content $_.FullName -Encoding UTF8 | Where-Object { $_ -match '^## ' }
  $last = $h2s | Select-Object -Last 1
  if ($h2s.Count -gt 0 -and $last -notmatch '^## (相关|Related|See also)') { $_.FullName }
}
```

---

## [2026-04-30] skill-update | obsidian-cli skill 补 Windows path + 批处理 troubleshooting

**Change:** `~/.codemaker/skills/obsidian-cli/SKILL.md` 新增 §File targeting 子节 "Path separators (Windows)" 与 "Shell pitfalls: batch loops through CLI wrappers"。

**理由：** `capture` skill iteration-3 批量清理 24 页 `created/updated` 时踩坑——cmd 嵌 PowerShell 再调 CLI 导致反斜杠转义丢失，`property:remove` 静默失败。用独立 `.ps1` 脚本 + `.Replace('\\\\', '/')` 才正常工作。这条 lesson 应该沉淀给未来所有 CLI 批处理调用者。

**Scope：** skill 源文件（codemaker-user）更新，不涉及 vault 内文件。