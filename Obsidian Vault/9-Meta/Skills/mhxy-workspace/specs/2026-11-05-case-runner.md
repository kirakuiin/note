# 真机用例执行器

日期：2026-11-05　版本：0.3.28

## 目标

真机自检和回归要快、可复现。之前测试执行者每一步都靠模型推理调用 mh-game-mcp：一次简单验收（读角色信息、装一个 Mock 再还原）约 11 分钟，自写脚本出错 3 次。改为：执行者写声明式 JSON 用例文件，本地执行器一次跑完并输出报告；模型只负责写用例和出问题时排查。

适用于所有玩法，不限战斗；战斗作为第一批内置等待预设，战斗测试同样一条命令跑完。

## 方案

- **入口**：`scripts/game-debugging/case_runner.py run --root <项目> --devid <设备ID> <用例.json | spec.md>...`。传 spec 时读取其「测试用例」一节（到同级或更高级标题为止）下的 json 代码块，作为回归用例的唯一来源。报告输出到 stdout，同时保存到 `<项目>/.mhxy-workspace/cases/reports/<时间>.json`。退出码 0 通过、1 失败、2 受阻。
- **自包含**：只依赖本 skill 自己的脚本和 mh-game-mcp 服务，不调用、不引用其他 skill；借鉴的设计都在本 skill 内重新实现。
- **设备与锁**：执行器不选设备、不加锁。test 任务由主会话按现有流程 `client_launch.py select` 并加锁；主线程直接回归时用 `codex_cli.py lock` / `release` 包住这次运行。
- **MCP 调用**：`mcp_http.py` 新增 `initialize`、`call`（返回结构化载荷，失败抛 `McpError`），`client_launch.py` 改用它。执行器一次运行只握手一次。
- 用例文件先全部校验，有问题直接 blocked，不连接客户端。每次运行先 `init_client` 一次（同一任务已调用过时加 `--no-init`）。

### 用例格式

```json
{
  "name": "用例名",
  "settle": 2,
  "mocks": [
    {"name": "固定随机", "patch": "模块.属性", "value": "替换值表达式，可用 orig 引用原值"},
    {"name": "自定义", "install": "代码", "restore": "代码，最后一行返回核对结果 True"}
  ],
  "steps": [
    {"gm": "$at fightN 2"},
    {"wait_for": {"preset": "war_turn", "args": {"n": 1}, "timeout": 30}},
    {"exec": "代码", "save_as": "wid"},
    {"mcp": "工具名", "args": {"devid": "{devid}"}, "save_as": "status"},
    {"assert": "表达式，可用 {vars.wid}", "message": "失败说明"},
    {"exec_check": {"cases": "定义 CASES 的代码", "files": ["可选：相对路径"]}}
  ]
}
```

- **占位符**：`{devid}`、`{root}` 原样代入；`{vars.名字}`（前面 `save_as` 保存的值）、`{args.名字}`（预设参数）在客户端代码里代入 `repr()`，在 GM 指令和 mcp 参数里代入文本。其他花括号不动。
- **步骤**：每步恰好一个类型键：`exec`、`gm`（`execute_command`）、`mcp`（其他 mh-game-mcp 工具）、`wait_for`、`assert`、`exec_check`。任一步失败即停止后续步骤，转入收尾。
- **wait_for**：本机轮询客户端表达式直到为真（不在客户端主线程等待），`timeout` 默认 30 秒、`interval` 默认 0.5 秒；表达式报错或超时即失败。executed 只记第一次轮询。
- **预设**：集中在 `PRESETS` 表，按领域分组；新增玩法只加预设，不改执行流程，每个预设在真机上验证过再加入。第一批战斗预设：`war_in`、`war_out`（`utils3.is_in_war()`）、`war_turn`（`war.Turn >= n`）、`war_idle`（命令队列 `war.Cmds` 为空）。界面类预设等有可靠判断依据后再加。
- **exec_check**：目标行由 `diff_lines` 计算（不给 `files` 时取全部未提交的 .py），在一次 `execute_code` 里用 `exec_trace.py` 跑完 `CASES`；用例报错算失败，没执行到的行列进 `unverified`，由执行者补测或说明。

### Mock 与收尾

- 报错收集不是步骤：每个用例开始时自动 `error_watch_start`，收尾时 `error_watch_finish`。
- `patch` 型 Mock 由执行器生成安装和还原代码：备份登记在客户端 `sys._mhxy_case_mocks`，跨多次调用仍可还原；只看对象自己的 `__dict__`，继承来的属性还原时删除而不是写回；先登记再替换。安装在登记前就失败的，视为不需要还原。`install`/`restore` 型用于其他情况，`restore` 最后一行必须返回 `True` 才算核对通过。
- 有 Mock 时，安装前记录各事件的监听数量。
- 收尾在 finally 中执行，各项单独捕获失败：等待 `settle` 秒（默认 2，让延迟回调跑完）→ 逆序还原 Mock → 核对监听数量（比基线多的列进 `unverified`，可能是被测代码正常注册）→ 结束报错收集。全部 Mock 核对通过为 `restored`，任一失败为 `unknown`，没有 Mock 为 `not_needed`。

### 报告

- 顶层沿用 test 结果字段 `status`、`cases`、`errors`、`unverified`、`restoration`，另有：
  - `results`：每个用例的步骤明细（耗时、返回值、报错、loginfo、附带的 `ui_events`／`client_event`）、Mock 安装和还原结果、失败原因；
  - `executed`：实际下发的全部工具调用，按顺序，可用于复现；模板全文以 `<error_watch.py 全文>` 等简写代替；
  - `report_path`。
- 用例 `passed` 需要：步骤全部成功、没有收集到报错、`restoration` 不是 `unknown`。判定仍以主会话核对报告为准。
- `codex_cli.py` 的 test 结果 schema 增加 `executed`（字符串列表，复现清单）。

## 流程与文档

- **test 任务**：执行者优先写用例文件、用执行器跑；出问题时排查用例或报告缺陷。用例文件写在 `.mhxy-workspace/cases/` 内。
- **用例留档**：真机自检通过的用例，由主会话写入项目 spec 的「测试用例」一节（json 代码块）。
- **回归例外**：spec 中已有用例的回归，主线程可以直接运行执行器（加锁 → 运行 → 核对报告和恢复 → 释放），不委派。用例需要修改或运行失败需要排查时，仍委派。
- **game-debugging.md**：新增「用例执行器」一节，含标准测试骨架（清场 → 造局 → 执行 → 收集证据 → 恢复）、格式和预设；开头的委派规则加上回归例外。
- **cli.md**：test 结果字段加 `executed`；test 任务的 `write_dirs` 用 `.mhxy-workspace/cases`。
- **test 沙箱联网**：执行器由 Codex 在命令行运行，要直连 mh-game-mcp 的 HTTP 入口，而 `workspace-write` 沙箱默认禁止命令联网。`codex_cli.py` 只给 test 任务加 `sandbox_workspace_write.network_access=true`（用户确认）；investigate、review 仍是只读、不联网。
- 设计借鉴：war-test 的声明式用例、执行清单和本机侧等待；mh-game-mcp-coverage-tester 的可恢复 Mock 和监听基线；client-loop-test 的 MCP 返回解包。

## 风险

- 预设表达式判断不准会导致等待超时；以超时失败报告，不静默通过。`war_idle` 只看命令队列，可能早于表演结束的最后几帧。
- 回归由主线程直接操作客户端，要严格按锁和恢复核对执行。

## 验收

- 单元测试（`tests/test_case_runner.py`，execute_code 在本进程内模拟执行）：用例校验、占位符、从 spec 读取用例、patch Mock 安装／还原（含继承属性、安装失败、网络中断后仍还原）、自定义 Mock 的核对、等待预设和超时、GM／mcp 参数、收集到报错判失败、执行检查、报告保存和退出码。
- 真机：一个通用用例（读角色信息 + Mock 安装与还原）一次跑完，用时明显少于 11 分钟；一个战斗用例（GM 进战斗、等回合、断言、离开战斗）跑通，验证战斗预设；人为让一步失败，确认 Mock 仍被还原、`restoration` 正确。

## 变更记录

- 2026-11-05（0.3.28）：初版。
