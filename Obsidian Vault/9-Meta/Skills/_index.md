---
area: meta
visibility: public
status: stable
created: 2026-04-29
updated: 2026-04-30
---
# Skills

Agent 可调用的 skill 集合。每个 skill 是一个子目录，至少含 `SKILL.md`。

> 本文件由 OpenSpec change `restructure-vault-as-llm-wiki` task 1.6 创建。
> Batch C (task 3.4) 合并外部系统 skill（原 `技术文档/AI/skills/`）后扩写。
> 2026-04-30 新增 `capture` skill。

## Vault 自有 skill

本 vault 业务流程相关，仅供本 vault 的 agent 使用。

| Skill | 文件 | 用途 |
|---|---|---|
| `ingest` | [[9-Meta/Skills/ingest/SKILL.md]] | 沉淀对话/文档为 session 文件，可选提取知识到 wiki |
| `capture` | [[9-Meta/Skills/capture/SKILL.md]] | 显式触发下采集单条开发经验/踩坑/短 insight 到 wiki；优先追加，必要时新建 |
| `query-wiki` | [[9-Meta/Skills/query-wiki/SKILL.md]] | 搜索 wiki 回答问题，综合多页内容，识别归档价值 |
| `lint-wiki` | [[9-Meta/Skills/lint-wiki/SKILL.md]] | 12 项 wiki 健康检查，按 Critical/Warning/Suggestion 分级报告 |
| `dev-assist` | [[9-Meta/Skills/dev-assist/SKILL.md]] | 编码任务开始时主动 ripgrep 探测 wiki，命中即注入相关页面快照供 agent 参考 |

`capture` 与 `ingest` 的分界：`ingest` 处理**整段对话/长文档**并产出 session 文件；`capture` 处理**单条结论/经验**直接落到 wiki 页，通过 `OBSIDIAN_VAULT` 定位 vault，可跨 cwd 触发。

## 外部系统 skill

由 [CodeMaker](https://codemaker.app) 等 AI 助手通用调用。这些 skill 在本目录维护，并通过 junction/symbolic-link 暴露给 `%USERPROFILE%\.codemaker\skills\<name>`。**修改文件后无需重建 link**（link 是路径级，不是文件级）。

### 来自 [kepano/obsidian-skills](https://github.com/kepano/obsidian-skills)

| Skill | 文件 | 用途 |
|---|---|---|
| `defuddle` | [[9-Meta/Skills/defuddle/SKILL.md]] | 用 Defuddle CLI 从网页提取干净 markdown，去除导航/广告，节省 token |
| `json-canvas` | [[9-Meta/Skills/json-canvas/SKILL.md]] | 创建/编辑 JSON Canvas 文件（`.canvas`），支持节点/边/分组 |
| `obsidian-bases` | [[9-Meta/Skills/obsidian-bases/SKILL.md]] | 创建/编辑 Obsidian Bases 文件（`.base`），数据库式视图 |
| `obsidian-cli` | [[9-Meta/Skills/obsidian-cli/SKILL.md]] | 通过 Obsidian CLI 与 vault 交互（读/写/搜索/插件调试） |
| `obsidian-markdown` | [[9-Meta/Skills/obsidian-markdown/SKILL.md]] | Obsidian 风格 markdown（wikilinks/embeds/callouts/properties） |

### 自定义

跨 cwd 可用（通过 junction 暴露给 codemaker）。

| Skill              | 文件                                          | 用途                          |
| ------------------ | ------------------------------------------- | --------------------------- |
| `coding-guideline` | [[9-Meta/Skills/coding-guideline/SKILL.md]] | Karpathy 编码守则，减少 LLM 编码常见错误 |
| `work-summary`     | [[9-Meta/Skills/work-summary/SKILL.md]]     | 把 AI 交互内容总结为日报/周报/月报/年报     |

## 安装新 obsidian-skills

```bash
npx skills add git@github.com:kepano/obsidian-skills.git --yes
```

## 关联

- [[9-Meta/AGENTS.md]]
- [[openspec/specs/agent-schema/spec|agent-schema spec]]