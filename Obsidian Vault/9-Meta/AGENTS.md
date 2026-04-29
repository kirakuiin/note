---
note_type: agents-config
area: meta
visibility: public
status: stable
created: 2026-04-29
updated: 2026-04-29
aliases:
  - Agent Bootstrap
  - AI Agent 入口
---

# AGENTS.md — AI Agent 操作此 Vault 的权威约定

> **如果你是一个 AI agent**：本文件是你操作此 Obsidian vault 之前**唯一**必须读完的入口。
> 所有规则**自包含**于本文件——长期执行时不依赖任何 OpenSpec change 文件。
>
> **如果你是人类用户**：随手翻翻就行；GitHub 访客请看仓库根 `README.md`。

---

## 1. What this vault is

这是一个 **个人 Obsidian vault + LLM Wiki 模式实践** 的笔记仓库。

- **Vault 用途**：日常知识沉淀、对话归档、项目跟踪、生活记录
- **LLM Wiki 模式**：和传统 RAG 不同，agent **增量地构建并维护一个持久化、互链的 markdown wiki**——知识被一次编译、长期维护，不是每次查询都重新推导。详见 vault 根的 `[[LLM wiki]]`
- **公私分区**：`netease/` 是工作私有区，已通过仓库根 `.gitignore` 物理隔离，永不进入 git 跟踪范围

仓库 git 根是 `c:\Users\wangzhuowei\note\`，**vault 是其下 `Obsidian Vault/` 子目录**——所有 git 命令必须在仓库根执行。

---

## 2. Three-layer architecture

知识在 vault 内按"生命周期"分三层流动：

| 层 | 目录 | 性质 | 谁主导写 |
|---|---|---|---|
| **Raw** 原始层 | `1-Sessions/` | 对话、外部文档的原文沉淀（不可变） | agent ingest 时写 |
| **Wiki** 知识层 | `2-Wiki/` | 结构化、互链、长期维护的知识页面 | agent 主导，用户审核 |
| **Meta** 元层 | `9-Meta/` | 仓库自身配置（本文件、Skills、Templates、openspec） | 用户与 agent 共同维护 |

其余顶级目录（`0-Inbox` `3-Projects` `4-Journal` `5-Life` `6-Tools`）按其它生命周期维度组织，详见下一节。

**关键原则**：知识从 Raw 层提炼后**写入** Wiki 层，原始 session 文件本身保持不变。Wiki 页面通过 `wiki_pages_touched` frontmatter 字段反向追溯它的源 session。

---

## 3. Top-level directories

| 目录 | area | 语义 | agent 可写 | 命名约定 |
|---|---|---|---|---|
| `0-Inbox/` | inbox | 未分类临时投递（人工速记、待整理项） | 是 | 无强制 |
| `1-Sessions/` | session | 对话与外部文档原始沉淀（raw 层） | 是 | `YYYY/MM/YYYY-MM-DD-<topic>.md` |
| `2-Wiki/` | knowledge | LLM 主导维护的结构化知识库 | 是（核心职责） | 中文领域名子目录，每个含 `_index.md` + `_MOC.md` |
| `3-Projects/` | project | 进行中的个人项目 | 谨慎写 | 一项目一目录，含 `README.md` |
| `4-Journal/` | journal | 个人复盘（年度/项目/面试） | 仅按用户请求 | `YYYY/` 子目录 |
| `5-Life/` | life | 生活兴趣（桌游、金融、读物） | 仅按用户请求 | 自由 |
| `6-Tools/` | tool | 工具速查（"用到才查、查完就走"） | 是 | **扁平结构**，文件名 `<类别>-<工具名>.md`（如 `编辑器-VSCode.md`） |
| `9-Meta/` | meta | 仓库元层（本文件 / Skills / Templates / Scripts / openspec） | 用户主导 | — |

**还允许的根级目录**（不在编号体系内）：`Assets/` `Excalidraw/`（Obsidian 插件管理的附件）、`netease/`（私有区）、根级仪表盘 `Dashboard.md`。

**新建顶级目录**必须先开 OpenSpec change 修订本文件，禁止擅自添加。

### 笔记归位决策

- 决策依据：**笔记的"性质 / 生命周期"**，不是"主题"
- 一个笔记同时合理属于多个目录时（如某项目相关的知识总结）：优先按生命周期短的归位（项目结束会归档，但知识是永久的；故知识入 `2-Wiki/`，并在 `3-Projects/` 中通过 wikilink 引用它）

---

## 4. Public/private boundary (RED LINE)

**红线只有一条**：

> **公开区任何文件不得 wikilink、embed、或 frontmatter 字段引用 `netease/` 路径下的内容。反向（`netease/` 引用公开区）允许。**

### 物理保障

- `netease/` 在仓库根 `.gitignore` 中已被排除，不会进入 git 跟踪
- 任何"公开区文件"指：**不在 `netease/` 子树下**的文件
- 检查方式：写完文件后 `obsidian unresolved` 不应新增指向 `netease/` 的链接

### Agent 行为守则

| 场景 | 必须做 |
|---|---|
| 创建公开区 .md | frontmatter `visibility: public`；正文不出现 `netease/...` 路径或对应 wikilink |
| 创建 netease/ 内 .md | frontmatter `visibility: private`；可自由引用公开区 |
| 即将破坏红线 | **立刻停下并告诉用户**，不得静默继续 |
| 不确定文件该归公开区还是 netease | 停下并问用户，不得猜 |

> **不需要维护敏感词清单**——只看路径边界即可。如果一个引用解析不到 netease 之外的位置，该引用就是合法的。

---

## 5. Wiki page conventions

### 5.1 frontmatter 必填字段

所有 vault 内 .md 都必须有 frontmatter，按所在 area 区分：

| area | 强制字段 | 可选字段 |
|---|---|---|
| 全部 | `area`、`visibility` | `created`、`updated`、`aliases` |
| `knowledge` (`2-Wiki/`) | + `tags`(>=1)、`status` | `source`、`wiki_pages_touched` |
| `session` (`1-Sessions/`) | + `tags`(>=1)、`date`、`topic` | `wiki_pages_touched` |
| `project` (`3-Projects/`) | + `status`(`active`/`paused`/`done`/`archived`)、`tags`(>=1) | — |
| `journal` (`4-Journal/`) | + `date` | `period`(`daily`/`weekly`/`monthly`/`yearly`) |
| `tool` (`6-Tools/`) | + `category` | — |
| `inbox`/`life`/`meta` | 仅需 area+visibility | — |

**`visibility` 必须严格匹配路径**：公开区路径 → `public`；`netease/` 路径 → `private`。Agent 在写文件前根据路径自动设值，且永不允许 public 文件 embed/wikilink 到 private 文件。

**`status` 取值**（knowledge 类）：`draft` / `stable` / `stale` / `archived`。新建默认 `draft`。

### 5.2 wikilink 优先

- `2-Wiki/` 下页面在提到一个有独立 wiki 页面的概念时 SHALL 用 `[[页面名]]` 而非裸文本
- 每个非 MOC 页面 SHOULD 有至少 1 个出链
- 跨边界引用尝试（公开区 → netease）→ 拒绝写入并停下问用户

### 5.3 `_index.md` / `_MOC.md` / `_log.md`

每个 `2-Wiki/<领域>/` 目录下：

- **`_index.md`**：本领域页面目录，每行 `[[页面名]] — 一句话摘要 (tags: ..., status: ...)`。每次新增/删除页面要同步更新
- **`_MOC.md`**：本领域的"知识地图"，按主题分组 + 学习路径组织 wikilink。允许"高出度低入度"，lint 不算孤儿
- `2-Wiki/_index.md`：全局领域索引（指向各 `<领域>/_MOC.md`）
- `2-Wiki/_log.md`：append-only 操作日志，每条 `## [YYYY-MM-DD] <operation> | <subject>`，agent ingest 后追加一条

netease 区独立维护 `netease/2-Wiki/_index.md` / `_log.md`，与公开区完全不互通。

---

## 6. Tag vocabulary

所有 `tags` 必须取自 `[[9-Meta/TAGS|TAGS.md]]` 词表。Agent 行为：

- 打 tag 前先读 TAGS.md 白名单，命中即用
- 未命中：**停下询问用户**"是否新增 `#xxx` 到白名单"，不得擅自造 tag
- TAGS.md 标记 `[deprecated]` 的 tag：禁止再使用，按其指向的目标值替换

> **TAGS.md 尚未建立时**（OpenSpec change `restructure-vault-as-llm-wiki` 的 task 1.11 完成之前）：agent 应显示警告 `"TAGS.md 未建立，tag 治理处于无序状态"`，并优先沿用现有 tag、不引入新 tag。

---

## 7. Naming conventions

| 类别 | 规则 | 示例 |
|---|---|---|
| Session 文件名 | `1-Sessions/YYYY/MM/YYYY-MM-DD-<topic>.md`，topic 是 kebab-case 或中文短语 | `1-Sessions/2026/04/2026-04-29-知识库结构设计.md` |
| 同日多次 session | 添加序号后缀 | `...-知识库结构设计-2.md` |
| 日报 | `netease/0-Daily/YYYY/MM/YYYY-MM-DD_日报.md` | — |
| Wiki 领域子目录 | 中文学科名 | `编程语言/` `游戏开发/` `算法与数据结构/` `AI与Agent/` `英语/` `方法论/` |
| Wiki 页面 | 中文短名，能独立表达概念 | `单例模式.md` `状态机.md` |
| 同名页面冲突 | 加领域后缀消歧 | `单例模式（游戏编程模式）.md` |
| `6-Tools/` 文件 | 扁平结构，`<类别>-<工具名>.md` | `编辑器-VSCode.md` `版本控制-Git.md` |
| MOC | `_MOC.md` 固定文件名 | — |
| 索引 | `_index.md` 固定文件名 | — |
| 日志 | `_log.md` 固定文件名 | — |
| 项目 | 一项目一目录，含 `README.md` | `3-Projects/代号α/README.md` |

---

## 8. Workflow entry points (Skills the agent should use)

本环境注册的 skill 按用途分组如下。**Agent 在执行对应任务前必须 `use_skill` 加载相应 skill**。

### 8.1 Obsidian 集成（操作 vault 内文件的强制工具）

| Skill | 必须用于 |
|---|---|
| `obsidian-cli` | vault 内 `.md` 的 CRUD / 移动 / 改名 / property 操作 / 搜索 / backlinks / 断链扫描 / 孤儿检测 / daily note |
| `obsidian-markdown` | 写 Obsidian Flavored Markdown 正文（wikilink、embed、callout、frontmatter、tag、模板）的语法权威 |
| `obsidian-bases` | 创建 / 修改 `.base` 文件（views、filters、formulas） |
| `json-canvas` | 创建 / 修改 `.canvas` 文件 |

### 8.2 OpenSpec 工作流（仓库结构性变更）

| Skill | 必须用于 |
|---|---|
| `openspec-explore` | 想清楚某个变更前的探索讨论 |
| `openspec-propose` / `openspec-new-change` | 开新 change |
| `openspec-continue-change` / `openspec-apply-change` | 推进现有 change |
| `openspec-verify-change` / `openspec-archive-change` | 验收 + 归档 |
| `openspec-research` / `openspec-review` | change 工作期内的调研与代码审查 |

### 8.3 内容生产 / 工具

| Skill | 必须用于 |
|---|---|
| `defuddle` | 网页内容抽取（替代 WebFetch，省 token） |
| `work-summary` | 把对话总结为日报 / 周报 / 月报 / 年报 |
| `karpathy-guidelines` (coding-guideline) | 代码编写 / 审查时的反"过度设计"行为约束 |
| `mh-code-guide` | 梦幻西游客户端代码开发（仅 netease 工作侧使用） |
| `skill-creator` | 创建 / 修改 / 评测 skill 自身 |

### 8.4 强制路由表（覆盖一切 vault 内文件操作）

| 操作意图 | 必须用 | 禁止 |
|---|---|---|
| .md 的 CRUD / 移动 / 改名 / property 操作 / 链接巡检 | `obsidian-cli` | 直接 `edit_file` 写新 .md / `mv` / `git mv` / `xcopy` / Explorer 拖拽 |
| 写 Obsidian Flavored Markdown 正文 | `obsidian-markdown` | 凭记忆乱写 OFM 语法 |
| 创建 / 修改 `.base` 文件 | `obsidian-bases` | 手写 base YAML/JSON |
| 创建 / 修改 `.canvas` 文件 | `json-canvas` | 手写 canvas JSON |

**为什么强制？**

- vault 设了 `alwaysUpdateLinks: true`。**只有走 `obsidian` CLI 的 move/rename**才能触发 Obsidian 的链接自动更新机制；任何外部 `mv` 都会绕过它，造成静默失链
- `obsidian create` 走标准模板渲染、frontmatter 自动补、target 路径合法性校验，比手写更安全
- 路径同名解析、wikilink 短格式渲染都依赖 Obsidian 内部状态，外部工具无法等价替代

### 8.5 Skill 缺失时的行为

- 该 skill 在当前会话未注册（`use_skill` 报错）→ **停下并提示用户先 enable / install**，不得跳过 skill 直接手写
- `obsidian` 命令找不到（PATH 未刷新）→ **重开终端**或用全路径 `%LOCALAPPDATA%\Programs\Obsidian\Obsidian.com`，不得降级到 `edit` 写 .md

---

## 9. Operation protocol

任何对 vault 的修改都必须按下面的顺序执行：

### Step 1 — 验证环境（每次新会话开始）

```bash
obsidian version          # 必须返回 1.12.7+
obsidian unresolved       # 记一下基线断链数（修改后回比，确保不增）
```

如 `obsidian` 命令找不到，参考第 8.5 节。

### Step 2 — 读上下文

按需读以下文件（按需，不必全部）：

1. `9-Meta/AGENTS.md`（本文件，规则权威）
2. 仓库根 `README.md`（仓库定位）
3. 目标 `2-Wiki/<领域>/_MOC.md`（要操作哪个领域）
4. 目标 `2-Wiki/<领域>/_index.md`（看现有页面）
5. `9-Meta/TAGS.md`（要打 tag 时）
6. 当前活跃的 OpenSpec change（`9-Meta/openspec/changes/<name>/`，仅当处在 change 工作期内）

### Step 3 — 加载 skill

按第 8 节路由表选 skill，`use_skill` 加载。

### Step 4 — 列改动 → 用户确认 → 执行

| 改动规模 | 流程 |
|---|---|
| < 5 个文件、纯新增 | 直接执行 → 报告结果 |
| >= 5 个文件，或涉及移动/改名/删除 | **先列完整文件清单 + 每个文件改动摘要** → 等用户确认 → 执行 |
| 涉及红线（公开区引用 netease） | **立刻停下问用户**，不得自己决策 |

### Step 5 — 留痕

每次 ingest-session / 大批 wiki 修改后：

- 在 `2-Wiki/_log.md` 末尾追加一行 `## [YYYY-MM-DD] <operation> | <subject>`，下接受影响页面列表
- 在 session 文件 frontmatter 回填 `wiki_pages_touched` 数组
- 跑 `obsidian unresolved` 比对断链数变化，如果新增断链立刻报告

### Step 6 — Session 结构

每个 `1-Sessions/YYYY/MM/YYYY-MM-DD-<topic>.md` 至少含以下小节：

```markdown
## 背景 / 问题
本次对话/文档要解决什么

## 关键讨论
核心来回、决策过程（提炼即可，不必逐字）

## 结论
最终达成的共识或答案

## 产出物
本次产生的 wiki 页面、代码、文档的 wikilink/路径

## 后续（可选）
未尽事宜、待办
```

长度建议 200-1500 字。过短信息不足、过长应拆分多次 ingest。

---

## 10. What NOT to do（明令禁止）

- **不得** 让公开区任何文件 wikilink / embed / frontmatter 引用 `netease/` 路径下内容
- **不得** 绕过第 8 节路由表，用通用文件工具直接操作 vault 内 `.md` / `.canvas` / `.base`
- **不得** 在用户未确认前批量修改 ≥5 个文件
- **不得** 在 lint 阶段擅自写入修复（lint 只产报告，修复必须经用户确认）
- **不得** 删除 agent 自己也不理解用途的文件
- **不得** 跳过 `_index.md` / `_log.md` 的同步更新
- **不得** 在 `2-Wiki/` 区放原始对话（那是 `1-Sessions/` 的职责）
- **不得** 把 OpenSpec 工作区从 `9-Meta/openspec/` 移到根目录
- **不得** 在不验证 `obsidian version` 的情况下开始操作（会撞 PATH 陷阱或 Obsidian 未启动陷阱）
- **不得** 静默忽略红线违反或确认协议失败 —— 任何疑问都必须停下问用户

---

## 附：当前 vault 状态速查

| 项 | 值 |
|---|---|
| Vault 路径 | `c:\Users\wangzhuowei\note\Obsidian Vault\` |
| Git 仓库根 | `c:\Users\wangzhuowei\note\`（vault 是其子目录） |
| `.gitignore` 私有区排除 | `Obsidian Vault/netease/` ✓ |
| Obsidian CLI 版本要求 | >= 1.12.7 |
| `alwaysUpdateLinks` 设置 | `true` |
| 顶级目录骨架 | 已建（task 1.5/1.6/1.7） |

---

最后更新：2026-04-29（OpenSpec change `restructure-vault-as-llm-wiki` task 1.10 终稿）
