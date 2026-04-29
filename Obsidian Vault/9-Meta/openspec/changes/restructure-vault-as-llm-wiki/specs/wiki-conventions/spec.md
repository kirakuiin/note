## ADDED Requirements

### Requirement: Wiki 页面 frontmatter 必填字段

Every markdown file under `2-Wiki/` (both public `2-Wiki/` and private `netease/2-Wiki/`) SHALL have a YAML frontmatter block at the top with at minimum the following fields:

- `tags`：数组，至少包含 1 个领域 tag（取自 `9-Meta/TAGS.md` 词表）
- `area`：固定字符串 `knowledge`
- `visibility`：`public` 或 `private`，必须与所在区域匹配
- `status`：`draft` / `stable` / `stale` / `archived` 之一

可选字段：`source`（来源 session 文件路径或外部书名/文档名）、`updated`（最近修改日期，ISO 格式）、`created`（创建日期）。

#### Scenario: 创建新 wiki 页面缺少必填字段
- **WHEN** agent 试图在 `2-Wiki/` 下创建新 markdown 文件，但 frontmatter 缺少必填字段
- **THEN** 必须在写入前补全所有必填字段；缺少 visibility 时根据所在路径自动判定（公开区 = public，netease/2-Wiki = private）

#### Scenario: visibility 与所在区域不匹配
- **WHEN** lint-wiki 工作流扫描发现某个公开区 wiki 页面的 frontmatter `visibility: private`，或 netease 区页面的 `visibility: public`
- **THEN** 必须在 lint 报告中标记为安全风险，立刻提示用户人工确认

---

### Requirement: 优先使用 wikilink 而非裸文本

Pages under `2-Wiki/` SHALL prefer wikilinks `[[页面名]]` over plain-text references when mentioning concepts that have their own wiki page. Each non-MOC page SHOULD have at least one outgoing wikilink (or an explicit reason in frontmatter for being a "leaf" page).

#### Scenario: 提到一个有独立页面的概念
- **WHEN** wiki 页面正文提到一个在 `2-Wiki/` 中已有独立页面的概念
- **THEN** SHALL 用 `[[页面名]]` 形式引用，而不是裸文本

#### Scenario: 概念被频繁提到但无独立页面
- **WHEN** lint 发现某概念在 ≥3 个 wiki 页面中以裸文本出现且无独立页面
- **THEN** 必须在 lint 报告中标记为"建议新增页面"，等待用户决定是否创建

#### Scenario: 跨边界引用尝试
- **WHEN** 公开区 wiki 页面试图 wikilink 到 `netease/` 路径
- **THEN** SHALL 拒绝写入，提示这违反公私边界

---

### Requirement: 全局索引文件 `_index.md`

`2-Wiki/_index.md` SHALL be maintained as a content-oriented catalog. Format:

- 按领域子目录分类组织
- 每个页面一行：`[[页面名]] — 一句话摘要 (tags: ..., status: ...)`
- 由 agent 在每次 ingest 后自动更新

netease 内部独立维护 `netease/2-Wiki/_index.md`，与公开区 index 不互通。

#### Scenario: 新增 wiki 页面
- **WHEN** agent 创建一个新的 wiki 页面
- **THEN** SHALL 在同区域 `_index.md` 中添加该页面的条目

#### Scenario: 删除或合并 wiki 页面
- **WHEN** agent 删除或合并 wiki 页面
- **THEN** SHALL 从 `_index.md` 移除对应条目；同时检查是否有其他页面 wikilink 指向被删页面，必要时修复或在 `_log.md` 标记待修

#### Scenario: 查询时 `_index.md` 是首要入口
- **WHEN** query-wiki 工作流接到查询请求
- **THEN** SHALL 先读 `_index.md` 找候选页面，再读具体页面正文

---

### Requirement: 操作日志 `_log.md`

`2-Wiki/_log.md` SHALL be an append-only chronological record of agent operations on the wiki. Format:

- 每条记录形如 `## [YYYY-MM-DD] <operation> | <subject>`，例如 `## [2026-04-29] ingest-session | 知识库结构设计`
- 记录下方可包含简短描述（影响的页面列表、决策摘要）
- 一致前缀让 `grep "^## \[" _log.md | tail -N` 可解析

#### Scenario: Agent 完成一次 wiki 修改
- **WHEN** agent 在 wiki 中完成 ingest / lint / restructure 等操作
- **THEN** SHALL 在 `_log.md` 末尾追加一行 `## [YYYY-MM-DD] <operation> | <subject>`，并列出受影响的页面

#### Scenario: Agent 检查最近的 wiki 活动
- **WHEN** agent 想了解最近 N 次 wiki 改动
- **THEN** SHALL 通过 grep `_log.md` 而不是扫描每个页面

---

### Requirement: 每个领域目录提供 `_MOC.md` 入口

每个 `2-Wiki/<领域>/` 子目录 SHALL 包含一个 `_MOC.md` 文件，作为该领域的导航地图。MOC 内容包含：

- 该领域涵盖的核心主题分组
- 关键页面的 wikilink（按重要程度或学习路径排序）
- 推荐的入门/深入阅读路径

`_MOC.md` 是少数允许"高出度（很多 outlink）但低入度（少 inlink）"的合法页面类型，lint 时不算孤儿。

#### Scenario: 新增领域子目录
- **WHEN** 在 `2-Wiki/` 下新增领域子目录
- **THEN** SHALL 同时创建该目录的 `_MOC.md`，且在 `_index.md` 中新增该领域分类

#### Scenario: 用户从顶层进入某领域
- **WHEN** 用户通过 Dashboard 或 `_index.md` 进入某领域
- **THEN** 入口 SHALL 是该领域的 `_MOC.md`，而不是某个具体页面
