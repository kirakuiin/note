---
name: openspec-review
description: >
  Multi-round structured code review within OpenSpec workflow.
  Activated after all tasks are implemented and before archive.
  Focuses on code cleanliness, robustness, and safety.
  Triggers on: '/opsx:review', 'code review', '代码审查',
  'review round', '帮我review', '看看代码质量'.
---

# OpenSpec Review — 多轮结构化代码审查

## 定位

Review 是 OpenSpec 流程中 **verify 之后、archive 之前** 的环节：

```
propose → design → tasks → apply → verify → ★ review ★ → archive
                                    做对了吗？   写好了吗？
```

- **verify** 确认代码是否符合 spec/design（功能正确性）
- **review** 确认代码是否写得好（质量、整洁、健壮性）

---

## 启动前提

### 必须在新上下文中启动

Review 要求独立视角，不受实现过程的路径依赖影响。启动时：

1. **提醒用户**：如果当前会话参与过该 change 的实现，建议用户开启新会话
2. **读取 change artifacts 建立设计意图理解**（不受实现细节干扰）：
   - `openspec/changes/<name>/proposal.md` — 理解为什么做
   - `openspec/changes/<name>/design.md` — 理解怎么做
   - `openspec/changes/<name>/tasks.md` — 理解做了什么
   - 相关 `specs/` — 理解规格要求
3. **读取项目规则**（如有 `openspec/config.yaml` 中的 `rules.review` 部分）
4. **识别变更文件**：从 tasks.md 中提取本次 change 涉及的文件列表

---

## Review 维度

按以下维度逐轮审查，每轮聚焦单一维度：

### 核心维度（必审）

| 维度 | 关注点 |
|------|--------|
| **代码整洁性** | 重复逻辑未合并（DRY）、冗余 import、死代码、过长函数、过深嵌套、魔法数字 |
| **缩进与格式** | Tab/空格混用、缩进层级不一致、多行格式尾随逗号、编码声明 |
| **健壮性** | 边界条件、空值防御、异常处理合理性、容错降级、类型安全 |
| **安全性** | 多线程安全、文件操作冲突、资源泄漏（定时器/事件订阅未清理）、注入风险 |

### 扩展维度（可选，由 config.yaml 的 rules.review 定制）

项目可在 `openspec/config.yaml` 的 `rules.review` 中追加项目特定的 review 维度和规则。

---

## 多轮 Review 流程

### 第一轮启动

1. 展示本次 change 涉及的文件列表
2. 展示所有 review 维度及状态
3. 建议从最可能有问题的维度开始（或用户指定）
4. 读取目标文件代码，执行该维度的审查

### 每轮输出格式

```markdown
## Round N: <维度> — <文件/模块>

### 发现

| # | 文件 | 行号 | 严重程度 | 问题描述 | 建议修改 |
|---|------|------|---------|---------|---------|
| 1 | xxx.py | 42 | critical | 描述 | 建议 |
| 2 | xxx.py | 108 | warning | 描述 | 建议 |

### 本轮小结
<核心发现概述，1-3句话>
```

### 严重程度定义

- **critical**: 会导致运行时错误、数据损坏或资源泄漏，必须修复
- **warning**: 潜在风险、设计缺陷或明显的代码异味，强烈建议修复
- **suggestion**: 可改进项，提升可读性或可维护性，不紧急

### 轮次衔接

每轮结束后展示：

```
── Review 进度 ──────────────────────────
  ✅ 代码整洁性    (3 critical, 2 warning)
  ⬜ 缩进与格式
  ⬜ 健壮性
  ⬜ 安全性
  累计: 3 critical, 2 warning, 0 suggestion
  建议下一轮: 健壮性
─────────────────────────────────────────
```

用户可以：
- 继续下一轮（接受建议或指定维度）
- 先修复当前发现的问题（暂停 review，进入修复）
- 结束 review（生成汇总）

---

## Review 文档（review.md）

### 生成时机

首轮 review 完成后生成 `review.md`：

- **有活跃 change**：放在 `openspec/changes/<name>/review.md`
- **无活跃 change（全项目 review）**：放在 `openspec/review.md`

```
# 有活跃 change 时：
openspec/changes/<name>/
├── .openspec.yaml
├── proposal.md
├── design.md
├── tasks.md
├── review.md              ← 新增
└── specs/

# 无活跃 change 时（全项目 review）：
openspec/
├── review.md              ← 项目级 review
├── specs/
└── ...
```

### 文档结构

问题列表采用 **checklist 格式**，按严重程度排序（critical → warning → suggestion），每个问题后留有用户批注位置：

```markdown
# Code Review — <change-name>

## 概览
- Change: <name>（全项目 review 时写"全项目"）
- 涉及文件: <文件列表>
- Review 日期: <date>

## 问题列表

按严重程度排序：critical > warning > suggestion。

### Critical

- [ ] **#1** `xxx.py` L42 — [整洁性] 问题描述
  - 建议: 建议修改内容
  - 处理意见: <!-- 用户填写：修复 / 忽略 / 降级 / 自由文本 -->

- [ ] **#3** `yyy.py` L15 — [健壮性] 问题描述
  - 建议: 建议修改内容
  - 处理意见: <!-- 用户填写 -->

### Warning

- [ ] **#2** `xxx.py` L108 — [整洁性] 问题描述
  - 建议: 建议修改内容
  - 处理意见: <!-- 用户填写 -->

### Suggestion

- [ ] **#4** `zzz.py` L200 — [安全性] 问题描述
  - 建议: 建议修改内容
  - 处理意见: <!-- 用户填写 -->

## 统计
- Total: N 项
- Critical: X 项
- Warning: Y 项
- Suggestion: Z 项

## 修复记录
<!-- 每次修复后追加 -->

### Fix Round 1 — <date>
- [x] #1: <简述修改内容>
- [x] #3: <简述修改内容>
- 备注: <如有设计层面的调整，说明影响>
```

#### 排序规则

问题列表**必须按严重程度分组排序**：
1. **Critical** — 最优先，放在最前面
2. **Warning** — 其次
3. **Suggestion** — 最后

同一严重程度内按发现顺序排列。

#### Checklist 格式说明

- `- [ ]` 表示未处理，`- [x]` 表示已处理（修复或标记 wontfix）
- 每个问题下方的「处理意见」是**留给用户填写**的位置
- 用户可填写：`修复`、`忽略`/`wontfix`、`降级`、或自由文本说明
- AI 在修复阶段读取处理意见，按用户意图执行

### 用户批注

用户可以直接在 review.md 的「备注」列或问题行中添加批注：
- `忽略` / `wontfix` — 标记为不修复，AI 跳过
- `降级` — 降低严重程度
- 自由文本 — 补充上下文或修改要求

AI 在下一轮修复时读取批注，按用户意图处理。

### 状态流转

```
⬜ open → 🔧 fixing → ✅ fixed
                    → ⏭️ wontfix (用户批注)
                    → 🔄 reopened (修复后复查发现仍有问题)
```

---

## 继续操作规则（必须遵守）

当用户说「继续」「处理」「下一轮」或类似指令时，**必须先读取 review.md**，解析用户的批注后再执行操作：

1. **先读取 review.md**：每次继续前，必须重新读取 review.md 文件获取最新内容
2. **解析用户批注**：逐条检查所有 open 状态的问题，根据用户在「处理意见」和 checkbox 中的标注判断意图：
   - 用户**主动打叉** `[X]` / `[x]`（勾选 checkbox）但**未填写「修复」等处理意见** → 视为 **wontfix**（不处理），AI 跳过
   - 用户填写了「修复」、「fix」或具体修改要求 → 视为 **需要修复**，AI 执行修复
   - 用户填写了「忽略」、「wontfix」→ 视为 **wontfix**，AI 跳过
   - 用户填写了「降级」→ AI 降低严重程度
   - checkbox 未勾选 `[ ]` 且有「处理意见」文本 → 按文本内容执行
   - checkbox 未勾选 `[ ]` 且「处理意见」为默认注释（`<!-- 用户填写 -->`）→ 保持 open，不处理
3. **按批注执行**：先修复所有标记为「修复」的问题，再进入下一轮 review
4. **更新 review.md**：修复完成后更新对应条目状态

> **核心原则**：用户的批注是最高优先级指令，AI 不得自行假设处理方式，必须严格按批注执行。

---

## 修复流程

当用户决定修复 review 发现的问题时：

1. AI 按 review.md 中的问题列表逐项修复
2. 每项修复后更新 review.md 状态
3. 如果修复涉及设计层面调整，同步更新 design.md 或 delta spec
4. 修复完成后，可以继续下一轮 review 或结束

**注意**：修复过程中遵循项目的老模块修改原则和编码规范。

---

## 收尾

当用户决定结束 review（或所有维度完成且问题全部处理）时：

### 汇总输出

```
══ Review 完成 ══════════════════════════
  总轮次: N
  总问题: X 项
    ✅ Fixed:    A 项
    ⏭️ Wontfix:  B 项
    ⬜ Open:     C 项（如有）

  文档变更:
    • review.md — 已生成/已更新
    • design.md — [已更新 / 无变化]
    • specs/    — [已更新 / 无变化]

  → 下一步: /opsx:archive <change-name>
═════════════════════════════════════════
```

### 归档行为

archive 阶段处理 review.md 时：
- **review.md 随 change 一起归档保留**（完整历史记录）
- review 过程中对 design.md / spec 的修改已同步完成
- archive 的 sync-specs 步骤会将 delta spec 合并到主线

---

## 约束

1. **Review 阶段默认只读** — 不主动修改代码，除非用户明确要求修复
2. **不质疑已决策的设计** — design.md 中已分析过的方案选择不在 review 范围内
3. **聚焦代码质量** — 功能正确性由 verify 负责，review 不重复检查
4. **遵循项目规则** — review 标准参考 .codemaker/rules/ 和 config.yaml 中的约定
