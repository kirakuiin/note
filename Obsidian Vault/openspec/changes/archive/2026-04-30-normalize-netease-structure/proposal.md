## Why

`Netease/` 私有区在之前的 `restructure-vault-as-llm-wiki` change 中建立了骨架（`1-Sessions/`、`2-Wiki/`、`3-Projects/`、`4-Reference/`），但历史 `daily/` 目录未归档，且目录名从 `netease` 改为 `Netease` 后内部大量路径引用未同步。现在无效数据已清理完毕，是正规化的最佳时机。

## What Changes

- 创建 `0-Daily/` 目录及 `_index.md`，补齐 AGENTS.md 规划的 journal area
- 将 `daily/2026/` 下所有日报/周报/月报迁移至 `0-Daily/2026/`，保持原有子目录结构
- 批量修复迁移后文件的 frontmatter：`area: unknown` → `area: journal`
- 删除 `daily/` 目录及 `_fix_daily.py` 脚本
- 更新 `4-Reference/_index.md`：从"暂无条目"改为二次索引，指向三个子目录的 INDEX.md
- 更新 `daily/工作报告总览.base`：`file.inFolder` 路径从 `netease/daily` 改为 `Netease/0-Daily`
- 全局替换 `Netease/AGENTS.md` 中所有 `netease/` → `Netease/`（约 36 处）

## Capabilities

### New Capabilities

- `netease-journal`: `0-Daily/` 目录作为私有区工作日报/周报/月报的 journal area，按 `YYYY/MM/` 子目录组织，文件命名 `YYYY-MM-DD_日报.md`

### Modified Capabilities

（无——本次不修改已有 spec 的需求，仅做结构调整和路径同步）

## Impact

- 受影响文件：`Netease/AGENTS.md`（路径引用更新）、`Netease/4-Reference/_index.md`（内容更新）、`Netease/daily/工作报告总览.base`（路径更新）
- 受影响目录：`Netease/daily/`（删除）、`Netease/0-Daily/`（新建）
- 迁移文件数：28 个（24 日报 + 3 周报 + 1 月报），frontmatter 批量修复
- 无公开区影响，无 API 变更，无依赖变更
