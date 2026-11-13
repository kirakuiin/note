# 客户端覆盖率（mh-game-mcp 直跑版）

用户明确要求覆盖率的创建、设置、跑测、补测、查询或提交时读取本文件。

- **只统计已提交代码**：覆盖率网站只按当前 SVN 分支的**已提交（committed）**代码计算应覆盖行，不统计本地未提交修改。跑覆盖率前先确认目标改动已 `svn commit`。
- **确认任务身份**：
  - `redmine_id`：程序开发单或总单号（纯数字），不明确时先问用户。
  - `task_name`：覆盖率任务名，**必须由用户确认**，不要自行编造。
  - `coder_name`：默认从 `~/.mhxy-workspace/config.json` 的 `coder_name` 或 `openid_username` 前缀读取，也可传 `--coder-name`。
  - `branch`：仓库相对路径（如 `branchs/2026_dev/xxx`、`trunk`）。`coverage_query.py` 省略 `--branch` 时会自动在 `--root` 下执行 `svn info` 推断。

---

## 1. 选择并初始化客户端设备

1. 用户指定了 `devid` 就直接用；未指定时调用 `mh-game-mcp` 的 `get_devices_by_ip`（传 `{"ip": ""}`）获取本机在线设备。
2. 多台设备在线时，用 `execute_code` 探测各设备的账号、平台和实际加载的源码路径：
   ```python
   (lambda s: {
       "account": getattr(s.modules.get("loginenter"), "Account", None),
       "source": getattr(s.modules.get("mainmenu"), "__file__", None),
       "platform": getattr(s.modules.get("C_app") or __import__("C_app"), "get_platform", lambda: None)(),
   })(__import__("sys"))
   ```
   选择已登录且 `source` 位于当前工作区目录下的设备；不明确时询问用户。
3. 选定设备后，开始新任务时调用一次 `init_client` 清空残留事件日志。

---

## 2. 创建或绑定覆盖率任务

1. **先查网站或客户端是否已有该任务**：
   - 可先运行一次网站查询脚本（见第 4 节）看远端任务是否已存在。
2. **远端任务不存在 → 创建任务**：
   - 调用 `execute_command` 发送：
     ```text
     $$scover_create <redmine_id> <task_name> <coder_name>
     ```
   - 注意：`$$scover_create` 在客户端 `thread_pool` 异步执行，“指令已发送”不代表创建成功。等待几秒后，用 `coverage_query.py` 查询网站或用 `execute_code` 检查 `SCover.run_var.get_cov_mgr().get_task('<task_name>') is not None` 核实创建成功，且检查网站的统计范围（`required_count > 0`，不能接受空范围的 100%）。
3. **远端任务已存在 → 绑定采集**：
   - 调用 `execute_command` 发送：
     ```text
     $$scover_set <task_name>
     ```
   - 用 `execute_code` 核实任务已在采集中：
     ```python
     import SCover.run_var as rv
     task = rv.get_cov_mgr().get_task('<task_name>')
     {'tracing': task is not None, 'revision': getattr(task, 'revision', None)}
     ```

---

## 3. 用 mh-game-mcp 执行被测逻辑并上传覆盖率

### 编写 `execute_code` 的关键规则
- `execute_code` 使用独立的 `globals`/`locals` 执行，**顶层定义的变量或函数在其他函数内部看不到**：需要共用的逻辑全部放进同一个外层函数里，或通过默认参数绑定（如 `def fn(_orig=orig):`），最后一行写函数调用表达式返回值。
- **严禁伪造覆盖**：必须调用客户端已加载的**原始业务模块和函数**；禁止把业务函数拷出来离线执行、禁止替换掉被测函数本身、禁止手工修改覆盖率统计范围。
- **Mock 必须完整恢复**：替换属性、网络发包或配置前先备份原值（区分实例自身属性与类属性），在 `try ... finally` 中无条件还原；新增的事件监听必须在 `finally` 中解除。

### 标准单轮跑测步骤

1. **造前置状态 + 开启报错收集**：
   - 如果被测逻辑依赖特定状态（如战斗 UI 需先进出一次 `$at fightN 1` / `$at kill`），先准备好前置状态。
   - 读取 `<skill>/scripts/error_watch.py` 全文，在末尾追加一行 `error_watch_start()`，通过 `execute_code` 发送，开始收集运行期 `ERROR` 日志与异常堆栈。
2. **确认采集开启**：
   - 发送 `execute_command`：`$$scover_set <task_name>`，确认 `get_cov_mgr().get_task('<task_name>')` 非空。
3. **执行 Mock 与被测代码**：
   - 根据目标提交 diff 和网站未覆盖行，通过 `execute_code` 在 `try ... finally` 中安装临时 Mock、调用原始被测函数、断言关键返回值与状态，并在 `finally` 中恢复所有 Mock。
4. **记录上传前时间戳（带时区）**：
   - 通过 `execute_code`（或本机 Python）记录当前带时区的 ISO 时间，作为后续网站查询的 `--submitted-after`：
     ```python
     __import__('datetime').datetime.now().astimezone().isoformat(timespec='seconds')
     ```
5. **在主线程同步上传覆盖率**：
   - **严禁通过 `execute_command` 发送 `$$scover_finish`**：`$$scover_finish` 会在 `thread_pool` 线程里执行上传，而 coverage 内存数据按线程隔离，后台线程上传的是空数据。
   - 必须通过 `execute_code` 在主线程调用 `wizard_cmd.scover_finish('<task_name>', True)`，并临时包装 `api_client.commit_coverage` 校验上传真正返回 `True`：
     ```python
     def _upload_cov(task_name):
         import wizard_cmd
         import SCover.run_var as rv
         api = rv.get_cov_mgr().api_client
         own = 'commit_coverage' in api.__dict__
         orig = api.commit_coverage
         box = {}
         def record(task, *args, _orig=orig, _box=box, **kwargs):
             _box['ok'] = _orig(task, *args, **kwargs)
             return _box['ok']
         api.commit_coverage = record
         try:
             wizard_cmd.scover_finish(task_name, True)
         finally:
             if own:
                 api.commit_coverage = orig
             else:
                 del api.commit_coverage
         return {'commit_ok': box.get('ok'), 'restored': ('commit_coverage' in api.__dict__) == own}
     _upload_cov('<task_name>')
     ```
   - 确认返回 `{'commit_ok': True, 'restored': True}`。多次提交网站会自动累计合并，补测时不要调用 `clear_cov`。
6. **结束报错收集**：
   - 等待 2～3 秒让延迟回调跑完，再读取 `<skill>/scripts/error_watch.py` 全文并追加 `error_watch_finish()` 发送，检查 `errors` 中是否有与被测逻辑相关的报错。

---

## 4. 网站查询与补测判定

网站地址是 `https://mh-mos2-coverage.eros.nie.netease.com`。通过 `<skill>/scripts/coverage_query.py` 查询结果：

```bash
python -X utf8 "<skill>/scripts/coverage_query.py" --root "<工作区>" --task-name "<task_name>" --submitted-after "<上传前记录的带时区ISO时间>"
```

- **参数说明**：
  - `--branch`：一般省略，脚本会自动从 `--root` 的 `svn info` 推断仓库相对路径（如 `branchs/2026_dev/xxx`）。若不在 SVN 工作副本下运行，显式传 `--branch`。
  - `--submitted-after`：首次查询定位未覆盖行时可省略（此时状态不会判为 `passed`）；上传后查询必须传入，确保网站已处理完本轮提交。
  - `--auth-file`（或环境变量 `MHXY_COVERAGE_AUTH_FILE`）：可选，支持传入仅含 `Cookie`/`Authorization` 的本机 JSON 请求头文件代替账密登录。
- **退出码与判定**：
  - 退出码：`0` 为 `passed`，`2` 为 `incomplete`（有未覆盖行），`3` 为 `blocked` 或错误。
  - 根据返回的 `files[].missing_lines` 定位未覆盖分支，补充 Mock 后重跑第 3 节并再次上传、查询。
  - 如果只剩 `global`、多行括号等疑似 Python 不可执行行，在客户端内用字节码行表（`code.co_lines()`，含嵌套 code object）核实；确认不可执行后列出文件、行号与证据，区分“可执行行已全部覆盖”与“网站显示百分比”。
  - **最终反馈**需包含：覆盖率链接（脚本输出的 `url`）、目标分支、网站百分比、覆盖行数／总应覆盖行数、未覆盖行说明、报错收集结果及 Mock 恢复核对结果。
