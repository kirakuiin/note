---
area: knowledge
visibility: public
---
# Wiki 操作日志

> Append-only 稀疏结构性日志。只记录高信号 wiki / agent 规则变更；低风险局部修改、只读 lint、错别字和格式清理不进入本文件。

---

## [2026-04-29] migration | restructure-vault-as-llm-wiki

- 创建编号化 vault 骨架、AGENTS/TAGS/templates/scripts/Dashboard，并迁移公开区 wiki 内容。
- 归档到 [[openspec/changes/archive/2026-04-30-restructure-vault-as-llm-wiki/proposal|restructure-vault-as-llm-wiki]]，同步 7 个 capability spec 到 `openspec/specs/`。
- 后续补齐 `6-Tools/` frontmatter，并解决 OpenSpec 目录分叉：根级 `openspec/` 成为唯一权威源。

## [2026-04-30] convention | `## 相关` 必须是文件最末节

- 更新 AGENTS 与 capture 规则，使反向链接可通过文件尾 append 稳定落入 `## 相关`。
- 公开区历史页面仍有非合规债务，留给 lint / cleanup 处理。

## [2026-05-06] skill-update | dev-assist 与 CLI/Markdown 规则

- 新增 `dev-assist` skill 及 trigger/domain references，用于编码现场主动检索 wiki。
- 扩展 Obsidian CLI / Markdown 规则：Windows path、append/eval 转义坑、Mermaid 优先、纯文本替换例外。

## [2026-06-04] maintenance | retire MOC navigation

- 移除公开区领域 `_MOC.md` 文件与 `9-Meta/Templates/MOC.md`。
- 更新 Dashboard、`_index.md`、skills、AGENTS、OpenSpec，统一用 `_index.md` 作为 wiki 入口。

## [2026-06-04] maintenance | simplify frontmatter policy

- 取消 `status`、`created`、`updated` 的必填/推荐地位。
- 保留 `area`、`visibility`、`tags` 为核心元数据；tag 深度限制为 `#top` 或 `#top/sub`。
- 同步 AGENTS、TAGS、templates、skills、active OpenSpec specs。

## [2026-06-04] convention | sparse wiki logs

- `_log.md` 从全量活动流水收窄为稀疏结构性审计日志。
- 更新 AGENTS、capture / ingest / lint skills、active OpenSpec specs，并压缩公开区与私有区历史 `_log.md`。

## [2026-06-04] skill-update | capture / ingest / dev-assist 协同

- 明确 capture 与 ingest 按“是否需要 session/追溯”分流，不按字数硬切。
- 修正 ingest 公私边界为公开区不得引用私有区，私有区可按需引用公开区。
- 补充 dev-assist 只提示适合 capture，不自动写入。

## [2026-06-04] skill-update | dev-assist 检索反馈

- 简化 dev-assist frontmatter description，仅保留触发条件。
- 将短英文 token 噪声降权写入 Phase 2 排序规则。
- 新增 miss lesson 记录机制，用于持续调优 token、domain mapping 与页面关键词。
