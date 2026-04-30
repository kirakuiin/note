---
note_type: migration-notes
change: restructure-vault-as-llm-wiki
visibility: public
status: living
area: meta
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
| Git 仓库根 | `c:\Users\wangzhuowei\note\` ⚠️ **vault 是其子目录** | 2026-04-29 |
| Vault 在仓库内的相对路径 | `Obsidian Vault/` | 2026-04-29 |
| 仓库根 `.gitignore` 排除 netease | `Obsidian Vault/netease/` ✅ 已正确排除（task 1.8 实测） | 2026-04-29 |
| Vault 内 .md 总数 | 699 → 721（task 1.5/1.6/1.7 后） | 2026-04-29 |
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

### Git 操作位置陷阱 ⚠️

仓库根**不是** vault 根。所有 git 命令（`git tag` / `git status` / `git log` / 后续 task 3.x 的回滚锚点）必须在 `c:\Users\wangzhuowei\note\` 下执行，不能在 `c:\Users\wangzhuowei\note\Obsidian Vault\` 下：

```cmd
cd /d c:\Users\wangzhuowei\note
git status                    # 查看 vault 改动会以 "Obsidian Vault/..." 形式展示
git tag pre-phase-1           # ✅ 已在 task 1.12 完成，commit 77646db
git log --oneline -5
```

如果在 vault 根执行 `git status`，会报 "fatal: not a git repository"。design.md / tasks.md 中所有 "git tag" 类操作均默认在仓库根执行。

### 编码陷阱 ⚠️（task 1.10 实战发现，**继任 agent 必读**）

Windows 中文系统下，**写中文 markdown 时有三个连环陷阱**，本节是踩完所有坑后的总结。如果忽略这一节，你写的任何含中文的 .md 都会落盘成 GBK，被 Obsidian / OpenSpec / git diff 渲染为乱码。

#### 陷阱 1：Codemaker 的 `write` 工具按系统 ANSI（GBK）落盘

调用 `write` 工具创建 vault 内/外的 `.md` / `.py` / `.txt`，含中文时会以 **GB18030 编码**写入磁盘，**不是 UTF-8**。表现：

- `read_file` 看起来正常（IDE 自动按系统编码解码）
- 但 `[System.IO.File]::ReadAllBytes(path)` 出来的字节按 UTF-8 strict 解码会失败
- Obsidian app 打开渲染：取决于 app 的 fallback，通常显示乱码
- `git diff` 显示乱码

**症状识别**：
```powershell
# 一行命令判断一个文件是否纯 UTF-8
$b = [System.IO.File]::ReadAllBytes('path/to/file.md')
$strict = [System.Text.UTF8Encoding]::new($false, $true)
try { $null = $strict.GetString($b); 'UTF-8 OK' } catch { 'NOT UTF-8: ' + $_.Exception.Message }
```

**修复**：用 `9-Meta/Scripts/convert_encoding.py <path>`（in-place GB18030→UTF-8 无 BOM）。本仓库 task 1.10 已实战验证：12 个 OpenSpec .md 中 11 个被 `write` 工具写成 GBK，全部一键转换成功。

**最佳实践**：
- **不要** 用 `write` 工具创建含中文的 .md
- 在 vault 内写 .md，**必须** 走 `obsidian` CLI（`obsidian create`）—— Obsidian 强制 UTF-8 落盘
- 如果必须用 `write`（如临时 .py 脚本），**写完立刻** `python 9-Meta/Scripts/convert_encoding.py <path>`
- 这条同样适用于 OpenSpec 工作区的 .md（`9-Meta/openspec/changes/<change>/**.md`）

#### 陷阱 2：`obsidian create` / `obsidian append` 的 `content=` 参数不能传长字符串

obsidian-cli 在解析 `content=<value>` 时，对长 / 含特殊字符（`,` `"` `[` `]` 等）的字符串会**当 JSON 尝试解析**，触发：

```text
Uncaught Exception:
SyntaxError: Unexpected token ',', "...XXX..." is not valid JSON
  at JSON.parse (<anonymous>)
```

且会弹出 Obsidian 的 main process 错误对话框。**任何超过几十字节的中文/复杂内容都会撞这个**。

**症状识别**：
- 命令运行后 stdout 完全为空（PowerShell 抓不到任何输出）
- 目标文件未被创建 / 内容未追加
- Obsidian 弹出红色 "JavaScript error in main process" 对话框

**绕开方案**（按推荐度排序）：

1. **先 `obsidian create` 占位（content 为短英文如 `placeholder`），再用 PowerShell `[System.IO.File]::WriteAllBytes($dst, $sourceBytes)` byte-perfect 覆写**——这是 task 1.10 落地 9-Meta/AGENTS.md 的最终方案，零失链协议不受影响（前提：该 .md 没有 wikilink 引用它，否则不能这样做）
2. 用 `obsidian create` + `template=<name>`（让 Obsidian 渲染模板，避免 content 参数）—— 但需要先有模板文件
3. 极短内容（< 50 字节、无特殊字符）才能直接用 `content=`

**禁忌**：不要为了"绕开 JSON 陷阱"就用 `edit` / `mv` / `xcopy` 直接操作 vault 内 .md——这违反零失链协议。byte-copy 仅在"目标文件全新创建、无 wikilink 引用"时是合规替代。

#### 陷阱 3：PowerShell stdout 管道会做 ANSI 转码

`obsidian read path=... | Out-File -Encoding utf8` 这种链路，**输出文件会被 mojibake**：obsidian-cli 输出的 UTF-8 字节进入 PowerShell stdout 时被按系统 ANSI 解码、再按 UTF-8 编码写文件，导致中文全部变成 `鍏ュ彛` 这种 mojibake。

**症状识别**：
- 文件本身是有效 UTF-8（`strict.GetString` 不抛错）
- 但中文字符全部变 mojibake（如 "入口" → "鍏ュ彛"）

**绕开方案**：
- 验证 vault 内 .md 内容时**不要**用 `obsidian read | Out-File`，直接 `read_file` 工具或 `Get-Content -Encoding UTF8`
- 如必须用 PowerShell，先 `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8` 再 invoke

#### 速查表（继任 agent 收藏）

| 场景 | 推荐做法 | 禁忌 |
|---|---|---|
| 在 vault 内创建含中文 .md | `obsidian create path=... content=<短英文占位>` + PS WriteAllBytes 覆写 | 直接 `write` 工具 / 直接 `obsidian create content=<长中文>` |
| 在 vault 外创建含中文文件（如 temp 脚本） | `write` 工具创建后立刻 `python 9-Meta/Scripts/convert_encoding.py <path>` | 假设 `write` 给的是 UTF-8 |
| 修改 OpenSpec 工作区已有 .md（已经是 UTF-8） | `edit` 工具 | （安全） |
| 修改任何不确定编码的 .md | 先 `[System.IO.File]::ReadAllBytes` + UTF-8 strict 检查；GBK 就先转 | 边写边乱 |
| 验证 .md 内容 | `read_file` 工具 | `obsidian read \| Out-File` |

**本仓库现状（2026-04-29 task 1.10 收尾后）**：
- vault 内通过 `obsidian create` 创建的所有 .md：UTF-8 ✅
- `9-Meta/AGENTS.md`：UTF-8 ✅（byte-copy 落盘）
- `9-Meta/openspec/changes/restructure-vault-as-llm-wiki/**.md` 共 12 个：全部 UTF-8 ✅（task 1.10 收尾时一键转换）
- `9-Meta/Scripts/convert_encoding.py`：本节核心工具，长期保留

#### 补丁：`edit` 工具用于 vault 内已存在 .md 的纯文本小修（task 3.6 实战补充）

陷阱 1 强调"不要用 `write` 工具创建含中文 .md"，但**没说 `edit` 工具如何用**。task 3.6 实测：

- `edit` 工具修改**已经是 UTF-8 的 .md** 时，**保持 UTF-8 落盘** ✅（与 `write` 工具行为不同——`write` 是创建新文件、按系统 ANSI；`edit` 是替换字符串、保持原编码）
- 单次 `edit` 后立即用 `[System.IO.File]::ReadAllBytes` + UTF-8 strict 验证，task 3.6 验证 6-Tools/_index.md 通过
- 适用场景：修复 `obsidian append` 多次拆分留下的格式问题（标题重复、空行多余）等"纯正文小修，不涉及链接/移动/改名"
- 仍然**禁止**：用 `edit` 创建新 .md（应走 `obsidian create`）；用 `edit` 改动 wikilink 目标（应走 `obsidian rename` 让 alwaysUpdateLinks 接管）

**判定流程**：
1. 改动只涉及正文文本？→ 是 → 进入下一步；否（涉及链接/路径）→ 用 obsidian-cli
2. 目标 .md 已经是 UTF-8（用陷阱 1 速查命令验证）？→ 是 → `edit` 安全；否 → 先 `convert_encoding.py` 转 UTF-8 再 `edit`
3. `edit` 后立即重验 UTF-8 strict + `obsidian unresolved` 计数不增

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

## 4. Phase 0 侦察扫描结果（task 1.3 / 1.4 实测）

> 2026-04-29 由后续会话 agent 执行。扫描方式：obsidian CLI v1.12.7 全量列文件 +
> PowerShell 分组 + grep_search 二次校验 .base/.canvas 内部绑定。
> **数据口径**：vault 内 .md 总数 **701**（design 中记的 699 是 task 1.2 时点的快照，
> 之间 OpenSpec 工作区新增了 2 个文件 — agents-md.draft.md / migration-notes.md）。

### 4.1 task 1.3 — 同名 .md 冲突清单

按 basename 分组（含 `netease/`），共 **9 个 basename 命中 ≥2 项 = 30 个文件**。
分类如下：

#### A. 真冲突（迁移时会落到同一目标目录，必须 1.3 预处理 rename）

| basename | 源路径 1 | 源路径 2 | 处置预案 |
|---|---|---|---|
| 状态模式.md | 读书笔记/设计模式/状态模式.md | 读书笔记/游戏编程模式/状态模式.md | 都映射到 `2-Wiki/编程/设计模式/`，必须 rename |
| 单例模式.md | 读书笔记/设计模式/单例模式.md | 读书笔记/游戏编程模式/单例模式.md | 同上 |
| 原型模式.md | 读书笔记/设计模式/原型模式.md | 读书笔记/游戏编程模式/原型模式.md | 同上 |
| 命令模式.md | 读书笔记/设计模式/命令模式.md | 读书笔记/游戏编程模式/命令模式.md | 同上 |
| 享元模式.md | 读书笔记/设计模式/享元模式.md | 读书笔记/游戏编程模式/享元模式.md | 同上 |
| 观察者模式.md | 读书笔记/设计模式/观察者模式.md | 读书笔记/游戏编程模式/观察者模式.md | 同上 |

**预案**（task 3.1 实施）：用 `obsidian rename` 把 `读书笔记/游戏编程模式/<X>模式.md`
统一改为 `<X>模式（游戏编程模式）.md`，然后再走 `obsidian move`。理由：「设计模式」
来自 GoF 经典，是更稳定的命名权威；「游戏编程模式」是 Robert Nystrom 一书的二次诠释，
加后缀消歧不影响阅读。⚠️ rename 后 wikilink 短格式会自动改写为完整路径或保留——
依赖 `alwaysUpdateLinks=true` 保证零失链。

#### B. 伪冲突（同名但目标目录不同，无需处理）

| basename | 出现次数 | 说明 |
|---|---|---|
| `SKILL.md` | 9 | 每个 skill 一份，迁移目标各自不同（`9-Meta/Skills/<name>/SKILL.md`），不冲突 |
| `spec.md` | 7 | OpenSpec 自带规范，每 capability 独立目录，不冲突 |
| `README.md` | 2 | 一份在 `netease/work/搜达撤预研/client/`，一份在 `技术文档/AI/skills/`；前者随 netease 私有区不动，后者随 skills 整体迁移；无冲突 |

**结论**：真正需要 task 3.1 预处理 rename 的只有 6 个文件（Group A），全部位于
`读书笔记/游戏编程模式/`。

### 4.2 task 1.4 — 路径绑定清单

#### A. Dataview `FROM "<目录>"` 真实绑定（共 **6 处**，原 design D11 / R2 中说的"4 处"低估了 2 处）

| 文件 | 行 | 绑定路径 | 迁移后目标 |
|---|---|---|---|
| 读书笔记/设计模式/📚大纲（设计模式）.md | 43 | `FROM "读书笔记/设计模式"` | `FROM "2-Wiki/编程/设计模式"` |
| 读书笔记/重构/📚大纲（重构）.md | 304 | `FROM "读书笔记/重构"` | `FROM "2-Wiki/编程/重构"` |
| 读书笔记/重构/📚大纲（重构）.md | 332 | `FROM "读书笔记/重构"` | `FROM "2-Wiki/编程/重构"` |
| 技术文档/Unity/Unity知识点.md | 10 | `FROM "技术文档/Unity"` | `FROM "2-Wiki/游戏开发/Unity"`（具体路径以 task 3.4 决定为准） |
| 技术文档/Unity/Unity知识点.md | 97 | `FROM "技术文档/Unity"` | 同上 |
| 英语学习/语法/📚目录（英语语法）.md | 7 | `FROM "英语学习/语法"` | `FROM "2-Wiki/英语/语法"` |

**伪命中已剔除**：`工具用法/Dataview用法指南.md:154` 出现 `FROM "test"` 是教程示例，非真实查询。
其他大量 `from`（Python `from x import`、英语介词、SKILL.md 描述等）均非 Dataview 语法。

#### B. `.canvas` 文件清单（共 **5 个**，原 design 记的"1 个"严重低估）

| 文件 | 内部 file 节点 | 迁移影响评估 |
|---|---|---|
| 读书笔记/3D数学/总结.canvas | （无 file 节点） | 安全 |
| 读书笔记/游戏编程模式/📚大纲.canvas | 1 个，指向 `Excalidraw/游戏编程模式/游戏问题解决流程.md` | 资产目录不动，安全 |
| 技术文档/算法与数据结构/总结.canvas | （无 file 节点） | 安全 |
| 日常杂谈/我的GTD实践笔记.canvas | 1 个，指向 `Excalidraw/English grammer/...excalidraw.md` | 资产目录不动，安全 |
| 日常杂谈/项目总结/里程碑.canvas | （无 file 节点） | 安全 |

**结论**：5 个 canvas 全部走 `obsidian move` 迁移即可，内部 file 节点都指向 `Excalidraw/`
（按 D11 资产目录原位不动），无需手工修正。⚠️ 但 canvas 文件本身在新结构下的归属位置
需要 task 3.x 决定（如 `读书笔记/3D数学/总结.canvas` 应随 batch B 进 `2-Wiki/编程/3D数学/`）。

#### C. `.base` 文件清单（共 **3 个**，原 design 记的"无路径绑定"是误判）

| 文件 | 是否含路径绑定 | 绑定内容 | 迁移影响 |
|---|---|---|---|
| 日常杂谈/杂项/桌游记录.base | ✅ **有** | `file.inFolder("日常杂谈/杂项/桌游记录")` | 必须随 batch D 同步改 base 内的路径 |
| netease/daily/工作报告总览.base | ❌ 无路径绑定（仅过滤 frontmatter 字段） | — | netease 私有区本次 change 不动 |
| netease/work/弥勒山新门派/mls/弥勒山技能制作.base | ❌ 无路径绑定 | — | 同上 |

**修订 design D11 / Risks R2 的措辞**：
- "1 个 canvas" → "5 个 canvas"
- "4 处 Dataview FROM" → "6 处 Dataview FROM"
- "无 .base 文件依赖路径绑定" → "1 处 .base 路径绑定（`桌游记录.base` 的 `file.inFolder`）"

design.md 的 D11 / R2 文本会在下一次 design 修订（或 task 3.10 实施时）一并对齐；
本扫描结果以 migration-notes 为权威实测。

### 4.3 给 task 3.1 / 3.10 的可执行行动项

- **task 3.1**：对 §4.1 Group A 的 6 个文件执行 `obsidian rename path="读书笔记/游戏编程模式/<X>模式.md" name="<X>模式（游戏编程模式）.md"`
- **task 3.10** Dataview 修正：按 §4.2.A 的 6 行表格逐条手工 grep+替换 `FROM "<旧>"` → `FROM "<新>"`
- **task 3.10** Canvas 修正：5 个 canvas 全部走 `obsidian move`，迁完后人工开 Obsidian 抽查每个 canvas 是否仍能渲染
- **task 3.5 / 3.10** Base 修正：`日常杂谈/杂项/桌游记录.base` 在 batch D 迁移后需手工改 `file.inFolder` 路径（按 `obsidian-bases` skill 流程）；netease 区两个 .base 本次不动

---

## 5. 回滚锚点

| Tag | 时间 | 说明 |
|---|---|---|
| `pre-phase-1` | 2026-04-29 | Phase 0 完成、Phase 1 开始前 |
| `post-batch-A` | 2026-04-29 | Batch A（英语学习）迁移完成 — commit ff837b0；含 task 2.4 Dashboard.md + 3.1 6 个游戏编程模式 rename + 3.2 112 个英语语法 move + dataview FROM 修正；零失链 |
| `post-batch-B` | 2026-04-29 | Batch B（读书笔记）迁移完成 — 149 文件 5 子目录全部迁出；含 4 处 dataview FROM 修正（含 1 处 canvas 内）+ 2 个根读书笔记 rename（GTD 去全角冒号、软技能加分隔符）；零失链 |
| `post-batch-C-low` | 2026-04-29 | Batch C 低风险段（task 3.4 一半）— commit ac552ef + 7b35c87；C-pre 4 rename + C-low 55 文件 `技术文档/*` → `2-Wiki/<域>/<子>/`（含 `计科基础/` 第 7 领域新建 + `计算机.md` rename 为 `计科基础知识.md`）+ C-dataview Unity知识点.md 2 处 FROM 修正；零失链 |
| `post-batch-C` | 2026-04-29 | Batch C 完整完成（task 3.4 done）— commit 4a261f3；C-skills 12 个外部系统 skill 文件 `技术文档/AI/skills/*` → `9-Meta/Skills/*`（与本 vault 自有 skill 同处共存）+ README.md 内容并入 `_index.md` + `~/.codemaker/skills/<7个>` junctions 重建指向新路径；unresolved 49 → 36（共下降 13） |
| `post-batch-D` | 2026-04-29 | Batch D 完成（task 3.5 done）— commit 804ac1e；80 文件从 `日常杂谈/` 拆解到 4 目标：D-1 桌游 65 → `5-Life/桌游/` + `桌游记录.base` 修 `inFolder`；D-2 项目总结 5 → 新建 `3-Projects/项目总结/`；D-3 年度总结 3 → `4-Journal/<YYYY>/` + rename；D-4 网易面试 → `4-Journal/2024/2024-08_网易面试经验.md` + `#interview` tag；D-5/D-6 散件 6 → 各自归位。新增 6 个 _index.md 容器骨架 + TAGS.md 把 `#interview` 从待定转白名单。源 `日常杂谈/` 整目录物理删除。git 80 R + 6 A + 5 M, 0 D+A. unresolved 36 → 36（零失链）|
| `post-batch-E` | 2026-04-29 | Batch E 完成（task 3.6 done）— commit c236f9e；`工具用法/` 13 文件全部 `obsidian move` 一步 move+rename 到 `6-Tools/<类别>-<工具名>.md` 扁平结构（git 13 R 100% 识别 + 3 M）；`软件食谱/` 实测早已空（无需迁移）；`6-Tools/_index.md` 按 8 类分组登记 13 条 wikilink；unresolved 36 → 36（零失链）。源 `工具用法/` 空壳留待 task 3.12 统一清理。|
| `post-batch-F` | 2026-04-29 | Batch F 完成（task 3.7 done）— `开发项目/代号α/` 3 文件 `obsidian move` 到 `3-Projects/代号α/`（用户拍板去掉「个人-」前缀）；新建 `3-Projects/代号α/_index.md`（status: paused，tags: game-design/card-game）+ `3-Projects/_index.md` 追加入口；unresolved 36 → 36；源 `开发项目/` 空壳留待 task 3.12。**坑点记录**：`obsidian move` 不会自动创建目标父目录，需先 `obsidian create` 占位文件触发 mkdir；`property:set` 子命令名带冒号（不是 `property`），参数名是 `name=` 不是 `key=`。|
| `post-batch-G` | 2026-04-29 | Batch G 完成（task 3.8 done）— `Templates/` 3 文件（英语语法模板/设计模式模板/重构手法模板）`obsidian move` 到 `9-Meta/Templates/`，与 task 2.2 创建的 7 个通用模板共存（无文件名冲突）；同步改 `.obsidian/templates.json` 的 `folder` 字段并 `obsidian eval` 热重载；`9-Meta/Templates/_index.md` 拆「通用/领域专属」两节；unresolved 36 → 36；源 `Templates/` 空壳留 task 3.12。|
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


## 7. task 1.11 落地记录（2026-04-29）

### 侦察数据

- `obsidian tags sort=count counts` 全量扫描：100 个 tag
- `Tags/` 顶级目录不存在（接手包提到的旧 tag 索引实体目录实际未建立）
- 高频 tag 语义确认：`#reference`(200) = 几乎所有读书笔记/技术文档/工具用法文件的泛标记；`#language`(111) = 全部英语语法笔记

### 用户决策

- 命名风格：kebab-case（英文）+ 中文（领域 tag，与 `2-Wiki/` 子目录名一致）
- 白名单边界：精简最小有效集（20 个 tag：6 领域 + 5 类型 + 4 状态 + 4 来源 + 1 工具）
- 红线清单：保留，用于后续清理不合规 tag

### 落地工艺

1. `obsidian create path="9-Meta/TAGS.md" content="placeholder" silent` 占位
2. `write` 工具写临时文件到 `C:\Users\WANGZH~1\AppData\Local\Temp\\TAGS.md`（GBK）
3. `python 9-Meta/Scripts/convert_encoding.py C:\Users\WANGZH~1\AppData\Local\Temp\\TAGS.md` 转 UTF-8
4. PowerShell `[System.IO.File]::WriteAllBytes` byte-copy 覆写 vault 内占位文件
5. UTF-8 strict 验证通过
6. `obsidian unresolved` 验证：29 条断链（baseline 不变），零新增

### TAGS.md 结构

- §1 命名规则（kebab-case + 中文领域 tag + `/` 嵌套约定）
- §2 核心白名单（20 个 tag，按领域/类型/状态/来源/工具分组）
- §3 红线清单（4 类：项目代号 / 内部系统模块 / 内部流程工作 / 内部技术栈 + 嵌套前缀匹配规则）
- §4 历史脏 tag 清理表（35 条，含频次 + 目标值 + 说明）
- §5 新增 tag 流程
- §6 维护记录

### 待后续处理

- `#interview`(7) 和 `#OpenSpec`(8) 标记为"待定"，清理时需用户确认归属
- 脏 tag 批量替换不在 Phase 0 范围，留给 Phase 3 frontmatter 规范化阶段