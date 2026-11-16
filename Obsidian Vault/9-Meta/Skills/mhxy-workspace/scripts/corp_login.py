"""CORP 登录（公司内部站点通用）：账号校验、跳转限制、登录表单解析与密码编码，以及通用登录入口 login()。

新接一个内部站点时先用 login()：打开站点的登录入口 → 跟着跳到 CORP 登录页 → 提交表单 → 回到站点，
返回带会话的 opener。各站只是登录入口路径和中途经过的主机不同，用参数说明（见 references/corp-login.md）。
eros 统一认证（eros_auth.py）和资源提交网站（art_bind.py）都走 login()；易协作（pm_issues.py）和覆盖率站
（coverage_auth.py）登录后还要和站点交换一次凭据，流程保留在各自脚本里，只复用这里的表单和密码编码。
登录协议变化时只修改这里。
"""
import getpass
from html.parser import HTMLParser
import http.cookiejar
import json
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPCookieProcessor, HTTPRedirectHandler, Request, build_opener

LOGIN = "https://login.netease.com"


class LoginError(Exception):
    """可直接显示的登录错误；不包含密码、Cookie、回调参数或服务器原始响应。"""


def account_prefix(username):
    """校验 CORP 邮箱或账号并返回小写账号名。

    Args:
        username: `name@corp.netease.com` 或 `name`。

    Raises:
        LoginError: 未配置、非 CORP 邮箱或账号含非法字符。
    """
    if not isinstance(username, str) or not username.strip():
        raise LoginError("请配置 openid_username 或在命令中指定账号")
    username = username.strip().lower()
    if "@" in username and not username.endswith("@corp.netease.com"):
        raise LoginError("只支持 CORP 账号或 @corp.netease.com 邮箱")
    prefix = username.split("@")[0]
    if not re.fullmatch(r"[a-z0-9_.-]+", prefix):
        raise LoginError("CORP 账号格式无效")
    return prefix


def redirect_handler(site):
    """生成只允许跳转到 `site` 与 CORP 登录页（均为 HTTPS）的跳转处理器类。"""
    allowed = {urlsplit(site).netloc, urlsplit(LOGIN).netloc}

    class RestrictedRedirects(HTTPRedirectHandler):
        """登录交换过程中拒绝跳转到未识别站点，避免凭据外泄。"""

        def redirect_request(self, req, fp, code, msg, headers, newurl):
            target = urlsplit(newurl)
            if target.scheme != "https" or target.netloc not in allowed:
                raise LoginError("登录跳转到未识别站点，已停止")
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    return RestrictedRedirects


def redirects(site, https_hosts=(), http_hosts=()):
    """生成 login() 用的跳转处理器类。

    允许的跳转：站点本身和 CORP 登录页（https）、`https_hosts` 里的主机（https）、`http_hosts` 里的主机（http）。
    http 只给服务端自己发 http 跳转的那一跳用（认证中转站，或站点登记的 OpenID 回调是 http 的情况）：这一跳带的是
    签过名的 OpenID 回调参数，不是密码；密码只提交给 https 的 CORP 登录页。地址里带账号密码的一律拒绝。
    跳转时去掉 Origin 和 Referer：它们只是提交 CORP 登录表单要用的，带到站点会被有的站当成跨站请求打回登录页
    （资源提交网站，2026-11-16 实测）。
    """
    https_ok = {urlsplit(site).netloc, urlsplit(LOGIN).netloc, *https_hosts}
    http_ok = set(http_hosts)

    class Redirects(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            target = urlsplit(newurl)
            allowed = ((target.scheme == "https" and target.netloc in https_ok)
                       or (target.scheme == "http" and target.netloc in http_ok))
            if not allowed or target.username or target.password:
                raise LoginError("登录跳转到未识别站点，已停止")
            request = super().redirect_request(req, fp, code, msg, headers, newurl)
            if request is not None:
                for name in ("Origin", "Referer"):
                    request.headers.pop(name, None)
                    request.unredirected_hdrs.pop(name, None)
            return request

    return Redirects


def login(site, username, password, entry="/login?next=/", https_hosts=(), http_hosts=(), timeout=30):
    """登录一个用 CORP OpenID 的内部站点，返回带会话的 opener。

    Args:
        site: 站点根地址（https），如 "https://artrestrans.eros.nie.netease.com"。
        username: CORP 邮箱或账号。
        password: CORP 密码；只提交给 CORP 登录页，调用方拿到返回值后应立即丢弃。
        entry: 站点上会跳去登录的入口路径（未登录时打开它会被带到 CORP 登录页）。
        https_hosts: 中途允许经过的其他主机（https），如认证中转站。
        http_hosts: 允许以 http 经过的主机，见 redirects()；站点自己的回调是 http 时把站点主机放进来。
        timeout: 单次请求超时秒数。

    Returns:
        urllib opener，Cookie 仅在内存中；调用方不得输出或持久化。之后的请求一律用 https 的站点地址。
        只确认回到了站点，不核对登录后的账号（各站的用户信息接口不同，需要时由调用方核对）。

    Raises:
        LoginError: 跳转异常、需要验证码／二次验证、凭据错误或协议变化。不自动重试密码。
    """
    prefix = account_prefix(username)
    site = site.rstrip("/")
    if urlsplit(site).scheme != "https":
        raise LoginError("站点地址必须是 https")
    opener = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()), redirects(site, https_hosts, http_hosts)())

    def read(url, data=None, headers=None):
        try:
            with opener.open(Request(url, data=data, headers=headers or {}), timeout=timeout) as response:
                return response.url, response.read().decode("utf-8", "replace")
        except HTTPError as error:
            raise LoginError(f"登录过程返回 HTTP {error.code}") from None
        except (URLError, OSError):
            raise LoginError("登录过程网络请求失败") from None

    login_url, html = read(site + entry)
    if urlsplit(login_url).netloc != urlsplit(LOGIN).netloc:
        raise LoginError("未到达 CORP 登录页")
    form = fill_corp_form(corp_form(html), html, prefix, password)
    try:
        final_url, _ = read(login_url, urlencode(form).encode(), {"Origin": LOGIN, "Referer": login_url})
    finally:
        form.clear()
    if urlsplit(final_url).netloc != urlsplit(site).netloc:
        raise LoginError("登录未完成，可能需要验证码／二次验证或凭据有误；请在本机处理，不自动重试")
    return opener


class LoginForms(HTMLParser):
    """收集页面中各表单的输入字段默认值，不执行网页脚本。

    Attributes:
        forms: 每个表单一项，键为 input 名称，值为默认值。
        current: 正在解析的表单；表单外为 None。
    """

    def __init__(self):
        super().__init__()
        self.forms = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form":
            self.current = {}
            self.forms.append(self.current)
        elif tag == "input" and self.current is not None and attrs.get("name"):
            self.current[attrs["name"]] = attrs.get("value", "")

    def handle_endtag(self, tag):
        if tag == "form":
            self.current = None


def encode_password(password, html):
    """按登录页的 OPHASH_ SM4-CBC/PKCS7 约定编码密码；协议变化时拒绝提交。

    Raises:
        LoginError: 缺少支持 SM4 的 cryptography，或登录页编码参数变化。
    """
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives.padding import PKCS7
        key = bytes.fromhex(re.search(r"_salt\s*=\s*'([^']+)'", html)[1])
        iv = bytes.fromhex(re.search(r"_salt2\s*=\s*'([^']+)'", html)[1])
        prefix = re.search(r"_prefix\s*=\s*'([^']+)'", html)[1]
        if prefix != "OPHASH_":
            raise ValueError("unknown encoding")
        padder = PKCS7(128).padder()
        padded = padder.update(password.encode("utf-8")) + padder.finalize()
        encryptor = Cipher(algorithms.SM4(key), modes.CBC(iv)).encryptor()
        return prefix + (encryptor.update(padded) + encryptor.finalize()).hex()
    except ImportError:
        raise LoginError("OpenID 登录需要支持 SM4 的 cryptography：python -m pip install cryptography") from None
    except (ValueError, TypeError, AttributeError):
        raise LoginError("登录页密码编码发生变化或 SM4 不可用，未提交密码") from None


def corp_form(html):
    """返回登录页中唯一的 CORP 登录表单字段（含隐藏字段默认值）。

    Raises:
        LoginError: 找不到或找到多个含 corpid／corppw 的表单。
    """
    forms = LoginForms()
    forms.feed(html)
    candidates = [form for form in forms.forms if "corpid" in form and "corppw" in form]
    if len(candidates) != 1:
        raise LoginError("无法唯一识别 CORP 登录表单")
    return candidates[0]


def fill_corp_form(form, html, prefix, password):
    """就地填入账号和编码后的密码，并去掉“记住登录”；返回同一个表单字典。

    调用方提交后应立即 `form.clear()`，避免编码后的密码在内存中久留。
    """
    form.update(corpid=prefix, corppw=encode_password(password, html), privacy="on")
    form.pop("remember", None)
    return form


def interactive_terminal():
    """能否隐藏输入密码：标准输入和标准错误（getpass 的提示写在这里）都要连着终端。

    Windows 上 agent 命令工具的标准输入是 NUL，属于字符设备，`stdin.isatty()` 也为 True；
    只看标准输入时 getpass 会一直等待输入。这类工具的标准错误是管道，据此排除。
    """
    return all(stream is not None and stream.isatty() for stream in (sys.stdin, sys.stderr))


def load_credentials(config_path, username=None):
    """从用户级配置读取 CORP 账号和密码；显式切换账号时不复用其他账号的密码。

    配置中没有密码（或为空串）时只在交互终端（见 interactive_terminal）隐藏输入（不保存）；
    没有交互终端时报错，由用户先通过 workspace.py config --prompt-password 保存密码。

    Args:
        config_path: 用户级配置文件路径（Path）。
        username: 显式指定的账号；为空时使用配置中的 openid_username。

    Returns:
        (账号, 密码)。调用方不得输出或持久化密码。

    Raises:
        LoginError: 配置无法读取、账号无效、缺少密码且无法交互输入。
    """
    values = {}
    if config_path.exists():
        try:
            values = json.loads(config_path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            raise LoginError("无法读取账号配置文件") from None
        if not isinstance(values, dict):
            raise LoginError("账号配置必须为 JSON 对象")
    saved_user = values.get("openid_username")
    selected = username or saved_user
    account_prefix(selected)
    password = values.get("openid_password")
    if username and (not saved_user or account_prefix(username) != account_prefix(saved_user)):
        password = None
    if not password:
        if not interactive_terminal():
            raise LoginError("未配置密码，请在交互终端输入或填写全局配置")
        password = getpass.getpass("CORP password (not saved): ")
    if not isinstance(password, str) or not password:
        raise LoginError("密码未填写")
    return selected, password
