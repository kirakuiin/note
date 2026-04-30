## 1. 创建 0-Daily 骨架

- [x] 1.1 创建 `Netease/0-Daily/` 目录
- [x] 1.2 创建 `Netease/0-Daily/_index.md`，frontmatter 含 `area: journal`、`visibility: private`，正文说明 journal area 用途和文件命名规则

## 2. 迁移日报文件

- [x] 2.1 将 `Netease/daily/2026/` 下所有文件和子目录移动至 `Netease/0-Daily/2026/`（保持 `03/`、`04/` 子目录结构）
- [x] 2.2 删除 `Netease/daily/2026/03/_fix_daily.py`
- [x] 2.3 删除空的 `Netease/daily/` 目录

## 3. 修复 frontmatter

- [x] 3.1 批量修改 `Netease/0-Daily/2026/` 下所有 `.md` 文件的 frontmatter：`area: unknown` → `area: journal`

## 4. 更新 4-Reference 索引

- [x] 4.1 更新 `Netease/4-Reference/_index.md`，将"暂无条目"替换为三个镜像源的二次索引链接（指向 `arcolab_docs/INDEX.md`、`popo_card_docs/INDEX.md`、`popo_robot_docs/INDEX.md`）

## 5. 同步路径引用

- [x] 5.1 全局替换 `Netease/AGENTS.md` 中所有 `netease/` → `Netease/`（约 36 处）
- [x] 5.2 更新 `Netease/daily/工作报告总览.base`（迁移后路径变为 `Netease/0-Daily/工作报告总览.base`）：`file.inFolder("netease/daily")` → `file.inFolder("Netease/0-Daily")`
- [x] 5.3 确认公开区无 `netease/` 引用（红线检查）

## 6. 验证

- [x] 6.1 运行 `obsidian unresolved` 检查无断裂 wikilink
- [x] 6.2 确认 `Netease/0-Daily/` 下所有文件 frontmatter 的 `area` 为 `journal`
- [x] 6.3 确认 `Netease/AGENTS.md` 中无残留 `netease/`（小写）
- [x] 6.4 确认 `Netease/daily/` 目录已删除
- [x] 6.5 更新 `Netease/AGENTS.md` §10 状态速查：`0-Daily/` 标记为已就位，移除 `daily/` 引用
