# 游戏 MCP 调试

在用户或内部流程需要 Mock、调试、debug、运行时探测或自测时先读取本文件。仅分析或生成代码时不操作游戏；实际执行要遵循任务授权。

## 选择设备

1. 用户指定了 `devid`（包括 Hunter 链接参数）就用它；不可用时报告，不要擅自换角色。
2. 未指定时用 `get_devices_by_ip` 查找，参数传 `{"ip": ""}`（空字符串表示查找本机发起请求的 IP 上的设备；同机多开的实例也会列出）。只有 1 台就直接用；有多台时问用户，若其中有配置的 `default_devid`，作为推荐选项。
3. 查找失败或结果为空时（例如网络环境导致按 IP 匹配不到），才用配置里的 `default_devid`。它明确离线、未连接或 Hunter 初始化失败时，依次尝试同一 ID 加 `_i1`、`_i2`（同机多开的实例）。都失败或没有配置时，向用户报告并询问设备 ID。
   - 找不到设备通常说明客户端没有启动。客户端由用户自己通过 Sunshine 启动：请用户启动并登录后告知，再重新查找。agent 不要自行运行客户端程序，也不要用打包服务（mh-patch-mcp 的 `control_aluba_client`）代替。
4. 同一任务一直用同一台成功的设备；遇到代码异常、业务状态问题或普通超时，不要换设备。
5. 设备确定后，每个新的客户端操作任务或切换设备时调用一次 `init_client`。它会清除旧事件，同一任务内不要重复调用。

## 找到并调用工具

- **先看实际工具定义，不要猜参数。**
- **Claude Code**：MCP 工具名形如 `mcp__mh-game-mcp__execute_code`，可能是延迟加载的，不在初始工具列表里。判断“未接入”之前，先用 ToolSearch 搜索 `execute_code` 和 `init_client` 并加载定义，搜不到才算未接入。
- **选工具**：
  - 状态、UI、NPC、移动、背包等，优先用专用工具。
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
- 脚本只解析 SSE 返回中的 `data: ` 行，不能只凭进程退出码判断成功。
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
- 判断操作是否报错，以「收集客户端报错」的结果为主，日志文件只作补充。日志在对应客户端（`pc_client_dir` 或 `ht_client_dir`）的 `Log/` 下，文件名带进程号（`log_<pid>.txt`、`errorlog_<pid>.txt`）。同机多开时，几个客户端共用这个目录，先用 `execute_code` 取 `os.getpid()` 确认是哪个文件，只看操作前后的内容。
- 交付时分别说明代码是否成功、客户端表现是否正确、服务端是否生效，并说明证据、未验证的范围和临时状态的恢复结果。用户明确要求保留的状态，按任务目标处理。

## 战斗测试

- 开始：`$at fightN <敌方单位数量>` 进入机器人测试战斗。结束：`$at kill`，不要用 `$halt`（可能导致崩溃）。
- 每回合人物和在场召唤兽都要下指令。`$at ka` 会让回合超时失效，只给人物下指令时服务端会一直等召唤兽；卡住时用 `$at ka 0` 解除，或给召唤兽下防御、攻击指令。
