# Tag 管理与 Frontmatter 管理的关系

## 它们的分工

**Tag 管理**（[[9-Meta/TAGS.md]]）定义"用什么 tag"——是 tag 的**词表**：
- 白名单：20 个合法 tag（6 领域 + 5 类型 + 4 状态 + 4 来源 + 1 工具）
- 红线清单：netease 私有区专属 tag
- 脏 tag 清理表：35 条历史 tag 的替换映射
- 规则：顶层必须来自白名单，嵌套自由组合

**Frontmatter 管理**（[[9-Meta/openspec/changes/restructure-vault-as-llm-wiki/specs/note-frontmatter/spec.md]]）定义"文件里写什么字段"——是文件的**元数据 schema**：
- 通用必填：`area`、`visibility`
- 区域专属：knowledge 需 `tags` + `status`，session 需 `tags` + `date` + `topic`
- `tags` 字段的值必须来自 TAGS.md 词表

## 关系

```
TAGS.md（词表）          note-frontmatter spec（schema）
     │                           │
     │  定义合法 tag 值           │  定义 tags 字段必须存在
     │                           │
     └───────────┬───────────────┘
                 │
                 ▼
        文件的 frontmatter tags 字段
        （值来自 TAGS.md，字段要求来自 spec）
```

TAGS.md 是"字典"，frontmatter spec 是"语法"。字典告诉你哪些词合法，语法告诉你句子必须包含哪些成分。

**参考页面**:
- [[9-Meta/TAGS.md]] — tag 词表（白名单 + 红线 + 清理表）
- [[9-Meta/openspec/changes/restructure-vault-as-llm-wiki/specs/note-frontmatter/spec.md]] — frontmatter schema 规范

---
这个回答综合了两个独立的设计文档，值得作为新 wiki 页面归档。要我走 ingest 流程存下来吗？
