---
area: meta
visibility: public
---
# session-ingestion Specification

## Purpose
TBD - created by archiving change restructure-vault-as-llm-wiki. Update Purpose after archive.
## Requirements
### Requirement: Session 文件命名与位置

Each ingested long conversation, external document, multi-page decision trail, or explicitly requested session SHALL be persisted as a markdown file under `1-Sessions/YYYY/MM/YYYY-MM-DD-<topic>.md`. Single atomic lessons, gotchas, rules, and small append requests SHALL route to `capture` and do not create a session file by default. `<topic>` is a kebab-case 或中文短语，能够独立表达本次内容主题（如 `知识库结构设计`、`debug-skill-loader`）。

netease 工作侧的 session 同样存放于 `netease/1-Sessions/YYYY/MM/`，结构对称。

#### Scenario: 同一天有多次 persisted session
- **WHEN** 同一天发生多次 ingest
- **THEN** 每次产出独立文件，文件名通过不同的 `<topic>` 区分；如有重名则添加序号后缀 `-2`、`-3`

#### Scenario: 用户没指定 topic
- **WHEN** ingest-session 触发且需要创建 session，但用户未明确给出主题
- **THEN** agent SHALL 基于对话内容自动提炼一个 5-15 字的主题，并在写入前呈现给用户确认

---
### Requirement: Session 文件内容结构

Each session file SHALL contain at minimum:

1. **Frontmatter**: `tags`, `area: session`, `visibility`, `date` (ISO date), `topic` (短标题), 可选 `wiki_pages_touched` (数组，列出本次产出的 wiki 页面)
2. **正文按以下小节组织**：
   - `## 背景 / 问题`：本次对话/文档要解决什么
   - `## 关键讨论`：核心来回、决策过程（不必逐字记录，提炼即可）
   - `## 结论`：最终达成的共识或答案
   - `## 产出物`：本次产生的 wiki 页面、代码、文档的 wikilink/路径
   - `## 后续`（可选）：未尽事宜、待办

#### Scenario: 沉淀有价值的长对话
- **WHEN** 用户请求"把这次对话总结归档"，且内容包含长上下文、重要决策、外部文档或多页面变更线索
- **THEN** agent SHALL 创建符合上述结构的 session 文件，长度建议在 200-1500 字之间（过短信息不足、过长应拆分多次 ingest）

#### Scenario: 单条知识保存
- **WHEN** 用户只要求保存一个独立经验、坑点、规则或短 insight
- **THEN** agent SHALL route to `capture` and write/update the target wiki page directly, without creating a session unless the user explicitly asks

#### Scenario: 直接输入文档的 ingest
- **WHEN** 用户粘贴一份外部文档让 agent 消化
- **THEN** session 文件的"背景 / 问题"中 SHALL 标注"输入文档来源"（如 URL、书名、对方人名），原文可附在 session 文件末尾或单独存到 `1-Sessions/YYYY/MM/raw/` 子目录

---

### Requirement: Session 触发 Wiki 更新的工作流

After persisting a session file (if one is needed), the agent SHALL evaluate whether wiki pages should be created or updated, following this protocol:

1. **检测**：基于 session 内容，识别需要新建/更新的 wiki 页面
2. **呈现**：把改动列表（新建 X 页、更新 Y 页）呈现给用户
3. **确认**：等待用户确认（默认全部接受、或勾选）
4. **执行**：按 `capture` 的轻量写入规则修改 wiki 页面、`_index.md`，并仅在满足稀疏日志条件时更新 `_log.md`
5. **回填**：如果存在 session 文件，在 frontmatter `wiki_pages_touched` 字段填入所有受影响页面

#### Scenario: 一次 session 涉及多个 wiki 页面
- **WHEN** ingest-session 检测到本次对话涉及创建 ≥1 个新页面或更新 ≥3 个已有页面
- **THEN** SHALL 把所有改动汇总成一个清单（含每页的预览/diff），一次性给用户确认，避免多次打断

#### Scenario: 用户拒绝某些改动
- **WHEN** 用户在确认时勾选只接受部分改动
- **THEN** agent SHALL 仅执行被接受的部分，被拒绝的改动 SHALL 在 session 文件的"后续"小节记录为"待整理"

#### Scenario: Session 不需要触发 wiki 更新
- **WHEN** 一次 session 内容是问答型/调试型，没有产生需要持久化到 wiki 的新知识
- **THEN** session 文件本身完整保存即可，`wiki_pages_touched` 字段为空数组

---

### Requirement: Ingest 操作必须留痕

每次 ingest-session 创建 session、创建 wiki 页面、或更新多个 wiki 页面后 SHALL 在 `2-Wiki/_log.md`（或 netease 区的 log）末尾追加一条紧凑记录。小型单页 capture 不强制写 `_log.md`。ingest-session 格式如下（注意：示例中的 `H2` 表示 markdown 二级标题 `##`，此处避免被解析器误吞）：

```text
H2 [YYYY-MM-DD] ingest-session | <topic>
- session: [[1-Sessions/YYYY/MM/YYYY-MM-DD-<topic>]]
- touched: [[页面1]], [[页面2]], ...
```

#### Scenario: ingest 失败或中途取消
- **WHEN** ingest 流程在执行 wiki 修改前被取消
- **THEN** session 文件 SHALL 仍然保留（已沉淀的原始素材不丢），但 `_log.md` 不追加记录；`wiki_pages_touched` 字段为空

