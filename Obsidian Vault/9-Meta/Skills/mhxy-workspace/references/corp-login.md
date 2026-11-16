# CORP 登录（内部站点通用）

要让脚本登录一个公司内部站点（`*.netease.com` 上用 CORP 邮箱账号登录的站）时读取本文件。账号和密码的配置、输入方式见 `workspace-management.md`「密码」，这里只讲脚本怎么登录。

## 用法

公司内部站点基本都走同一套 CORP OpenID：未登录时打开站点会被带到 `login.netease.com` 的登录页，提交账号密码后带着签名的回调参数回到站点，站点发会话 Cookie。`scripts/corp_login.py` 的 `login()` 实现了这一整套，新接站点直接用：

```python
import corp_login

username, password = corp_login.load_credentials(config_path)   # 用户级配置里的 openid_username／openid_password
try:
    opener = corp_login.login(SITE, username, password, entry="/login?next=/")
finally:
    password = None
# 之后用 opener.open(Request(SITE + "/api/…")) 调接口；Cookie 只在内存里
```

各站只有三处不同，用参数说明：

| 参数 | 含义 | 怎么确定 |
| --- | --- | --- |
| `entry` | 站点上会跳去登录的入口路径 | 未登录时用浏览器打开站点，看它先跳到自己的哪个路径（常见 `/login?next=/`、`/auth/login?next=/`） |
| `https_hosts` | 中途经过的其他主机（https） | 登录跳转链里除站点和 `login.netease.com` 之外的主机，如认证中转站 |
| `http_hosts` | 允许以 http 经过的主机 | 服务端自己发 http 跳转的那一跳：认证中转站，或站点登记的 OpenID 回调是 http 时的站点主机 |

没声明的主机、http 跳转、地址里带账号密码的跳转一律拒绝并停止登录，不要为了登录成功把限制整体放开；按上表查清是哪一跳，只加那一个主机。

## 已接入的站点

| 站点 | 脚本 | 入口和主机 |
| --- | --- | --- |
| eros 统一认证的站（提测系统 `newtestreport.eros`） | `eros_auth.login()` → `corp_login.login()` | `/auth/login?next=/`，中转站 `auth.eros.nie.netease.com`（http、https） |
| 提单平台 `popomgr.eros` | 同上，`auth_host=eros_auth.QKIT_AUTH_HOST` | 中转站 `auth2.qkit.nie.netease.com` |
| 资源提交网站 `artrestrans.eros` | `art_bind.py` | `/login?next=/`，站点自己的回调是 http：`http_hosts=(站点主机,)` |
| 易协作 `xyq.pm`、覆盖率站 `mh-mos2-coverage.eros` | `pm_issues.py`、`coverage_auth.py` | 登录后还要和站点交换一次凭据并核对账号，流程在各自脚本里，只复用 `corp_login` 的表单和密码编码 |

## 规则

- 密码只从 `load_credentials()` 取，只提交给 https 的 CORP 登录页；不放命令行、不输出、不落盘，用完置空。会话 Cookie 同样只在内存里。
- 登录不自动重试。停在登录页（验证码、二次验证、密码错）时报错，请用户在本机处理；连续失败会锁账号。
- 一次脚本运行只登录一次，同一个 opener 发完所有请求；不要每个请求登录一次。
- 跳转时不带 `Origin`、`Referer`（`login()` 已处理）：带着登录页的来源回到站点，有的站会当成跨站请求打回登录页。
- 站点回调登记的是 http 时不要改成 https，OpenID 校验会不过；这一跳带的是签名的回调参数，不是密码。
- 摸一个新站点的登录链时，逐跳打印“状态码、主机、路径、参数名、Cookie 名”即可，不要打印参数值和 Cookie 值。
- `login()` 只确认回到了站点，不核对登录后的账号；站点有用户信息接口且账号重要时由调用方核对。
