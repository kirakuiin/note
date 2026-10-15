# 自动启动客户端：真机自检闭环

日期：2026-10-15　版本：0.3.23（自动选设备：0.3.24）

## 目标

去掉真机自检前“用户开好客户端”这一步人工操作：没有在线设备时，由主会话启动客户端、自动登录、拿到 devid。

## 方案

- **权限**：客户端要以管理员身份运行。用户在管理员终端运行一次 `client_launch.py install`，注册以最高权限运行的计划任务 `mhxy-client-launch`；agent 用 `schtasks /run` 触发，不再弹 UAC。
- **启动器**：`client_launch_task.py` 复制到 `%ProgramData%\mhxy-client-launch\`（普通权限不能改），只启动安装时登记的客户端目录下的 `mhmain.exe`。请求文件里没有密码，启动器按账号从用户级配置读取。命令行参数会被客户端转成小写，密码中大写字母的位置用 `caps` 还原。
- **账号池**：用户级 `login_accounts`，`login-account` 命令维护，密码隐藏输入。启动前用 mh-game-mcp 读本机每台在线设备的 `loginenter.Account`，选第一个空闲账号；都被占用就停止。`roleidx` 固定为 0。
- **服务器**：工作区级 `login_server`，只存用户说的名字。以“模拟”开头用大区 `刘强98服`；其他名字按内服服务器列表 `serverlist.txt` 匹配，大区为 `more_server`。
- **workspace**：项目根（mhimage）的上一级；其中 `_test/mhimage.wdf` 存在时拒绝启动，由用户处理。
- **部署**：`install` 可重复执行，`doctor` 列出缺什么和怎么补，`uninstall` 删除。
- 不使用 mh-patch-mcp 的 `control_aluba_client`：它拉起的是 aluba 自我验证循环，不能指定 workspace 和账号。

## 自动选设备

`client_launch.py select`：用户指定 devid 就用它；否则在本机在线设备中取第一台加载当前工作区源码（`mainmenu.__file__` 在项目根下）、已登录、没有设备锁的；没有就 `launch`。整个过程不需要用户确认，开发流程中用户只做真正的决策和只有本人能完成的操作。

## 风险

- 计划任务让本用户的普通权限进程可以免确认地以管理员身份启动登记目录下的 `mhmain.exe`；客户端目录和 Python 解释器本身普通权限可写，这一点不能完全防住。
- 占用检查只覆盖本机设备。

## 验收

- 单元测试覆盖账号选择、服务器解析、请求校验、密码不外泄。
- 真实环境：`doctor`、`launch --dry-run` 能读出在线设备占用的账号并解析服务器；`install` 后一次完整 `launch` 拿到 devid。
