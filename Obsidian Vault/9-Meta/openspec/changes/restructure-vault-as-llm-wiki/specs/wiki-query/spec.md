## ADDED Requirements

### Requirement: 查询 Wiki 的标准流程

When a user issues a query that the agent should answer from the wiki, the agent SHALL follow this protocol:

1. **读 `_index.md`** 找候选页面（按 tag、领域、标题匹配）
2. **读 候选页面正文**（最多 5 页，按相关性排序）
3. **若信息不足**，扩展到 `1-Sessions/` 中按主题搜索相关 session
4. **综合回答**，所有引用的页面用 `[[页面名]]` 形式标注，让用户能追溯
5. **判断回答的沉淀价值**（见后续 Requirement）

#### Scenario: 简单查询有现成页面
- **WHEN** 用户问的问题正好对应 wiki 中某一页面
- **THEN** agent SHALL 读该页面内容直接回答，并在末尾注明 `详见 [[页面名]]`

#### Scenario: 查询需要综合多页
- **WHEN** 用户问题需要综合 ≥2 个 wiki 页面才能回答
- **THEN** agent SHALL 列出参考页面（`基于 [[页面1]]、[[页面2]]`），再给出综合回答

#### Scenario: 查询无答案
- **WHEN** wiki 中没有相关内容
- **THEN** agent SHALL 明确告知"wiki 中没有相关页面"，并询问是否要发起 ingest 流程把答案沉淀进 wiki

---

### Requirement: 高价值答案反哺为新 wiki 页面

After answering a query, the agent SHALL evaluate whether the answer itself has persistent value (e.g., a comparison table, a synthesis across multiple sources, a newly discovered connection). If yes, the agent SHALL ask the user whether to file the answer back as a new wiki page.

判断标准（满足任一即可）：
- 回答跨越 ≥2 个 wiki 页面做了**综合/对比**
- 回答揭示了一个原本没 wiki 页面的**新概念**
- 回答是用户特意询问的**清单/总结/索引**类内容

#### Scenario: 综合回答有沉淀价值
- **WHEN** agent 完成一次跨多页的综合回答
- **THEN** SHALL 在回答末尾询问"这个综合是否值得作为新 wiki 页面归档？"，征得用户同意后走 ingest-session 流程

#### Scenario: 简单事实型回答
- **WHEN** 回答只是从某一页面提取一段文字
- **THEN** 不需要反哺；wiki 中已有的内容不重复存储

---

### Requirement: 查询尊重公私边界

When the user asks a query, the agent SHALL determine the query's visibility scope and only access the appropriate side:

- **公开域查询**（如"我学过什么算法"）：只读 `2-Wiki/`、`1-Sessions/` 公开侧
- **工作域查询**（如"那个项目的踩坑记录"）：可同时读 `netease/2-Wiki/`、`netease/1-Sessions/`、公开侧
- **混合查询**：可读两侧；但回答**写入**时必须明确目标位置（默认写到与查询触发场景一致的一侧）

#### Scenario: 公开侧查询
- **WHEN** 用户在公开域上下文中提问，且未明确指向工作内容
- **THEN** agent SHALL 仅检索公开区，不读 netease 侧；这样输出可以安全公开

#### Scenario: 工作侧查询
- **WHEN** 用户在工作域上下文中提问（如"上周我处理了什么 bug"）
- **THEN** agent 可读 netease 侧；若回答涉及敏感信息，沉淀时 SHALL 写到 `netease/`

#### Scenario: 不确定边界
- **WHEN** 查询的归属区域不明确
- **THEN** agent SHALL 主动询问"这个问题的答案要存到公开区还是工作区？"，不要默默选择
