# 自动启动的客户端：流程结束时关闭，空闲兜底

日期：2026-11-12　版本：0.3.41

## 目标

`client_launch.py` 自动启动的客户端以前“用完不关”，开发流程和无人值守工单跑多了会在本机留下一堆客户端，占账号、占内存。改为：只关自己开的，在整个流程结束时关；会话崩溃没人关时，由空闲兜底清理。用户手动开的、有设备锁（正在测试或待恢复）的客户端一律不动。

## 登记

- `launch`（含 `select` 触发的启动）拿到客户端进程号后立即登记，设备上线后补上 devid；`device_timeout` 的客户端也已登记（devid 为空）。
- 位置：`%LOCALAPPDATA%\mhxy-cli-testing\clients\`，与设备锁目录 `locks\` 同级；每台客户端一个文件 `<pid>-<进程创建时间>.json`，先写临时文件再 `os.replace`，不同会话并发写不同文件，互不覆盖。
- 字段：`devid`、`pid`、`created`（进程创建时间，FILETIME 整数）、`platform`、`account`、`client_dir`、`root`（启动它的工作区，项目根绝对路径）、`owner`（发起方）、`started_at`、`last_used`。
- `owner`：`--owner` 参数，没有时取环境变量 `MHXY_CLIENT_OWNER`，都没有为 null。popo-agent-service 给工单会话设 `MHXY_CLIENT_OWNER=issue:<工单号>`；交互会话不设。
- 核对：凡是要关，先用 pid 打开进程（`PROCESS_QUERY_LIMITED_INFORMATION`，普通权限对管理员进程也可用），核对进程仍在运行、创建时间与登记一致、映像名是 `mhmain.exe`；不一致说明原进程已退出（进程号可能被复用），只删除登记，不关任何进程。

## 空闲判断

- `last_used`：启动时为启动时间；之后在这些时刻刷新为当前时间——`select` 选中这台在线设备时；`codex_cli.py` `release` 释放锁时（先刷新再删锁，避免间隙里被兜底关掉；刷新失败时不删锁，release 报错）；`reap` 看到它有设备锁时。
- 空闲时间 = 现在 − `last_used`。设备锁存在期间不会被关；锁释放时刷新 `last_used`，所以一轮测试刚结束不会被立刻判为空闲。
- 阈值：配置项 `client_idle_minutes`（正整数分钟，默认 null 即 30），`reap --idle-minutes` 可覆盖本次。
- 测试执行者不经设备锁直接操作客户端时不刷新 `last_used`；按规范测试都持锁，主线程的一次性只读探测不持锁，30 分钟足以覆盖。

## 关闭

一台登记的客户端按以下顺序处理：

1. 进程核对不通过 → `gone`，删除登记。
2. 有 devid 时用与 `codex_cli.py` 相同的规则独占创建这台设备的设备锁，整个关闭过程持有、结束后删除，期间别的会话加锁会失败；锁已存在（不管谁加的）→ `locked`，不关，刷新 `last_used`。锁内容记下 close 进程的 pid 和创建时间；close 被杀后残留、持有者已退出的这种锁，`client_launch.py` 和 `codex_cli.py` 加锁时原子地回收（`client_registry.reclaim_close_lock`），判断“有锁”时也不算它。拿到锁后重新读取登记：已被删除 → `gone`；`reap` 时按最新 `last_used` 重新判断空闲，未超阈值 → `kept`。查不清进程状态（如读不到映像路径）→ `failed`，不删登记。
3. `--dry-run` → `would_close`。
4. 有 devid 时先经 mh-game-mcp 的 `execute_code` 让客户端自己退出：代码在客户端进程内先比对 `os.getpid()` 与登记的 pid，一致才调 `C_app.quit_game(1)`，否则返回 `pid_mismatch`（devid 可能在重启后被另一台客户端沿用）。调用本身可能因进程退出而报错，不作判断依据；之后最多等 30 秒看进程是否退出。
5. 仍未退出（或没有 devid）→ 写关闭请求 `{"id", "action": "close", "pid", "created"}`，触发计划任务 `mhxy-client-launch`。启动器在管理员权限下打开进程，在同一个句柄上核对创建时间、映像路径在安装时登记的客户端目录下且名为 `mhmain.exe`，再 `TerminateProcess` 并等待退出，写回结果。
6. 核对进程确已退出 → `closed`（`method` 为 `mcp` 或 `task`），删除登记；否则 `failed`，保留登记，输出原因。旧版启动器不认识关闭请求，会报“启动请求字段无效”，输出提示重新 `install`。

`doctor` 已经比对已安装启动器与 skill 中的版本，启动器更新后会提示重新 `install`。

## 命令

```text
client_launch.py close --root <项目> (--mine [--owner <发起方>] | --devid <devid> | --pid <pid>) [--dry-run]
client_launch.py reap  --root <项目> [--idle-minutes N] [--dry-run]
```

- `close --mine`：登记中 `root` 与当前项目根相同、且 `owner` 与本次发起方相同（都为空也算相同）的全部客户端。交互会话关不到服务工单会话开的，反之亦然。
- `close --devid`／`--pid`：只在登记中查找；未登记的设备不关。
- `reap`：全部登记（不分工作区和发起方），空闲超过阈值、没有设备锁的关闭；进程已不在的删除登记。
- `select`／`launch` 开始前自动 `reap` 一次（`--dry-run` 时也只预览），结果放在输出的 `reap` 字段；兜底本身出错只记在 `reap.error`，不影响选设备。
- 输出 JSON：`{"action", "dry_run", "results": [{"devid", "pid", "account", "root", "owner", "outcome", "method", "idle_minutes", "error"}]}`；有 `failed` 时退出码 1。

## 关闭时机（文档）

整个流程结束时关，同一流程内多轮测试复用同一台：

- 交互开发：`svn_commit.py` 提交成功的 `next_steps` 增加 `close --mine`；用户放弃本次改动时由主会话运行（写进 engineering-principles.md 开发流程、session.md）。
- 启动失败（`device_timeout` 等）：收集完日志后 `close --pid <pid>`，报告里仍写进程号和日志位置。
- 无人值守：工单会话结束后（待提交、需要你处理、放弃、等前一单提交）由 popo-agent-service 运行 `close --mine --owner issue:<工单号>`；会话自己不关（避免依赖会话正常走到结尾，也不必扩大无人值守会话的权限）。

## 风险

- 启动和关闭共用一个请求文件 `request.json`，两个会话同时触发计划任务时后写的会覆盖先写的，等不到结果的一方报 `task_no_result`；与原有的启动并发限制相同。
- 关闭请求让普通权限进程可以免确认地结束登记目录下的 `mhmain.exe`（创建时间必须匹配，不能任意指定进程）。

## 验收

- 单元测试：登记读写和原子替换、pid 复用（创建时间不符只删登记）、有锁不关并刷新、空闲判断与阈值配置、`--mine` 只匹配同工作区同发起方、`--dry-run` 不动进程、MCP 退出成功与回退计划任务、启动器关闭请求的校验、`codex_cli` 加锁和释放刷新 `last_used`。
- 全量测试通过；popo-agent-service 测试通过。
- 真机：`launch` 起一台，`close` 关掉并移除登记；再起一台，`reap --idle-minutes 0` 清理；用户自己开着的客户端不受影响（先 `select --dry-run` 看清在线设备，关闭前后对比）。

## 变更记录

- 2026-11-12（0.3.41）：初版。
