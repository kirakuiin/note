# CLI 测试执行

仅 GPT 顶层主会话在 mhxy 工作区执行本流程；非 GPT 主会话、设计和代码审查沿用原流程。受委派的 CLI 只执行测试，不再次委派，也不与用户核对需求。

## 分工与边界

- 主线程先确定授权范围、目标代码／提交、设备、用例和断言、Mock 方案、允许写入的测试目录与恢复步骤，再委派 Codex CLI，固定 `gpt-6-luna`、`max`。不是每个接口参数都要预先写死，执行者可查询接口、补充局部探测和修正测试脚本。
- CLI 可写测试／Mock 脚本，不修改业务源码。发现业务缺陷、需要改变测试目标或 Mock 方案、状态不明或无法恢复时停止并返回证据，由主线程判断。
- Mock、自测与执行检查遵循 `game-debugging.md`、`exec-check.md`；覆盖率任务遵循 `coverage.md`，包括已授权的创建／复用、设置、跑测、上传、查询与补测。委派不增加授权，不自动删除任务、修改统计范围或绕过原有确认。
- 同一设备只允许一个测试执行者。主线程可做独立工作，不改被测文件、不操作该设备；本轮保持运行，收到通知后在当前独立操作结束时核验并向用户汇报，再结束本轮。

## 统一脚本

使用本 skill 的 `scripts/cli_testing.py`，需要 Python 3.11+（标准库 `tomllib`）和已安装的 Codex CLI；工作区其他脚本仍支持 Python 3.10+。任务文件为 UTF-8 JSON，不放密码、令牌或认证头：

```json
{
  "devid": "已选定的设备ID",
  "instructions": "目标、用例与断言、Mock方案、停止条件和恢复步骤",
  "references": ["需要执行的 coverage.md 或 exec-check.md 的绝对路径"],
  "mcp_tools": {"mh-game-mcp": ["init_client", "execute_code", "get_game_status"]},
  "write_dirs": ["当前项目 .mhxy-workspace 内允许写入的测试目录"]
}
```

主线程根据计划给出实际需要的 MCP 工具，不机械照搬示例。脚本只对这些工具设置 `approve`，临时接入游戏 MCP；其他 MCP 禁用，配置不落入全局文件。CLI 在任务目录运行，额外可写目录限于本项目 `.mhxy-workspace/` 内且不允许链接。项目 AGENTS.md、调试规范和本文件自动传入任务；其他所需 reference 由主线程列出。CLI 可读取源码，但写权限只用于辅助测试目录；沙箱不隔离远端游戏状态。

```text
python -X utf8 "<skill>/scripts/cli_testing.py" start --root "<项目>" --task-file "<任务.json>"
python -X utf8 "<skill>/scripts/cli_testing.py" status --job "<start返回的任务目录>"
python -X utf8 "<skill>/scripts/cli_testing.py" wait --job "<任务目录>" --timeout 30
python -X utf8 "<skill>/scripts/cli_testing.py" cancel --job "<任务目录>"
python -X utf8 "<skill>/scripts/cli_testing.py" release --job "<任务目录>" --restored
```

- `start` 后台启动，返回任务目录；`status` 读取状态，`wait` 在完成时立即返回，等待上限到达则返回当前状态。两者均输出 JSON；测试结论看 `result`，不能凭退出码或 `completed` 判定通过。
- 当前 Codex 宿主用 `exec_command` 启动 `start`：FastCtx `run` 可能在命令结束时回收后台进程，不适合承载本脚本的后台启动。若宿主会回收子进程，用其持久终端运行任务目录的 `_worker --job`，并确认状态已进入 `running`；不得因启动命令返回就认定任务仍在运行。
- 从启动或最后一次 CLI stdout／stderr 输出开始，连续 **600 秒无输出**则杀掉 CLI 进程树，保留日志并标记 `timed_out`；没有总时长上限。脚本自己的心跳不刷新计时，任意实际 CLI 输出都会刷新；这表示输出活跃，不保证业务有进展。
- `cancel` 请求监控器停止 CLI，不自动重跑。任务终止后设备锁仍保留，主线程核对／恢复 Mock、监听器、追踪器和报错收集器后调用 `release --restored`；不能把杀进程当成恢复客户端。其他手工操作与进程不受此锁管理。
- 结果含用例、断言、报错证据、未覆盖范围和恢复状态。CLI 退出却没有完整结果、模型执行失败或工具失败均不能算测试通过。中断留下的恢复状态默认未知。

## 异步回报

脚本本身不唤醒主会话。Codex 当前宿主可用 `functions.exec` 保持异步监控：调用上述 `wait`，`exec` yield 后主线程继续工作，监控结束通过 `notify` 注入工具结果。示意如下（命令路径和任务目录用宿主正确的 shell 引号构造）：

```javascript
// @exec: {"yield_time_ms": 1000}
let r = await tools.exec_command({cmd: waitCommand, yield_time_ms: 1000});
while (r.session_id) {
  r = await tools.write_stdin({session_id: r.session_id, chars: "", yield_time_ms: 1000});
}
notify({event: "cli_testing_finished", output: r.output, exit_code: r.exit_code});
```

异步 cell 必须持续 await 到监控结束；不要启动未 await 的 promise 后退出，也不要 terminate 仍在监控的 cell。结束后可用 `functions.wait` 回收 cell，回收不是通知前提。此路径只保证仍在运行的本轮收到事件，不保证本轮结束后自动唤醒。其他宿主没有该能力时，用有界 `wait`／`status`，如实说明差异。设备恢复后再允许下一项客户端任务。
