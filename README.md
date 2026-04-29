# note — 个人知识库

这是一个 [Obsidian](https://obsidian.md/) vault + LLM Wiki 模式实践的个人笔记仓库。

**LLM Wiki 模式**：和传统 RAG（每次查询都从原始文档检索）不同，这个仓库让 LLM **增量地构建并维护一个持久化 wiki**——结构化、互链的 markdown 文件集合，知识被一次编译、长期维护，而不是每次查询都重新推导。详见 [`Obsidian Vault/LLM wiki.md`](Obsidian%20Vault/LLM%20wiki.md)。

## 仓库结构

实际的 vault 在子目录 `Obsidian Vault/` 下（用 Obsidian 打开这个目录即可）。

| 顶级目录 | 用途 |
|---|---|
| `0-Inbox/` | 未分类临时投递 |
| `1-Sessions/` | 对话与外部文档原始沉淀（按 `YYYY/MM/`） |
| `2-Wiki/` | LLM 主导维护的结构化知识库（按学科领域） |
| `3-Projects/` | 进行中的个人项目 |
| `4-Journal/` | 个人复盘、年度总结、面试准备 |
| `5-Life/` | 兴趣爱好（桌游、金融、读物收藏等） |
| `6-Tools/` | 工具速查（"用到才查"，扁平结构） |
| `9-Meta/` | 仓库自身配置（`AGENTS.md` / `Skills/` / `Templates/` / `Scripts/` / `openspec/`） |
| `Assets/` `Excalidraw/` | Obsidian 插件管理的附件（不参与上面的编号体系） |

详见 [`Obsidian Vault/9-Meta/openspec/specs/vault-structure/`](Obsidian%20Vault/9-Meta/openspec/) 的权威 spec。

## 私有区

`Obsidian Vault/netease/` 是工作私有目录，已通过仓库根 `.gitignore` 排除，**不会** push 到公网仓库。

## 推荐入口

- **日常使用**：在 Obsidian 中打开 `Obsidian Vault/`，从 `Dashboard.md` 进入
- **了解架构**：先读 `Obsidian Vault/9-Meta/AGENTS.md`（agent 与人类共用的权威约定）
- **了解理念**：读 `Obsidian Vault/LLM wiki.md`（LLM Wiki 模式的设计动机）

## 工作流约定

仓库使用 [OpenSpec](https://github.com/Fission-AI/OpenSpec) 做 spec-driven development。所有结构性变更都通过 OpenSpec change 记录，活跃 change 见 `Obsidian Vault/9-Meta/openspec/changes/`。

任何 AI agent 操作此仓库前 **必须** 先读 `Obsidian Vault/9-Meta/AGENTS.md`。详细规则见该文件。

## License

[LICENSE](LICENSE)
