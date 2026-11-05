# 真机测试 Playbook 执行器

日期：2026-11-05　版本：0.3.28（待编码）

## 目标

真机自检和回归要快、可复现。现在测试执行者每一步都靠模型推理调用 mh-game-mcp：一次简单验收（读角色信息、装一个 Mock 再还原）约 11 分钟，自写脚本出错 3 次。改为：执行者写声明式 JSON 剧本，本地执行器一次跑完并输出报告；模型只负责写剧本和出问题时排查。

适用于所有玩法，不限战斗；战斗作为第一批内置预设，保证战斗测试同样一条命令跑完。

## 方案

- **入口**：`scripts/game-debugging/playbook.py run --root <项目> --devid <设备ID> <剧本.json | spec.md>...`。传 spec 时读取其「测试用例」一节下的 JSON 代码块，作为回归剧本的唯一来源。stdout 输出报告 JSON，同时保存到剧本所在测试目录。
- **自包含**：只依赖本 skill 自己的脚本和 mh-game-mcp 服务，不调用、不引用其他 skill。下文“借鉴”的设计都在本 skill 内重新实现。
- **设备与锁**：执行器不选设备、不加锁。test 任务由主会话按现有流程 `client_launch.py select` 并加锁；主线程直接回归时用 `codex_cli.py lock` / `release` 包住这次运行。
- **MCP 调用**：在 `mcp_http.py` 增加返回结构化结果的调用函数（解包 `structuredContent`／`content[].text`、内层 `ret/error/loginfo`，保留 `ui_events`、`client_event`）；一次运行复用同一个会话，不每步重新 initialize。`mcp_eval.py`、`mcp_call.py` 保持命令行用途。

### 剧本格式

```json
{
  "name": "用例名",
  "mocks": [
    {"name": "固定随机", "patch": "模块.属性", "value": "替换值表达式"},
    {"name": "自定义", "install": "代码", "restore": "代码"}
  ],
  "steps": [
    {"init_client": {}},
    {"gm": "at fightN 2"},
    {"wait_for": {"preset": "war_turn", "args": {"n": 1}, "timeout": 30}},
    {"exec": "代码", "save_as": "wid"},
    {"mcp": "工具名", "args": {}},
    {"assert": "表达式，可用 {vars.wid}", "message": "失败说明"},
    {"exec_check": {"cases": "定义 CASES 的代码"}}
  ]
}
```

- **占位符**：`{devid}`、`{root}`，以及前面步骤 `save_as` 保存的 `{vars.名字}`。
- **步骤**：`init_client`、`exec`（代码或 `file`）、`gm`、`mcp`（其他 mh-game-mcp 工具）、`wait_for`、`assert`、`exec_check`。任一步失败即停止后续步骤，转入收尾。
- **wait_for**：在本机轮询客户端表达式（不在客户端主线程等待），带超时和间隔；可写 `expr`，也可引用预设。
- **预设**：集中在一个预设表里，按领域分组，新增玩法只加预设、不改执行流程。第一批：通用（界面打开／关闭）、战斗（进入战斗、离开战斗、到达第 N 回合、命令队列空闲）。战斗预设的具体判断表达式编码时按 `war.Turn`、`war.Cmds`、`war.ProcessFunc` 等确认，并在真机上验证。
- **exec_check**：目标行由 `diff_lines.collect` 计算，复用 `exec_trace.py` 在一次同步调用里跑完用例；跨多步的异步流程没跑到的行照实列进 `missing`，由执行者补测。

### Mock 与收尾

- 报错收集不是剧本步骤：执行器开始时自动 `error_watch_start`，收尾时 `error_watch_finish`。
- `patch` 型 Mock 由执行器生成安装和还原代码：用 `_MISSING` 哨兵备份原值，备份存在客户端的专用模块属性上，跨多次调用也能还原；`install`/`restore` 型用于其他情况。安装前记录事件监听数量作为基线。
- 收尾在 finally 中执行：逆序还原 Mock、结束报错收集、核对监听数量回到基线。全部核对通过为 `restored`；核对不了为 `unknown`；没有 Mock 为 `not_needed`。

### 报告

- 顶层沿用 test 结果字段 `status`、`cases`、`errors`、`unverified`、`restoration`，另加：
  - `steps`：每步耗时、返回值、报错、附带的 UI 事件；
  - `executed`：实际下发的全部工具调用、GM 指令和代码，按顺序，可用于复现。
- `passed` 需要：所有断言通过、没有收集到报错、`restoration` 不是 `unknown`。判定仍以主会话核对报告为准。
- `codex_cli.py` 的 test 结果 schema 增加 `executed`。

## 流程与文档

- **test 任务**：执行者先写剧本、用执行器跑；出问题时排查剧本或报告缺陷。剧本写在任务的测试目录内。
- **剧本留档**：真机自检通过的剧本，由主会话写入项目 spec 的「测试用例」一节（JSON 代码块）。
- **回归例外**：spec 中已有剧本的回归，主线程可以直接运行执行器（加锁、运行、核对恢复、释放），不委派；这是“操作客户端一律委派”的例外。剧本需要修改或运行失败需要排查时，仍委派。
- **game-debugging.md**：给出标准测试骨架：清场 → 造局 → 执行 → 收集证据 → 恢复，并说明剧本格式和预设。
- **cli.md**：test 结果字段加 `executed`；test 任务说明改为优先用执行器。
- 设计借鉴：war-test 的声明式剧本、执行清单和本机侧等待；mh-game-mcp-coverage-tester 的 `_MISSING` 可恢复 Mock 和监听基线；client-loop-test 的 MCP 返回解包。

## 风险

- 客户端状态复杂，预设表达式判断不准会导致等待超时；以超时失败报告，不静默通过。
- 回归由主线程直接操作客户端，要严格按锁和恢复核对执行。

## 验收

- 单元测试：剧本校验、占位符、预设展开、Mock 安装／还原代码生成、失败时仍执行收尾、报告字段、从 spec 读取剧本。
- 真机：一个通用剧本（读角色信息 + Mock 安装与还原）一次跑完，用时明显少于 11 分钟；一个战斗剧本（GM 进战斗、等回合、断言、离开战斗）跑通；人为让一步失败，确认 Mock 仍被还原、`restoration` 正确。

## 变更记录

- 2026-11-05（0.3.28）：初版。
