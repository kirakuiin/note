---
area: meta
visibility: public
status: stable
created: 2026-04-29
updated: 2026-04-29
aliases:
  - Tag 词表
  - Tag Vocabulary
---

# TAGS.md — Tag 词表

> 本文件是 vault 内 tag 治理的**单一权威源**。所有 `tags` 字段的取值必须来自本文件的白名单。
> Agent 在打 tag 前 SHALL 先查本文件；未命中白名单的 tag SHALL 停下询问用户。

---

## 1. 命名规则

| 规则 | 说明 |
|---|---|
| **风格** | 统一使用 **kebab-case**（小写字母 + 连字符），如 `game-dev`、`data-structure` |
| **中文 tag** | 领域 tag 使用中文（与 `2-Wiki/` 子目录名一致），如 `编程语言`、`游戏开发` |
| **嵌套 tag** | 使用 `/` 分隔层级，如 `编程语言/Python`、`算法与数据结构/图`。**顶层必须来自白名单**，嵌套路径自由组合 |
| **大小写** | 全部小写（中文无此概念）。禁止 camelCase、PascalCase、snake_case |
| **禁止** | 禁止在 tag 中使用空格、emoji、标点符号（`/` 除外） |

---

## 2. 核心白名单

### 2.1 领域 tag（对应 `2-Wiki/` 子目录）

| Tag | 说明 | 对应目录 |
|---|---|---|
| `#编程语言` | 编程语言特性、范式、编译原理 | `2-Wiki/编程语言/` |
| `#游戏开发` | 游戏引擎、渲染、物理、架构 | `2-Wiki/游戏开发/` |
| `#算法与数据结构` | 算法、数据结构、复杂度分析 | `2-Wiki/算法与数据结构/` |
| `#AI与Agent` | LLM、Agent 架构、RAG、Prompt Engineering | `2-Wiki/AI与Agent/` |
| `#英语` | 英语语法、词汇、表达 | `2-Wiki/英语/` |
| `#方法论` | 学习法、工作流、GTD、知识管理 | `2-Wiki/方法论/` |

### 2.2 笔记类型 tag

| Tag | 说明 |
|---|---|
| `#概念` | 对某个概念/术语的定义和解释 |
| `#手法` | 可操作的技术/技巧/模式（how-to） |
| `#速查` | 快速参考（API 签名、命令、配置模板） |
| `#踩坑` | 踩坑记录、bug 复盘、经验教训 |
| `#项目` | 项目级笔记（计划、进度、复盘） |
| `#interview` | 面试经验复盘（含问题、答案、HR 流程、薪资谈判等） |

### 2.3 状态 tag（与 frontmatter `status` 字段对应）

| Tag | 说明 |
|---|---|
| `#draft` | 草稿，内容不完整 |
| `#stable` | 稳定，可被引用 |
| `#stale` | 过时，需要更新 |
| `#archived` | 已归档，仅保留供参考 |

### 2.4 来源 tag

| Tag | 说明 |
|---|---|
| `#from-session` | 提炼自某次对话 session |
| `#from-doc` | 提炼自外部文档/网页 |
| `#from-book` | 提炼自书籍阅读 |
| `#from-conference` | 提炼自会议/分享 |

### 2.5 工具 tag

| Tag | 说明 |
|---|---|
| `#工具` | 工具用法、配置、踩坑（对应 `6-Tools/`） |

---

## 3. 红线清单

> 以下 tag **仅可在 `netease/` 私有区出现**。公开区（`netease/` 子树外的任何文件）出现以下任一 tag = lint **Critical**。

### 3.1 项目/产品代号

| Tag | 说明 |
|---|---|
| `#arcolab` | Arcolab 内部平台 |
| `#popo` | POPO 内部系统 |
| `#popo-card` | POPO 卡片 |
| `#POPO卡片` | POPO 卡片（中文变体，待统一清理） |
| `#sdc` | 搜打撤项目 |
| `#搜打撤` | 搜打撤项目（中文） |
| `#mhxy` | 梦幻西游 |

### 3.2 内部系统/模块

| Tag | 说明 |
|---|---|
| `#战斗系统` | 战斗系统（内部） |
| `#战斗` | 战斗（内部，简写） |
| `#frame-tool` | 框架工具（内部） |
| `#frametool` | 框架工具（内部，旧拼写） |
| `#buff系统` | Buff 系统（内部） |
| `#大地图` | 大地图模块（内部） |
| `#美术路由` | 美术资源路由（内部） |
| `#导表工具` | 导表工具（内部） |
| `#SVN自动化` | SVN 自动化（内部） |

### 3.3 内部流程/工作

| Tag | 说明 |
|---|---|
| `#日报` | 工作日报 |
| `#周报` | 工作周报 |
| `#月报` | 工作月报 |
| `#工作总结` | 工作总结 |
| `#技术调研` | 技术调研 |
| `#需求核对` | 需求核对 |
| `#文档同步` | 文档同步 |
| `#自动化测试` | 自动化测试 |
| `#端到端测试` | 端到端测试 |
| `#定时任务` | 定时任务 |

### 3.4 内部技术栈

| Tag | 说明 |
|---|---|
| `#FastAPI` | FastAPI（内部服务） |
| `#Pydantic` | Pydantic（内部服务） |

### 3.5 嵌套红线（前缀匹配即命中）

以下前缀开头的所有 tag 均为红线（**仅限 netease 内部路径**，公开区同名顶层 + 不同嵌套路径合法）：

- `#Arcolab/*`（如 `#Arcolab/POPO卡片`、`#Arcolab/API集成`、`#Arcolab/EventHub`）
- `#sdc/*`（如 `#sdc/大地图`、`#sdc/出生点选择`、`#sdc/大地图性能`、`#sdc/状态HUD`、`#sdc/JSON预览`）
- `#frame-tool/*`（如 `#frame-tool/UI优化`、`#frame-tool/新功能`、`#frame-tool/文档`）
- `#战斗/*`（如 `#战斗/技能特效`、`#战斗/技能消耗`、`#战斗/神变卡`）
- `#战斗系统/*`（如 `#战斗系统/技能播放`）
- `#模块/*`（如 `#模块/bigmap`）
- `#文档/*`（如 `#文档/月报`）

以下嵌套路径为红线（**仅限 netease 内部项目**，公开区 `#项目/代号α` 等合法）：

- `#项目/搜打撤` `#项目/梦幻西游` `#项目/arcolab-review-service`

以下嵌套路径为红线（**仅限 netease 内部工具**，公开区 `#工具/Git`、`#工具/VSCode` 等合法）：

- `#工具/打包` `#工具/web2md`

---

## 4. 历史脏 tag 清理表

> 以下 tag 已废弃，禁止再使用。Agent 遇到时应替换为目标值。

| 脏 tag | 频次 | 目标 tag | 说明 |
|---|---|---|---|
| `#reference` | 200 | 按文件所在领域替换为对应领域 tag | 语义太泛，无法索引 |
| `#language` | 111 | `#英语` | 全部为英语语法笔记 |
| `#dataStructure` | 11 | `#算法与数据结构` | 命名风格不统一（camelCase） |
| `#algorithm` | 10 | `#算法与数据结构` | 与 dataStructure 合并 |
| `#dataStructure/graph` | 3 | `#算法与数据结构/图` | 修正顶层命名风格 |
| `#dataStructure/tree` | 2 | `#算法与数据结构/树` | 同上 |
| `#algorithm/search` | 1 | `#算法与数据结构/搜索` | 同上 |
| `#algorithm/dp` | 1 | `#算法与数据结构/动态规划` | 同上 |
| `#algorithm/interval` | 1 | `#算法与数据结构/区间` | 同上 |
| `#algorithm/two-pointer` | 1 | `#算法与数据结构/双指针` | 同上 |
| `#algorithm/backtrace` | 1 | `#算法与数据结构/回溯` | 同上 |
| `#algorithm/sort` | 1 | `#算法与数据结构/排序` | 同上 |
| `#algorithm/sliding-window` | 1 | `#算法与数据结构/滑动窗口` | 同上 |
| `#algorithm/greedy` | 1 | `#算法与数据结构/贪心` | 同上 |
| `#dataStructure/hash` | 1 | `#算法与数据结构/哈希表` | 同上 |
| `#dataStructure/heap` | 1 | `#算法与数据结构/堆` | 同上 |
| `#dataStructure/union-set` | 1 | `#算法与数据结构/并查集` | 同上 |
| `#dataStructure/array` | 1 | `#算法与数据结构/数组` | 同上 |
| `#dataStructure/stack` | 1 | `#算法与数据结构/栈` | 同上 |
| `#dataStructure/link-list` | 1 | `#算法与数据结构/链表` | 同上 |
| `#game_dev` | 2 | `#游戏开发` | 命名风格不统一（snake_case） |
| `#csharp` | 3 | `#编程语言/CSharp` | 修正为嵌套 tag |
| `#cpp` | 2 | `#编程语言/Cpp` | 同上 |
| `#python` | 5 | `#编程语言/Python` | 同上 |
| `#godot` | 3 | `#游戏开发/Godot` | 同上 |
| `#methodology` | 3 | `#方法论` | 命名风格不统一（英文） |
| `#AI-Skill` | 3 | `#AI与Agent` | 命名风格不统一 |
| `#AI编程` | 1 | `#AI与Agent` | 合并到领域 tag |
| `#obsidian` | 2 | `#工具` | 具体工具名不作为独立 tag |
| `~~#interview~~` | 7 | ✅ 已转白名单 (§2.2) | 2026-04-29 决定纳入类型 tag，无需清理 |
| `#OpenSpec` | 8 | 待定 | OpenSpec 工作流 tag，暂不纳入白名单；清理时询问用户 |
| `#xxx` | 1 | 删除 | 测试 tag，直接删除 |
| `#frame_tool` | 1 | 红线 `#frame-tool` | snake_case 变体，归入红线 |
| `#High` | 1 | 删除 | 无意义 tag |
| `#SDD` | 1 | 删除 | 无意义 tag |
| `#record` | 1 | 删除 | 语义不明 |
| `#lan` | 1 | 删除 | 语义不明 |
| `#inbox` | 1 | 删除 | 与目录语义重复 |

---

## 5. 新增 tag 流程

1. Agent 发现需要新 tag → 停下，向用户提议"是否新增 `#xxx` 到 TAGS.md 白名单？"
2. 用户确认后 → 在本文件对应分组追加一行，并注明 `added: YYYY-MM-DD`
3. 新增后 → 方可使用该 tag

Agent **不得**自行扩充白名单。

---

## 6. 维护记录

| 日期 | 操作 | 说明 |
|---|---|---|
| 2026-04-29 | 创建 | task 1.11 初版，基于 `obsidian tags` 全量扫描（100 个 tag）整理 |
| 2026-04-29 | 修订 | 嵌套 tag 规则改为"顶层约束 + 嵌套自由组合"；脏 tag 清理表目标值同步更新为嵌套形式；红线清单区分 netease 内部路径与公开区合法嵌套 |
