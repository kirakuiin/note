---
note_type: dashboard
area: meta
visibility: public
status: stable
created: 2026-04-29
updated: 2026-04-29
aliases:
  - Dashboard
  - 工作台
  - 我的笔记本
---

# Dashboard

> 这是我自己的**行动型工作台**。
> Agent 入口在 [[9-Meta/AGENTS|AGENTS.md]]；GitHub 访客请看仓库根 `README.md`。

---

## 快捷入口

| 入口 | 用途 |
|---|---|
| [[9-Meta/AGENTS\|AGENTS.md]] | Agent 操作约定（首次接触此 vault 必读） |
| [[2-Wiki/_index\|🗺️ 知识地图]] | 全部 wiki 领域索引 |
| [[0-Inbox/_index\|📥 收件箱]] | 未分类临时投递（请定期清理） |
| [[LLM wiki]] | 本 vault 的 LLM Wiki 模式说明 |
| [[9-Meta/TAGS\|TAGS.md]] | tag 词表（打标签前查阅） |

---

## 知识地图

按学科领域分类的 6 个主题 MOC（每个 MOC 是该领域的"知识地图入口"，从这里两跳可达任意 wiki 页）：

- [[2-Wiki/编程语言/_MOC|💻 编程语言]]
- [[2-Wiki/游戏开发/_MOC|🎮 游戏开发]]
- [[2-Wiki/算法与数据结构/_MOC|🧮 算法与数据结构]]
- [[2-Wiki/AI与Agent/_MOC|🤖 AI 与 Agent]]
- [[2-Wiki/游戏开发/3D数学/_MOC|🔤 英语]]
- [[2-Wiki/方法论/_MOC|🧭 方法论]]

> 新增领域请先开 OpenSpec change 修订 [[9-Meta/AGENTS|AGENTS.md]]，禁止直接加顶级目录。

---

## 最近 sessions

最近 5 次对话归档（来自 `1-Sessions/`）：

```dataview
TABLE WITHOUT ID file.link as Session, topic as 主题, date as 日期
FROM "1-Sessions"
WHERE file.name != "_index"
SORT date DESC, file.mtime DESC
LIMIT 5
```

→ 进入 [[1-Sessions/_index|Sessions 索引]]

---

## 活跃 projects

进行中的项目（`status: active`）：

```dataview
TABLE WITHOUT ID file.link as 项目, status as 状态, file.mtime as 最近更新
FROM "3-Projects"
WHERE status = "active"
SORT file.mtime DESC
```

→ 进入 [[3-Projects/_index|Projects 索引]]

---

## 维护提醒

固定的维护动作清单（不依赖 dataview，纯静态）：

- [ ] **月度 wiki lint 巡检**：跑 `lint-wiki` skill，处理 Critical/Warning 级问题（参见 [[9-Meta/Skills/lint-wiki/SKILL]]）
- [ ] **Tag 词表同步**：新 wiki 页面引入了未登记 tag 时，更新 [[9-Meta/TAGS|TAGS.md]]
- [ ] **断链清零**：`obsidian unresolved` 应保持基线值（迁移期可能有暂时升高，迁移完毕需归零）
- [ ] **OpenSpec change 归档**：完成的 change 及时跑 `/opsx:archive` 入历史
- [ ] **`0-Inbox/` 清理**：投递项分流到对应区（wiki / sessions / projects / tools）
- [ ] **Sessions 价值评估**：高价值 session 用 `ingest` skill 提炼成 wiki 页面

---

## 全局动态视图

### 最近修改的笔记

```dataview
TABLE WITHOUT ID file.link as 笔记, file.etags as 标签, file.mtime as 最近修改
WHERE !contains(file.folder, "Excalidraw") and !contains(file.folder, "Templates") and !contains(file.folder, "Assets")
SORT file.mtime DESC
LIMIT 8
```

### 被引用最多的笔记（高入度）

```dataview
TABLE WITHOUT ID file.link as 笔记, number(length(file.inlinks)) as 被引用次数
WHERE !contains(file.path, "Excalidraw") AND !contains(file.path, "Templates")
WHERE number(length(file.inlinks)) > 0
SORT number(length(file.inlinks)) DESC
LIMIT 8
```

### 引用其他笔记最多的（高出度）

```dataview
TABLE WITHOUT ID file.link as 笔记, number(length(file.outlinks)) as 引用次数
WHERE !contains(file.path, "Excalidraw") AND !contains(file.path, "Templates")
WHERE number(length(file.outlinks)) > 0
SORT number(length(file.outlinks)) DESC
LIMIT 8
```

---

## 当日操作（手动占位）

- 今日复盘 / 周报 / 月报 → 用 `work-summary` skill 触发，落地至 `4-Journal/<YYYY>/`
- 想清楚某事但还没成型 → 写到 `0-Inbox/` 或开 `/opsx:explore`
- 对话有沉淀价值 → 用 `ingest` skill 归档为 `1-Sessions/YYYY/MM/YYYY-MM-DD-<topic>.md`

---

> 本文件由 OpenSpec change `restructure-vault-as-llm-wiki` task 2.4 创建；
> 旧的 `🧠 第二大脑.md` 将在 task 3.11 删除（功能已迁入此处）。
