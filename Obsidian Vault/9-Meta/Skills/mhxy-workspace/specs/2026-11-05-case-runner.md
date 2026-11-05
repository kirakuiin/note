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
  "ignore_errors": ["NSRank 的size不对"],
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

- **ignore_errors**：可选，正则列表。收集到的报错命中任一条时移入用例报告的 `ignored_errors`，不计入 `errors`、不判失败，并在 `unverified` 注明忽略了几条。只用于已确认与被测内容无关的客户端既有报错，例如每次退出战斗都会出现的 NSRank 图标尺寸告警。正则写得越具体越好，避免把真正的报错一起吞掉。
- **占位符**：`{devid}`、`{root}` 原样代入；`{vars.名字}`（前面 `save_as` 保存的值）、`{args.名字}`（预设参数）在客户端代码里代入 `repr()`，在 GM 指令和 mcp 参数里代入文本。其他花括号不动。
- **步骤**：每步恰好一个类型键：`exec`、`gm`（`execute_command`）、`mcp`（其他 mh-game-mcp 工具）、`wait_for`、`assert`、`exec_check`。任一步失败即停止后续步骤，转入收尾。
- **wait_for**：本机轮询客户端表达式直到为真（不在客户端主线程等待），`timeout` 默认 30 秒、`interval` 默认 0.5 秒；表达式报错或超时即失败。executed 只记第一次轮询。
- **预设**：集中在 `PRESETS` 表，按领域分组；新增玩法只加预设，不改执行流程，每个预设在真机上验证过再加入。第一批战斗预设：`war_in`、`war_out`（`utils3.is_in_war()`）；`war_idle`：本场已进入某回合且在等下指令（`PlayerTurn >= 1`、`war.Cmds` 为空、`ProcessFunc == wait_cmd`）；`war_turn`：在 `war_idle` 基础上 `ActualTurn >= n`。不用 `war.Turn`：它是“已收到、未播完的回合协议”计数，进入回合时被 `war.turn()` 减 1（真机验证）；`ActualTurn` 只在 `do_end()` 重置，单独判断会在刚开战或连续战斗时过早成立。界面类预设等有可靠判断依据后再加。
- **exec_check**：目标行由 `diff_lines` 计算（不给 `files` 时取全部未提交的 .py），在一次 `execute_code` 里用 `exec_trace.py` 跑完 `CASES`；用例报错算失败，没执行到的行列进 `unverified`，由执行者补测或说明。

### Mock 与收尾

- 报错收集不是步骤：每个用例开始时自动 `error_watch_start`，收尾时 `error_watch_finish`。
- **合并调用**：真机上每次 `execute_code` 往返约 2.8 秒，固定开销合并为每个用例两次调用：开始时一次完成“开始报错收集 + 监听基线（有 Mock 时）+ 安装全部 patch Mock”，收尾时一次完成“逆序还原 patch Mock + 核对监听 + 结束报错收集”。客户端辅助函数（`CLIENT_HELPERS`）各自捕获异常并返回结果，同一次调用里一项失败不影响其他项。自定义 Mock 代码任意，安装和还原仍逐个调用，在 patch Mock 之后安装、之前还原。
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

### 战斗原语、证据采集与用例检索（0.3.29）

借鉴 war-test 的回合指令、场面映射、造局、按出手等待、录像和配方检索，全部在本机执行器内实现，不依赖远端服务。

- **`war_act` 步骤**：`{"war_act": {"role": {"act", "id", "target", "item"}, "pet": {...}, "wait": true, "timeout": 90}}`，一次 `execute_code` 下完人物和全部在场召唤兽的指令，再调 `dlgwar.wait()` 收起指令面板。
  - 人物动作：`attack`、`magic`（`id` 为 `infoskillperform2021` 的编号，发 `netwar.c_war_perform`）、`sp`（`id` 为 `infosp` 编号，发 `netskill.c_sp_perform`）、`guard`、`protect`（必须写 `target`）、`item`（`item` 写道具名或造型编号，按背包实例 `nOID` 发包）、`fabao`（`id` 为法宝造型编号，按 `dlgfabao.FABAO_INFO` 反查位置）。召唤兽动作：`attack`、`magic`、`guard`、`protect`、`item`；不写 `pet` 时全部防御，避免服务端等召唤兽指令。
  - 目标：`e0`/`e1`…（敌方按 `(place, wid)` 排序）、`f0`…（其他友方）、`self`、`pet`（第一只在场召唤兽），或直接写 wid。先全部解析再发包，解析失败时一个包都不发。
  - 前置：必须处于 `war_idle`；否则失败。发包后若 `dlgwar.SelfID` 不为空（还有身外化身、奇袭召唤兽等单位等指令），步骤失败并说明，不支持这些单位。
  - `wait` 默认为真：本机轮询直到进入下一回合的等待下指令阶段，或战斗已结束。
  - 步骤记录里附场面映射 `roster`（label、wid、名字、阵营、主人、站位、`sid`、血量百分比）。
- **`setup` 造局**（用例字段，开始阶段之后、步骤之前执行）：`school: [门派, 流派]`（与 `sdata.hero.Prop` 的 `nSchool`/`nSect` 一致就跳过；否则必须写 `allow_destructive: true` 才发 `$at cs`，因为会清空经脉）、`teji`（`$at teji 1 名字`）、`items`（背包里已有就跳过，否则 `$at cloneobj`）、`gm`（其他指令原样下发）。召唤兽技能、法宝等没有核实过的指令写在 `gm` 里。
- **证据采集**（都按需开启，默认不做）：每次运行的媒体文件放在 `reports/<运行编号>/`，与报告 `reports/<运行编号>.json` 同名。
  - `record: true`：开始阶段的合并调用里 `C_app.start_record_screen(绝对路径, 1, 0)`，收尾合并调用里 `stop_record_screen()`；`settle` 等待正好补上录屏延后约 2 秒的尾部。之后本机等 mp4 出现且大小稳定（最多 30 秒），否则记入 `unverified`。
  - `frames: true`：开始阶段调用 `frame_collector.start_collect()`（必须在进入战斗前），收尾时把本场 `BattleData` 写成 JSON（战斗中取快照，已结束取 `_last_battle`，并排除开始前就有的上一场）后 `stop_collect()`。战斗结束时采集器会弹窗提示导出路径，执行器用内部 patch Mock 把 `_notify_export_done` 换成空函数，收尾还原。
  - `screenshot` 步骤：`{"screenshot": "说明"}`，调用 `utils.screenshot` 截渲染画面（窗口在后台也能截），本机等文件出现（最多 10 秒）。不直接调 `C_app.save_screen`（会崩溃）。
- **预设 `war_action`**（需要 `frames: true`）：帧采集器里 `magic_id` 等于 `args.magic_id`、已结束的出手次数 ≥ `args.n`。
- **用例模板与检索**：模板放在 `assets/cases/<领域>/*.json`，格式 `{"description", "keywords", "case"}`，`case` 必须能通过校验（单测覆盖）。`case_runner.py search --root <项目> 关键词...` 先查模板（全部关键词命中名字、说明或关键词）；没有命中时按技能名在 `data/infoskillperform2021.py`、`data/infosp.py` 里精确查编号，生成战斗用例骨架（进战斗 → `war_act` 放技能 → `war_action` 等出手完成 → 退战），执行者补造局和断言后再跑。
- 待真机确认：服务端战内 GM 的 `<n1>` 是否等于客户端单位的 `sid`（roster 里给出 `sid` 以便核对）；互通版能否录屏；特技在帧数据里的 `magic_id` 是否为 `sp_id + 3000`；截图文件格式和 `SCREENSHOT2` 事件有无副作用。
- 这次不做：同一场战斗里连跑多个用例。

### pump：真实战斗内注入技能表现（0.3.30）

不经服务端结算，在已进入的真实战斗（GM 测试战斗）里直接构造战斗命令，让客户端播放指定技能的出手、受击、血条和 Buff，用于反复看技能表现。不做纯客户端建场：`war.start()` 会清空大世界对象（`war.py:3246`），结束后不会自动恢复，还会向服务端发回合结束包。

- **步骤**：`{"pump": {"perform": {...}, "timeout": 15}}` 或 `{"pump": {"events": [...], "timeout": 15}}`，`perform` 与 `events` 二选一，字段类型在运行前校验。前置是 `war_idle`（否则失败，一个命令都不入队）。
  - `perform` 简写：`attacker`（默认 `self`）、`magic_id`（必填）、`victims`（默认 `["e0"]`）、`hp_chg`（默认 100，负数为加血）、`hits`（受击段数，默认 1）、`life`（默认 0，2 为倒地）、`status`（可选，受击后的血量百分比）、`addons`（可选，`[{"target", "pid", "turn", "level"}]`）。展开为：出手 → 每个目标 `hits` 条受击（第 2 段起前置分段命令）→ 可选血条 → 可选 Buff → 行动结束。
  - `events` 原始事件：`{"op", "data"}`，`op` 为 `perform`、`attack`、`wstate`、`wstate_split`、`status`、`addon`、`action_end`；数据字段同客户端构造函数（`netwar.DO_S_WAR_PERFORM`、`war2021_net.AttackCmd`/`WstateCmd`/`WstateSplitCmd`/`StatusCmd`/`AddonCmd`），单位字段（`attacker_id`、`victims`、`victim_id`、`wid`、`aid`）可写 `e0`/`self`/`pet` 等标签或 wid；原始 `perform` 的 `victims` 可为空列表（无目标技能），简写必须非空。不提供 `delete`（会删掉真实战斗的单位）和 `turn`（`war.turn()` 会发包导致回合失步）。
- **入队**：一次 `execute_code` 内完成，复用 `war_act` 的场面映射。出手直接调 `netwar.DO_S_WAR_PERFORM`（由它分流新战斗、Timeline、老战斗），其余命令直接构造 `war2021_net` 的命令对象（构造即入队）。最后加完成哨兵（`war.CCmd`，执行时置 `state`、减回 `Turn`、写标记、`next_cmd`；不用 `war.push_war_cmd`，它在 `war.WarFlag` 为假时静默不入队），`war2021_net.LastCmd = None` 后调 `war2021_net.manage_cmd(war.AccTurn)` 把受击、血条、Buff 挂到出手下面（不挂会不扣血、不飘字）。构造中途出错时删除本次入队的全部命令。
- **`war.Turn`**：下指令阶段 `war.Turn` 为 0，而 `war.perform`、`attack_normal` 等在 `Turn == 0` 时一直等待（`war.py:9286`、`6369`）。注入时 `war.Turn += 1`，哨兵执行时 `-= 1`（用增减而非赋值：注入期间若收到服务端回合包，`Turn` 会被正常累加）；构造失败时同样减回。
- **完成**：本机轮询哨兵标记（`sys._mhxy_case_pump` 等于本次编号）且命令队列为空、处理函数回到 `wait_cmd`；超时则失败，记录当时的 `war.Turn`、处理函数、标记和队列（类名、处理函数名）。超时后不自动清理，按标记区分两种情况：哨兵未执行（`war.Turn` 仍含注入时加的 1，实际值见记录），或哨兵已执行但队列里排进了服务端回合协议；步骤失败即停止，用例里后面的 `$at kill` 不会执行，需要执行者手动结束战斗。等待表达式本身报错时按原错误报告，不算超时。
- **风险**：服务端回合倒计时可能在播放途中到点，回合协议会排在注入命令之后；技能较长时先用 GM 关闭倒计时。部分特殊门派技能依赖扩展字段 `info` 或前置协议，只发出手会走降级分支，这类用 `events` 补齐。

## 流程与文档

- **test 任务**：执行者优先写用例文件、用执行器跑；出问题时排查用例或报告缺陷。用例文件写在 `.mhxy-workspace/cases/` 内。
- **用例留档**：真机自检通过的用例，由主会话写入项目 spec 的「测试用例」一节（json 代码块）。
- **回归例外**：spec 中已有用例的回归，主线程可以直接运行执行器（加锁 → 运行 → 核对报告和恢复 → 释放），不委派。用例需要修改或运行失败需要排查时，仍委派。
- **game-debugging.md**：新增「用例执行器」一节，含标准测试骨架（清场 → 造局 → 执行 → 收集证据 → 恢复）、格式和预设；开头的委派规则加上回归例外。
- **cli.md**：test 结果字段加 `executed`；test 任务的 `write_dirs` 用 `.mhxy-workspace/cases`。
- **test 沙箱联网**：执行器由 Codex 在命令行运行，要直连 mh-game-mcp 的 HTTP 入口，而 `workspace-write` 沙箱默认禁止命令联网。`codex_cli.py` 只给 test 任务加 `sandbox_workspace_write.network_access=true`（用户确认）；investigate、review 仍是只读、不联网。
- 设计借鉴：war-test 的声明式用例、执行清单和本机侧等待；mh-game-mcp-coverage-tester 的可恢复 Mock 和监听基线；client-loop-test 的 MCP 返回解包。

## 风险

- 预设表达式判断不准会导致等待超时；以超时失败报告，不静默通过。
- 每次调用约 2.8 秒的往返是 mh-game-mcp 服务本身的耗时，执行器只能减少调用次数；`wait_for` 的轮询间隔实际由往返时间决定。
- 回归由主线程直接操作客户端，要严格按锁和恢复核对执行。

## 验收

- 单元测试（`tests/test_case_runner.py`，execute_code 在本进程内模拟执行）：用例校验、占位符、从 spec 读取用例、patch Mock 安装／还原（含继承属性、安装失败、网络中断后仍还原）、自定义 Mock 的核对、等待预设和超时、GM／mcp 参数、收集到报错判失败、执行检查、报告保存和退出码。
- 真机：一个通用用例（读角色信息 + Mock 安装与还原）一次跑完，用时明显少于 11 分钟；一个战斗用例（GM 进战斗、等回合、断言、离开战斗）跑通，验证战斗预设；人为让一步失败，确认 Mock 仍被还原、`restoration` 正确。

## 变更记录

- 2026-11-05（0.3.28）：初版。
- 2026-11-05（0.3.29）：新增 `war_act`、场面映射、`setup`、`record`、`frames`、`screenshot`、预设 `war_action`、用例模板与 `search`。
- 2026-11-05（0.3.30）：新增 `pump`（真实战斗内注入技能表现）。
