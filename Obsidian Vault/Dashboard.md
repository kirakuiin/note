---
note_type: dashboard
area: meta
visibility: public
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
| [[LLM个人知识库模式]] | 本 vault 的 LLM Wiki 模式说明 |
| [[9-Meta/TAGS\|TAGS.md]] | tag 词表（打标签前查阅） |

---

## 知识入口

按学科领域分类的 7 个主题索引：

- [[2-Wiki/编程语言/_index|💻 编程语言]]
- [[2-Wiki/游戏开发/_index|🎮 游戏开发]]
- [[2-Wiki/算法与数据结构/_index|🧮 算法与数据结构]]
- [[2-Wiki/AI与Agent/_index|🤖 AI 与 Agent]]
- [[2-Wiki/英语/_index|🔤 英语]]
- [[2-Wiki/方法论/_index|🧭 方法论]]
- [[2-Wiki/计科基础/_index|🏗️ 计科基础]]

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
- [ ] **断链清零**：`obsidian unresolved` 应保持 ≤33（公开区基线，不含 netease 私有区内部断链和模板占位符）
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

> 本文件由 OpenSpec change `restructure-vault-as-llm-wiki` task 2.4 创建，task 5.5 更新（2026-04-30）；
> 旧的 `🧠 第二大脑.md` 已在 task 3.11 删除（功能已迁入此处）。
