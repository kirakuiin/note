# Trigger keywords — Token 提取规则

dev-assist 的 ripgrep 侦测**不维护固定关键词清单**，而是从当前任务描述、
cwd、打开文件中按以下规则即席提取 token。这样 wiki 增长时不需要更新本文件。

## 提取规则（按强度）

### 1. 代码标识符（最强信号）

从任务描述、当前文件名、cwd 中提取：

- **snake_case 函数/变量名**：`confirm_box`、`time_utils`、`set_scale`、
  `get_ins`、`Tick`
  - 正则：`[a-z_][a-z0-9_]{2,}`（限制最短 3 字符避免 `id`、`fn` 等噪声）
- **CamelCase 类名/组件名**：`CPanel`、`UIStateGroupComponent`、`Handle`、
  `Single`
  - 正则：`[A-Z][a-zA-Z0-9]{2,}`
- **文件名（去扩展名）**：`xxx.py` → `xxx`、`some_panel.lua` → `some_panel`
- **API 路径段**：路径含 `mhimage/docs/<module>/...` 时，取 `<module>` 名

**为什么强**：wiki 页面标题里大量包含 API 名 / 类名 / 模块名，这类 token
直接 ripgrep 命中率最高（如 `confirm_box回调语义反直觉`、
`CPanel_set_scale单位是千分之一`）。

### 2. 错误现象短语（强信号）

从任务描述里出现以下"问题描述触发词"附近的名词短语提取：

- 触发词：`为什么`、`怎么`、`不`、`没`、`异常`、`报错`、`卡`、`挂`、`不工作`、
  `失败`、`出不来`、`不对`、`反了`
- 提取相邻 2-4 字的名词短语

例：
- "回调没触发" → `回调`
- "Z 序乱了" → `Z序`、`Z 序`
- "状态机卡住" → `状态机`
- "单位不对" → `单位`

**为什么强**：踩坑集页面命名几乎都是"<现象> 反直觉/坑"模式，与现象短语高度重合。

### 3. 领域术语（中信号）

从任务描述识别如下术语，按出现即提取：

- UI 控件类：`控件`、`面板`、`按钮`、`label`、`button`、`panel`、`prefab`
- 状态机类：`状态机`、`状态`、`status`、`StateGroup`
- 协议类：`协议`、`S_`、`C_`、`route`、`路由`
- 渲染类：`Z序`、`层级`、`坐标`、`缩放`、`scale`
- 时间类：`帧`、`tick`、`时间`、`定时`

**为什么中**：领域术语会带来一些非精确命中，但能补充强信号漏掉的页面。

### 4. 通用编程词（弱信号 / 噪声 — **不要 grep**）

以下词**不应**作为 probe token：

- 中文通用：`函数`、`类`、`变量`、`模块`、`方法`、`代码`、`项目`
- 英文关键字：`function`、`class`、`var`、`module`、`method`、`return`、
  `if`、`for`、`while`、`true`、`false`
- 调试通用：`bug`、`fix`、`error`、`debug`
- **短英文标识符（**实战印证 2026-05-06**）**：单独提取的 `Single` /
  `Handle` / `Panel` 这种**短** CamelCase 会命中大量公开区无关页面
  （`单例模式`、`状态模式`、`Effective CSharp` 等）。这类词只有在与
  其它 token 共现于同一描述时才作为强信号；单独出现时降级为弱信号。

它们会全库命中，让相关性排序失去意义。

## 决策流程（Phase 1 probe）

按以下步骤进行——这是描述性的，不要按字面去找一个名为 `extract()` 的函数：

1. **收集输入**：当前任务描述、cwd 路径字符串、当前打开文件列表
2. **逐规则提取**：按规则 1 → 2 → 3 顺序，从输入中提取候选 token
3. **去重 + 过滤黑名单**：去重所有 token，移除规则 4 列出的噪声词
4. **截断到 8 个**：若候选 token >8，按"规则强度 + 在描述中越早出现越优先"
   排序，保留前 8（与 SKILL.md `Cap at 8 tokens` 约定一致）
5. **空集即跳过**：若过滤后无 token，输出"已跳过（无可用 token）"并停止
6. **构造 ripgrep 命令**：`rg -i -l --type md --no-ignore-vcs -e <token1> -e <token2> ... <wiki roots>`
7. **判断结果**：
   - 0 命中 → 输出"已跳过（probe miss）"并停止
   - ≥1 命中 → 进入 SKILL.md Phase 2 深查

## ripgrep 调用细节

- `--no-ignore-vcs`：必加。`Netease/` 在 `.gitignore`，不加它 ripgrep 不会扫
- `-i`：忽略大小写。中文不受影响，英文标识符匹配更鲁棒
- `-l`：只输出文件名，不输出匹配上下文（Phase 1 不需要内容）
- `--type md`：只搜 .md 文件（避免误匹配代码片段中的同名词）
- 多个 `-e`：ripgrep 把多个 `-e` 当 OR 处理，单次调用搞定

## 调优记录

随着 dev-assist 实战使用，这里追加 lessons（capture skill 同款格式）。

> [!note] L-0 (2026-05-06 · spec)
> 本文件诞生时未有实战数据，所有规则基于 21 页私有 wiki + 公开区索引推断。
> 第一次 evals 后回填真实命中率，不命中的规则要么删要么改。

> [!note] L-1 (2026-05-06 · self-review 实测)
> 用 `confirm_box`、`状态机`、`Single` 三 token 跑 ripgrep（314 页 wiki），
> 发现 `Single` 单独命中 15+ 公开区无关页（`单例模式`、`Effective CSharp` 等）。
> 印证规则 4 黑名单需要扩展短英文 CamelCase。**若被命中文件中超过 50%
> 来自单一 token 且该 token 是短英文词（≤6 字符），考虑该 token 是噪声，
> 在 Phase 2 排序时降权。**
