"""eros 统一登录：站点 → auth.eros.nie.netease.com → CORP OpenID 登录页 → 回到站点。

适用于使用 eros 统一认证的 *.eros.nie.netease.com 站点（如提测系统）；提单平台跳往
auth2.qkit.nie.netease.com，结构相同，用 auth_host 参数指定。CORP 登录页的表单
与密码编码、登录流程都在 corp_login.login()，这里只指定入口和中转站；会话 Cookie 只保存在内存中，不落盘、不输出。
"""
from urllib.request import Request  # noqa: F401  （测试和调用方从这里取）

import corp_login
from corp_login import LOGIN, LoginError  # noqa: F401

# eros 统一认证中转站。它发出的跳转是 http（由服务端决定），这一段的 OpenID 回调参数以明文
# 传输；这里只把 http 限定在该主机，不改协议。密码只提交给 https 的 CORP 登录页。
AUTH_HOST = "auth.eros.nie.netease.com"
# 提单平台（popomgr）走的中转站，跳转链与 eros 统一认证相同，只是主机不同。
QKIT_AUTH_HOST = "auth2.qkit.nie.netease.com"


def _redirects(site, auth_host=AUTH_HOST):
    """只允许跳转到站点本身（https）、认证中转站（http／https）和 CORP 登录页（https）。"""
    return corp_login.redirects(site, https_hosts=(auth_host,), http_hosts=(auth_host,))


def login(site, username, password, timeout=30, auth_host=AUTH_HOST):
    """登录 eros 站点并返回带会话的 opener。

    Args:
        site: 站点根地址，如 "https://newtestreport.eros.nie.netease.com"。
        username: CORP 邮箱或账号。
        password: CORP 密码；只提交给 CORP 登录页，调用结束后不保留。
        timeout: 单次请求超时秒数。
        auth_host: 站点 /auth/login 跳往的认证中转站；提单平台用 QKIT_AUTH_HOST。

    Returns:
        urllib opener，Cookie 仅在内存中；调用方不得输出或持久化。只确认回到了站点，
        不核对登录后的账号：目前没有已知的 eros 通用用户信息接口。

    Raises:
        LoginError: 跳转异常、需要验证码／二次验证、凭据错误或协议变化。不自动重试密码。
    """
    return corp_login.login(site, username, password, entry="/auth/login?next=/", https_hosts=(auth_host,),
                            http_hosts=(auth_host,), timeout=timeout)
