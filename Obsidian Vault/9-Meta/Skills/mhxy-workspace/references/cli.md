# Codex 委派

开发流程中的调查、review 和真机自检交给 Codex 执行，主会话只下达任务、判断结果。Claude 主会话用脚本调起 Codex CLI，Codex 主会话用原生子代理；两者共用「共用」中的任务模板和结果格式。

## 共用

### 何时委派

| 类型 | 用在 | 权限 |
| --- | --- | --- |
| investigate | 讨论需求时读代码、还原执行路径、确认影响范围 | 只读，可开放列出的只读 MCP 工具 |
| review | 第 4 步 Codex review，审查清单、收敛条件和 3 轮上限见 [code-review.md](code-review.md) | 只读，不接入 MCP |
| test | 第 5 步真机自检，默认做改动执行检查（[exec-check.md](exec-check.md)）；客户端操作、Mock 和恢复按 [game-debugging.md](game-debugging.md) | 只写 `.mhxy-workspace/` 内的测试目录，只开放列出的 MCP 工具 |

- 受委派方是执行者：不得派生、调用或者请求新的子代理，不与用户核对需求。需要用户判断的事项写进结果返回，由主会话处理。
- 项目 AGENTS.md 受管区段中的「会话开始」「开发流程」「按需读取」是主会话规则，执行者不执行，只遵守「项目约定」「边界」和任务给的 references。`codex_cli.py` 已写入提示；Codex 主会话在任务说明里写明。
- 委派不增加授权。覆盖率任务仍按 `coverage.md` 的确认要求，破坏性 GM 指令要在任务里预先授权。

### 任务内容

任务文件是 UTF-8 JSON，不放密码、令牌或认证头。所有类型都有：

- `instructions`（必填）：要做什么、判断标准和停止条件。
- `references`（可选）：额外要读的文件的绝对路径，追加在默认列表之后。默认列表：项目 `AGENTS.md`；review 加 `code-review.md`、`engineering-principles.md`；test 加本文件、`game-debugging.md`、`exec-check.md`。

**investigate**：`instructions` 写清问题和已知线索，需要的话限定范围（模块、分支）。可选 `mcp_tools` 按服务列出要用的只读工具，例如 `{"codeviewer-mcp": ["get_commit_info_by_rid"]}`；只允许 `codeviewer-mcp`、`expert_knowledge`，服务定义（含认证头）从用户 Codex 配置复制，只开放列出的工具。

例如迭代已有功能时查找原 spec：写明要改的代码文件和工单号，`mcp_tools` 列出 codeviewer 的 `get_commit_info_by_rid`，要求按 engineering-principles.md「迭代已有功能」的查找顺序返回候选 spec 及依据。

**review**：`instructions` 提供哪些信息、不提供什么、各轮如何续接，见 [code-review.md](code-review.md)「委派与审查信息」。续接时 Claude 主会话加 `--resume "<上一轮 review 任务目录>"`，Codex 主会话继续发给同一个 reviewer。

**test**：另有以下字段。

```json
{
  "devid": "已选定的设备ID",
  "instructions": "目标代码、用例与断言、Mock 方案、已授权的 GM 指令、停止条件和恢复步骤",
  "mcp_tools": {"mh-game-mcp": ["init_client", "execute_code", "get_game_status"]},
  "write_dirs": ["<项目>/.mhxy-workspace/exec-check"]
}
```

- 设备按 game-debugging.md「选择设备」由主会话用 `client_launch.py select` 自动确定（没有合适的在线设备时会自动启动客户端），不需要用户确认。一个 test 任务只对应一台设备；PC 和互通都要测时分成两个任务。
- `mcp_tools` 按计划列出实际要用的工具，不照抄示例；其他 MCP 一律不接入。
- `write_dirs` 必须是 `.mhxy-workspace/` 内的子目录，不能经过链接。执行者可写测试和 Mock 脚本，不改业务源码；发现业务缺陷、需要改变测试目标或 Mock 方案、状态不明或无法恢复时停止并返回证据。
- 执行者不能写 `.mhxy-workspace/tracking.json`。覆盖率跑测的本地登记由主会话按结果完成，任务要返回的内容见 [coverage.md](coverage.md)「跑测流程」第 2 步。

### 读取结果

| 类型 | 结果字段 |
| --- | --- |
| investigate | `conclusion`；`evidence`，每条“文件:行号 —— 说明”；`uncertainties`，未确认的事项和最快的验证方法 |
| review | `summary`；`items`，每条有 `level`（必须修改／建议修改／疑问）、`location`（文件:行号）、`problem`、`basis`、`suggestion`。脚本另给 `formatted`（`[级别] 文件:行号 —— 问题；依据；建议`）和 `must_fix` 条数 |
| test | `status`（passed／failed／blocked）、`cases`、`errors`、`unverified`、`restoration`（restored／unknown／not_needed） |

- 只看结果内容下结论。退出码为 0、任务 `completed` 都不等于调查正确、审查通过或测试通过；没有完整结果、模型或工具失败都不算通过。
- 结果是证据，不是结论：主会话逐条核对后再采纳，review 意见的处理见 code-review.md。

### 设备锁

- 同一设备同时只允许一个测试执行者，跨工作区也一样。test 任务启动时加全机设备锁（Codex 主会话用 `lock`，见「Codex 主会话」），任务结束后锁仍保留。
- 任务结束（包括取消、超时）后，主会话核对并恢复 Mock、监听器、追踪器和报错收集器，再执行 `release --restored` 释放；杀进程不等于恢复了客户端。中断留下的状态默认未知。
- `release` 可以重复执行，只删除属于本任务的锁；它会复核后台监控和 CLI 进程都已退出（按记录的进程创建时间排除 PID 复用），否则拒绝并保留锁。监控异常退出而 CLI 仍在运行时，`status` 记为 failed 并给出 `orphan_cli_pid`，此时 `cancel` 已无效：确认是该任务的 Codex 进程后手动结束其进程树，再核对恢复并 release。
- 测试期间主会话可以做独立工作，但不改被测文件、不操作该设备。

## Claude 主会话

用本 skill 的 `scripts/codex_cli.py`，需要 Python 3.11+（标准库 `tomllib`）和已安装的 Codex CLI。默认模型 `gemini-4-argon`、推理强度 `medium`；`start` 可用 `--model`、`--effort` 指定其他模型和强度。

```text
python -X utf8 "<skill>/scripts/codex_cli.py" start --root "<项目>" --kind <investigate|review|test> --task-file "<任务.json>" [--resume "<上一轮 review 任务目录>"] [--model <模型>] [--effort <强度>]
python -X utf8 "<skill>/scripts/codex_cli.py" wait --job "<任务目录>" --timeout 3600
python -X utf8 "<skill>/scripts/codex_cli.py" status --job "<任务目录>"
python -X utf8 "<skill>/scripts/codex_cli.py" cancel --job "<任务目录>"
python -X utf8 "<skill>/scripts/codex_cli.py" release --job "<任务目录>" --restored
```

- `start` 启动后台进程后立即返回任务目录（`<项目>/.mhxy-workspace/codex-cli/<任务>/`）。随后用 Bash 工具的 `run_in_background` 运行 `wait`，主会话继续其他工作，任务结束时会收到通知；`wait` 到时仍未结束就再运行一次。各命令都输出 JSON，状态有 starting、running、completed、failed、timed_out、cancelled。
- 模型走用户 Codex 配置里的模型连接（如 CodeMaker 代理），可选模型名取自其 `model_catalog_json`（如 `gemini-4-argon`、`claude-opus-5-5`、`glm-5.3`）。配置了目录时，`start` 会校验模型名和强度，填错直接报错并列出可选项；不指定强度时用 `medium`，该模型不支持就用它的默认档位。review 续接（`--resume`）不指定模型时沿用上一轮的。实际用的模型和强度记在任务 `state.json` 的 `model`、`effort`。
- 结果格式：提示末尾总会附上结果的 JSON Schema。只有 `gpt-*` 模型另加 `--output-schema` 强制结构化输出，因为 Gemini 带上这个参数会被上游以 400 拒绝，GLM 等模型也不会执行它。非 GPT 模型的结果允许外面包一层代码块，字段校验不放宽。Claude 系列受公司高价模型额度限制，未验证。
- 连续 600 秒没有任何 CLI 输出时，杀掉进程树并标记 `timed_out`；没有总时长上限。`cancel` 只停止，不自动重跑。
- 子 Codex 带环境变量 `MHXY_CODEX_CHILD=1`，在这个环境里 `start` 会拒绝运行；同时关闭子代理、hooks 和插件，不加载任务未列出的 MCP。

## Codex 主会话

不调用脚本，直接派生原生子代理：investigate → `investigator`，review → `reviewer`，test → `verifier`。

- 每次派生都传 `fork_turns = "none"`，不继承主会话历史。
- 任务说明按「共用」的模板写，开头写明“你是受委派的执行者，不得派生、调用或者请求新的子代理”，并要求按「读取结果」中对应类型的字段返回。
- 模型和推理强度由角色配置决定，不在任务里指定。
- review 第 2 轮起把新信息发给同一个 reviewer，不另起新的。
- 真机自检与 Claude 主会话共用同一把全机设备锁，规则见「设备锁」。派生 verifier 前加锁，报设备已被占用时不要派生；verifier 结束、主会话核对并恢复客户端后释放：

  ```text
  python -X utf8 "<skill>/scripts/codex_cli.py" lock --root "<项目>" --devid "<设备ID>"
  python -X utf8 "<skill>/scripts/codex_cli.py" release --job "<lock 返回的 job>" --restored
  ```

  `lock` 只建 status 为 `native` 的 test 任务目录（clean 同样会等它 release），不启动 Codex，不受 `MHXY_CODEX_CHILD` 限制；需要 Python 3.11+。这类任务不能 `wait`／`cancel`。
