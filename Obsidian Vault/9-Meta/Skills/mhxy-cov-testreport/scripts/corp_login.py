#!/usr/bin/env python3
"""CORP 登录页公共逻辑与独立账号配置工具：账号校验、跳转限制、登录表单解析与密码编码。

coverage_auth.py（覆盖率站）与 testreport.py（提测系统）共用本模块；默认读取
~/.mhxy-workspace/config.json，与 mhxy-workspace 完全兼容。也可直接运行本脚本配置或查看
CORP 账号与密码（密码仅支持在交互终端隐藏输入，不出现在命令行参数或输出中）。
"""
import argparse
import getpass
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler

sys.dont_write_bytecode = True

LOGIN = "https://login.netease.com"
DEFAULT_CONFIG = Path.home() / ".mhxy-workspace" / "config.json"


class LoginError(Exception):
    """可直接显示的登录或配置错误；不包含密码、Cookie、回调参数或服务器原始响应。"""


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


def normalize_corp_email(username):
    """校验 CORP 账号并统一补全为小写 `<prefix>@corp.netease.com`。"""
    return f"{account_prefix(username)}@corp.netease.com"


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


class LoginForms(HTMLParser):
    """收集页面中各表单的输入字段默认值，不执行网页脚本。"""

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
    """返回登录页中唯一的 CORP 登录表单字段（含隐藏字段默认值）。"""
    forms = LoginForms()
    forms.feed(html)
    candidates = [form for form in forms.forms if "corpid" in form and "corppw" in form]
    if len(candidates) != 1:
        raise LoginError("无法唯一识别 CORP 登录表单")
    return candidates[0]


def fill_corp_form(form, html, prefix, password):
    """就地填入账号和编码后的密码，并去掉“记住登录”；返回同一个表单字典。"""
    form.update(corpid=prefix, corppw=encode_password(password, html), privacy="on")
    form.pop("remember", None)
    return form


def interactive_terminal():
    """能否隐藏输入密码：标准输入和标准错误（getpass 的提示写在这里）都要连着终端。

    Windows 上 agent 命令工具的标准输入是 NUL，属于字符设备，`stdin.isatty()` 也为 True；
    只看标准输入时 getpass 会一直等待输入。这类工具的标准错误是管道，据此排除。
    """
    return all(stream is not None and stream.isatty() for stream in (sys.stdin, sys.stderr))


def read_config_dict(config_path):
    """读取 JSON 配置文件对象；不存在时返回空字典。"""
    path = Path(config_path).expanduser()
    if not path.exists():
        return {}
    try:
        values = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        raise LoginError("无法读取账号配置文件") from None
    if not isinstance(values, dict):
        raise LoginError("账号配置必须为 JSON 对象")
    return values


def load_credentials(config_path, username=None):
    """从用户级配置读取 CORP 账号和密码；显式切换账号时不复用其他账号的密码。"""
    values = read_config_dict(config_path)
    saved_user = values.get("openid_username")
    selected = username or saved_user
    account_prefix(selected)
    password = values.get("openid_password")
    if username and (not saved_user or account_prefix(username) != account_prefix(saved_user)):
        password = None
    if not password:
        if not interactive_terminal():
            raise LoginError("未配置密码，请在交互终端运行 corp_login.py config --prompt-password --apply")
        password = getpass.getpass("CORP password (not saved): ")
    if not isinstance(password, str) or not password:
        raise LoginError("密码未填写")
    return selected, password


def masked_summary(values):
    """返回脱敏后的 CORP 配置摘要，绝不暴露密码原文。"""
    username = values.get("openid_username")
    coder_name = values.get("coder_name") or (username.split("@", 1)[0] if isinstance(username, str) and username else None)
    return {
        "openid_username": username,
        "openid_password": "***" if values.get("openid_password") else None,
        "coder_name": coder_name,
    }


def update_config(config_path, username=None, coder_name=None, prompt_password=False, clear_password=False, apply=False):
    """更新用户级配置中的 CORP 账号、密码与 coder_name，保留文件中的其他字段。"""
    if prompt_password and clear_password:
        raise LoginError("--prompt-password 与 --clear-password 不能同时使用")
    if prompt_password and not apply:
        raise LoginError("--prompt-password 必须与 --apply 一起使用")
    path = Path(config_path).expanduser().resolve()
    values = dict(read_config_dict(path))
    if username is not None:
        normalized = None if username == "null" else normalize_corp_email(username)
        if values.get("openid_username") != normalized:
            values.pop("openid_password", None)
        values["openid_username"] = normalized
    if coder_name is not None:
        if coder_name != "null" and not re.fullmatch(r"[a-zA-Z0-9_.-]+", coder_name.strip()):
            raise LoginError("coder_name 格式无效")
        values["coder_name"] = None if coder_name == "null" else coder_name.strip()
    if clear_password:
        values["openid_password"] = None
    if prompt_password:
        if not values.get("openid_username"):
            raise LoginError("请先指定 --username 或配置 openid_username")
        if not interactive_terminal():
            raise LoginError("输入密码需要交互终端，请在自己的终端中运行本命令")
        first = getpass.getpass("CORP password: ")
        second = getpass.getpass("Confirm CORP password: ")
        if not first:
            raise LoginError("密码不能为空")
        if first != second:
            raise LoginError("两次输入的密码不一致，未保存")
        values["openid_password"] = first
    if apply:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(values, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    return {"action": "config", "applied": apply, "config_path": str(path), **masked_summary(values)}


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("show", "config"))
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="配置文件路径，默认 ~/.mhxy-workspace/config.json")
    parser.add_argument("--username", help="config：设置 openid_username（CORP 邮箱或前缀，传 null 清空）")
    parser.add_argument("--coder-name", help="config：设置 coder_name（默认取邮箱前缀，传 null 清空）")
    parser.add_argument("--prompt-password", action="store_true", help="config：在交互终端隐藏输入并保存密码（需配合 --apply）")
    parser.add_argument("--clear-password", action="store_true", help="config：清空已保存的密码")
    parser.add_argument("--apply", action="store_true", help="config：实际写入配置文件")
    args = parser.parse_args(argv)
    try:
        if args.action == "show":
            path = Path(args.config).expanduser().resolve()
            result = {"action": "show", "config_path": str(path), **masked_summary(read_config_dict(path))}
        else:
            result = update_config(args.config, args.username, args.coder_name,
                                   args.prompt_password, args.clear_password, args.apply)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (LoginError, OSError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
