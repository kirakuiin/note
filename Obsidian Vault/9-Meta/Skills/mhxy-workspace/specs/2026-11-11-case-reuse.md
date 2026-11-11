# 用例复用、候选原语收集与覆盖率跑测接入用例执行器

日期：2026-11-11　版本：0.3.36

## 目标

1. **用例复用**（最重要）：至少在一个制作或维护周期内，会话知道工作区里有哪些用例、哪些和当前工作有关，重新测试时直接复用，不重写。只靠本 skill 实现，不依赖 popo-agent-service。
2. **候选原语收集**：测试执行者把这次写的、可能复用的判断表达式、造局步骤、弹窗关闭方式上报，主会话汇总后经用户一次确认，再加进预设表、清场清单或模板，让写用例越来越快。
3. **覆盖率跑测接入用例执行器**：一轮覆盖率跑测写成一个用例文件，一条命令跑完，补测时改 Mock 再跑同一个文件。

用户明确不需要兼容旧行为：用例格式、目录结构、`search` 的行为直接改，旧写法不保留兼容逻辑。

## 背景

`.mhxy-workspace/cases/` 在一个周期内一直保留，只在周期边界整体清理（维护流程开始前清理个人目录、`branch.py` 复用目录切分支时）。之前缺的是发现和关联：用例平铺存放、没有归属信息，`search` 只查模板，没有“先找再写”的规则；小改动不写 spec，用例只留在工作区。

## 方案

### 1. 用例复用

**归属字段**（用例对象的顶层字段）：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `issue` | 字符串（工单号，纯数字）或 `null` | 不属于某张工单的功能用例写 `null` |
| `spec` | 字符串（相对项目根的路径）或 `null` | 小改动没有 spec 时写 `null` |
| `targets` | 非空字符串列表 | 测的文件（相对项目根，如 `war/war2021_net.py`）、目录（以 `/` 结尾）或模块名（如 `war2021_net`） |
| `keywords` | 字符串列表 | 玩法、界面、现象等检索词，可以为空 |

- `.mhxy-workspace/` 下的用例文件（`cases/`、`coverage/`）四项都必须写，缺了或类型不对时 blocked，不连接客户端。spec「测试用例」一节和模板里的用例可以不写（spec 本身就是归属）；写了也按同样规则校验。
- **归档目录**：工作区用例放在 `.mhxy-workspace/cases/<工单号或功能名>/*.json`，目录名是单个路径段。直接放在 `cases/` 下的用例文件 blocked 并提示移动。`cases/reports/`（执行器报告）和 `cases/runs.json`（通过记录）是保留名。覆盖率用例放在覆盖率任务目录 `.mhxy-workspace/coverage/<任务目录>/`（见第 3 项），同样收录。
- **通过记录** `cases/runs.json`：每次运行（非 blocked）结束后，执行器按“来源文件相对路径 + 用例名”记录 `last_run`、`last_status`、`report`，通过时另记 `last_passed` 和用例内容的摘要 `passed_hash`（规范化 JSON 的 SHA-256 前 16 位）。来源在项目根之外的不记录。用例内容改过、摘要对不上时，检索结果标 `changed_since_pass: true`，提示上次通过不代表当前内容。多个执行器并发写时用同目录的锁文件串行化（等待最多 10 秒，等不到只在报告 `unverified` 记一条，不判失败）。
- **共用模块** `scripts/case_store.py`：用例文件读取（`.json` 和 spec「测试用例」一节）、归属字段校验、工作区用例扫描、通过记录读写、按工单／文件／关键词匹配。`case_runner.py`、`workspace.py`、`report.py` 都用它；它在模块顶层只依赖标准库（`precommit` 在取未提交改动时才导入，避免与 `workspace.py` 循环导入）。

**`search`**：

```text
case_runner.py search --root <项目> [--issue <工单号>] [--file <路径>]... [--changed] [关键词...]
```

- 至少给一个条件；多个条件同时满足才命中。
- 工作区用例（`cases/`、`coverage/` 下）按条件匹配：`--issue` 比对 `issue`；`--file` 与 `targets` 匹配（路径相同或以其结尾、目录前缀、模块名等于文件名去掉 `.py`）；`--changed` 取 `svn status` 里待提交的文件（同 `precommit` 的范围，未纳入版本控制的目录展开），与任一目标匹配即命中；关键词全部出现在名字、关键词、目标、工单号里才命中。输出每条的路径、用例名、归属字段、`last_status`、`last_passed`、`changed_since_pass`，不输出用例正文（按路径读或直接跑）。
- 读不了、不合法或缺归属字段的工作区用例文件列在 `problems`，不静默跳过。
- 只给关键词时同时查模板（行为同前：全部关键词命中名字、说明或关键词，输出正文）；工作区用例和模板都没有命中时，按技能名查导表生成战斗用例骨架（同前）。只给 `--issue`、`--file`、`--changed` 时不查模板。
- `--changed` 时输出里附 `changed_files`；svn 不可用时报错退出（退出码 2），不当作“没有改动”。

**`context`**：输出新增 `cases`：`{"total": 工作区用例数, "tracked": [{"issue_id", "count", "passed", "last_passed", "files"}]}`，`tracked` 只列追踪工单中有用例的，`files` 是相对项目根的用例文件路径；不放用例内容。扫描出的问题文件只计数（`problem_files`），详情用 `search` 查。读取失败记入 `problems`，不影响其他部分。

**规则**（`game-debugging.md`「用例执行器」）：写新用例前先 `search`（按工单号、文件或 `--changed`，再按关键词查模板）；重新测试时先跑已有的相关用例，有缺口再在原文件补用例或新增文件，不重写已有的；用例写好归属字段、放进归档目录。委派测试时 `cli.md` 的 test 任务说明带上已有相关用例的路径（主会话在委派前跑一次 `search`）。

**处理报告**：执行器报告新增 `sources`（本次运行的用例来源绝对路径）。`report.py build` 把每份用例执行器报告的来源拷进报告文件夹的 `cases/`：`.json` 原样拷贝，spec（`.md`）只取「测试用例」一节的用例写成 `<spec 名>.json`；重名加序号。页面列出这些文件和重跑命令，报告拷到别处也能重跑。重新 build 时 `cases/` 与 `media/` 一样整体重建。

跨周期的长期保存不变：有 spec 的功能写进 spec「测试用例」一节；能通用的提升为 `assets/cases/` 模板。

### 2. 候选原语收集

- **执行者上报**：test 结果新增字段 `candidates`（没有时为空列表），每条 `{"kind", "content", "runs", "note"}`：`kind` 为 `preset`（等待条件表达式）、`clean_ui`（新弹窗的关闭方式）、`template`（可通用的造局或整段用例）、`step`（值得做成新步骤类型的操作）；`content` 是表达式、代码或用例片段；`runs` 是这次在真机上跑通的次数（整数）；`note` 写用途、适用范围和证据（报告路径）。`codex_cli.py` 的 test schema 同步增加（结构化校验支持整数）。
- **主会话汇总**：Claude 主会话在提交后整理记忆时，把候选原语和候选经验一起列给用户，一次确认（`session.md`）；Codex 主会话没有该流程，在交付时一并列出（`cli.md`「Codex 主会话」）。
- **确认后再加**：用户同意的，由主会话加进 `PRESETS`、`_case_clean_ui`、`assets/cases/` 模板或新步骤类型，并补单元测试。只跑通过一次的候选要在列出时注明，预设仍要求“真机验证可靠后再加”。

### 3. 覆盖率跑测接入用例执行器

一轮跑测写成一个用例文件，放在 `.mhxy-workspace/coverage/<任务目录>/`，归属字段 `issue` 写覆盖率工单：

- 前置：`gm` 步骤 `$$scover_create <redmine_id> <task_name> <coder_name>`（首次）或 `$$scover_set <task_name>`（已存在），再用 `wait_for`／`assert` 以客户端成功日志核实。
- Mock 并调用**原始**被测逻辑、断言。
- `$$scover_finish <task_name>`，同样核实上传。
- 收尾由执行器自动恢复 Mock、收集报错。

网站查询和“是否 100%”的判定仍由执行者读结果后用 `coverage_query.py` 完成；`coverage.md` 原有禁止事项全部保留。补测时改 Mock 再跑同一文件。

先在真实覆盖率任务上验证 `$$scover_*` 能在用例的 `gm` 步骤里跑通，记录一轮的耗时和工具调用次数，与手动方式对比后再改文档；验证不通先找用户。

## 改动文件

- `scripts/case_store.py`（新增）、`scripts/game-debugging/case_runner.py`、`scripts/workspace.py`、`scripts/report.py`、`scripts/codex_cli.py`
- `assets/cases/` 模板（补归属字段示例的说明）、`references/game-debugging.md`、`cli.md`、`session.md`、`coverage.md`、`workspace-management.md`、`unattended.md`
- 测试：`tests/test_case_runner.py`、`test_workspace.py`、`test_report.py`、`test_codex_cli.py`，新增 `tests/test_case_store.py`

## 验收

- 单元测试：归属字段校验（工作区用例必填、spec／模板可选）、归档目录检查、通过记录写入与摘要比对、`search` 各条件与组合、`--changed`（模拟 svn）、`context` 的 `cases`、`report.py` 拷贝用例文件、test schema 的 `candidates`。全量 `python -m pytest -q` 通过。
- 真机：在 trunk 工作区写一个带归属字段的用例跑通，确认 `runs.json` 记录、`search --issue`／`--changed` 和 `context` 能看到它。
- 覆盖率：在真实任务上跑一轮 `$$scover_*` 用例，与手动方式对比耗时和工具调用次数。

## 变更记录

- 2026-11-11（0.3.36）：初版。
