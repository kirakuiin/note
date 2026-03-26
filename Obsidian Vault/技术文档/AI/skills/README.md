# AI Skills 集合

> 本目录存放 AI Agent 使用的 Skills，通过 junction 链接到 `C:\Users\wangzhuowei\.codemaker\skills` 供 CodeMaker 调用。

## Skills 一览

### 来自 [kepano/obsidian-skills](https://github.com/kepano/obsidian-skills)

| Skill                                         | 说明                                                                                               |
| --------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| **[defuddle](./defuddle/)**                   | 使用 Defuddle CLI 从网页中提取干净的 Markdown 内容，去除导航、广告等杂乱元素，节省 token 用量。适用于在线文档、文章、博客等网页内容提取。             |
| **[json-canvas](./json-canvas/)**             | 创建和编辑 JSON Canvas 文件（`.canvas`），支持节点、边、分组和连接。适用于在 Obsidian 中制作可视化画布、思维导图、流程图等。                   |
| **[obsidian-bases](./obsidian-bases/)**       | 创建和编辑 Obsidian Bases 文件（`.base`），支持视图、过滤器、公式和汇总。适用于构建笔记的数据库式视图，包含表格、卡片、列表和地图视图。                  |
| **[obsidian-cli](./obsidian-cli/)**           | 通过 Obsidian CLI 与 Obsidian Vault 交互，支持读取、创建、搜索和管理笔记、任务、属性等。同时支持插件和主题开发调试（重载插件、执行 JS、截图、DOM 检查等）。 |
| **[obsidian-markdown](./obsidian-markdown/)** | 创建和编辑 Obsidian 风格的 Markdown，支持 wikilinks、嵌入、callouts、properties 等 Obsidian 特有语法扩展。               |

### 自定义 Skills

| Skill                                         | 说明                                                                                                          |
| --------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| **[openspec-research](./openspec-research/)** | OpenSpec 工作流中的深度调研阶段。在设计前或设计中对不熟悉的代码库、机制或技术方案进行调研，生成结构化的调研文档（research.md）。触发词：`/opsx:research`、`调研`、`研究一下`。 |
| **[openspec-review](./openspec-review/)**     | OpenSpec 工作流中的多轮结构化代码审查。在所有任务实现后、归档前激活，聚焦代码整洁性、健壮性和安全性。触发词：`/opsx:review`、`code review`、`代码审查`。             |
| **[work-summary](./work-summary/)**           | 将 AI 交互内容总结为工作日报/周报/月报/年报，保存到 Obsidian 笔记目录。触发词：`总结`、`写日报`、`写周报`、`记录一下今天的工作` 等。                             |

## 安装方式

### 从 Git 安装 Obsidian Skills

```bash
npx skills add git@github.com:kepano/obsidian-skills.git --yes
```

## 目录结构

```
skills/
├── README.md              # 本文件
├── defuddle/              # ?? 网页内容提取 (Git: kepano/obsidian-skills)
├── json-canvas/           # ?? JSON Canvas 画布 (Git: kepano/obsidian-skills)
├── obsidian-bases/        # ?? Obsidian Bases 数据库视图 (Git: kepano/obsidian-skills)
├── obsidian-cli/          # ???? Obsidian CLI 命令行交互 (Git: kepano/obsidian-skills)
├── obsidian-markdown/     # ?? Obsidian Markdown 语法 (Git: kepano/obsidian-skills)
├── openspec-research/     # ?? OpenSpec 调研 (自定义)
├── openspec-review/       # ?? OpenSpec 代码审查 (自定义)
└── work-summary/          # ?? 工作总结生成 (自定义)
```
