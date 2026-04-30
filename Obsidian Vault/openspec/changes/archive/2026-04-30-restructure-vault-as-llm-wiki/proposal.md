---
visibility: public
area: meta
---

## Why

当前 vault 是按"内容来源"组织的传统 Obsidian 知识库（`读书笔记/`、`技术文档/`、`日常杂谈/` 等 11 个顶级目录），存在三个核心问题：(1) 几乎所有笔记的 frontmatter `tags` 字段为空，导致 agent 无法基于元数据检索；(2) `日常杂谈/` 沦为杂物筐，6 种性质迥异的内容混杂；(3) 完全没有给 agent 用的 schema/导航/工作流约定，agent 每次都要从零理解仓库。

我们希望参考 Karpathy 的 [LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) 模式，把 vault 升级为 **由 LLM 增量维护的、持续累积的知识库**，让对话和文档输入能被自动消化、交叉引用、归档，agent 既是"读者"也是"维护者"。同时必须严格保持 `netease/` 私有目录与公开区的物理隔离。

## What Changes

- **BREAKING** 重构顶级目录结构，从 11 个按"内容来源"分类的目录改为 7 个按"性质/生命周期"分类的目录（`0-Inbox/`、`1-Sessions/`、`2-Wiki/`、`3-Projects/`、`4-Journal/`、`5-Life/`、`6-Tools/`、`9-Meta/`）
- **BREAKING** 现有的 `读书笔记/`、`技术文档/` 按"来源（书 vs 自己整理）"的划分被废弃，统一按"领域（编程语言/游戏开发/算法/...）"重新组织到 `2-Wiki/` 下
- 新增 `1-Sessions/` 概念：把"对话/直接输入文档"作为知识来源持久化（你的 raw 层不是网页剪藏，而是对话归档）
- 新增 `2-Wiki/` 区域，由 LLM 主导维护：交叉引用、`_index.md` 全局索引、`_log.md` 操作日志、各领域 `_MOC.md` 入口
- 新增 `9-Meta/AGENTS.md`：作为 agent 的 schema 配置（仓库结构、命名约定、tag 词表、公私边界、工作流入口）
- 新增 4 个核心 skill：`ingest-session`（沉淀对话）、`ingest-document`（消化文档）、`query-wiki`（检索答题并反哺）、`lint-wiki`（健康检查）
- 拆分 `日常杂谈/`：年度/项目/面试 → `4-Journal/`；桌游/金融/收藏 → `5-Life/`；技术性内容（zerotier 等）回 `2-Wiki/`；方法论（GTD/金字塔写作）入 `2-Wiki/方法论/`
- 重命名 `工具用法/` → `6-Tools/` 并扁平化（用 `编辑器-VSCode.md` 类前缀替代子目录）
- 把 `技术文档/AI/skills/` 从"知识区"移到 `9-Meta/Skills/`（明确它是 agent 资产而非学习材料）
- `netease/` 内部对称采用同样的结构（`0-Daily/`、`1-Sessions/`、`2-Wiki/`、`3-Projects/`、`4-Reference/`），第三方文档镜像（arcolab/popo）独立到 `4-Reference/`
- 全量补齐 frontmatter（脚本生成 + 人工 review）：`tags`、`area`、`visibility: public/private`、`source`、`status`
- 取代 `🧠 第二大脑.md` 为 `Dashboard.md`：从"摆设型"统计页升级为"行动型"工作台（待办、当日日报快捷入口、知识地图）
- 新增 `README.md`：给 GitHub 访客的仓库说明
- OpenSpec 工作区固定在 `9-Meta/openspec/`（不在根目录），保持顶级目录干净

## Capabilities

### New Capabilities
- `vault-structure`: 顶级目录的语义、命名、公私边界，agent 在哪里读、在哪里写的硬性约定
- `wiki-conventions`: `2-Wiki/` 内部的页面规范（frontmatter、wikilink 密度、MOC、`_index.md`/`_log.md` 维护）
- `session-ingestion`: 把对话/直接输入文档转化为 `1-Sessions/` 持久化条目，并触发 wiki 更新的工作流
- `wiki-query`: 基于 `_index.md` + 页面正文的检索答题工作流，含"答案反哺为新 wiki 页面"
- `wiki-lint`: 周期性健康检查（孤儿/断链/重复/过时/缺 frontmatter），生成报告供用户确认
- `agent-schema`: `9-Meta/AGENTS.md` 的内容契约，告诉 agent 仓库是什么、约定有哪些、不能做什么
- `note-frontmatter`: 所有 markdown 笔记的 frontmatter 字段集合与取值规范

### Modified Capabilities
<!-- 这是 vault 的第一个 OpenSpec change，目前 specs/ 为空，没有 modified -->

## Impact

- **影响的目录**：vault 下除 `Assets/`、`Excalidraw/`、`netease/assets/`、`netease/res/` 外的几乎所有目录都涉及移动/重命名
- **影响的笔记数量**：~500 个 markdown 文件需要迁移路径或补 frontmatter
- **影响的链接**：Obsidian wikilink 大部分按文件名匹配可保留，但路径形 link、Dataview/Bases 中的 `contains(file.folder, ...)` 查询、Excalidraw 关联需逐一检查
- **影响的工具/插件**：Dataview 查询、`.base` 文件（桌游记录、弥勒山技能制作、工作报告总览）需要更新路径过滤
- **不影响**：`netease/` 公私隔离边界（强化而非破坏），`.gitignore` 仅需扩展 netease 子目录路径，不改变隔离语义
- **新增依赖**：无外部依赖；`9-Meta/Scripts/maintenance/` 可能用 Python（标准库即可，frontmatter 处理用 PyYAML 可选）
