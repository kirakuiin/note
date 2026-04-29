## ADDED Requirements

### Requirement: 顶级目录采用编号 + 性质分类

The vault SHALL use exactly the following top-level directories at the repository root, with numeric prefixes for ordering and lifecycle-based semantics: `0-Inbox/`, `1-Sessions/`, `2-Wiki/`, `3-Projects/`, `4-Journal/`, `5-Life/`, `6-Tools/`, `9-Meta/`. The numeric prefix uses a single digit followed by a hyphen (`0-`, not `00_`). Numbers `7-` and `8-` are reserved for future expansion.

In addition, the following directories are allowed at the root but are NOT part of the numbered structure: `Assets/` (Obsidian-managed attachments), `Excalidraw/` (Excalidraw plugin canvases), `netease/` (private workspace, see private-workspace requirement), and root-level dashboard files (`Dashboard.md`, `README.md`).

#### Scenario: Agent identifies a top-level directory by prefix
- **WHEN** an agent encounters a path starting with `2-Wiki/`
- **THEN** the agent SHALL treat it as the LLM-maintained knowledge wiki area regardless of subdirectory contents

#### Scenario: New top-level directory is proposed
- **WHEN** a contributor wants to add a new top-level directory not in the defined list
- **THEN** the change MUST go through OpenSpec (a new change proposal modifying this requirement) before implementation

#### Scenario: Numeric prefix collision
- **WHEN** two top-level directories would share the same numeric prefix
- **THEN** the structure MUST be rejected; each number is used by at most one directory

---

### Requirement: 每个顶级目录承担明确且互斥的语义

Each top-level directory SHALL have a single, well-defined purpose. Content placement MUST follow these semantics:

- `0-Inbox/`：未分类的临时投递（人工速记、待整理项）
- `1-Sessions/`：对话与外部文档的原始沉淀（"raw" 层），按 `YYYY/MM/` 子目录组织
- `2-Wiki/`：LLM 主导维护的结构化知识库（永久知识、按学科领域分类）
- `3-Projects/`：进行中的个人项目（有目标导向、状态会变化）
- `4-Journal/`：个人复盘（年度总结、项目复盘、面试准备）
- `5-Life/`：生活领域内容（兴趣、爱好，如桌游、金融、读物收藏）
- `6-Tools/`：工具速查（"用到才查、查完就走"的查询型笔记，扁平结构）
- `9-Meta/`：仓库自身的配置和 agent 资产（`AGENTS.md`、`Skills/`、`Templates/`、`Scripts/`、`openspec/`）

#### Scenario: 笔记归位决策
- **WHEN** 用户或 agent 创建新笔记需决定放在哪个顶级目录
- **THEN** 必须基于该笔记的"性质/生命周期"匹配上述定义之一，而非基于"主题"

#### Scenario: 一个笔记同时符合多个目录语义
- **WHEN** 一个笔记同时合理归属于多个目录（如某个项目相关的知识总结）
- **THEN** 优先按生命周期短的归位（项目结束会归档，但知识是永久的；故知识入 `2-Wiki/`，并在 `3-Projects/` 中通过 wikilink 引用它）

#### Scenario: `6-Tools/` 内容扁平化
- **WHEN** 在 `6-Tools/` 下放置工具速查文件
- **THEN** 文件 SHALL 直接位于 `6-Tools/` 根（不开子目录），命名采用 `<类别>-<工具名>.md` 形式（如 `编辑器-VSCode.md`、`版本控制-Git.md`）

---

### Requirement: 公私目录物理隔离

The vault SHALL maintain two physically isolated zones:

- **Public zone** (公开区)：所有非 `netease/` 的目录和文件，通过 `git push` 同步到公网仓库（GitHub/Gitee）
- **Private zone** (私有区)：`netease/` 目录及其全部子内容，必须在 `.gitignore` 中被排除，永不进入 git index

The `.gitignore` MUST contain a pattern that excludes the entire `netease/` directory (and any future top-level private directories explicitly designated).

`netease/` 内部应采用与公开区对称的结构：`0-Daily/`、`1-Sessions/`、`2-Wiki/`、`3-Projects/`、`4-Reference/`，其中 `4-Reference/` 用于存放第三方文档镜像（如 arcolab/popo 文档）。

#### Scenario: 公开区文件被 push 时
- **WHEN** 在 vault 根目录执行 `git status` 或 `git add .`
- **THEN** 整个 `netease/` 目录（含所有子文件）必须不出现在 git 跟踪范围内

#### Scenario: 公开区笔记不得引用私有内容
- **WHEN** 公开区的任何 markdown 文件试图通过 wikilink、embed、或 frontmatter `source` 字段引用 `netease/` 下的内容
- **THEN** 该引用 SHALL 被视为违规；agent 在写入前必须检查并拒绝此操作

#### Scenario: 私有区可以引用公开区
- **WHEN** `netease/` 下的笔记需要引用公开区的知识页面（例如工作 wiki 引用通用算法笔记）
- **THEN** 允许通过 wikilink 引用，但反向不允许

#### Scenario: 新增顶级私有目录
- **WHEN** 未来需要新增其他私有目录（非 netease）
- **THEN** 必须显式更新本 spec 与 `.gitignore`，并在 `9-Meta/AGENTS.md` 中标注

---

### Requirement: 子目录命名约定

Within `2-Wiki/`, second-level directories SHALL use Chinese names organized by subject domain (e.g., `编程语言/`, `游戏开发/`, `软件工程/`, `算法与数据结构/`, `AI与Agent/`, `计算机基础/`, `英语/`, `方法论/`).

Within `1-Sessions/`, the structure SHALL follow `YYYY/MM/` subdirectories with files named `YYYY-MM-DD-<topic>.md`.

Within `9-Meta/Skills/`, each skill SHALL be a self-contained directory with at minimum a `SKILL.md` entry file. Optional substructure: `references/`, `scripts/`, `templates/`, `assets/`, `tests/`.

#### Scenario: 创建新 wiki 主题分支
- **WHEN** 在 `2-Wiki/` 下创建新的领域目录
- **THEN** 命名 SHALL 用中文且能精确描述该领域；同时在该目录下创建 `_MOC.md` 入口文件

#### Scenario: 归档 session
- **WHEN** 在 `1-Sessions/` 下保存对话记录
- **THEN** 路径 SHALL 形如 `1-Sessions/2026/04/2026-04-29-知识库结构设计.md`

---

### Requirement: 根目录入口文件

The vault root SHALL contain three entry files, each serving a distinct audience:

- `Dashboard.md`：给用户自己看的行动型工作台（待办、当日入口、知识地图）
- `README.md`：给 GitHub 访客看的仓库简介（这是什么仓库、如何浏览、如何贡献）
- 旧的 `🧠 第二大脑.md` SHALL 被删除（其功能由 Dashboard.md 替代）

`9-Meta/AGENTS.md` 是 agent 的入口（不在根目录，但被 Dashboard 和 README 引用，详见 agent-schema 规范）。

#### Scenario: 用户在 Obsidian 中打开 vault
- **WHEN** 用户首次/每天打开 vault
- **THEN** Dashboard.md SHALL 是用户的首选入口，提供当日操作的快捷链接

#### Scenario: GitHub 访客访问仓库
- **WHEN** 公网用户在 GitHub 浏览此仓库
- **THEN** README.md SHALL 在仓库首页展示，用一段话说明仓库定位、推荐入口、私有区说明
