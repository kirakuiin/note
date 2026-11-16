#!/usr/bin/env python3
"""给资源提交网站（artrestrans）上的美术标签绑定程序的资源 SVN 地址。

流程说明见 references/art-bind.md。两个子命令：
  show  查标签现有的绑定（只读）。
  bind  把资源地址追加到标签的绑定里；默认只预览，加 --apply 才提交。已经绑过时不动。

标签用 --tag 直接给，或用 --text-file 给一份美术上传通知的原文（从里面取标签）。
资源地址用 --root <项目>（取 <项目>/../_test 工作副本的地址）或 --svn <地址>。
登录用用户级配置里的 CORP 账号（corp_login.login），会话只在内存中。
输出一个 JSON 对象，字段固定；退出码 0 成功，1 失败且平台没改，2 已提交但读回核对不上。
"""
import argparse
import json
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlsplit
from urllib.request import Request

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import branch  # noqa: E402
import corp_login  # noqa: E402
from corp_login import LoginError  # noqa: E402
import workspace  # noqa: E402

SITE = "https://artrestrans.eros.nie.netease.com"
HOST = urlsplit(SITE).netloc
RES_SUBDIR = "_test"  # 资源工作副本在 <项目>/../_test；手工绑定填的也是带 _test 的地址（用户 2026-11-16 确认）。
# 页面「程序SVN或者popo」输入框接受的地址前缀（2026-11-16 从页面脚本核实）；其余的页面报“非法格式”。
SVN_PREFIXES = tuple(f"{scheme}://svn-xyq.gz.netease.com/svn/{repo}/"
                     for scheme in ("https", "svn")
                     for repo in ("products/xy1/share/patch", "products/xy1/share", "xyqs/share/patch", "xyqs/share"))
# 美术上传通知：“<人>已于 <标签> 成功上传N份新资源: temp/res_copy/<标签>/…”。
NOTICE_TAG = (re.compile(r"已于\s*(art\S.*?)\s*成功上传", re.S), re.compile(r"res_copy/(art[^/\r\n]+)/"))


class ArtBindError(LoginError):
    """可直接显示的错误；不包含密码、Cookie 或服务器原始响应。"""

    def __init__(self, message, code=1):
        super().__init__(message)
        self.code = code


def normalize(url):
    return unquote((url or "").strip()).rstrip("/")


def same_key(url):
    """比较两个绑定项是不是同一个地址用的键：平台存的时候会把 svn:// 换成 https://（2026-11-16 实测），所以不看协议。"""
    url = normalize(url)
    return url.split("://", 1)[1] if "://" in url else url


def tag_from_text(text):
    """从美术上传通知的原文里取标签名；取不到时返回空串。"""
    for pattern in NOTICE_TAG:
        match = pattern.search(text or "")
        if match:
            return " ".join(match.group(1).split())
    return ""


def check_svn(url):
    """地址必须是页面接受的资源仓库地址，否则平台会拒绝。"""
    url = normalize(url)
    if not any(url.startswith(prefix) and len(url) > len(prefix) for prefix in SVN_PREFIXES):
        raise ArtBindError(f"不是资源仓库（share 或 share/patch）下的地址，平台不接受：{url or '（空）'}")
    return url


def resource_svn(root):
    """<项目>/../_test 资源工作副本的地址。"""
    path = Path(root).resolve().parent / RES_SUBDIR
    try:
        url = branch.svn_info(path, item="url")
    except branch.BranchError as error:
        raise ArtBindError(f"读取资源工作副本地址失败：{error}") from None
    if not url:
        raise ArtBindError(f"没有找到资源工作副本 {path}")
    return check_svn(url)


class Client:
    """已登录的资源提交网站会话，只提供本脚本用到的接口。"""

    def __init__(self, opener, timeout=30):
        self.opener = opener   # corp_login.login 返回的 opener，Cookie 只在内存中。
        self.timeout = timeout

    def post(self, path, payload):
        """POST JSON，返回 (HTTP 状态码, JSON)。页面约定：200 成功，201 是带 msg 的业务失败。"""
        request = Request(SITE + path, data=json.dumps(payload).encode("utf-8"),
                          headers={"Content-Type": "application/json"})
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                if urlsplit(response.url).netloc != HOST:
                    raise ArtBindError("资源提交网站会话失效，请重试")
                status, body = getattr(response, "status", 200), response.read().decode("utf-8", "replace")
        except HTTPError as error:
            raise ArtBindError(f"资源提交网站返回 HTTP {error.code}") from None
        except (URLError, OSError):
            raise ArtBindError("资源提交网站网络请求失败") from None
        try:
            data = json.loads(body)
        except ValueError:
            raise ArtBindError("资源提交网站返回的不是 JSON，接口可能已变化") from None
        return status, data

    def info(self, tag):
        """标签详情；标签不存在时返回 None。"""
        status, data = self.post("/api/tag/get_redmine_svn_info", {"tags": [tag]})
        infos = data.get("infos") if isinstance(data, dict) else None
        if status != 200 or not isinstance(infos, list):
            raise ArtBindError(f"查标签详情失败：{_msg(data)}")
        return next((item for item in infos if isinstance(item, dict) and item.get("tag") == tag), None)

    def bound(self, tag):
        """标签现有的绑定列表（资源地址和 popo 群号混在一起）、最新绑定者、平台是否还在等绑定。"""
        status, data = self.post("/api/tag/get_redmine_svn_by_tag", {"tag": tag})
        if status != 200 or not isinstance(data, dict) or not isinstance(data.get("bindSVN"), list):
            raise ArtBindError(f"查标签绑定失败：{_msg(data)}")
        return [str(item) for item in data["bindSVN"]], data.get("code_svn_binder"), bool(data.get("needBindSvn"))

    def bind(self, tag, items):
        """提交整份绑定列表（平台是整份覆盖，不是追加）。"""
        status, data = self.post("/api/tag/bind_redmine_svn_by_tag", {"searchTag": tag, "bindSVN": items})
        if status != 200:
            raise ArtBindError(f"平台拒绝了绑定：{_msg(data)}")
        return _msg(data)


def _msg(data):
    text = data.get("msg") if isinstance(data, dict) else data
    return str(text or "没有说明")[:200]


def connect(config):
    username, password = corp_login.load_credentials(config)
    try:
        # 这个站登记的 OpenID 回调是 http（改成 https 会校验不过），所以放行站点自己的 http 这一跳。
        return Client(corp_login.login(SITE, username, password, entry="/login?next=/", http_hosts=(HOST,)))
    finally:
        password = None


def describe(client, tag, result):
    """读标签现状，写进 result，返回现有绑定列表。"""
    info = client.info(tag)
    if info is None:
        raise ArtBindError(f"资源提交网站上没有这个标签：{tag}")
    items, binder, need = client.bound(tag)
    result.update(bound=items, svns=[i for i in items if not i.isdigit()], groups=[i for i in items if i.isdigit()],
                  binder=binder, need_bind=need, art_svn=info.get("art_svn"), uploader=info.get("sub_account"),
                  mod_time=info.get("mod_time"))
    return items


def run(client, args, result):
    tag = result["tag"]
    items = describe(client, tag, result)
    if args.action == "show":
        return
    target = result["svn"]
    if same_key(target) in {same_key(item) for item in items}:
        result["message"] = "已经绑定过这个地址，没有改动"
        return
    wanted = items + [target]     # 原有的每一项（包括 popo 群号）都保留，只在后面追加
    if not args.apply:
        result["message"] = "预览：加 --apply 后提交"
        result["will_bind"] = wanted
        return
    result["message"] = client.bind(tag, wanted)
    result["applied"] = True
    after, binder, need = client.bound(tag)
    result.update(bound=after, svns=[i for i in after if not i.isdigit()], groups=[i for i in after if i.isdigit()],
                  binder=binder, need_bind=need)
    # 平台会改写提交的内容：svn:// 存成 https://，还会自动补上同分支的 _testhd。所以只核对每一项都还在，不要求列表一模一样。
    missing = [item for item in wanted if same_key(item) not in {same_key(i) for i in after}]
    if missing:
        raise ArtBindError("已提交，但读回的绑定里缺：" + "、".join(missing) + "；请到网站上核对", code=2)
    result["changed"] = True


def main(argv=None, client=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=("show", "bind"))
    parser.add_argument("--tag", help="标签名（美术通知里 art 开头的那一行）")
    parser.add_argument("--text-file", type=Path, help="美术上传通知的原文（UTF-8），从里面取标签")
    parser.add_argument("--root", help="bind：项目根目录，绑定 <项目>/../_test 资源工作副本的地址")
    parser.add_argument("--svn", help="bind：直接给资源地址")
    parser.add_argument("--apply", action="store_true", help="bind：实际提交")
    parser.add_argument("--global-config", "--config", dest="config", type=Path,
                        default=Path.home() / workspace.DIRECTORY / "config.json")
    args = parser.parse_args(argv)
    result = {"action": args.action, "applied": False, "changed": False, "tag": None, "svn": None, "bound": [],
              "svns": [], "groups": [], "binder": None, "need_bind": None, "art_svn": None, "uploader": None,
              "mod_time": None, "will_bind": None, "message": None, "errors": []}
    code = 0
    try:
        # 先检查参数和本地信息，再登录。
        tag = " ".join((args.tag or "").split())
        if not tag and args.text_file:
            try:
                tag = tag_from_text(args.text_file.read_text(encoding="utf-8-sig"))
            except (OSError, UnicodeDecodeError):
                raise ArtBindError(f"读不了 {args.text_file}（要 UTF-8 文本）") from None
            if not tag:
                raise ArtBindError("没有从通知原文里找到标签（要有“已于 art… 成功上传”或 res_copy/art…/ 路径）")
        if not tag:
            raise ArtBindError("需要 --tag 或 --text-file")
        result["tag"] = tag
        if args.action == "bind":
            if bool(args.root) == bool(args.svn):
                raise ArtBindError("bind 需要 --root 或 --svn 其中一个")
            result["svn"] = resource_svn(args.root) if args.root else check_svn(args.svn)
        run(client or connect(args.config), args, result)
    except ArtBindError as error:
        result["errors"].append(str(error))
        code = error.code
    except LoginError as error:
        result["errors"].append(str(error))
        code = 1
    except (AttributeError, KeyError, TypeError):
        result["errors"].append("资源提交网站返回的数据结构已变化，没有继续")
        code = 2 if result["applied"] else 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
