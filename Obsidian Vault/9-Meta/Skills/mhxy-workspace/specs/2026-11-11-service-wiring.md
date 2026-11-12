# skill 一致性修复，以及与 popo-agent-service 的串联

日期：2026-11-11　版本：0.3.38

## 背景

两份只读审查（skill 内部一致性；skill 与 `D:\workspace\popo-agent-service` 的接口）发现规则互相矛盾、服务依赖的状态和保护开关缺失。用户 2026-11-11 确认整体方案：先修 skill，全量测试通过后再改服务。

## skill 侧（0.3.38）

### 规则统一

1. **无人值守与合并**：无人值守会话不发起合并，B 类单只报告“需要你处理”；用户同意后由用户或调用方另起会话按 `svn-merge.md` 合并，`run` 不带 `--commit`，停在 `merged` 等用户批准提交。`svn-merge.md` 新增「无人值守与后台服务」一节，`unattended.md` 的 B 类行指向它；`five-items` spec 里“按 svn-merge skill 做”同步改正。
2. **复用目录的自动清理**：入口「边界」和 `workspace-management.md`「清理个人目录」写明唯一例外——用户确认复用目录检出即包含清理该目录的 `.mhxy-workspace/`。
3. **合并提交后更新工单**：`svn-merge.md`「流程」新增第 6 步：合并提交成功后按「更新工单」处理 `finish #` 那张单，并给报告补版本号；`task-tracking.md`「何时做」和 `svn-commit.md`「提交后更新工单」同步。
4. **禁止提交开关**：`MHXY_NO_COMMIT` 不为空也不是 `0` 时，`svn_commit.py --apply` 返回 `committed: false` 和 `error`，`pm_update.py --apply` 在登录前退出码 1；预览不受影响。判断集中到 `workspace.commit_forbidden()`，`svn_merge.py` 共用。
5. **提交后补报告**：`svn-commit.md`「提交」新增第 5 步：本次工单有处理报告时 `report.py commit`。

### 结果文件

- 新状态 **等前一单提交**：要改的文件被同一工作区另一张未提交的工单占用。占用关系以调用方的提示词为准（没列出时不自己推断，按“需要你处理”停下）；不改那些文件，已做的其他修改保留。必须给 `--waiting-for <工单号>`，结果多一个字段 `waiting_for`；其他状态不能给，不能是本工单，不能带工单更新。调用方在占用单提交或放弃后让会话继续，先 `svn update` 再接着做。
- 新的可选字段 **candidates**：`--candidates-file` 接受 test 结果 JSON（取其 `candidates`）或候选原语列表本身，每条 `kind`／`content`／`runs`／`note`，按 codex_cli 的 test schema 校验，任何状态都可带。无人值守会话不跑 session.md，候选原语由调用方列给用户确认。
- 可选字段固定顺序：`waiting_for`、`candidates`、`pm_update`，排在 9 个固定字段之后；`show` 按同一规则校验。旧结果文件（只有固定字段或加 `pm_update`）仍然有效。
- `report.py build --status` 只接受 待提交／需要你处理／放弃／等前一单提交；“已提交”只由 `commit` 设置。

### 小问题

- 0.3.34、0.3.35 补记到 `2026-10-15-dev-flow.md` 变更记录，合并脚本补 spec `2026-11-11-svn-merge.md`。
- spec 版本头统一为“日期：…　版本：…”（`dev-flow`、`five-items`）；spec 里的测试命令统一引用 SKILL.md。
- `svn_update.py` 文档字符串写明入口文件冲突取服务器版本后自动重新 sync；`svn-update.md` 结果补 `local_changes`、dry-run 的 `locked` 和 `planned`。
- 用户级配置参数统一为 `--global-config`：`pm_update.py`、`pm_issues.py`、`cr_diff.py`、`testreport.py`、`branch.py` 增加该写法，`--config` 保留为旧写法。

### 验证

- 新增测试：等前一单提交的字段与拒绝条件、候选原语两种输入与校验、可选字段顺序、`report build --status 已提交` 拒绝、`svn_commit` 与 `pm_update` 的 `MHXY_NO_COMMIT`、`--global-config`。全量 491 → 496 通过，未改动已有断言。

## 服务侧（`D:\workspace\popo-agent-service`，记录在该项目 `docs/spec.md` §4）

- 开关 `clean`、`unattended`、`report` 打开，新增 `pm_update`。
- 结果文件“等前一单提交”→ `waiting_dep`；只认服务列出的占用关系，占用单提交、放弃或被更新脚本还原后只续接在等它的单。
- `work` 档位放行 `scripts/game-debugging/`、`scripts/exec-check/` 子目录脚本，并禁止 `svn_merge.py commit`；会话带 `MHXY_NO_COMMIT=1`（已有），由本 skill 的脚本层拒绝写入。
- 提示词：正文给相对工作区根目录的路径；带用例复用规则和 `--candidates-file`。
- 提交（含合并提交）成功后按结果的 `pm_update` 写工单：待提交时预览进卡片，用户点“提交”即确认（用户 2026-11-11 定）；随后 `report.py commit`。
- 卡片列候选原语，“收下候选原语”追加到服务的 `data/candidates.jsonl`，由后续会话经用户确认后加进本 skill（`game-debugging.md`「候选原语」）。
- 测试替身补齐 `unattended.py`、`pm_update.py`、`svn_merge.py`、`game-debugging/case_runner.py`；新增 `tests/test_real_skill.py` 对本 skill 的真实脚本跑 `--help` 和不联网命令，核对参数名、结果状态、结果文件往返和 `MHXY_NO_COMMIT`。服务测试 26 → 49 通过。

## 变更记录

- 2026-11-11（0.3.38）：skill 侧完成；服务侧接入完成（服务改动未提交，等用户确认）。真实链路验证待用户同意后在外测工作区进行。
- 2026-11-12（0.3.39）：禁止写入的开关拆成两个：`MHXY_NO_COMMIT` 只管 SVN 提交（`svn_commit.py`、`svn_merge.py`），新增 `MHXY_NO_PM_WRITE` 只管 `pm_update.py --apply`（`workspace.pm_write_forbidden()`）。原因：用户在 POPO 里要求改工单状态和登记工时并点了确认，服务执行会话仍带着 `MHXY_NO_COMMIT=1`，写工单被拒（849400）；共用一个开关时，放开写工单就会连提交一起放开。服务同步改为按卡片上确认的动作分别放开。
