# 游戏 MCP 调试

在用户或内部流程需要 Mock、调试、debug、运行时探测或自测时先读取本文件。仅分析或生成代码时不操作游戏；实际执行要遵循任务授权。

要实际操作客户端的测试——第 5 步真机自检、用户临时要求的 Mock／跑测／自测、覆盖率跑测——一律委派执行（见 [cli.md](cli.md)），主线程不自己跑。唯一例外：只调用一次、只读的探测（如读一个变量、确认客户端状态），主线程可以直接做。本文件是客户端操作和恢复规范，测试执行者和例外情况下的主线程都遵守。

## 选择设备

设备由主会话确定，不需要用户确认，也不需要用户打开客户端：

1. 用户指定了 `devid`（包括 Hunter 链接参数）就用它；不可用时报告，不要擅自换角色。
2. 未指定时，先按 spec 和本次改动决定测哪几端，不问用户：只有 PC 走得到的改动（如 `win32/` 下的文件）测 `pc`；只有互通走得到的（如 `mobile/` 下的文件）测 `ht`；PC 与互通两端都会走到的公共逻辑，或判断不了时，两端都测。每一端各运行一次 `client_launch.py select --root "<项目>" --platform <pc|ht>`（用 Bash 工具的 `run_in_background`），各得一台设备；两次要依次运行，前一次结束再运行后一次，同时运行会选中同一个空闲账号、争用同一个启动请求；两端分别委派 test 任务，一台设备一个执行者（见 cli.md「设备锁」）。
3. `select` 在本机在线设备（`get_devices_by_ip`，同机多开的实例也会列出）中，按顺序取第一台**类型相符**（`C_app.get_platform()`：`win32` 为 PC，`mobile` 为互通）、**加载当前工作区源码**（`mainmenu.__file__` 在项目根目录下）、已登录且没有设备锁的；没有就按「自动启动客户端」启动一台。输出 `devid` 和 `how`（`online` 或 `launched`），跳过的设备和原因在 `skipped` 里，交付时一并说明。加载其他工作区或打包脚本的设备测不到本次改动，不选用。加 `--dry-run` 只扫描，给出会选用的设备或启动计划（`how` 为 `would_launch`），不启动客户端。
4. `select` 报 `mcp_error`、按 IP 查找本身失败（例如网络环境导致匹配不到）时，才用配置里的 `default_devid`，并用 `C_app.get_platform()` 确认类型相符。它明确离线、未连接或 Hunter 初始化失败时，依次尝试同一 ID 加 `_i1`、`_i2`（同机多开的实例）。都失败或没有配置时，向用户报告并询问设备 ID。其他失败按「自动启动客户端」的 `code` 处理。
5. 同一任务一直用同一台成功的设备；遇到代码异常、业务状态问题或普通超时，不要换设备。唯一例外是客户端没加载到最新代码，处理见 `exec-check.md`「准备客户端」。
6. 设备确定后，每个新的客户端操作任务或切换设备时调用一次 `init_client`。它会清除旧事件，同一任务内不要重复调用。

## 自动启动客户端

客户端以管理员身份运行，由用户安装一次的计划任务代为启动，之后不再弹 UAC。只由主会话执行（测试执行者不启动客户端），用 `scripts/client_launch.py`：

```text
python -X utf8 "<skill>/scripts/client_launch.py" select --root "<项目>" [--platform pc|ht] [--dry-run]
python -X utf8 "<skill>/scripts/client_launch.py" launch --root "<项目>" [--platform pc|ht] [--server <服务器名>] [--dry-run]
python -X utf8 "<skill>/scripts/client_launch.py" doctor --root "<项目>"
```

- **launch 做什么**：确认客户端目录的类型与 `--platform` 相符；用项目根的上一级作为 workspace（加载当前工作副本的 `mhimage/` 和 `_test/`）；查本机在线设备当前登录的账号（`loginenter.Account`），选账号池中第一个空闲账号；触发计划任务启动 `mhmain.exe` 并自动登录第一个角色；等新设备以该账号上线后输出 `devid`。默认等 240 秒，用 Bash 工具的 `run_in_background` 运行。
- **客户端类型（PC／互通）**：由客户端目录当前同步的版本决定，与 `xy1.ini` 的 `mobile_user`、分辨率无关。两个目录里的 `mhmain.exe` 是同一个启动壳，引擎是否按互通运行在编译期就定了（`C_app.get_platform()` 返回 `mobile` 还是 `win32`）。按约定 `pc_client_dir`（一般是 `mhxy_dev`）是 PC，`ht_client_dir`（一般是 `mhxy_mini`）是互通；但目录一旦放了指向 `xyq_ht` 的 `cloud_inner.json` 再同步，就会变成互通版。`launch` 启动前读该目录 `update.ini` 的 `[Setting]`（PC 有 `Arch = X64`／`X86`，互通有 `Platform = HT`），只读不改；`doctor` 在 `clients` 中列出每个客户端目录的实际类型，与配置项不符时列为问题。
- **服务器**：取工作区配置 `login_server`，`--server` 只覆盖本次。名字以“模拟”开头时用大区 `刘强98服`；其他名字在内服服务器列表中精确匹配，再做唯一的模糊匹配。没配置（`need_server`）时问用户这个分支用哪个服务器，按 workspace-management.md 保存到工作区配置；有多个候选（`server_ambiguous`）时把候选给用户选。
- **其他失败**按输出的 `code` 处理，不要重试或换方式启动：
  - `platform_mismatch`：客户端目录的实际类型（`detected`）与要求不符。报告用户，不要改 ini 硬切；把目录同步回 PC 版按 mhxy-client-sync-launch 处理，需要用户确认。`platform_unknown`：`update.ini` 读不出类型，请用户检查该目录是否完整同步。
  - `all_occupied`：账号池都被本机在线客户端占用，报告各账号所在设备，请用户关掉一个或添加账号。
  - `need_accounts`、`task_failed`、`task_no_result`、`launcher_error`：运行 `doctor`，把其中的 `fix` 交给用户（`install` 和录入密码要用户在管理员终端或交互终端执行）。
  - `bad_workspace`：例如 workspace 的 `_test/mhimage.wdf` 存在，客户端会加载打包脚本而不是源码。告诉用户，由用户决定是否移走，不要自行删除。
  - `device_timeout`：客户端已启动但没等到登录，查对应进程号的日志，报告用户。
- 只查得到本机的设备；账号在其他机器上登录时会被顶下线或登录失败。读不出账号的设备列在 `unknown_devices` 中。
- 用完不自动关闭客户端。不要用打包服务（mh-patch-mcp 的 `control_aluba_client`）代替：它拉起的是 aluba 自我验证循环，不能指定 workspace 和账号。
- **部署**（新电脑或重装后）：先把 skill 链接到位，再在管理员 PowerShell 运行 `client_launch.py install`（全机一次，与工作区无关，可重复执行；客户端目录变化或 skill 更新启动器后要重新运行），然后按 workspace-management.md 录入账号池。`doctor` 列出还缺什么；`uninstall` 删除计划任务。

## 找到并调用工具

- **先看实际工具定义，不要猜参数。**
- **Claude Code**：MCP 工具名形如 `mcp__mh-game-mcp__execute_code`，可能是延迟加载的，不在初始工具列表里。判断“未接入”之前，先用 ToolSearch 搜索 `execute_code` 和 `init_client` 并加载定义，搜不到才算未接入。
- **选工具**：
  - 状态、UI、NPC、移动、背包等，优先用专用工具：
    - UI：`get_ui_navigation` → `get_top_panel` → `get_panel_interactive_widgets`；改控件前先看 `get_ui_control_docs`，再 `set_ui_data`。
    - NPC：`goto_npc`／`click_npc` → `get_npc_chat` → `click_option`／`answer_question`。
    - 移动：`walk_to` 是异步的，用 `get_distance` 验证到达；`goto` 是跳转，不等于普通寻路。
  - 游戏指令用 `execute_command`；不确定指令时先用 `search_chat_cmd`。
  - 专用工具覆盖不了的探测、函数调用和 Mock，用 `execute_code`。
  - 客户端代码不要发给 MOS2 服务端工具。
- **`execute_code` 的写法**：传 `devid`、多行 `code` 字符串和 `need_loginfo: true`。先核对目标函数、参数和前置状态，按客户端的 Python 版本编写。封装成函数时把 import 放在函数内，最后一行用裸表达式取返回值。代码用分开的 globals／locals 执行，顶层定义的名字在函数里看不到：函数不能引用其他顶层函数或变量，需要共用的逻辑放进同一个外层函数，或作为参数传入。只返回精简数据；不要假设局部变量能跨调用保留，不要阻塞主线程，没有依据不要 reload。

## HTTP 保底脚本

MCP 工具没有接入时，使用本 skill 的两个保底脚本：

```text
python -X utf8 "<skill>/scripts/game-debugging/mcp_eval.py" "<UTF-8代码文件.py>" "<devid>"
python -X utf8 "<skill>/scripts/game-debugging/mcp_call.py" <工具名> < "<UTF-8参数.json>"
```

- `mcp_eval.py` 调用 `execute_code`；`mcp_call.py` 用于其他工具，如 `init_client`、`execute_command`、`get_devices_by_ip`。参数 JSON 示例：`{"devid":"<devid>","command":"$at ..."}`。
- 第二条命令是 Bash 语法（stdin 重定向）。其他 shell 用等价的 UTF-8 文件输入，避免手拼引号和美元符号。
- 脚本的握手不能代替 `init_client`。
- 脚本从普通 JSON 或 SSE 响应中取出与请求 id 对应的结果；返回 JSON-RPC error 或找不到结果时以非 0 退出，后者会打印原始响应。退出码 0 只说明取到了工具的 `result`，业务是否成功仍按「读取结果与处理失败」检查。
- 网络故障或执行结果不明时，不要换另一个通道重复执行。

服务入口是 `https://mh-game-mcp.eros.nie.netease.com/mcp`，配置连接时使用这个完整地址：
- Codex：`~/.codex/config.toml` 中的 `[mcp_servers.mh-game-mcp]`。
- Claude Code：`claude mcp add --transport http --scope user mh-game-mcp <入口>`，新会话生效。

## 读取结果与处理失败

- 先检查 MCP 或工具本身是否报错。成功时优先取 `structuredContent`，没有就解析 `content` 里的 JSON 文本。客户端结果在业务载荷的 `result` 中：`ret` 是返回值，`error` 是异常，`loginfo` 是打印输出。
- `error` 不为空时保留完整堆栈。`ret: null` 可能是正常返回；但整个响应为 null 或无法解析时不代表成功，要先检查实际响应，不要盲目重放。
- 超时、断线和部分异常可能发生在操作已经生效之后。先核对状态，确认未执行或可以安全重复后再重试。只针对明确的错误修正，通常最多自动修正 1–2 次。
- 优先使用工具返回中已带的 `client_event`。`get_client_event` 读取后会清空，不要反复读取；也不要让多个代理并行操作同一台设备或争抢事件。

## 收集客户端报错

`execute_code` 的 `error` 只包含这次调用当场抛出的异常。移动、点击 NPC、操作界面、服务端指令回包后的刷新，以及定时器和事件回调里的报错，都发生在之后的帧，不会出现在返回里；日志文件也不一定及时刷新。需要确认一段操作没有报错时，用报错收集模板 `scripts/game-debugging/error_watch.py`：

1. **开始**：操作前发送该文件全文，最后一行写 `error_watch_start()`。它会在客户端 `log.py` 的 `MHXY` logger 上挂一个内存 handler，收集 ERROR 级别的记录（含堆栈）。返回的 `stale` 不为空，说明上次的收集没有正常结束，其中的记录要单独说明，不能算在本次操作里。
2. **操作**：照常调用工具或 `execute_code`。
3. **结束**：操作完成后，再等 2～3 秒让延迟执行的代码跑完；然后发送该文件全文，最后一行写 `error_watch_finish()`。它返回这段时间的记录，并卸载 handler。开始之后无论操作是否成功，都要执行这一步。

- **判断**：逐条区分与本次操作有关的报错和无关的报错，无关的也要列出并说明理由。最多保留 50 条，`dropped` 大于 0 时说明报错过多，需要先处理。
- **收集不到的**：引擎层崩溃、不经过 Python logger 的错误、其他线程中的错误。
- **使用范围**：Mock 与自测、覆盖率跑测（`coverage.md`）和改动执行检查（`exec-check.md`）都用这套方法，各文档只引用本节。

## Mock 与验证

- 替换前保存原来的函数、属性、模块和监听状态。同步 Mock 用 `try/finally` 恢复：原先不存在的属性要删除，新增的监听要解除。跨调用或异步的 Mock，要明确保存位置、完成条件和恢复步骤，观察完成后再恢复；中断后检查残留，无法恢复时如实报告。
- 控件 ID、物品位置、NPC 序号都从当前状态获取。异步的移动、UI 操作和服务端指令，通过后续状态来验证。
- 沿 `get_parent()` 向上遍历控件（找顶层对话框、判断实际显隐等）时，必须同时设最大步数（如 32）和按 `get_instance()` 去重的已访问集合，遇到 `None`、实例为 0、已访问或超过步数就停止，并在返回值中标明停止原因。部分 UI 的父链在顶层会成环（已见于 HT 奇袭召唤兽面板），没有保护的遍历会死循环，可能导致客户端无响应。其他 `while` 循环同样要设上限。
- 判断操作是否报错，以「收集客户端报错」的结果为主，日志文件只作补充。日志在对应客户端（`pc_client_dir` 或 `ht_client_dir`）的 `Log/` 下，文件名带进程号（`log_<pid>.txt`、`errorlog_<pid>.txt`）。同机多开时，几个客户端共用这个目录，先用 `execute_code` 取 `os.getpid()` 确认是哪个文件，只看操作前后的内容。
- 交付时分别说明代码是否成功、客户端表现是否正确、服务端是否生效，并说明证据、未验证的范围和临时状态的恢复结果。用户明确要求保留的状态，按任务目标处理。

## 服务端指令

- 前缀：普通服 `$`，战斗服 `$%`，客户端 `$$`。服务端 `$call 文件->函数(...)` 中的 `$id` 是自己 uid 的占位符，不能改写成客户端 `$$call`。不要给已有前缀的指令重复拼接，也不要凭前缀猜执行权限。
- 指令回显在聊天的 254 频道（`RECV_SYSTEM_MSG`）。
- 改运行期变量（run_conf）：`$call 文件->wizcmd($id, "ls 变量")`／`"set 变量 值"`／`"reset_conf 变量"`。改之前记下原值和是否已被覆盖，测试结束恢复：原来是默认值就 `reset_conf`，原来有覆盖值就设回原值。update 不会清掉覆盖值，只有重启才恢复默认。

## 战斗测试

- 开始：`$at fightN <敌方单位数量>` 进入机器人测试战斗。结束：`$at kill`，不要用 `$halt`（可能导致崩溃）。
- 每回合人物和在场召唤兽都要下指令。`$at ka` 会让回合超时失效，只给人物下指令时服务端会一直等召唤兽；卡住时用 `$at ka 0` 解除，或给召唤兽下防御、攻击指令。
