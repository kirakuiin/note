---
area: meta
visibility: public
---
# Domain mapping — cwd → wiki 子目录加权表

dev-assist 的 ripgrep 侦测**始终全库搜**（公开区 + Netease）。
本文件仅用于 Phase 2 深查阶段的**相关性排序加权**：cwd 命中条目时，
对应 wiki 子目录的页面 +2 权重。

## 显式映射

| cwd 路径模式（正则，前缀风格） | 优先 wiki 子目录 | 备注 |
|---|---|---|
| `D:/workspace/.*/mhimage/` | `Netease/2-Wiki/梦幻西游客户端/` | mhxy 客户端主仓库（兜底） |

**匹配规则**：
- 路径用正斜杠（与 obsidian-cli `path=` 一致）
- 模式按**正则前缀**匹配 cwd —— 大部分项目用纯字面量（如
  `D:/workspace/foo/`），需要跨分支/变种时用 `.*`（如
  `D:/workspace/.*/mhimage/` 同时吃 `trunk/` `branch-xxx/` `feature-yy/`）
- **最长字面前缀优先**（更具体的映射先匹配；正则元字符 `.*` 不计入字面长度）
- 同一 cwd 只命中一行；命中后停止匹配
- 若你只想纯字面前缀匹配，直接写不带元字符的路径即可（无副作用）

## 兜底推断（无显式映射命中时）

agent 按以下信号顺序自推：

1. **当前打开文件路径**含 `Netease/` → 私有领域（视具体子目录二次加权）
2. **`git remote -v`** 输出含已知关键词：
   - `mhimage` / `mhxy` → `Netease/2-Wiki/梦幻西游客户端/`
3. **当前打开文件后缀 + 内容特征**：
   - `.py` 且 import 含游戏专有模块（如 `event`、`utils`, `pto`, `uisln`）→ mhxy
   - `.md` 在 vault 内 → 公开区 `2-Wiki/`
4. **以上都不命中** → 无加权，所有候选页平等参与排序

## 维护守则

- **append-only**：新项目落地时由用户加一行，不删历史行
  （历史项目的 wiki 内容仍可能被旧代码查询命中）
- **路径用正斜杠**：与 obsidian-cli 风格一致，跨平台无歧义
- **不要写过细路径**：只到能区分 wiki 子目录的层级即可——更深的细分由
  ripgrep 命中文件名自然完成
- **不维护"反向"信息**：本文件不写"wiki 页面对应哪些 cwd"——那种映射
  让 wiki 页面被 cwd 绑死，违反"知识独立于使用场景"原则
- **skill 主动提示**：dev-assist 在未匹配 cwd 触发时会输出建议，按其
  提示决定是否 append 一行

## append 一行的标准操作

用户同意添加新映射时：

```bash
obsidian append path=9-Meta/Skills/dev-assist/references/domain-mapping.md \
  content="| <cwd 模式> | <wiki 子目录> | <备注> |"
```

注意：表格 append 单行如果加在文件末尾会破坏表格结构（"## 兜底推断"在
表格之后）。实操要么把表格挪到文件末尾，要么用 `obsidian eval` 精确插入
表格末行。**建议第一次实战遇到时再决定方案**，不要预先优化。

## 调优记录

> [!note] L-0 (2026-05-06 · spec)
> 初版只列了 mhxy 一个项目 + vault 自身。后续接新项目时按格式追加。
