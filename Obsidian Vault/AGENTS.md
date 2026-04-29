---
note_type: agents-bootstrap
visibility: public
status: bootstrap
---

# AGENTS.md — Vault Bootstrap

> **如果你是一个 AI agent**，看到本文件**必读**。这是你接手这个 Obsidian vault 之前需要知道的全部。
>
> **如果你是人**，参见 `README.md`。

---

## ⚠️ 仓库正在重构中（OpenSpec 进行时）

本 vault 当前正在通过 **OpenSpec 流程**进行结构性重构，目标是把它从"按内容来源分类的传统 Obsidian 知识库"升级为 **Karpathy LLM Wiki 模式**的、agent 可持续维护的个人知识库。

| 项 | 值 |
|---|---|
| 活跃 change | `restructure-vault-as-llm-wiki` |
| change 目录 | `9-Meta/openspec/changes/restructure-vault-as-llm-wiki/` |
| 当前阶段 | Phase 0（环境就绪，等待开工） |
| 任务进度 | 见 `tasks.md` |

**任何对 vault 的改动**都应当通过这个 change 推进，**不要绕过 OpenSpec 流程**。

---

## 🚦 接手协议（按顺序执行）

### Step 1 — 验证环境

新会话开始的第一件事：

```bash
obsidian version          # 必须返回 1.12.7+
openspec list             # 错误时 cd 9-Meta && openspec list
```

如果 `obsidian` 命令找不到：参见 `9-Meta/openspec/changes/restructure-vault-as-llm-wiki/migration-notes.md` 第 1 节"Windows PATH 陷阱"。

### Step 2 — 读懂正在做什么

按顺序读以下文件：

1. `9-Meta/openspec/changes/restructure-vault-as-llm-wiki/proposal.md` —— **为什么**做
2. `9-Meta/openspec/changes/restructure-vault-as-llm-wiki/design.md` —— **怎么**做（11 个决策 + 5 阶段计划 + 零失链协议）
3. `9-Meta/openspec/changes/restructure-vault-as-llm-wiki/specs/agent-schema/spec.md` —— **agent 必须遵守的硬约束**（强制 skill 路由表 / 禁止事项）
4. `9-Meta/openspec/changes/restructure-vault-as-llm-wiki/migration-notes.md` —— **实测命令签名速查**（不要凭记忆猜命令）
5. `9-Meta/openspec/changes/restructure-vault-as-llm-wiki/tasks.md` —— **下一步做什么**（找最近一个未勾选项）

### Step 3 — 加载正确的 skill

| 当前要做的事 | use_skill |
|---|---|
| 继续推进 task | `openspec-apply-change` |
| 决定下一个 task 顺序 / 拆分 | `openspec-continue-change` |
| 写新页面正文（OFM 语法） | `obsidian-markdown` |
| 操作 vault 文件（CRUD/move/property） | `obsidian-cli` |
| 操作 .base | `obsidian-bases` |
| 操作 .canvas | `json-canvas` |
| 不确定 | `openspec-onboard` |

### Step 4 — 执行

按 task 推进，每完成一个勾掉一个。任何 ≥5 文件的批量操作必须先列计划让用户确认。

---

## 🔴 红线（公私边界，绝对不能破）

1. **`netease/` 是工作私有目录**，已在仓库根 `.gitignore` 中排除。这是物理隔离，不可越界。
2. **公开区任何文件不得 wikilink / embed / 引用 `netease/` 内容**。
3. **公开区不得出现 netease 项目代号、内部系统名、同事真名等敏感词**。
4. 每次创建 / 修改公开区 .md 后，agent 应自检 `visibility` frontmatter 是否为 `public`，且正文不含跨边界引用。
5. 如果 agent 发现自己即将破坏上述任一条，**立刻停下并告诉用户**，不得静默继续。

---

## 🛠 强制 skill 路由表（覆盖一切 vault 内文件操作）

| 操作意图 | 必须用 | 禁止 |
|---|---|---|
| .md 的 CRUD / 移动 / 改名 / property 操作 / 链接巡检 | **`obsidian-cli` skill**（即 `obsidian` 命令） | 直接 `edit_file` 写新 .md / `mv` / `git mv` / `xcopy` / Explorer 拖拽 |
| 写 Obsidian Flavored Markdown 正文（wikilink / embed / callout / frontmatter / tag） | **`obsidian-markdown` skill** | 凭记忆乱写 Obsidian 语法 |
| 创建 / 修改 `.base` 文件 | **`obsidian-bases` skill** | 手写 base YAML/JSON |
| 创建 / 修改 `.canvas` 文件 | **`json-canvas` skill** | 手写 canvas JSON |

**为什么强制？**

- vault 设了 `alwaysUpdateLinks: true`。**只有走 `obsidian` CLI 的 move/rename**才能触发 Obsidian 自身的链接自动更新机制；任何外部 `mv` 都会绕过它，造成静默失链。
- 详见 `9-Meta/openspec/changes/restructure-vault-as-llm-wiki/design.md` 的 **D11 零失链协议**。

---

## 🚫 What NOT to do（明令禁止）

- 不得绕过上述 skill 直接用通用文件工具操作 vault 内 .md / .canvas / .base
- 不得让公开区 wikilink / embed / 引用 `netease/` 内容
- 不得在用户未确认前批量修改 ≥5 个文件
- 不得删除 agent 自己也不理解用途的文件
- 不得在 wiki 区放原始对话（那是 `1-Sessions/` 的职责，重构完成后启用）
- 不得把 OpenSpec 工作区从 `9-Meta/openspec/` 移到根目录
- 不得跳过本文件 Step 1～4 的接手协议直接动手

---

## 📍 仓库结构（当前是过渡态）

**旧结构**（仍是主体，迁移中）：
```
读书笔记/  技术文档/  日常杂谈/  软件食谱/  英语学习/
开发项目/  工具用法/  Templates/  Tags/
Assets/  Drawings/  Excalidraw/  Resources/
0-我的笔记本.md  🧠 第二大脑.md  README.md
```

**目标结构**（Phase 0 后会开始建立）：
```
0-Inbox/      临时收件
1-Sessions/   原始对话/文档归档（按 YYYY/MM/）
2-Wiki/       LLM 维护的知识库（带 _index/_log/_MOC）
3-Projects/   项目工作区
4-Journal/    日记/周报/月报
5-Life/       生活长期信息
6-Tools/      工具速查（扁平）
9-Meta/       仓库元信息
  ├── openspec/         本次重构的 spec 工作区
  ├── Skills/           agent skill（自包含）
  ├── Templates/        笔记模板
  ├── Scripts/          维护脚本
  ├── AGENTS.md         完整 agent 约定（Phase 0 task 1.10 创建）
  └── TAGS.md           tag 词表（Phase 0 task 1.11 创建）

netease/       🔴 私有工作区（物理隔离，独立 AGENTS.md）
Assets/ Excalidraw/ Drawings/ Resources/    资产目录（迁移中保持原位）
```

---

## 🔄 本文件的状态

这是 **bootstrap 版本**——目的是让 agent 能在重构完成前**安全地接手工作**。

完整的 `9-Meta/AGENTS.md`（按 `agent-schema/spec.md` 的 10 个必备小节写）将在 Phase 0 task 1.10 创建。完整版上线后，本文件会简化为一句话指针 → 完整版。

最后更新：2026-04-29 by restructure-vault-as-llm-wiki / Phase 0 / pre-phase-1
