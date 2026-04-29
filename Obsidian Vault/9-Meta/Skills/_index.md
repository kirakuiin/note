---
area: meta
visibility: public
status: stable
created: 2026-04-29
updated: 2026-04-29
---

# Skills

Agent 可调用的 skill 集合。每个 skill 是一个子目录，至少含 ``SKILL.md``。详见 agent-schema spec。

> 本文件由 OpenSpec change `restructure-vault-as-llm-wiki` task 1.6 创建。

## 当前条目

| Skill | 文件 | 用途 |
|---|---|---|
| `ingest` | [[9-Meta/Skills/ingest/SKILL.md]] | 沉淀对话/文档为 session 文件，可选提取知识到 wiki |
| `query-wiki` | [[9-Meta/Skills/query-wiki/SKILL.md]] | 搜索 wiki 回答问题，综合多页内容，识别归档价值 |
| `lint-wiki` | [[9-Meta/Skills/lint-wiki/SKILL.md]] | 12 项 wiki 健康检查，按 Critical/Warning/Suggestion 分级报告 |