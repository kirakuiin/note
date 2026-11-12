# 五项改动：入口规则自动更新、无人值守、处理报告、SVN 更新脚本、复用目录自动清理

日期：2026-11-10　版本：0.3.32

2026-11-10 与用户逐项确认的设计。本文件是实现依据，也是原交接文件（已删除）的留档。按顺序实现，第 1 项单独做完并验证后再做其余。

## 共同约束：不影响旧功能

- 基线：2026-11-10 全量测试 383 通过（命令见 SKILL.md「维护本 skill」）。每项做完再跑；不允许已有测试失败，也不删改旧测试来通过；确实要改已有测试时先向用户说明。
- 每项新功能都加测试。涉及 SVN 的测试用临时仓库（`svn import` 建库、通过 Python 提交）。
- 旧的调用方式和输出字段保持不变；新增能力默认保守。
- 不向真实 SVN 分支提交，不对真实工单做写操作。`D:\workspace` 下已初始化的真实工作区可以直接用来实验（2026-11-10 用户确认）；自动化测试照旧只用临时目录和临时仓库。
- 不读取、不打印 `~/.mhxy-workspace/config.json` 里的密码。skill 目录在 git 仓库里每小时自动备份，不自己提交。

## 1. 入口规则：context 自动更新工作区副本

**问题**：每个工作区的 `AGENTS.md` 有一份受管区段副本，改规则要逐个工作区 sync，出现过落后多版没人发现。

**否决的方案（指针模式）**：让 `CLAUDE.md` 用 `@` 引入用户目录下的一份本机版规则。2026-11-10 验证不可行：
- Claude Code 对项目级 `CLAUDE.md` 引入工作目录以外的文件要求逐项目批准（官方文档 memory「Import additional files」）。
- 2.1.139 的加载逻辑：项目级文件的外部引入只在 `~/.claude.json` 该项目的 `hasClaudeMdExternalIncludesApproved` 为真时加载，否则静默跳过；确认框只在交互式终端启动时出现。无头模式（`claude -p`）和未批准的工作区会整份丢失规则且没有提示。本机所有工作区该标记都是 false，也没有预先批准的设置项。

**采用的方案**：结构不变（`AGENTS.md` 放完整规则，`CLAUDE.md` 用 `@AGENTS.md` 引入，工作区内引入不需要批准），由 `context` 发现副本落后时自动重写。

- **触发条件**（全部满足）：`AGENTS.md` 已有本 skill 的受管区段（不是旧名 `mhxy-workspace-init`）；区段的 `schema_version` 等于当前模板；`applied_version` 低于 skill 的 `config/version.json`。版本相同但内容不同（安装路径变化、手工改过）不自动更新，仍由 `sync` 处理；区段版本更高时不动（不降级）。
- **更新范围**：只重写 `AGENTS.md` 和 `CLAUDE.md` 的受管区段（与 sync 同一段渲染逻辑，保留区段外内容、编码和换行），写入后同 sync 一样把受版本控制的入口文件放进 `ignore-on-commit`。不动配置、hooks。`CLAUDE.md` 没有受管区段或版本更高时只更新 `AGENTS.md`。
- **输出**：发生更新时 context 多一个字段 `entry_rules_updated`：`{"from", "to", "files", "rules_changed", "notice"}`。`rules_changed` 与 sync 的 `entry_rules_changed` 同一算法（去掉管理元数据后比较）；为 true 时 `notice` 提示本会话可能已加载旧规则，要重新读取 `AGENTS.md` 受管区段并向用户说明变化。没有更新时不出现该字段，其余字段不变。
- **失败不阻断**：只读文件、编码损坏、并发修改等记入 `problems`，context 其余部分照常返回。
- **关闭方式**：`context --no-entry-update` 本次不更新。回退到旧行为就是每次带这个开关，或继续用 `sync`。
- **sync 不变**：`entry_rules_changed` 的含义不变（本次 sync 是否改变了 `AGENTS.md` 的规则内容）；因为 context 通常已先更新，升级后再 sync 一般为 false。
- **守住**：入口模板里提到细则文档只写普通路径，不出现 `@路径`（`CLAUDE.md` 的 `@AGENTS.md` 会递归引入，最多四层）。测试守住这条。上下文大小与现在相同。
- **未证实**：Claude Code 是在 SessionStart hook 之前还是之后读取 `CLAUDE.md`，没有实测；按“可能已加载旧内容”处理，靠 `notice` 兜住。

## 2. 无人值守模式

- 新增 `references/unattended.md`，入口规则「按需读取」表加一行；平时不读。
- 进入方式：提示词明确写“按无人值守模式处理工单 xxx”。不靠环境变量或自动检测。
- 行为：
  1. 不向用户提问，不出方案流程图。
  2. 只处理 A 类单，分拣标准写在该文档：
     - A 自动处理：bug 修复（非合并、非新功能）；描述清楚且能定位到代码；属于“小改动”；只改客户端脚本，不需要策划配置、美术资源或服务端配合；没有需要用户取舍的问题。
     - B 问用户：合并类工单，无人值守会话不发起合并；用户同意后由用户或调用方另起会话，按本 skill 的 `references/svn-merge.md` 合并（0.3.35 起不用独立的 svn-merge 技能；0.3.38 起统一为合完停在 merged、由用户批准提交）。
     - C 只列出：其余，写明原因。拿不准一律归 C。
  3. 需要决策、改动超出小改动、定位不到、自检不过时立即停下，不猜。
  4. 做完提交前自检后停下，不提交，拟好提交说明和文件清单。
  5. 跳过上下文检查、会话交接、整理记忆。
- 结果交付：结束前调用脚本写出固定格式的结果文件，字段至少有状态（待提交／需要你处理／放弃）、原因、改动文件、提交说明、自检结果、报告路径；脚本校验字段齐全。

## 3. 处理报告

- 新增报告脚本，按固定模板生成独立文件夹 `.mhxy-workspace/reports/<工单号>/`：`index.html` 加媒体文件，拷到哪里都能打开。
- 内容从上到下：工单（号、标题、分支、时间、状态）、问题定位、处理方案、改动（文件清单和 diff，diff 默认折叠）、自检结果、截图和录屏（嵌入、视频可播放）、提交说明（提交后可补版本号）。
- 会话只提供“问题定位”和“处理方案”两段文字；工单信息、diff、用例执行器的 JSON 报告、截图录屏、提交说明由脚本收集。会话不读 diff、截图和生成的 HTML。
- 只要求修复后的证据；工单自带的问题截图放进“问题定位”。
- 不限于无人值守，平时说“生成处理报告”也能用。页面要清晰美观。

## 4. SVN 更新脚本

- 新增 `scripts/svn_update.py`，固化 `references/svn-update.md` 的规则：识别周期分支、算目标周、确认远端分支、切换或更新、核对结果，含 `../_test`。输出 JSON。
- **默认行为**（2026-11-10 用户确认，取代原定的“只报告并停下”）：先更新或切换，遇到挡路的内容自动处理，不问用户：先把本地修改备份成 patch 到 `.mhxy-workspace/backups/<时间>/`（保留最近 5 次）；更新产生冲突的文件采用服务器版本；挡住新增文件的未纳管文件挪进备份目录；工作副本被锁时 cleanup。不冲突的本地修改保留。结果里列出处理了哪些文件和备份路径，会话向用户汇报。
- 开关 `--clean-blockers`（给维护流程用）：备份后把全部本地修改 revert，再更新或切换；其余同默认。其余未纳管文件（入口文件、`.mhxy-workspace/` 等）两种方式都不动。
- 输出列出前后分支、版本号、处理的文件、备份路径。
- 同步更新 `svn-update.md` 和入口规则「边界」里关于 SVN 写操作的说明（去掉“不自动 revert、清理”的说法）。

## 5. 目录复用时自动清理

- `branch.py` 复用旧目录切到新分支：预览里增加“清理 `.mhxy-workspace/`”一步，切换成功后执行，复用 `workspace.py clean` 的逻辑和安全检查。
- 有 Codex 任务在运行或设备锁没释放时，预览阶段就拒绝。
- 全新检出不涉及。同步更新 `branch.md`，写明复用会改目录名、正在该目录运行的会话会失效。

## 不在本次范围

- 维护流程开始前对外测、trunk、release2 的整体清理：由 popo-agent-service 调用现有 `workspace.py clean`。
- 按保留期的自动清理：用户选择不做。
- popo-agent-service 本身（`D:\workspace\popo-agent-service`，只调用 skill）。接口约定见该项目 `docs/design-brief.md` 末尾「补充」；本次定下的脚本名、参数、结果文件格式如与那里不同，做完后更新那份文档并通知那个会话。

## 变更记录

- 2026-11-10：建立。第 1 项由指针模式改为 context 自动更新副本（原因见上）。
- 2026-11-10（0.3.32）：五项全部实现。
  - 第 1 项：`workspace.py` 的 `update_entry_files`、`context --no-entry-update`，输出字段 `entry_rules_updated`。
  - 第 2 项：`references/unattended.md`、`scripts/unattended.py`（`result`／`show`），结果文件 `.mhxy-workspace/unattended/<工单号>/result.json`。
  - 第 3 项：`scripts/report.py`（`build`／`commit`），报告在 `.mhxy-workspace/reports/<工单号>/`。自检结果由脚本现场跑提交前自检（阻断和警告）并读取用例执行器报告；`--case-report latest` 取最新一份。
  - 第 4 项：`scripts/svn_update.py`，另有 `--code-only`、`--dry-run`。实现细节：更新用 `--force --accept postpone`，被 `--force` 原地纳管且内容不同的未纳管文件存进备份后换成服务器版本；未纳管目录与新增文件互相挡路时 svn 报树冲突，按冲突处理；被换掉的文件除 patch 外另存原件（patch 不含二进制）；`AGENTS.md`／`CLAUDE.md` 冲突取服务器版本后自动重新 sync。每一项先备份成功再动手，失败即放弃该项；链接、入口文件和本地辅助目录上的树冲突不自动处理。
  - 第 5 项：`branch.py` 的 `reuse_workspace_entries` 和 `clean_workspace` 步骤。
  - 补记：2026-11-06 `workspace.py`、`precommit.py` 调用 svn 加了 `CREATE_NO_WINDOW`（UTF-8 代码页下 svn 会把中文路径参数转成乱码），当时没有提升版本号，随本次一并发布。
  - 测试：383 → 439（新增 `test_entry_update.py`、`test_report.py`、`test_svn_update.py`、`test_branch_reuse_clean.py` 和公共的 `svn_fixture.py`，未删改已有测试）。Codex review：第 1 项 1 轮通过；第 2～5 项 2 轮通过（第 1 轮 1 条必须修改：`svn_update.py` 还原失败后仍可能删除本地内容、链接静默跳过备份、未排除本地辅助目录的树冲突，已修并补测试）。
  - 真实工作区验证：`svn_update.py --dry-run` 在 trunk 和外测（`test_2026_11_10` → 目标 `test_2026_11_17`）只读运行正常；发版后 trunk 的入口文件由 `context` 自动更新到 0.3.32。
- 2026-11-12（0.3.44）：试玩（`shiwan`）周期分支默认不切到下一个维护周，原地更新（`svn_update.py` 的 `NO_ADVANCE_TYPES`），用户明确要求时加 `--advance`。原因：用户说明试玩分支一般不跟周走。同日 popo-agent-service 把 shiwan 登记为工作区但不参加周维护（`enabled: false`）。
