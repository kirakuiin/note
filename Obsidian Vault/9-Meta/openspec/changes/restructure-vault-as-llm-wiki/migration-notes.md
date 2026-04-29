---
note_type: migration-notes
change: restructure-vault-as-llm-wiki
visibility: public
status: living
---

# Migration Notes — restructure-vault-as-llm-wiki

> 本文件记录迁移过程中的**实测事实**（命令签名、环境状态、扫描结果），
> 给后续接手的 agent / 未来的自己**减少猜测**。
> 与 spec/design/tasks 不同——spec 写"应该怎么做"，这里写"实地是什么样"。

---

## 1. 环境实测（task 1.1 + 1.2 验收依据）

| 项 | 值 | 验证时间 |
|---|---|---|
| Obsidian app | 1.12.7 (installer 1.12.7) | 2026-04-29 |
| `obsidian` CLI 路径 | `C:\Users\wangzhuowei\AppData\Local\Programs\Obsidian\Obsidian.com` | 2026-04-29 |
| Vault 名 | `Obsidian Vault` | 2026-04-29 |
| Vault 内 .md 总数 | 699 | 2026-04-29 |
| `alwaysUpdateLinks` | `true` ✅ 零失链关键 | 2026-04-29 |
| `newLinkFormat` | (未设置 = 默认 `shortest`) | 2026-04-29 |
| `useMarkdownLinks` | (未设置 = 默认 false，即 wikilink) | 2026-04-29 |

### Windows PATH 陷阱

启用 CLI 后 Obsidian 把可执行路径写入 user PATH。**已经打开的 cmd/PowerShell 窗口不会读到新 PATH**——必须新开终端，或用全路径调用：

```cmd
"C:\Users\wangzhuowei\AppData\Local\Programs\Obsidian\Obsidian.com" version
```

或在 PowerShell 里强刷 PATH：

```powershell
$env:Path = [System.Environment]::GetEnvironmentVariable('Path','User') + ';' + [System.Environment]::GetEnvironmentVariable('Path','Machine')
```

后续会话开始时**第一件事**应该是：

```cmd
obsidian version
```

如果命令找不到，按上面任一方法解决。

---

## 2. obsidian CLI 实测命令签名速查

> 完整命令列表见 `obsidian help`。以下是迁移阶段会高频使用的命令，**已实测真实签名**（2026-04-29 from CLI v1.12.7）。

### 文件 CRUD

```bash
# 创建（name 仅文件名，会落到 vault 根；path 是完整相对路径；可用 template）
obsidian create path="2-Wiki/技术/Python/装饰器.md" content="# 装饰器\n\n..."
obsidian create path="2-Wiki/英语/语法/_index.md" template="index"

# 读取
obsidian read path="0-我的笔记本.md"
obsidian read file="装饰器"            # 按 wikilink 名称匹配

# 追加 / 前置
obsidian append path="2-Wiki/_log.md" content="\n## [2026-04-29] migration | batch-A done"
obsidian prepend path="..." content="..."

# 移动 / 改名（★ 自动更新所有引用，因为 alwaysUpdateLinks=true）
obsidian move path="英语学习/语法/被动语态.md" to="2-Wiki/英语/语法/被动语态.md"
obsidian move path="英语学习/语法/被动语态.md" to="2-Wiki/英语/语法/"   # 目标是目录，文件名不变
obsidian rename path="读书笔记/设计模式/状态模式.md" name="状态模式（设计模式）.md"

# 删除（默认进 trash，加 permanent 直接删）
obsidian delete path="0-我的笔记本.md"
obsidian delete file="0-我的笔记本" permanent
```

### 链接 / 健康巡检（替代很多自写脚本）

```bash
# 未解析链接（断链）—— Phase 2 每批 verify 必跑
obsidian unresolved verbose format=json

# 孤儿（没有入链的文件）
obsidian orphans

# 死端（没有出链的文件）
obsidian deadends

# 某文件的反向链接
obsidian backlinks file="装饰器" counts

# 某文件的出链
obsidian links path="..."
```

### Frontmatter / Property

```bash
obsidian property:set name="visibility" value="public" path="..."
obsidian property:set name="tags" value="编程,Python" type=list path="..."
obsidian property:read name="area" path="..."
obsidian property:remove name="obsolete-key" path="..."
obsidian properties path="..." format=yaml    # 列文件所有 properties
```

### 搜索 / 列表

```bash
obsidian search query="alwaysUpdateLinks" path="技术文档" format=json
obsidian search:context query="FROM \"读书笔记\""    # 带上下文，比 grep 更精准
obsidian files folder="读书笔记" ext="md" total
obsidian folders folder="读书笔记"
```

### Tag

```bash
obsidian tags counts sort=count format=json     # 全 vault tag 词频
obsidian tag name="编程" verbose                # 某 tag 在哪些文件
```

### 元信息

```bash
obsidian vault info=name
obsidian vault info=files
obsidian eval code="app.vault.config.alwaysUpdateLinks"
obsidian outline path="..." format=json
```

---

## 3. 中文路径与转义

- Windows cmd / PowerShell：路径内含空格用 `path="..."`，含中文不需要特殊处理（Obsidian CLI 内部用 UTF-8）
- 但 cmd 输出窗口受 chcp 影响可能乱码——**只影响显示，不影响命令本身的执行结果**
- 写脚本时优先用 PowerShell `& $obs ...` 调用，比 cmd 更稳

---

## 4. 待 Phase 0 后续 task 填充的扫描结果

### task 1.3 — 同名 .md 冲突清单

```
TODO（执行 1.3 后填入）：
- 用 `obsidian files folder="" ext=md format=json` 拉全清单，按 basename 分组找 ≥2 项
- 已知热点：读书笔记/设计模式/{状态/单例/原型/命令/享元}模式.md vs 读书笔记/游戏编程模式/同名
```

### task 1.4 — 路径绑定清单

```
Dataview FROM "..." 路径绑定：
TODO（执行 1.4 后填入完整路径），已知有 4 处：
- 读书笔记/设计模式/📚大纲（设计模式）.md
- 读书笔记/重构/📚大纲（重构）.md   （×2）
- 技术文档/Unity/Unity知识点.md      （×2）
- 英语学习/语法/📚目录（英语语法）.md

Canvas 文件（手工 verify 内部节点）：
- 日常杂谈/我的GTD实践笔记.canvas

.base 文件（已 grep 验证：无路径绑定）
```

---

## 5. 回滚锚点

| Tag | 时间 | 说明 |
|---|---|---|
| `pre-phase-1` | 2026-04-29 | Phase 0 完成、Phase 1 开始前 |
| `post-batch-A` | TBD | Batch A（英语学习）迁移完成 |
| `post-batch-B` | TBD | Batch B（读书笔记）迁移完成 |
| ... | ... | 每批一个 tag |

---

## 6. 给下一个接手的 agent 的话

1. **先读** `9-Meta/openspec/changes/restructure-vault-as-llm-wiki/proposal.md` + `design.md` 理解意图
2. **再读** `specs/agent-schema/spec.md` 理解强制 skill 路由表（哪些操作必须用哪个 skill）
3. **接着读本文件** 拿到所有实测命令签名，不要凭记忆猜
4. **`openspec list`** 看活跃 change，**`openspec change show ...`** 看详情
5. **`use_skill openspec-apply-change`** 启动 task 推进
6. **任何对 vault .md/.canvas/.base 的改动**都通过 `obsidian` CLI，绝不用 `mv`/`edit_file`/`xcopy`

如果某条命令没在本文件出现，**先 `obsidian help <command>` 查一下真实签名再用**，不要凭官方文档猜。
