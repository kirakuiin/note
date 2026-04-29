## ADDED Requirements

### Requirement: AGENTS.md 是 agent 的单一权威入口

The vault SHALL contain a file at `9-Meta/AGENTS.md` that serves as the single authoritative configuration for any AI agent operating on this vault. Any agent SHOULD read this file at the beginning of a session before performing operations.

#### Scenario: Agent 接入新 vault
- **WHEN** 一个 agent 第一次操作此 vault
- **THEN** SHALL 优先读 `9-Meta/AGENTS.md`，再决定具体操作

#### Scenario: 仓库约定变更
- **WHEN** 仓库的目录结构、命名约定、tag 词表等基础约定发生变更
- **THEN** 必须同步更新 `9-Meta/AGENTS.md`，且通过 OpenSpec change 记录

---

### Requirement: AGENTS.md 内容契约

`9-Meta/AGENTS.md` SHALL contain at minimum the following sections (use markdown headers for structure):

1. **What this vault is**：用 1-2 段说明仓库定位（个人知识库 + LLM Wiki 模式 + 工作私有区）
2. **Three-layer architecture**：sessions / wiki / meta 的关系
3. **Top-level directories**：每个顶级目录的语义、agent 是否可写、命名约定（参照 vault-structure spec）
4. **Public/private boundary (RED LINE)**：硬性安全规则
5. **Wiki page conventions**：frontmatter、wikilink、_index/_log/_MOC（参照 wiki-conventions spec）
6. **Tag vocabulary**：指向 `9-Meta/TAGS.md` 词表
7. **Naming conventions**：session 文件名、日报、MOC、index、log
8. **Workflow entry points**：列出主要 skill 及其用途
9. **Operation protocol**：agent 在做改动时必须遵循的流程（先 read index、列改动、确认、执行、updateindex/log）
10. **What NOT to do**：明确的禁止事项

#### Scenario: AGENTS.md 与实际 spec 不一致
- **WHEN** lint 发现 `9-Meta/AGENTS.md` 描述的约定与 `9-Meta/openspec/specs/` 中已 archive 的 spec 不一致
- **THEN** 必须在 lint 报告中标记为 Critical，要求同步

#### Scenario: 缺少必要小节
- **WHEN** AGENTS.md 缺少上述任一必要小节
- **THEN** 必须补全；这是验收 OpenSpec change 关闭的前置条件

---

### Requirement: AGENTS.md 必须包含明确的禁止事项

The "What NOT to do" section in AGENTS.md SHALL explicitly list:

- 不得让公开区任何文件 wikilink/embed/引用 `netease/` 内容
- 不得在公开区出现 netease 项目代号、内部系统名、同事真名等敏感词（参考 sensitive-words 列表）
- 不得在用户未确认前批量修改 ≥5 个文件
- 不得在 lint 阶段擅自写入修复
- 不得删除 agent 不理解用途的文件
- 不得跳过 `_index.md` / `_log.md` 的更新
- 不得在 wiki 区放原始对话（那是 sessions 的职责）

#### Scenario: Agent 试图执行禁止操作
- **WHEN** agent 内部决策即将触发上述任一禁止操作
- **THEN** SHALL 主动停下并询问用户，不得静默执行

---

### Requirement: README.md 与 AGENTS.md 分工

`README.md` (vault root) MUST 面向 **GitHub 访客和仓库主人本人**，而不是 agent。`README.md` SHALL 仅包含以下内容，且不得复述 `AGENTS.md` 的细节约定（避免双重维护）：

- 仓库简介（1-2 段）
- 仓库结构总览（顶级目录列表 + 一句话说明）
- 私有区说明（"netease/ 是工作私有目录，已通过 .gitignore 排除"）
- 推荐入口（Dashboard.md / `_index.md`）

任何只与 agent 行为有关的约定 MUST 写入 `AGENTS.md`，禁止写入 `README.md`。

#### Scenario: 受众错位
- **WHEN** 有内容既适合 README 又适合 AGENTS
- **THEN** 优先放 AGENTS.md（agent 受众更需要严格语义），README 只放面向访客的概述

---

### Requirement: 必须主动使用 Obsidian-aware skills 而不是手写文件

Agents operating on this vault MUST 优先使用 Obsidian 生态对应的专用 skill，而不是直接写文件 / 直接调通用文件 API。这条要求覆盖 vault 内一切 `.md` / `.canvas` / `.base` 的创建、修改、移动、删除，以及对 frontmatter / wikilink / 视图等 Obsidian 特性的操作。

强制路由表（agent 必须按下表选择工具）：

| 操作意图 | 必须使用 | 不允许 |
|---|---|---|
| 创建 / 读取 / 追加 / 移动 / 删除 vault 中的 `.md`、读 daily note、设置 property、扫断链 / 孤儿、查 backlinks | **`obsidian-cli` skill**（即官方 `obsidian` 命令） | 直接 `edit_file` 写新 .md、`mv` / `xcopy` / `git mv` 移动 .md、自己造 frontmatter 字符串 |
| 写 Obsidian Flavored Markdown（wikilink、embed、callout、frontmatter、tag、模板）正文 | **`obsidian-markdown` skill** | 凭记忆乱写 Obsidian 语法 |
| 创建 / 修改 `.base` 文件（views、filters、formulas） | **`obsidian-bases` skill** | 手写 base YAML / JSON |
| 创建 / 修改 `.canvas` 文件 | **`json-canvas` skill** | 手写 canvas JSON 节点坐标 |

操作触发顺序约定：

1. agent 接到一个意图（如"把这次对话归档为 session"、"创建一个新 wiki 页"、"移动这批文件"）
2. 先检查上表，识别该意图归属的 skill；若有，**先 `use_skill` 加载它，再执行**
3. skill 加载后按 skill 的指示选择具体子命令（如 `obsidian create` / `obsidian move` / `obsidian property:set` 等）
4. 仅当上表未覆盖（如读取 vault 外部的 .md、纯文本工具脚本等）才回落到通用文件工具

#### Scenario: 创建新 wiki 页面
- **WHEN** agent 要在 `2-Wiki/<主题>/` 下新建一个页面
- **THEN** SHALL 先 `use_skill obsidian-markdown`（确认 frontmatter / wikilink / callout 写法），再 `use_skill obsidian-cli`（用 `obsidian create path=... template=wiki-page` 落地），不得直接 `edit_file` 写入

#### Scenario: 沉淀一次对话为 session
- **WHEN** ingest-session 流程开始
- **THEN** SHALL 用 `obsidian create` + 现成的 `session.md` 模板生成文件，而不是手工拼接 markdown 字符串

#### Scenario: 移动 / 重命名 vault 内文件
- **WHEN** agent 需要调整一个或多个 .md / .canvas / .base 的路径或文件名
- **THEN** SHALL 走 `obsidian move` / `obsidian rename`（参见 design D11 零失链协议），不得使用 `mv` / `xcopy` / `git mv` / `edit_file` 重写

#### Scenario: 创建 / 编辑 .base 或 .canvas 文件
- **WHEN** agent 要新建一个 base 视图或 canvas
- **THEN** SHALL 先 `use_skill obsidian-bases` 或 `use_skill json-canvas`，按 skill 指引生成结构化内容；不得直接拼 YAML / JSON 字符串

#### Scenario: skill 不可用或 CLI 未就绪
- **WHEN** Obsidian app 未运行、`obsidian` 命令不在当前终端 PATH、或对应 skill 未注册
- **THEN** SHALL 主动停下并提示用户先解决前置（启动 Obsidian / 重启终端 / 注册 skill），不得擅自降级到 `edit_file` / `mv`

---

### Requirement: AGENTS.md 必须列出当前 vault 适用的 Obsidian skills 清单

`9-Meta/AGENTS.md` SHALL contain a "Skills the agent should use" section that explicitly enumerates the Obsidian-aware skills available in this environment, with one-line guidance for each. At minimum this section MUST cover:

- `obsidian-cli`：所有 vault 文件 CRUD / 搜索 / 链接检查 / property 操作的入口
- `obsidian-markdown`：写 Obsidian Flavored Markdown 正文的语法权威
- `obsidian-bases`：操作 `.base` 文件
- `json-canvas`：操作 `.canvas` 文件

并且 SHALL 在 "What NOT to do" 区追加一条：**禁止绕过上述 skill 直接用通用文件工具操作 vault 内 .md / .canvas / .base 文件**。

#### Scenario: 新 skill 加入或现有 skill 升级
- **WHEN** 用户为本环境新注册了一个 Obsidian 相关的 skill，或现有 skill 能力发生变化
- **THEN** AGENTS.md 的 skills 清单 SHALL 同步更新；这是验收 OpenSpec change 关闭的前置条件之一

#### Scenario: skill 缺失但仍要执行
- **WHEN** 上述某个必备 skill 在当前会话中未注册（agent 调用时报错）
- **THEN** SHALL 提示用户"先 enable / install 该 skill"，不得跳过 skill 直接手写
