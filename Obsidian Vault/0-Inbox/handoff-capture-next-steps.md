---
area: inbox
visibility: public
status: handoff
tags:
  - 工具/Obsidian
  - 交接
---
# Handoff · capture skill 后续 + wiki 待办

**Handoff from:** 2026-04-30 会话末
**Target audience:** 接手的 AI agent（读完这份就能独立推进）
**Previous commits landed:** `b959ff2`, `02eaddc`, `1e515cc` (push 已完成)

---

## 背景：本次会话做了什么

用户在 Obsidian vault（`$OBSIDIAN_VAULT = C:\Users\wangzhuowei\note\Obsidian Vault`）搭了一套 LLM Wiki 系统。本会话新建 `capture` skill 用于"低摩擦采集单条开发经验 / 踩坑 / 短 insight 到 wiki"。

关键文件：
- `9-Meta/Skills/capture/SKILL.md` — skill 本体（已过 3 轮 self-review 迭代，9 条 lessons 固化）
- `9-Meta/Skills/capture/references/` — `classification.md` / `link-maintenance.md`
- `9-Meta/AGENTS.md` §5.4 — 全局约定："`## 相关` 必须是文件最末节"
- `~/.codemaker/skills/obsidian-cli/SKILL.md` — Windows 路径 + 批处理 troubleshooting（通过 junction 与 vault 内同步）

环境：
- `OBSIDIAN_VAULT` 用户级环境变量已配置（值同上）
- junction `~\.codemaker\skills\capture` 由用户自维护机制同步，不需要手动重建
- Obsidian CLI（`Obsidian.com`）需在 PATH 中，或用 `%LOCALAPPDATA%\Programs\Obsidian\Obsidian.com` 全路径

红线（AGENTS.md §红线政策）：
- 公开区文件（`2-Wiki/` 等）不得 wikilink 到 `Netease/` 私有区
- `Netease/` 被 git `.gitignore` 过滤（父仓库 `C:\Users\wangzhuowei\note\.gitignore`），任何涉及私有区的内容不进 git

---

## 未完成任务（按优先级排）

### P0 · iteration-4：真机验证 capture skill 闭环

**目标：** 用一条真实的开发经验，完整跑一次 `capture` skill 的 draft → 用户确认 → `obsidian` CLI 落盘 → `unresolved` 验证 闭环。之前的 iteration 1/2/3 都停在 draft 层（不真正落文件），需要一次真机跑通来暴露 CLI 细节问题。

**建议场景：** 等用户下次自然说"记一下 XX"时就触发一次。不要为了测试而造假经验。

**预期暴露的问题：**
- `obsidian append` vs `obsidian eval` 的具体断点
- 真实的 wikilink 解析路径（Obsidian 是按文件名解析还是按 path）
- `property:set` / `property:remove` 对 yaml 多值字段的行为
- 中文文件名 + `silent` flag 下 Dataview 插件索引延迟（见 capture eval-2 推测）

**成功标准：**
- 一条经验从 draft 到落盘，全程只用 `obsidian-cli` 指令
- 落盘后 `obsidian unresolved total` 不增
- 目标页双向 wikilink 都生效
- `_log.md` 有对应条目

**参考：** 之前 3 轮 iteration 的 workspace 已删除；SKILL.md body 里的 "Step 2 checklist" 5 条是最终版的前置验证。

---

### P1 · 公开区 44/317 页 `## 相关` 位置历史债

**目标：** `2-Wiki/` 下有 44 页违反 AGENTS.md §5.4 "`## 相关` 必须是最末节"。这是历史债，capture iteration-3 引入约定时由用户决定"留给未来处理"。

**现状诊断命令（已验证可跑）：**

```powershell
Get-ChildItem -Recurse '2-Wiki' -Filter *.md | Where-Object { $_.Name -notmatch '^_' } | ForEach-Object {
  $h2s = Get-Content $_.FullName -Encoding UTF8 | Where-Object { $_ -match '^## ' }
  $last = $h2s | Select-Object -Last 1
  if ($h2s.Count -gt 0 -and $last -notmatch '^## (相关|Related|See also)') { $_.FullName }
}
```

输出给出 44 个违例文件的绝对路径。**私有区 `Netease/2-Wiki/梦幻西游客户端/` 已 20/20 合规**，不需要处理。

**建议做法：**
- 不要一次性批量改 44 页。先挑 5-10 页人工抽查，看模式：是"`## 相关` 后面跟了 `## 来源` / `## Changelog` 这种附加段"，还是"根本没有 `## 相关`"，还是其它。
- 按模式分组后再决定自动化策略。
- 所有改动都通过 `obsidian-cli`，不要用通用 `write`/`edit` 绕过 link 追踪。
- 每页处理完用 `obsidian unresolved total` 检查基线（当前 183，下降或持平即 OK，上升要回滚）。

**不要做：** 不要把"`## 相关` 后跟 `## 来源`"这种页暴力合并——有些页的 `## 来源` 确有独立语义，合到 `## 相关` 会丢信息。

**沉淀路径：** 如果推进这个任务，建议把它实现为一个独立的 `wiki-lint` skill check（lint-wiki 当前有 12 项 check，加第 13 项"Related-section-must-be-last"），而不是作为 one-off 脚本。

---

### P2 · dev-assist skill：proactive retrieval during coding

**目标：** 让 agent 在写代码时**主动**检索 wiki，不依赖用户显式 `query-wiki`。

**动机：** 本会话用户原话："开发的时候想把一些开发经验沉淀下来，然后后续开发可以让 ai 自动读取这部分知识，增加开发效率"。当前 `query-wiki` 只在用户问问题时触发；`capture` 只在用户说"记一下"时触发。这中间缺了"编码时 agent 自发查 wiki"的 skill。

**设计要点：**
- 触发条件：agent 开始编码/调试任务时，描述里包含某些关键词（文件路径、API 名、错误信息模式）
- 查询范围：基于当前 cwd 推断 domain —— 比如 cwd 在某 mhxy 仓库下就查 `Netease/2-Wiki/梦幻西游客户端/`；否则只查公开区
- 输出格式：不是长篇报告，而是"相关 wiki 页快照 + 一句话相关性"，塞进 agent 上下文前缀
- 避免陷阱：不能每次都全库搜（成本）；需要启发式收缩（按文件类型/路径选领域）

**前置依赖：**
- P0 完成后，capture 经验已足够，wiki 有真实可检索内容
- 建议先让 wiki 积累 ~20 条 real capture 再做 dev-assist，否则测不出来有没有用

**实现建议：** 走 `skill-creator` 流程，跟 capture 一样 draft → evals → iterate。

---

### P3 · TODO 清理：log 中提到但未做的小事

**从 `2-Wiki/_log.md` / `Netease/2-Wiki/_log.md` 梳理：**

1. **confirm_box 页 review 的 C-4/C-6/C-7**（handoff 时 marked ⏭️ 可选）：
   - C-4：症状/错误示例信息重叠，未合并
   - C-6：`[[Python编码规范]]` 作为相关项关联弱，可寻更强邻居
   - C-7：源码注释引用 `` # func(0)是 func(1)否 `` 的格式（inline code vs blockquote）

2. **`2-Wiki/_log.md` line 147-148 的状态描述已过时**：
   > "根级重复 `openspec/` 现仍含旧的 restructure-vault-as-llm-wiki/（未归档）和空 specs/，与 `9-Meta/openspec/` 状态完全分叉"

   这是 archive 时写的诊断，commit `9b53e29` 后已经不适用——openspec 只剩根级这一份。可以在 `_log.md` 末尾补一条"resolution"条目说明 divergence 已消除，不要改历史日志原文。

3. **`9-Meta/Skills/capture/evals/evals.json`** —— 压缩摘要里曾声称已写入，实际 capture/ 下没有 evals/ 目录。如果 P0 真机验证后需要回归测试，补一份 evals.json（skill-creator 规范格式）。

---

## 工作守则（继承自 AGENTS.md 与本次会话 lessons）

1. **所有 vault 文件操作走 `obsidian-cli`**，不用通用 `write`/`edit` —— 避免破坏 Obsidian 内部索引
2. **Windows 批量 CLI 调用写独立 `.ps1` 脚本** —— 不跨 shell 层拼 one-liner（cmd→powershell→CLI 反斜杠会被吃）
3. **`path=` 用正斜杠**，不要用 Windows `\`
4. **`## 相关` 必须是每页最末节**（AGENTS.md §5.4）
5. **Frontmatter 最短原则** —— 不加 `source_skill`/`created`/`updated`/`status: draft` 这些冗余字段，除非有明确理由
6. **不杜撰机制** —— 用户给了症状就记症状，别加"原理推测"伪装成事实；真想推测用 `> [!question] 待验证` callout
7. **停下问 > 擅自决定** —— 无匹配领域时给中性选项（不加 Recommended），让用户定
8. **跨 skill 改动要追漪** —— 比如 frontmatter policy 变了，要回溯存量页面；这次 capture iteration-3 的 C-1 就是这样发现的
9. **日志 append-only** —— `_log.md` 条目不重写历史；有错补一条新 resolution
10. **`_index.md` 同步** —— 新页要进 domain `_index.md`，这是用户浏览入口

---

## 一句话总结

capture skill 本身已经定版 + 上线，handoff 的核心是**让它真的被用起来**（P0 真机验证） + **把历史债和下一阶段规划清楚**（P1/P2/P3）。不需要继续改 capture 本体；改它的代价现在比收益高。
