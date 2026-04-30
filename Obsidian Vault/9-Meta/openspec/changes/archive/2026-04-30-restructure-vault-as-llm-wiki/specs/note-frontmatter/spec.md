---
visibility: public
area: meta
---

## ADDED Requirements

### Requirement: 全 vault frontmatter 字段集

All markdown files in the vault SHALL adopt a unified frontmatter schema. Fields are categorized as required (per file location) or optional.

**Universal optional fields** (任何文件都可有):
- `created` — ISO date, 文件创建时间
- `updated` — ISO date, 最近修改时间
- `aliases` — 数组，文件别名（Obsidian wikilink 解析时使用）

**Universal required fields**:
- `area` — 字符串，所在生命周期区，取值见下方
- `visibility` — `public` 或 `private`

**`area` 取值集合**：
- `inbox` — 在 `0-Inbox/`
- `session` — 在 `1-Sessions/` 或 `netease/1-Sessions/`
- `knowledge` — 在 `2-Wiki/` 或 `netease/2-Wiki/`
- `project` — 在 `3-Projects/` 或 `netease/3-Projects/`
- `journal` — 在 `4-Journal/` 或 `netease/0-Daily/`
- `life` — 在 `5-Life/`
- `tool` — 在 `6-Tools/`
- `meta` — 在 `9-Meta/`
- `reference` — 在 `netease/4-Reference/`（第三方文档镜像）

#### Scenario: 创建新笔记
- **WHEN** agent 在 vault 任意目录创建新 markdown 文件
- **THEN** SHALL 写入至少 `area` 和 `visibility` 字段；`area` 取值与所在路径一致

#### Scenario: 移动笔记到新区域
- **WHEN** 笔记从一个区域移动到另一个区域（如 `1-Sessions/` → `2-Wiki/`）
- **THEN** SHALL 同步更新 `area` 字段

---

### Requirement: 区域专属必填字段

不同 area 下的文件 SHALL 有额外的必填字段：

- **area: knowledge** (wiki 页面)：必须有 `tags`(≥1)、`status`(`draft`/`stable`/`stale`/`archived`)
- **area: session**：必须有 `tags`(≥1)、`date` (ISO date)、`topic` (短标题)；可选 `wiki_pages_touched` (数组)
- **area: project**：必须有 `status`(`active`/`paused`/`done`/`archived`)、`tags`(≥1)
- **area: journal**：必须有 `date` (ISO date)；可选 `period` (`daily`/`weekly`/`monthly`/`yearly`)
- **area: tool**：必须有 `category` (字符串，如 `编辑器`/`版本控制`/`AI` 等)
- **area: meta**：无强制额外字段（meta 文件内部结构差异大）
- **area: inbox**、**area: life**、**area: reference**：仅需 universal required，无额外必填

#### Scenario: knowledge 类页面缺 status
- **WHEN** wiki 页面的 frontmatter 缺少 `status` 字段
- **THEN** lint 标记为 Warning；agent 创建时默认 `status: draft`

#### Scenario: project 类页面 status 不在合法集
- **WHEN** project 文件的 `status` 字段值不属于 `active`/`paused`/`done`/`archived`
- **THEN** lint 标记为 Warning，建议改为合法值

---

### Requirement: Tag 词表统一管理

All `tags` values used in frontmatter SHALL come from the controlled vocabulary defined in `9-Meta/TAGS.md`. New tags MUST be added to TAGS.md before being used in any file.

`9-Meta/TAGS.md` SHALL organize tags by dimension:

- **领域 tag**：`#编程语言` `#游戏开发` `#算法` `#软件工程` `#AI` `#英语` `#方法论` `#金融` `#桌游` `#工作流` ...
- **类型 tag**：`#概念` `#手法` `#速查` `#项目` `#踩坑`
- **来源 tag**：`#from-session` `#from-doc` `#from-book` `#from-conference`

每个 tag 在 TAGS.md 中有 1-2 行说明。

#### Scenario: 使用不在词表的 tag
- **WHEN** agent 试图给笔记加一个不在 TAGS.md 中的 tag
- **THEN** SHALL 先建议把该 tag 加入 TAGS.md（征得用户同意），再写入笔记

#### Scenario: 词表条目废弃
- **WHEN** 某个 tag 决定废弃
- **THEN** 必须在 TAGS.md 标记为 `[deprecated]` 并指向替代 tag；同时跑一次 batch rename 清理所有现存使用

---

### Requirement: 安全字段 visibility 的硬约束

`visibility` field SHALL strictly match the file's physical location:

- 公开区路径下的所有文件 → `visibility: public`
- `netease/` 路径下的所有文件 → `visibility: private`

agent 在写入任何文件前必须根据路径自动设置 visibility，且永不允许 public 文件 embed/wikilink 到 private 文件。

#### Scenario: visibility 误标
- **WHEN** lint 发现一个文件的 visibility 与所在路径不匹配
- **THEN** 标记为 🔴 Critical；优先级高于其他所有 lint 检查项

#### Scenario: Agent 跨边界写入
- **WHEN** agent 试图把一个 `visibility: private` 的内容写入公开区路径
- **THEN** SHALL 拒绝写入并提示用户："该内容标记为 private，应写入 netease/ 而非公开区"
