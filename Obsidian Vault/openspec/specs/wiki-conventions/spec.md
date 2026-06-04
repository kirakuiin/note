# wiki-conventions Specification

## Purpose
TBD - created by archiving change restructure-vault-as-llm-wiki. Update Purpose after archive.
## Requirements
### Requirement: Wiki 页面 frontmatter 必填字段

Every markdown file under `2-Wiki/` (both public `2-Wiki/` and private `netease/2-Wiki/`) SHALL have a YAML frontmatter block at the top with at minimum the following fields:

- `tags`：数组，至少包含 1 个领域 tag（取自 `9-Meta/TAGS.md` 词表）
- `area`：固定字符串 `knowledge`
- `visibility`：`public` 或 `private`，必须与所在区域匹配

可选字段：`source`（来源 session 文件路径或外部书名/文档名）。

#### Scenario: 创建新 wiki 页面缺少必填字段
- **WHEN** agent 试图在 `2-Wiki/` 下创建新 markdown 文件，但 frontmatter 缺少必填字段
- **THEN** 必须在写入前补全所有必填字段；缺少 visibility 时根据所在路径自动判定（公开区 = public，netease/2-Wiki = private）

#### Scenario: visibility 与所在区域不匹配
- **WHEN** lint-wiki 工作流扫描发现某个公开区 wiki 页面的 frontmatter `visibility: private`，或 netease 区页面的 `visibility: public`
- **THEN** 必须在 lint 报告中标记为安全风险，立刻提示用户人工确认

---
### Requirement: 优先使用 wikilink 而非裸文本

Pages under `2-Wiki/` SHALL prefer wikilinks `[[页面名]]` over plain-text references when mentioning concepts that have their own wiki page. Ordinary wiki pages SHOULD include a small number of useful outgoing wikilinks when they improve understanding or discovery; graph completeness is not required.

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
- 每个页面一行：`[[页面名]] — 一句话摘要`
- `tags` 等 metadata 以页面 frontmatter 为准，不在 `_index.md` 双写
- 由 agent 在每次新建/删除页面后自动更新

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

`2-Wiki/_log.md` SHALL be an append-only sparse chronological record of
structural agent operations on the wiki. It is not a full activity stream.
Format:

- 每条记录形如 `## [YYYY-MM-DD] <operation> | <subject>`，例如 `## [2026-04-29] ingest-session | 知识库结构设计`
- 记录下方可包含 1-3 行简短描述（影响的页面列表、决策摘要）
- 一致前缀让 `grep "^## \[" _log.md | tail -N` 可解析

#### Scenario: Agent 完成结构性 wiki 修改
- **WHEN** agent 在 wiki 中完成 session ingest、capture 新建页面、批量重构、移动/改名/删除、跨页 lint-fix、公私边界处理、AGENTS / skill / OpenSpec 规则变更
- **THEN** SHALL 在 `_log.md` 末尾追加一行 `## [YYYY-MM-DD] <operation> | <subject>`，并列出受影响的页面

#### Scenario: Agent 完成低风险局部修改
- **WHEN** agent 只做错别字、措辞润色、格式清理、单页小段落补充、单个链接微调、只读 lint 报告
- **THEN** SHALL NOT append to `_log.md`

#### Scenario: Agent 检查最近的 wiki 活动
- **WHEN** agent 想了解最近 N 次 wiki 改动
- **THEN** SHALL 通过 grep `_log.md` 了解最近 N 次结构性改动；低风险局部修改不保证出现在 `_log.md`

---

### Requirement: `_MOC.md` 不再作为 wiki 结构

`_MOC.md` SHALL NOT be part of the maintained wiki structure. Agents SHALL NOT
create, update, read, or rely on domain `_MOC.md` files during normal
capture/ingest/query/lint workflows. `_index.md` is the required domain entry
and machine-maintained catalog.

If an old `_MOC.md` file is encountered during maintenance, it SHOULD be
removed after any remaining useful links have been represented in `_index.md`
or normal wiki pages.

#### Scenario: 新增领域子目录
- **WHEN** 在 `2-Wiki/` 下新增领域子目录
- **THEN** SHALL 创建该目录的 `_index.md`，且在全局 `_index.md` 中新增该领域分类；不得创建 `_MOC.md`

#### Scenario: 用户从顶层进入某领域
- **WHEN** 用户通过 Dashboard 或 `_index.md` 进入某领域
- **THEN** 入口 SHALL 是该领域的 `_index.md`

