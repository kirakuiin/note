# 自动启动客户端：真机自检闭环

日期：2026-10-15　版本：0.3.23（自动选设备：0.3.24；按 PC／互通选设备：0.3.26；大区名-服务器名：0.3.27）

## 目标

去掉真机自检前“用户开好客户端”这一步人工操作：主会话自己判断要测 PC 还是互通（或两端），没有合适的在线设备时启动对应客户端、自动登录、拿到 devid。

## 方案

- **权限**：客户端要以管理员身份运行。用户在管理员终端运行一次 `client_launch.py install`，注册以最高权限运行的计划任务 `mhxy-client-launch`；agent 用 `schtasks /run` 触发，不再弹 UAC。
- **启动器**：`client_launch_task.py` 复制到 `%ProgramData%\mhxy-client-launch\`（普通权限不能改），只启动安装时登记的客户端目录下的 `mhmain.exe`。请求文件里没有密码，启动器按账号从用户级配置读取。命令行参数会被客户端转成小写，密码中大写字母的位置用 `caps` 还原。
- **账号池**：用户级 `login_accounts`，`login-account` 命令维护，密码隐藏输入。启动前用 mh-game-mcp 读本机每台在线设备的 `loginenter.Account`，选第一个空闲账号；都被占用就停止。`roleidx` 固定为 0。
- **服务器**：工作区级 `login_server`，只存用户说的名字。以“模拟”开头用大区 `刘强98服`；其他名字先在内服服务器列表 `serverlist.txt` 中精确匹配（大区为 `more_server`）；再按客户端目录 `common/server.ini`（选服界面的大区和服务器，GB18030）把 `大区名-服务器名` 精确解析为（大区名, 服务器名），大区名可含 `-`，按已知大区名前缀切分；最后在 `serverlist.txt` 中做唯一的模糊匹配。都只在唯一命中时采用。`launch`、`select` 都可用 `--server` 覆盖本次。
- **客户端类型**：启动前只读客户端目录 `update.ini` 的 `[Setting]`：`Platform = HT` 为互通，`Arch = X64`／`X86` 为 PC。与 `--platform` 不符报 `platform_mismatch`，判断不了报 `platform_unknown`，都不启动、不改 ini。`doctor` 列出每个客户端目录的实际类型。
- **workspace**：项目根（mhimage）的上一级；其中 `_test/mhimage.wdf` 存在时拒绝启动，由用户处理。
- **部署**：`install` 可重复执行，`doctor` 列出缺什么和怎么补，`uninstall` 删除。
- 不使用 mh-patch-mcp 的 `control_aluba_client`：它拉起的是 aluba 自我验证循环，不能指定 workspace 和账号。

## 自动选设备

`client_launch.py select --platform pc|ht`：用户指定 devid 就用它；否则在本机在线设备中取第一台类型相符（`C_app.get_platform()`：`win32` 为 PC，`mobile` 为互通，识别不了的跳过）、加载当前工作区源码（`mainmenu.__file__` 在项目根下）、已登录、没有设备锁的；没有就 `launch`。`--dry-run` 只扫描并给出会选用的设备或启动计划，不启动。

测哪几端由主会话按 spec 和改动决定：只有 PC 或只有互通走得到的改动测一端；两端都会走到的公共逻辑或判断不了时两端都测，每端 `select` 一台设备、分别委派。整个过程不需要用户确认，也不需要用户打开客户端；开发流程中用户只做真正的决策和只有本人能完成的操作，启动失败时才报告。

## 风险

- 计划任务让本用户的普通权限进程可以免确认地以管理员身份启动登记目录下的 `mhmain.exe`；客户端目录和 Python 解释器本身普通权限可写，这一点不能完全防住。
- 占用检查只覆盖本机设备。

## 验收

- 单元测试覆盖账号选择、服务器解析（含 server.ini 的大区名-服务器名）、请求校验、密码不外泄、按类型筛选设备、`update.ini` 类型判断、`select --dry-run`、`doctor` 的类型报告。
- 真实环境：`doctor`、`launch --dry-run`、`select --platform pc|ht --dry-run` 能读出在线设备占用的账号和类型并解析服务器；`install` 后一次完整 `launch` 拿到 devid。

## 变更记录

- 2026-10-15（0.3.23）：初版，自动启动客户端。
- 2026-10-15（0.3.24）：`select` 自动选设备。
- 2026-10-20（0.3.26）：`select` 按 `--platform` 筛选在线设备；`launch` 启动前按 `update.ini` 校验客户端目录类型（`platform_mismatch`／`platform_unknown`）；`doctor` 报告各客户端目录类型；新增 `select --dry-run`；主会话按改动决定测 PC、互通或两端，两端各一台设备、分别委派。
- 2026-10-21（0.3.27）：服务器名支持客户端 `common/server.ini` 的 `大区名-服务器名`（如 `孙锐贤-test_branch`），用于不在 `serverlist.txt` 里的服务器；`select` 支持 `--server`。
