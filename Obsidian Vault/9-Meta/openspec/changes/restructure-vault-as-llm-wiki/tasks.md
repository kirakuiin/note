## 1. Phase 0 — 骨架与安全基线

- [x] 1.1 **[迁移前置·阻断项]** 安装/启用 Obsidian 官方 CLI（参见 design D11）：升级 Obsidian 至 1.12.7+ → Settings → General → 启用 Command line interface → **新开一个终端**（已打开的不会读到新 PATH，参见 D11 Windows 陷阱）→ `obsidian version` 返回版本号 → `obsidian help move` 显示 move 子命令。**当前状态：CLI v1.12.7 已就位（路径 `%LOCALAPPDATA%\Programs\Obsidian\Obsidian.com`），后续会话务必新开终端后再执行。**
- [x] 1.2 **[迁移前置]** 验证零失链关键配置：`obsidian eval code="app.vault.config.alwaysUpdateLinks"` 返回 `true`；记录 `newLinkFormat` / `useMarkdownLinks` 当前值（用于后续迁移参考）。**当前状态：`alwaysUpdateLinks=true`，`newLinkFormat`/`useMarkdownLinks` 未显式设置（即默认 shortest + wikilink），完美适配迁移。Vault 内 markdown 文件总数 699。**
- [ ] 1.3 **[迁移前置]** 同名冲突扫描：写一次性脚本/命令列出 vault 内所有 .md 同名重复（如 `读书笔记/设计模式/状态模式.md` vs `读书笔记/游戏编程模式/状态模式.md`），输出冲突清单 → 在 design Open Questions 中记录预案（合并/改名）
- [ ] 1.4 **[迁移前置]** 路径绑定扫描：`grep 'FROM "' *.md` 输出所有 Dataview 路径过滤位置（已知 ≥4 处）；`grep -l '\.canvas$'` 列出所有 canvas 文件（已知 1 个）；汇总到 `9-Meta/openspec/changes/restructure-vault-as-llm-wiki/migration-notes.md`（migration-notes.md 已创建为 living 文档，扫描结果待填入）
- [ ] 1.5 在 vault 根目录创建新顶级目录骨架：`0-Inbox/`、`1-Sessions/`、`2-Wiki/`、`3-Projects/`、`4-Journal/`、`5-Life/`、`6-Tools/`，每个目录放一个 `_index.md` 占位（含 frontmatter）
- [ ] 1.6 确认 `9-Meta/` 已存在并放好 `openspec/`；在 `9-Meta/` 下补建 `Skills/`、`Scripts/`、`Templates/` 三个子目录（各放一个 `_index.md` 占位）
- [ ] 1.7 在 `2-Wiki/` 下按 spec `vault-structure` 的"子目录命名约定" requirement 创建二级主题目录骨架（按学科分），初始集 6 个：`编程语言/`、`游戏开发/`、`算法与数据结构/`、`AI与Agent/`、`英语/`、`方法论/`，每个放 `_index.md` + `_MOC.md`。`软件工程/`、`计算机基础/` 等暂不预建，迁移过程中如有内容再开新二级目录
- [ ] 1.8 校验 `.gitignore`（仓库根）确认 `netease/` 已在排除列表，必要时补一条；在 `9-Meta/AGENTS.md` 草稿里写入"红线"段落引用 `vault-structure` spec
- [ ] 1.9 校对/重写 vault 根 `README.md`：仅保留访客视角的概述、目录速览、私有区说明、入口指引（依据 `agent-schema` spec 的 README/AGENTS 分工要求）
- [ ] 1.10 编写 `9-Meta/AGENTS.md` 完整第一版，覆盖 `agent-schema/spec.md` 列出的 10 个必备小节。**已有草稿**：`9-Meta/openspec/changes/restructure-vault-as-llm-wiki/agents-md.draft.md`（前期为冷启动验证而写的 bootstrap 版本，171 行，含接手协议 / 红线 / 强制 skill 路由表 / 仓库结构。task 1.10 执行时直接基于此草稿扩充至 spec 要求的 10 个小节，然后用 `obsidian move` 落到 `9-Meta/AGENTS.md`，并删除草稿）
- [ ] 1.11 编写 `9-Meta/TAGS.md` 初版词表（基于现有 `Tags/` 目录扫描整理）
- [x] 1.12 在 git 打 tag `pre-phase-1`（回滚锚点）。**已打：commit `77646db` + tag `pre-phase-1`**

> **2026-04-29 修订记录**：原 task 1.10a 创建的根目录 bootstrap `AGENTS.md` 已移除——经讨论确认这违反 spec 的"根目录入口文件 = Dashboard.md + README.md"单一真理源原则，且会话切换由用户人工指引足以覆盖冷启动需求（YAGNI）。bootstrap 内容已用 `obsidian move` 迁至 `agents-md.draft.md` 作为 task 1.10 的实施草稿。本次移动同时实战验证了 D11 零失链协议（unresolved baseline 31 → 31，0 新增断链）。

## 2. Phase 1 — 核心 agent 资产

- [ ] 2.1 在 `9-Meta/Skills/` 创建 4 个新 skill 目录与 `SKILL.md`：`ingest-session`、`ingest-document`、`query-wiki`、`lint-wiki`（内容遵循对应 spec）
- [ ] 2.2 在 `9-Meta/Templates/` 增补模板：`session.md`、`wiki-page.md`、`project.md`、`daily.md`、`MOC.md`、`index.md`、`log.md`（frontmatter 字段对齐 `note-frontmatter` spec）
- [ ] 2.3 在 `9-Meta/Scripts/maintenance/` 添加 Python 脚本骨架：`scan_frontmatter.py`、`check_links.py`、`check_visibility.py`（标准库实现，PyYAML 可选）
- [ ] 2.4 写一份 `Dashboard.md`（vault 根）替代旧的「我的笔记本.md」：含最近 sessions、活跃 projects、待办 lint、知识地图入口

## 3. Phase 2 — 内容迁移（公开区，零失链协议）

> **铁律**：本 phase 所有 .md / .canvas 移动**必须**通过 `obsidian move path=<src> to=<dst>` 执行（参见 design D11）。**禁止使用** `git mv` / `mv` / `xcopy` / Explorer 拖拽。每批迁移完成后用 `obsidian unresolved` + `check_links.py` 双重 verify。资产目录（Assets/Excalidraw/Drawings/Resources）**保持原位不动**。

- [ ] 3.1 **[预处理]** 对 1.3 列出的同名冲突文件，先用 `obsidian rename` 在原目录改名（避免迁移后冲突），并验证所有引用仍指向正确文件
- [ ] 3.2 **[Batch A · 最独立]** 迁移 `英语学习/` → `2-Wiki/英语/`，每文件 `obsidian move`；本批后跑 `obsidian unresolved` + `check_links.py`，git tag `post-batch-A`
- [ ] 3.3 **[Batch B]** 迁移 `读书笔记/` → `2-Wiki/<对应领域>/`（设计模式、3D数学、重构等按子目录映射）；本批后双重 verify + tag
- [ ] 3.4 **[Batch C]** 迁移 `技术文档/` → `2-Wiki/技术/<语言或主题>/`；其中 `技术文档/AI/skills/` 下的"知识型文档"移入 `9-Meta/Skills/<相应 skill>/references/`，运行/规范文档移入 `9-Meta/Skills/<skill>/SKILL.md` 或 `scripts/`；本批后双重 verify + tag
- [ ] 3.5 **[Batch D]** 拆分 `日常杂谈/`：日记/周报/总结 → `4-Journal/<YYYY>/`，长期生活类（zerotier、网盘等）→ `5-Life/`，GTD/方法论 → `2-Wiki/方法论/`；本批后双重 verify + tag
- [ ] 3.6 **[Batch E]** 迁移 `软件食谱/`、`工具用法/` → `6-Tools/`（按 design D3 保持扁平，文件名加类别前缀如 `编辑器-VSCode.md`）；本批后双重 verify + tag
- [ ] 3.7 **[Batch F]** 迁移 `开发项目/代号α/` → `3-Projects/个人-代号α/`；本批后双重 verify + tag
- [ ] 3.8 **[Batch G]** 迁移 `Templates/` → `9-Meta/Templates/`；本批后双重 verify + tag
- [ ] 3.9 **[资产目录决策]** `Assets/`、`Drawings/`、`Resources/`、`Excalidraw/` **不动**；在 `9-Meta/AGENTS.md` 显式标注"历史扁平资产目录，新资产走 `2-Wiki/<主题>/_assets/`"
- [ ] 3.10 **[Dataview/Canvas 修正]** 按 1.4 清单逐条手工修正：
  - 4 处 Dataview `FROM "..."` 路径
  - `日常杂谈/我的GTD实践笔记.canvas` 内部节点（手工 verify wikilink 是否仍解析正确，必要时在 Obsidian 内打开重保存）
- [ ] 3.11 老 `0-我的笔记本.md` 内容并入新 `Dashboard.md` 后用 `obsidian delete file="0-我的笔记本"`
- [ ] 3.12 验证旧的 11 个顶级目录已为空，用 `obsidian eval code="app.vault.adapter.rmdir(...)"` 或文件管理器删除空目录（此时不会再产生失链）
- [ ] 3.13 **[Phase 2 总验收]** `obsidian unresolved` 全量返回 ≤ 旧基线值；`check_links.py` 残余断链清单 ≤ 5 条且全部为已知例外；git log 全 phase 看到的应是 R（rename）而非大量 D+A

## 4. Phase 3 — Frontmatter 规范化

- [ ] 4.1 在所有迁移后的 `.md` 上跑 `scan_frontmatter.py`，输出"缺字段 / 字段值非法"清单
- [ ] 4.2 按 `note-frontmatter/spec.md` 批量补齐必填字段：`tags`、`area`、`visibility`、`status`，每批 ≤30 个文件、每批呈现 diff 后由用户确认
- [ ] 4.3 跑 `check_visibility.py` 验证公开区无 `visibility: private`、无引用到 `netease/`；红线问题直接阻断后续步骤
- [ ] 4.4 填写 `4-Journal/`、`3-Projects/` 的领域专属字段（如 `project: status/start/end`）

## 5. Phase 4 — 首次完整 Lint 与收尾

- [ ] 5.1 执行 `lint-wiki` 全量巡检，按 `wiki-lint/spec.md` 的 10 项检查输出报告
- [ ] 5.2 修复 Critical/Warning 项（隐私/断链/index 漂移）；Suggestion 项酌情处理
- [ ] 5.3 在 `2-Wiki/_log.md` 追加首条 `migration` 记录，链回本 OpenSpec change
- [ ] 5.4 在每个顶级目录的 `_index.md` 中补全已迁入条目
- [ ] 5.5 更新 `Dashboard.md` 的"知识地图"入口，确保从首页两跳可达任意主题 MOC

## 6. netease 私有区对齐（仅约定，不动现有内容）

- [ ] 6.1 在 `netease/` 下新建空骨架 `1-Sessions/`、`2-Wiki/`、`3-Projects/`、`4-Reference/`，各放 `_index.md`（不迁移已有内容）
- [ ] 6.2 在 `netease/AGENTS.md` 写一份私有区专属 schema：明确允许的 tag、敏感词清单、与公开区的引用边界
- [ ] 6.3 公开区 `9-Meta/AGENTS.md` 显式声明：私有区拥有独立 AGENTS.md，agent 跨入 `netease/` 时必须切换上下文

## 7. 验收

- [ ] 7.1 `openspec validate restructure-vault-as-llm-wiki --strict` 通过
- [ ] 7.2 `lint-wiki` 全量报告无 Critical
- [ ] 7.3 `check_visibility.py` 报告 0 处跨边界引用
- [ ] 7.4 用户人工巡检 `Dashboard.md` → 任意主题 MOC → 任意 wiki 页 的导航顺畅
- [ ] 7.5 准备 archive：在 `_log.md` 写明 "本 change 即将归档"，确认 main specs 同步策略
