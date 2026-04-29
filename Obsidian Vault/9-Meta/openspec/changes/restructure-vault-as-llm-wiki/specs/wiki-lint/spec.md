## ADDED Requirements

### Requirement: Wiki Lint 检查项

The `lint-wiki` workflow SHALL inspect the wiki for the following health issues and produce a structured report:

1. **断链 (Broken wikilinks)**：wikilink 指向不存在的页面
2. **孤儿页面 (Orphans)**：除 `_MOC.md`、`_index.md`、`_log.md` 外，无任何反向链接的页面
3. **缺 frontmatter**：缺少必填字段 `tags`、`area`、`visibility`、`status` 的页面
4. **visibility 与位置不符**：公开区页面标 `private`、netease 区页面标 `public` (跨边界泄露风险)
5. **跨边界引用**：公开区页面 wikilink 到 netease 路径
6. **Index 漂移**：`_index.md` 漏登记的页面、登记了但已被删的页面
7. **重复主题**：两页讨论几乎相同的主题（agent 通过标题/内容启发式判断）
8. **过时声明 (Stale claims)**：旧 session 的结论被新 session 推翻但 wiki 未同步
9. **概念缺页**：被频繁裸文本提到但无独立页面的概念（≥3 处）
10. **超期未访问的活跃项目**：`3-Projects/` 中标 `status: active` 但 `updated` 已 >30 天

#### Scenario: 全量 lint
- **WHEN** 用户请求"巡检 wiki"
- **THEN** agent SHALL 按上述 10 项检查全量扫描，输出分类报告（每项问题列出受影响文件清单）

#### Scenario: 单项 lint
- **WHEN** 用户请求只检查某一项（如"找出所有断链"）
- **THEN** agent SHALL 只跑该项检查，不浪费 token 跑全项

---

### Requirement: Lint 报告格式

The lint report SHALL be structured markdown, organized by severity:

- **🔴 Critical**：visibility 不匹配、跨边界引用（安全相关）
- **🟡 Warning**：断链、缺必填 frontmatter、index 漂移
- **🟢 Suggestion**：孤儿、重复主题、概念缺页、过时声明、过期项目

每条问题包含：受影响文件路径、问题描述、建议的修复操作。

报告默认输出到对话中（不落地为文件），用户确认后 agent 才执行修复。可选地，重大 lint 后用户可以请求把报告归档到 `1-Sessions/YYYY/MM/YYYY-MM-DD-lint-report.md`。

#### Scenario: 报告优先级排序
- **WHEN** lint 完成
- **THEN** 报告按 Critical → Warning → Suggestion 顺序展示，让用户优先关注高风险项

#### Scenario: 用户确认修复
- **WHEN** 用户对报告中的某些项说"这些都修了吧"
- **THEN** agent SHALL 按确认范围执行修复，并在 `_log.md` 追加 `## [YYYY-MM-DD] lint-fix | ...`

---

### Requirement: Lint 频率与触发

`lint-wiki` MUST 至少每月执行一次（手动或定时），并且 SHALL 在以下场景立即触发针对性 lint：

- **大批量 ingest 后**：一次 ingest 涉及 ≥10 个文件改动后，自动触发 index/log 一致性检查
- **目录结构变更后**：迁移文件后必须 lint 断链和孤儿
- **archive 一次 OpenSpec change 前**：full lint，确保 change 描述的状态与实际一致

#### Scenario: 大批量 ingest 后
- **WHEN** ingest-session 单次操作影响 ≥10 个文件
- **THEN** 完成后 SHALL 自动调用 lint-wiki 的 index 一致性检查

#### Scenario: 月度巡检
- **WHEN** 距离上次 lint 已超过 30 天
- **THEN** Dashboard.md SHALL 提示"建议运行月度巡检"

---

### Requirement: Lint 不得擅自修改

Lint workflow SHALL be read-only at the analysis phase. Modifications happen only after explicit user confirmation:

- 默认行为：分析 → 报告 → 等待
- 即使是"明显的"修复（如补 frontmatter 默认值），也不得自动写入
- 唯一例外：`_log.md` 自身的追加（记录 lint 已执行）允许自动

#### Scenario: 发现明显问题
- **WHEN** lint 发现一个明显应该修复的问题（如缺 frontmatter）
- **THEN** SHALL 在报告中给出建议修复内容，但不立即写入；等用户确认
