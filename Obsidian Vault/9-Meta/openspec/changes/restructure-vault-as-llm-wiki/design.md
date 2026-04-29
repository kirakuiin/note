## Context

Vault 当前是按"内容来源（读书笔记/技术文档/日常杂谈/...）"组织的传统 Obsidian 知识库，约 500 个 markdown 文件分布在 11 个顶级目录中，几乎没有 frontmatter，缺少 agent 可消费的元数据和导航。

用户希望把它升级为 [Karpathy LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) 模式：LLM 增量维护、持续累积、对话即素材、wiki 即代码库。同时存在两个硬约束：

1. **公私物理隔离**：`netease/` 是工作私有目录（含敏感信息），通过 `.gitignore` 排除后，其余目录定时 push 到 GitHub。这条边界绝对不能被打破。
2. **Agent 跨边界工作**：尽管物理上隔离，agent 在工作场景下需要能同时读写 netease 和公开区。

设计需要在 PARA 类生命周期分类、Karpathy LLM Wiki 模式、Obsidian 习惯三者之间找平衡。

## Goals / Non-Goals

**Goals:**

- 顶级目录数量控制在 7±2，每个目录能用一句话回答"它放什么"
- 提供给 agent 一份单一权威的 schema（`9-Meta/AGENTS.md`），让任何 agent 第一次接触这个 vault 都能在 5 分钟内理解结构和约定
- 把"对话/直接输入文档"作为一等的知识来源，提供持久化和消化路径
- 让 LLM 能持续维护交叉引用、索引、日志，而不是每次查询都从原始素材重建
- 保持 Obsidian wikilink 的可用性（迁移过程通过 Obsidian 自带的"重命名/移动"机制保留链接）
- 公私边界硬隔离 + agent 跨边界协作两者兼得
- 整个迁移过程可分阶段交付，每个阶段独立可用，不要求"一次到位"

**Non-Goals:**

- **不引入向量数据库或 RAG 基础设施**：100~1000 篇笔记规模下，`_index.md` + grep 足够
- **不强制 LLM 接管所有写入**：用户仍然可以人工写笔记，LLM 主要负责 ingest/lint/cross-reference
- **不做任何会破坏 .gitignore 边界的事**：例如在公开区 wikilink 到 `netease/`、把 netease 内容引用进公开 wiki 等
- **不引入新工具/插件依赖**：保持 vanilla Obsidian + LLM agent 即可工作（Dataview/Excalidraw 已有的不算新引入）
- **不统一处理 Excalidraw 文件迁移**：Excalidraw 由插件按文件名管理，目录无关，本次 change 不动它的存放位置
- **不为了优雅而过度抽象**：每个目录、每个 skill 都必须有具体内容支撑，不留空架子
- **本次 change 不实施"对每个旧笔记都人工 review 一遍"的工作**：迁移以路径调整 + 脚本补 frontmatter 为主，深度内容重构留给后续 ingest/lint 流程

## Decisions

### D1: 顶级目录采用"性质/生命周期"而非"主题"分类，并加数字前缀

**决定**：7 个顶级目录加数字短横线前缀：`0-Inbox/`、`1-Sessions/`、`2-Wiki/`、`3-Projects/`、`4-Journal/`、`5-Life/`、`6-Tools/`、`9-Meta/`。

**理由**：
- 性质分类（PARA 思想）的容量上限可控，主题分类会无限扩张
- 数字前缀强制排序，让 Obsidian 侧栏顺序与重要程度一致（高频在上）
- 用单数字 + 短横线（不是 `00_`），视觉更轻
- `9-` 表示"系统/元信息"，永远在最后；中间留 `7/8` 给未来扩展（如归档、沙箱）

**否定的备选方案**：
- 保持纯中文目录名 + emoji 前缀（如 `📥 收件箱/`）：emoji 在 git/CLI/某些系统上显示为方块，对 agent 不友好
- 完整 PARA 命名（`Projects/Areas/Resources/Archives`）：英文味太重，且 PARA 的 Resources 太大，区分不清"知识"和"工具速查"
- 保持现状只补 frontmatter：不解决"日常杂谈杂物筐"和"读书 vs 技术分类失效"的根本问题

### D2: 把"对话"作为一等知识源，新增 `1-Sessions/` 层

**决定**：在 wiki 三层架构中，用 `1-Sessions/` 替代 Karpathy 原 pattern 的 "Raw Sources"。每次有价值的对话或文档输入，归档为 `1-Sessions/YYYY/MM/YYYY-MM-DD-主题.md`。

**理由**：
- 用户的素材源不是网页剪藏，而是开发对话和直接粘贴的文档（和 Karpathy 默认场景不同）
- 对话有强时间属性，按年/月/日分目录天然有序
- 文件名带主题让 agent 后续能基于文件名快速判断"我们之前聊过 X 没有"
- 保留原始对话有助于后续追溯 wiki 页面的来源（frontmatter 的 `source` 字段指向 session 文件）

**否定的备选方案**：
- 不留对话归档，全部直接消化进 wiki：丢失追溯链，且 wiki 页面无法解释"为什么这样写"
- 对话只放在 `0-Inbox/`：inbox 是临时的，sessions 应该是永久的"原始素材层"

### D3: `2-Wiki/` 是 LLM 主导维护区，而 `6-Tools/` 是手册型笔记区，明确分离

**决定**：`2-Wiki/` 内的页面满足"LLM Wiki 规范"（强 wikilink、frontmatter、纳入 `_index.md`、按学科分类）；而 `6-Tools/` 的工具速查文件保持扁平、独立、不强求交叉引用。

**理由**：
- 工具速查是"用到才查、查完就走"的查询型笔记，强行让 LLM 给它建交叉引用是浪费
- 把它隔离出 wiki 区，避免污染 wiki 的"互联性"指标（lint 时孤儿检查会误报）
- `6-Tools/` 用 `编辑器-VSCode.md`、`版本控制-Git.md` 这种类别前缀代替子目录（13 个文件不值得开多层目录）

### D4: `9-Meta/AGENTS.md` 作为单一 schema 入口

**决定**：所有"给 agent 看的约定"集中在一份 `9-Meta/AGENTS.md`，而不是散落在多个 README 或各 skill 内部。

**理由**：
- Karpathy 模式明确指出 schema 是关键配置文件，需要单一权威源
- agent 每次工作前只需读一份文件就能掌握全局，不用拼凑
- 后续约定演化时只改一处，不会出现多处不一致
- `AGENTS.md` 是 OpenAI Codex/Claude 等多家 agent 的事实标准命名

**与 README.md 的分工**：`AGENTS.md` 给 agent，`README.md` 给 GitHub 访客（仓库简介、用途、如何浏览）。

### D5: Skills 拆离知识区，统一到 `9-Meta/Skills/`

**决定**：`技术文档/AI/skills/` 整体迁移到 `9-Meta/Skills/`，每个 skill 是自包含目录，预留 `scripts/`、`templates/`、`assets/`、`references/` 子结构。

**理由**：
- Skills 是 agent 的"代码"，不是给人学习的知识，性质完全不同
- 放在 Meta 区表明它们是"仓库基础设施"
- 每个 skill 自包含（self-contained）的设计参考 Anthropic Agent Skills 标准
- 区分"skill 内部脚本"（在 skill 目录内）和"仓库级维护脚本"（在 `9-Meta/Scripts/`）

### D6: netease/ 内部采用与公开区对称的 PARA 结构

**决定**：netease/ 也用 `0-Daily/`、`1-Sessions/`、`2-Wiki/`、`3-Projects/`、`4-Reference/` 的结构，与公开区对称（区别仅在于多了 daily、`4-Reference/` 放第三方文档镜像）。

**理由**：
- agent 跨边界工作时认知模型一致，不用学两套结构
- 第三方文档镜像（arcolab/popo）独立到 `4-Reference/`，明确"只读参考"语义
- 工作日报与私有约定，对应公开区的 inbox 概念，但更结构化（按年/月分目录已建立的习惯沿用）

### D7: 全量补 frontmatter，最小字段集 + 渐进扩展

**决定**：所有笔记必填字段：`tags`、`area`、`visibility`；按需选填：`source`、`status`、`updated`、`created`。
- `tags`：领域 tag（数组）
- `area`：所在生命周期区（`knowledge`/`session`/`project`/`journal`/`life`/`tool`/`meta`/`work-*`）
- `visibility`：`public`/`private`（**这是给 agent 的安全防线**）
- `source`：来源（如某 session 文件、某本书）
- `status`：`draft`/`stable`/`stale`/`archived`

**理由**：
- 字段越少越易维护，先建立最小可用集
- `visibility` 是关键安全字段，agent 在跨区操作时可基于它做检查
- 大部分字段可由脚本根据所在目录自动生成

### D8: 取代 `🧠 第二大脑.md`，建立 `Dashboard.md` + `README.md` 双入口

**决定**：
- 删除 `🧠 第二大脑.md`（现版本是摆设型 dashboard）
- 新建 `Dashboard.md`：行动型工作台（待办、当日入口、知识地图）
- 新建 `README.md`：GitHub 访客的仓库说明
- `9-Meta/AGENTS.md` 作为 agent 入口（已在 D4）

**理由**：
- 三种受众（自己/访客/agent）对入口的需求完全不同，强行用一个文件会牺牲所有人的体验
- Dashboard 用 wikilink + dataview 做"行动驱动"，不是"数据展示"

### D9: 用 OpenSpec 管理本次重构 + 后续重大变更

**决定**：在 `9-Meta/openspec/` 建立 OpenSpec 工作区，本次重构作为第一个 change。后续涉及"目录结构调整、AGENTS.md 重大修订、新增 capability"的变更都走 OpenSpec 流程。

**理由**：
- 改动跨度大、有迁移风险，需要"先设计再执行"的纪律
- 留下完整文档让未来的你/其他 agent 能理解为什么这么设计
- 放在 `9-Meta/openspec/` 而非根目录，保持 7 个顶级目录的整洁
- 不依赖 OpenSpec CLI 在根目录运行——用户/agent 用 `cd 9-Meta && openspec ...` 即可

### D10: 迁移分阶段执行，每个阶段独立可交付

**决定**：迁移分 5 个 phase，从骨架到内容到元数据再到健康检查，每个 phase 完成后系统都可用：
- Phase 0: 搭骨架（不动现有内容，只新增）
- Phase 1: 写核心 Skills + AGENTS.md
- Phase 2: 迁移现有内容（按领域分批）
- Phase 3: 批量补 frontmatter
- Phase 4: 首次 lint 巡检

**理由**：避免"做到一半中断后留下半成品"，每个阶段都是 commit-ready 的状态。

### D11: 迁移操作模式 — obsidian-cli 优先的"零失链"协议

**背景**：本 vault 的 `app.json` 设了 `alwaysUpdateLinks: true`，且全仓库使用 wikilink 短格式（`[[Page]]`、`![[image.png]]`）。Obsidian 自身的链接更新机制是迁移的核心保障——**只要走 Obsidian 自身的 move/rename，所有 wikilink、embed、canvas 节点路径都会被自动改写**；反之任何外部 mv（`git mv`、`xcopy`、Explorer 拖拽）都会绕过这一机制，造成静默失链。

**决定**：迁移操作严格按以下优先级执行，禁止跨级降级：

| 优先级 | 机制 | 适用场景 | 链接更新 |
|---|---|---|---|
| ★ 首选 | **官方 `obsidian` CLI 的 `move` / `rename`**（Obsidian 1.12.7+ 内置） | 任何 .md / .canvas / .base 文件的目录变更或改名 | ✅ 等同 UI 操作，自动改写所有引用 |
| 备选 | Obsidian UI 内手动拖拽 / 重命名 | CLI 不可用、单个文件、需要可视化确认 | ✅ |
| 兜底 | 关闭 Obsidian → `git mv` → 启动 Obsidian → 用 `unresolved` / `check_links.py` 扫断链 → 人工修 | 仅限 CLI/UI 都不可用的极端情况 | ❌ 需事后手工补救 |
| 禁止 | `mv` / `xcopy` / Explorer 拖拽（在 Obsidian 运行中执行） | — | ❌ 静默失链，且 Obsidian 索引会错乱 |

**关于工具选型**：
- 系统中目前安装的是 `npx obsidian-cli@0.5.1`（社区版，依赖 Local REST API 插件，**不提供 `move`/`rename`**），不能用于本次迁移。
- 必须使用 **Obsidian 官方内置 CLI**（命令名 `obsidian`，需 Obsidian 桌面版 1.12.7+ 并在 Settings → General → Command line interface 中启用）。这是 Phase 0 的强制前置条件。
- **Windows PATH 陷阱（已在本环境验证遇到）**：启用 CLI 后注册的可执行 `Obsidian.com` 在 `%LOCALAPPDATA%\Programs\Obsidian\` 下，写入的是 user PATH。**已经打开的终端窗口不会读到新 PATH**——必须新开终端，或在当前终端用全路径 `"%LOCALAPPDATA%\Programs\Obsidian\Obsidian.com" <cmd>` 调用。这条是 task 1.1 验收时必须实测确认的项。

**纯资产目录的特殊规则**：`Assets/`、`Excalidraw/`、`Drawings/`、`Resources/` 在本次迁移中**完全保持原位不动**。理由：所有 `![[xxx.png]]` `![[xxx.excalidraw]]` 都是按文件名匹配，资产文件不动 = 引用零风险。新结构下的资产改放到 `2-Wiki/<主题>/_assets/` 仅适用于**新增**资产，旧资产的归并放到独立的后续 change。

**辅助：Dataview / Bases / Canvas 的路径绑定**：
- `obsidian` CLI 的 `move` **不会**修改 markdown 正文里的 dataview 查询字符串（如 `FROM "读书笔记"`），这部分必须靠迁移后的 grep + 手工改。当前 vault 已 grep 出 4 处依赖。
- `.canvas` 文件内部节点的路径如果是 wikilink 短格式则随 Obsidian 自动更新；如果是相对路径 markdown link 则需要手工核对。本 vault 1 个 canvas，单独 verify。
- 没有 `.base` 文件依赖路径绑定（已 grep 验证）。

**同名冲突预案**：迁移前必须先扫描 vault 内的同名 .md（如 `读书笔记/设计模式/状态模式.md` vs `读书笔记/游戏编程模式/状态模式.md`），不能让两个同名文件落到同一目录，否则 Obsidian 的 wikilink 解析会变成"歧义引用"，引发链接指向错误文件。冲突项必须先用 `obsidian rename` 改名（同样会自动更新引用）。

**理由**：把"链接安全"从"靠人盯"提升到"靠机制"，是这套迁移能在数百文件规模下不出事的根本前提。

## Risks / Trade-offs

- **R1: Wikilink 大规模断裂** → 缓解：见 **D11 零失链协议**——必须使用官方 `obsidian` CLI 的 `move`/`rename` 触发 `alwaysUpdateLinks`；纯资产目录（Assets/Excalidraw/Drawings/Resources）原地不动；同名文件冲突先 rename 后 move；每批迁移后用 `obsidian unresolved` + `check_links.py` 双重 verify
- **R2: Dataview FROM "<旧目录>" 路径绑定全部失效** → 缓解：已 grep 识别 vault 中仅 4 处依赖（`读书笔记/设计模式/📚大纲（设计模式）.md`、`读书笔记/重构/📚大纲（重构）.md` 两处、`技术文档/Unity/Unity知识点.md` 两处、`英语学习/语法/📚目录（英语语法）.md` 一处），Phase 2 收尾任务专项手工修正；无 `.base` 文件依赖路径绑定
- **R3: `.gitignore` 边界因新结构而出错（误把 netease 子目录漏掉）** → 缓解：迁移完成后立刻 `git status` 验证 netease 内容确实未被 track；`9-Meta/AGENTS.md` 中明确写出 visibility 检查机制
- **R4: 全量补 frontmatter 脚本可能破坏现有 frontmatter** → 缓解：脚本采用"只补充不存在的字段"策略，先 dry-run 输出 diff，人工 review 后再实际写入
- **R5: 用户在迁移中途有新增笔记，落到错误位置** → 缓解：Phase 0 完成后立刻把 AGENTS.md 推上线，新笔记按新约定写；Phase 2 迁移时把这些新笔记一起处理
- **R6: 改造后 Obsidian 启动变慢（文件多+索引重建）** → 接受：一次性代价，可忽略
- **R7: OpenSpec 工作区不在根目录，未来若引入其他 OpenSpec 自动化工具会需要配置 working dir** → 接受：当前工作流不依赖外部自动化，影响小
- **R8: Agent 错误地把 netease 内容引用到公开 wiki** → 缓解：`9-Meta/AGENTS.md` 设硬规则，所有 wiki 页面都有 `visibility: public`，agent 写入前必须检查目标位置和源 visibility 一致；lint skill 会扫描跨边界引用

## Migration Plan

### Phase 0: 搭骨架（耗时 ~1 小时）
- 创建 `9-Meta/AGENTS.md`（基础版本，后续可增补）
- 创建空目录 `0-Inbox/`、`1-Sessions/`、`2-Wiki/`、`3-Projects/`、`4-Journal/`、`5-Life/`、`6-Tools/`
- 创建占位文件 `2-Wiki/_index.md`、`2-Wiki/_log.md`
- 不动现有 11 个目录

**验收**：新对话/文档能按新约定沉淀到 `1-Sessions/` 和 `2-Wiki/`，旧内容完全不受影响。

### Phase 1: 写 4 个核心 Skills（耗时 ~半天）
- `9-Meta/Skills/ingest-session/SKILL.md`
- `9-Meta/Skills/ingest-document/SKILL.md`
- `9-Meta/Skills/query-wiki/SKILL.md`
- `9-Meta/Skills/lint-wiki/SKILL.md`
- 把现有 `技术文档/AI/skills/` 整体迁移到 `9-Meta/Skills/`

**验收**：能用 ingest-session 沉淀本次对话；能用 query-wiki 查询新建的 wiki 页面。

### Phase 2: 迁移现有内容（耗时 ~1-2 天，可分批）
按独立性排序，每批结束后 commit：
1. `英语学习/` → `2-Wiki/英语/`（最独立）
2. `读书笔记/` → `2-Wiki/<对应领域>/`
3. `技术文档/` → `2-Wiki/<对应领域>/` + 散落根目录的 5 个文件归类
4. 拆分 `日常杂谈/` → `4-Journal/`、`5-Life/`、`2-Wiki/方法论/`
5. `工具用法/` → `6-Tools/` 加前缀
6. `开发项目/代号α/` → `3-Projects/个人-代号α/`
7. `Templates/` → `9-Meta/Templates/`
8. netease 内部重构

**每批的步骤**（严格按 D11 零失链协议）：
1. 前置检查：本批文件名与目标位置已有文件**无同名冲突**（如有，先用 `obsidian rename` 改名）
2. 用 `obsidian move path=<src> to=<dst>` 逐文件迁移；或写脚本批量调用 CLI（每条命令独立、可中断）
3. 迁移完成后跑 `obsidian unresolved` 看是否多出未解析链接（理论上应为 0）
4. 跑 `check_links.py` 二次 verify（脚本只读，不改文件）
5. 抽查本批 5 个高频笔记的入链/出链是否完好
6. 修正本批涉及的 Dataview `FROM "..."` 路径
7. 单批 commit（`git status` 应当看到 R 类型的 rename 而非 D+A，证明 Obsidian 走的是真 rename）

### Phase 3: 批量补 frontmatter（耗时 ~半天）
- 写 `9-Meta/Scripts/maintenance/batch_add_frontmatter.py`
- 根据所在目录推断 `area`、`visibility`、初始 `tags`
- 先 dry-run 输出 diff，review 后实际执行
- 抽样人工修正 tags 不准的文件

### Phase 4: 首次 Lint（耗时 ~1-2 小时）
- 运行 `lint-wiki` skill
- 修复发现的：断链、孤儿页面、缺 frontmatter、`_index.md` 与实际不符
- 给每个领域目录补 `_MOC.md`

### 收尾
- 删除 `🧠 第二大脑.md`，创建 `Dashboard.md` 和 `README.md`
- 更新 `.gitignore`（确认仍正确隔离 netease）
- 跑一次 `git status` 验证未泄露
- archive 本 change

### 回滚策略
- 每个 phase 前打 git tag（`pre-phase-N`），出问题可 `git reset --hard`
- 由于绝大多数操作是文件移动 + 文本编辑，没有不可逆的破坏性操作
- 唯一不可回滚的：删除 `🧠 第二大脑.md`、改写 `.gitignore`，这两个动作在收尾阶段做且单独 commit

## Open Questions

- **Q1**：`5-Life/桌游/` 的 70 个文件名带英文括号（如 `7连翻(Flip 7).md`），是否要在迁移时统一规范化？暂定保持原样，未来再说。
- **Q2**：`Excalidraw/` 下有按"English grammer"等子目录组织的文件，是否随 `2-Wiki/英语/` 一起调整？暂定不动 Excalidraw（插件管理，目录无关），让它独立成顶级目录就好。
- **Q3**：`5-Life/读书-非技术/` 是否值得作为子目录？目前只有《小狗钱钱》一本，可能不值得开目录。决策延后到 Phase 2 迁移时按实际数量决定。
- **Q4**：`netease/work/弥勒山新门派/mls/弥勒山技能制作.base` 等 base 文件的路径过滤规则，迁移时具体如何修改，需要在 Phase 2 实操时逐个看。
- **Q5**：是否需要在 Dashboard.md 中放"今日 git 待 commit 笔记数"等动态数据？暂定不放，避免 Dashboard 越来越复杂。
