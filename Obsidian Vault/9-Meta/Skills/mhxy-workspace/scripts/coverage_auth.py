"""Create an in-memory coverage session through the site's CORP OpenID login.

The password is supplied by the caller or prompted without echo. Requires
cryptography with SM4 support, matching the login page's password encoding.
Shared CORP login-page handling lives in corp_login.py.
"""
import getpass
import http.cookiejar
import json
from pathlib import Path
import sys
from urllib.parse import urlencode, urlparse
from urllib.request import HTTPCookieProcessor, Request, build_opener

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import corp_login  # noqa: E402
from corp_login import LOGIN, LoginForms, encode_password  # noqa: E402,F401  (re-exported for callers)

SITE = "https://mh-mos2-coverage.eros.nie.netease.com"
AuthError = corp_login.LoginError
LoginRedirects = corp_login.redirect_handler(SITE)


def login(username, timeout=20, password=None):
    """Return an in-memory CookieJar after verified same-user login.

    Args:
        username: CORP email address or account prefix.
        timeout: Per-request timeout in seconds.
        password: Optional password loaded from user settings; never logged. Empty means
            missing: prompt only when corp_login.interactive_terminal() is true.

    Returns:
        An in-memory cookie jar; callers must not print or persist it implicitly.

    Raises:
        AuthError: Login rejected, interactive verification required, or protocol
            changed. Does not retry passwords or expose server response bodies.
    """
    username = corp_login.account_prefix(username)
    jar = http.cookiejar.CookieJar()
    opener = build_opener(HTTPCookieProcessor(jar), LoginRedirects())

    def read(url, data=None, headers=None):
        with opener.open(Request(url, data=data, headers=headers or {}), timeout=timeout) as response:
            return response.url, response.read().decode("utf-8")

    try:
        _, body = read(SITE + "/api/auth/key")
        key = json.loads(body)["assoc_handle"]
        query = {"openid.mode": "checkid_setup", "openid.ns": "http://specs.openid.net/auth/2.0",
                 "openid.realm": SITE, "openid.sreg.required": "nickname,email,fullname",
                 "openid.assoc_handle": key, "openid.return_to": SITE + "/consume",
                 "openid.ns.sreg": "http://openid.net/extensions/sreg/1.1",
                 "openid.identity": "http://specs.openid.net/auth/2.0/identifier_select",
                 "openid.claimed_id": "http://specs.openid.net/auth/2.0/identifier_select"}
        login_url, html = read(LOGIN + "/openid/?" + urlencode(query))
        if urlparse(login_url).netloc != urlparse(LOGIN).netloc:
            raise AuthError("未到达已识别的 OpenID 登录页")
        form = corp_login.corp_form(html)
        if not password:  # 未配置或为空串都视为缺少密码。
            if not corp_login.interactive_terminal():
                raise AuthError("没有已配置密码；请先配置账密、使用交互终端或提供认证文件")
            password = getpass.getpass("OpenID password (not saved): ")
        try:
            corp_login.fill_corp_form(form, html, username, password)
            callback, _ = read(login_url, urlencode(form).encode(), {"Referer": login_url, "Origin": LOGIN})
        finally:
            password = None
            form.clear()
        target = urlparse(callback)
        if target.netloc != urlparse(SITE).netloc or target.path != "/consume":
            raise AuthError("登录未完成，可能需要验证码／二次验证或凭据有误；请在本机处理，不自动重试")
        read(SITE + "/api/auth/login?" + target.query)
        _, identity = read(SITE + "/api/auth/info")
        if str(json.loads(identity).get("name") or "").lower() != username:
            raise AuthError("登录后的账号与指定账号不一致")
        return jar
    except AuthError:
        raise
    except (EOFError, KeyboardInterrupt):
        raise AuthError("登录输入已取消") from None
    except Exception:
        raise AuthError("OpenID 登录未完成或协议响应发生变化；未自动重试") from None
