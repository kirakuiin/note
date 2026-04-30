## Context

`Netease/` 私有区在 `restructure-vault-as-llm-wiki` change 中建立了数字前缀骨架（`1-Sessions/`、`2-Wiki/`、`3-Projects/`、`4-Reference/`），但 `0-Daily/` 未创建，历史日报仍在 `daily/` 下。同时目录名从 `netease` 改为 `Netease` 后，`AGENTS.md` 内约 36 处路径引用仍为小写。`4-Reference/_index.md` 内容过时（说"暂无条目"但实际有 3 个镜像源、150+ 篇文档）。

本次是纯结构调整 + 路径同步，不涉及内容变更。

## Goals / Non-Goals

**Goals:**
- 补齐 `0-Daily/` 目录，使私有区骨架与 AGENTS.md 规划一致
- 将 `daily/` 下所有日报/周报/月报迁移至 `0-Daily/`，保持 `YYYY/MM/` 子目录结构
- 修复迁移文件的 frontmatter（`area: unknown` → `area: journal`）
- 更新 `4-Reference/_index.md` 为二次索引
- 同步所有 `netease/` → `Netease/` 路径引用
- 更新 `.base` 文件的 folder 过滤路径

**Non-Goals:**
- 不修改日报/周报/月报的正文内容
- 不迁移 `Assets/` 目录
- 不修改 `4-Reference/` 下子目录命名（保持 snake_case）
- 不修改公开区任何文件
- 不修改 `.gitignore`

## Decisions

### 1. 迁移方式：移动文件而非复制

**决定**：使用文件移动（rename/move）将 `daily/2026/` → `0-Daily/2026/`。

**理由**：避免重复文件，保持 vault 内 wikilink 一致性。Obsidian 会自动更新 wikilink 引用。

**备选方案**：复制后删除原文件。效果相同但多一步。

### 2. `4-Reference/_index.md`：二次索引而非全文列表

**决定**：`_index.md` 只列出三个子目录及其 INDEX.md 的链接，不枚举具体文档。

**理由**：用户明确要求"顶部的 index 做二次索引即可"。每个子目录已有自己的 INDEX.md（如 `arcolab_docs/INDEX.md` 列出 37 篇文档），重复列出会造成维护负担。

### 3. 路径替换范围：仅 `Netease/` 内部

**决定**：`netease/` → `Netease/` 替换仅限 `Netease/` 目录内文件。

**理由**：公开区文件不应引用 `Netease/` 路径（红线规则），因此公开区不应存在需要替换的引用。如果发现公开区有引用，那是红线违规，需单独处理。

### 4. `.base` 文件路径更新

**决定**：`工作报告总览.base` 中 `file.inFolder("netease/daily")` 改为 `file.inFolder("Netease/0-Daily")`。

**理由**：Obsidian Bases 的 folder 过滤基于 vault 相对路径，目录重命名和迁移后必须同步更新，否则视图为空。

### 5. `_fix_daily.py` 直接删除

**决定**：删除 `daily/2026/03/_fix_daily.py`，不迁移。

**理由**：用户确认该脚本已不需要。

## Risks / Trade-offs

- **[低风险] wikilink 断裂**：日报文件之间存在 wikilink 引用（如月报引用各日报）。移动文件时 Obsidian 会自动更新 wikilink，但需验证。→ 迁移后运行 `obsidian unresolved` 检查。
- **[低风险] `.base` 视图暂时失效**：`.base` 文件更新前，基于旧路径的视图会显示空。→ 在迁移完成后立即更新 `.base` 文件。
- **[无风险] 公开区引用**：理论上公开区不应引用 `Netease/`，但需在替换前确认。→ 先 grep 公开区确认无 `netease/` 引用。
