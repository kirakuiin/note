"""eros 统一登录：站点 → auth.eros.nie.netease.com → CORP OpenID 登录页 → 回到站点。

适用于使用 eros 统一认证的 *.eros.nie.netease.com 站点（如提测系统）。CORP 登录页的表单
与密码编码复用 corp_login；会话 Cookie 只保存在内存中，不落盘、不输出。
"""
import http.cookiejar
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPCookieProcessor, HTTPRedirectHandler, Request, build_opener

import corp_login
from corp_login import LOGIN, LoginError

AUTH_HOST = "auth.eros.nie.netease.com"  # eros 统一认证中转站；该站使用 http 跳转。


def _redirects(site):
    """只允许跳转到站点本身（https）、eros 认证站（http／https）和 CORP 登录页（https）。"""
    site_host = urlsplit(site).netloc
    login_host = urlsplit(LOGIN).netloc

    class Redirects(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            target = urlsplit(newurl)
            allowed = ((target.netloc in (site_host, login_host) and target.scheme == "https")
                       or (target.netloc == AUTH_HOST and target.scheme in ("http", "https")))
            if not allowed or target.username or target.password:
                raise LoginError("登录跳转到未识别站点，已停止")
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    return Redirects


def login(site, username, password, timeout=30):
    """登录 eros 站点并返回带会话的 opener。

    Args:
        site: 站点根地址，如 "https://newtestreport.eros.nie.netease.com"。
        username: CORP 邮箱或账号。
        password: CORP 密码；只提交给 CORP 登录页，调用结束后不保留。
        timeout: 单次请求超时秒数。

    Returns:
        urllib opener，Cookie 仅在内存中；调用方不得输出或持久化。

    Raises:
        LoginError: 跳转异常、需要验证码／二次验证、凭据错误或协议变化。不自动重试密码。
    """
    prefix = corp_login.account_prefix(username)
    opener = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()), _redirects(site)())

    def read(url, data=None, headers=None):
        try:
            with opener.open(Request(url, data=data, headers=headers or {}), timeout=timeout) as response:
                return response.url, response.read().decode("utf-8", "replace")
        except HTTPError as error:
            raise LoginError(f"登录过程返回 HTTP {error.code}") from None
        except (URLError, OSError):
            raise LoginError("登录过程网络请求失败") from None

    login_url, html = read(site.rstrip("/") + "/auth/login?next=/")
    if urlsplit(login_url).netloc != urlsplit(LOGIN).netloc:
        raise LoginError("未到达 CORP 登录页")
    form = corp_login.fill_corp_form(corp_login.corp_form(html), html, prefix, password)
    try:
        final_url, _ = read(login_url, urlencode(form).encode(), {"Origin": LOGIN, "Referer": login_url})
    finally:
        form.clear()
    if urlsplit(final_url).netloc != urlsplit(site).netloc:
        raise LoginError("登录未完成，可能需要验证码／二次验证或凭据有误；请在本机处理，不自动重试")
    return opener
