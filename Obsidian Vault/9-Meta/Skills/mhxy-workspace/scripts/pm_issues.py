#!/usr/bin/env python3
"""通过 CORP 登录只读查询易协作工单，按工单保存正文和图片。

依赖 cryptography（SM4）。账号默认读取 ~/.mhxy-workspace/config.json；
会话 Cookie 仅保留在内存中，不使用浏览器、API Key 或已有登录态。
标题标签用 --title-tags 部分服务器外测 报错清理 筛选，--title-tags-mode and/or
控制全部/任一匹配（默认 or）。仅精确匹配标题中的【完整标签】，无别名。
--target-version 按目标版本完整名称或 ID 精确筛选，省略时不限制版本。
默认存入当前工作区 .mhxy-workspace/tasks/；--stdout 仅输出原三列表格。
--show 工单号 只输出该工单的基本信息（标题、状态、直接父单号等）JSON，不落盘。
"""

import argparse
import csv
import hashlib
from html.parser import HTMLParser
import http.cookiejar
import io
import json
from pathlib import Path
import re
import sys
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPCookieProcessor, Request, build_opener

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import corp_login  # noqa: E402
from corp_login import LOGIN, account_prefix  # noqa: E402
import workspace  # noqa: E402


SITE = "https://xyq.pm.netease.com"
DEFAULT_TRACKER = "[客户端]程序开发"
HEADERS = ["工单号", "标题", "具体内容"]


class QueryError(corp_login.LoginError):
    """可直接显示的错误；不包含密码、Cookie 或服务器原始响应。

    继承 LoginError，使调用方用同一个 except 处理查询与登录失败。
    """


RestrictedRedirects = corp_login.redirect_handler(SITE)


class Client:
    """独立内存会话；提供已核实的登录和只读 JSON 接口。"""

    def __init__(self, timeout=30):
        self.timeout = timeout  # 单次网络请求的超时秒数。
        self.csrf = None  # 登录后获取，仅用于本站详情查询。
        self.opener = build_opener(
            HTTPCookieProcessor(http.cookiejar.CookieJar()), RestrictedRedirects()
        )

    def read(self, url, data=None, headers=None):
        """读取响应；错误信息不包含回调 URL、凭据或原始响应。"""
        try:
            with self.opener.open(Request(url, data=data, headers=headers or {}),
                                  timeout=self.timeout) as response:
                body = response.read(32 * 1024 * 1024 + 1)
                if len(body) > 32 * 1024 * 1024:
                    raise QueryError("接口响应过大")
                return response.url, body.decode("utf-8")
        except HTTPError as error:
            raise QueryError(f"接口返回 HTTP {error.code}，未输出部分结果") from None
        except (URLError, OSError, UnicodeError):
            raise QueryError("网络请求失败或响应编码异常，未输出部分结果") from None

    def api(self, path, params=None, post=False):
        """调用本站只读接口，校验业务成功码。"""
        allowed = {"/account/user_info", "/issues", "/issues/all_users", "/issue_show/base"}
        if path not in allowed:
            raise QueryError("不支持此接口")
        url = SITE + "/api/v6" + path
        headers = {"Accept": "application/json"}
        data = None
        if post:
            headers["Content-Type"] = "application/json"
            if self.csrf:
                headers["X-CSRF-Token"] = self.csrf
            data = json.dumps(params or {}).encode("utf-8")
        elif params:
            url += "?" + urlencode(params, doseq=True)
        _, body = self.read(url, data, headers)
        try:
            value = json.loads(body)
        except ValueError:
            raise QueryError("接口未返回 JSON，可能需要登录或认证已失效") from None
        if not isinstance(value, dict) or value.get("res_code") != 1 or "data" not in value:
            raise QueryError("接口拒绝请求或响应格式已变化，请检查登录与权限")
        return value["data"]

    def login(self, username, password):
        """密码登录并核对实际身份，不自动重试密码。"""
        prefix = account_prefix(username)
        login_url, html = self.read(SITE + "/login")
        if urlsplit(login_url).netloc != urlsplit(LOGIN).netloc:
            raise QueryError("未到达已识别的 CORP 登录页")
        form = corp_login.fill_corp_form(corp_login.corp_form(html), html, prefix, password)
        try:
            self.read(login_url, urlencode(form).encode(), {"Origin": LOGIN, "Referer": login_url})
        finally:
            form.clear()
        user = as_dict(as_dict(self.api("/account/user_info"), "用户信息").get("user"), "用户信息")
        if (user.get("mail") or "").lower() != prefix + "@corp.netease.com":
            raise QueryError("登录未完成或账号不匹配；可能需要二次验证，未自动重试")
        self.csrf = user.get("csrf_token")
        return user

    def image(self, url):
        """下载受限大小的真实图片；跨站图片使用独立无凭据会话。"""
        target = urlsplit(url)
        if target.scheme != "https" or not target.netloc or target.username or target.password:
            raise QueryError("图片地址必须是无内嵌凭据的 HTTPS 地址")

        class ImageRedirects(HTTPRedirectHandler):
            """图片重定向仅允许同源 HTTPS，避免转发认证信息。"""

            def redirect_request(self, req, fp, code, msg, headers, newurl):
                destination = urlsplit(newurl)
                if (destination.scheme, destination.netloc) != (target.scheme, target.netloc):
                    raise QueryError("图片发生跨站重定向，未下载")
                return super().redirect_request(req, fp, code, msg, headers, newurl)

        handlers = [ImageRedirects()]
        if target.netloc == urlsplit(SITE).netloc:
            for handler in self.opener.handlers:
                if isinstance(handler, HTTPCookieProcessor):
                    handlers.append(HTTPCookieProcessor(handler.cookiejar))
        opener = build_opener(*handlers)
        try:
            with opener.open(Request(url, headers={"Accept": "image/*"}), timeout=self.timeout) as response:
                data = response.read(32 * 1024 * 1024 + 1)
            if len(data) > 32 * 1024 * 1024:
                raise QueryError("图片超过 32 MiB，未保存")
            extension = image_extension(data)
            if extension is None:
                raise QueryError("响应不是支持的图片，可能需要认证")
            return data, extension
        except (HTTPError, URLError, OSError):
            raise QueryError("图片下载失败，可能需要认证或网络不可用") from None


def as_dict(value, label):
    """接口数据应为对象；不是时报“格式已变化”，不让后续 .get 抛出难懂的异常。"""
    if not isinstance(value, dict):
        raise QueryError(f"{label}格式已变化")
    return value


def issue_detail(client, issue_id):
    """读取工单详情接口中的 base 对象。"""
    detail = as_dict(client.api("/issue_show/base", {"id": issue_id}, post=True), "工单详情")
    return as_dict(detail.get("base"), "工单详情")


def resolve_user(client, selector, current_user):
    """将本人、用户 ID、邮箱、账号或精确显示名解析为唯一用户 ID。"""
    if selector == "me":
        return int(current_user["id"])
    if selector.isascii() and selector.isdigit() and int(selector) > 0:
        return int(selector)
    users = client.api("/issues/all_users")
    if not isinstance(users, list):
        raise QueryError("用户列表格式已变化")
    matches = []
    for user in users:
        mail = user.get("mail") or ""
        candidates = [str(user.get("name", "")), mail, mail.split("@")[0], str(user.get("login", ""))]
        if selector.lower() in [candidate.lower() for candidate in candidates if candidate]:
            matches.append(user)
    if len(matches) != 1:
        raise QueryError("无法唯一匹配用户，请使用精确邮箱、显示名或用户 ID")
    return int(matches[0]["id"])


def matches_target_version(issue, target_version):
    """精确匹配目标版本名称或 ID；字段缺失不冒充没有匹配工单。"""
    if target_version is None:
        return True
    if not isinstance(target_version, str) or not target_version.strip():
        raise QueryError("目标版本必须为完整名称或 ID，不能留空")
    if "fixed_version" not in issue:
        raise QueryError("接口未返回目标版本字段，无法可靠筛选")
    version = issue["fixed_version"]
    if version is None:
        return False
    if not isinstance(version, dict) or not isinstance(version.get("value"), str) or type(version.get("id")) is not int:
        raise QueryError("目标版本字段结构已变化，无法可靠筛选")
    selector = target_version.strip()
    return str(version["id"]) == selector if selector.isascii() and selector.isdigit() else version["value"] == selector


def list_open_issues(client, project, user_id, tracker, page_size=100, target_version=None):
    """遍历所有分页，验证负责人和状态，再按跟踪标签和目标版本筛选。"""
    issues = []
    seen = set()
    page = 1
    total = None
    while True:
        params = {
            "project_id": project, "set_filter": 1, "mode": "list",
            "filter_mode": "simple", "f[]": ["status_id", "assigned_to_id"],
            "op[status_id]": "o", "op[assigned_to_id]": "=",
            "v[assigned_to_id][]": str(user_id), "page": page, "per_page": page_size,
            "sort": "id:asc", "c[]": ["id", "tracker", "subject", "assigned_to", "status", "fixed_version"],
        }
        data = as_dict(client.api("/issues", params), "工单列表")
        rows = data.get("list")
        if not isinstance(rows, list):
            raise QueryError("工单列表格式已变化")
        if data.get("invalid_filter_fields"):
            raise QueryError("服务器拒绝了查询筛选条件")
        count = data.get("total_count")
        if type(count) is not int or count < 0 or data.get("page") != page:
            raise QueryError("分页元数据缺失或页码不一致，未输出部分结果")
        if total is not None and count != total:
            raise QueryError("查询期间工单数量发生变化，请重新运行以获取完整结果")
        total = count
        for row in rows:
            row = as_dict(row, "工单列表")
            issue_id = row.get("id")
            if not isinstance(issue_id, int) or issue_id in seen:
                raise QueryError("分页出现重复或无效工单，未输出不完整结果")
            seen.add(issue_id)
            assignee = row.get("assigned_to")  # 未指派时为 null。
            if row.get("is_closed") is not False or not isinstance(assignee, dict) or assignee.get("id") != user_id:
                raise QueryError("服务端返回了不符合负责人或未关闭条件的工单")
            if (tracker == "*" or row.get("tracker") == tracker or str(row.get("tracker_id")) == tracker) and matches_target_version(row, target_version):
                issues.append(row)
        if len(seen) == total:
            break
        if not rows or len(seen) > total:
            raise QueryError("工单条数与服务端总数不一致，未输出部分结果")
        page += 1
        if page > 10000:
            raise QueryError("分页超过安全上限，未输出部分结果")
    return issues


class DescriptionText(HTMLParser):
    """将正文 HTML 转为可读文本，保留链接和图片地址。"""

    def __init__(self, local_links=None):
        super().__init__(convert_charrefs=True)
        self.parts = []  # 文本和段落分隔符。
        self.links = []  # 当前尚未结束的链接目标。
        self.suppressed = 0  # 不展示的脚本或样式嵌套深度。
        self.local_links = local_links  # 非 None 时输出 Markdown，并替换已下载文件链接。
        self.images = []  # 按正文顺序收集图片源地址。

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("script", "style"):
            self.suppressed += 1
        if self.suppressed:
            return
        if tag in ("p", "div", "br", "tr", "pre", "blockquote", "h1", "h2", "h3", "h4"):
            self.parts.append("\n")
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag in ("td", "th"):
            self.parts.append("\t")
        elif tag == "a":
            self.links.append(urljoin(SITE, attrs["href"]) if attrs.get("href") else "")
            if self.local_links is not None:
                self.parts.append("[")
        elif tag == "img":
            source = urljoin(SITE, attrs["src"]) if attrs.get("src") else ""
            if source and source not in self.images:
                self.images.append(source)
            label = attrs.get("alt") or "未命名"
            if self.local_links is None:
                self.parts.append(f"[图片：{label}] {source}")
            else:
                label = markdown_text(label)
                self.parts.append(f"![{label}](<{self.local_links.get(source, source)}>)")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.suppressed:
            self.suppressed -= 1
            return
        if self.suppressed:
            return
        if tag == "a" and self.links:
            target = self.links.pop()
            if self.local_links is not None:
                self.parts.append(f"](<{self.local_links.get(target, target)}>)")
            elif target:
                self.parts.append(f" ({target})")
        elif tag in ("p", "div", "tr", "li", "pre", "blockquote", "h1", "h2", "h3", "h4"):
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.suppressed:
            self.parts.append(markdown_text(data) if self.local_links is not None else data)


def description_text(description):
    """转换富文本正文；普通文本原样保留。"""
    if not re.search(r"<(?:p|div|br|a|img|ul|ol|table|pre|h[1-6])\b", description, re.I):
        return description
    parser = DescriptionText()
    parser.feed(description)
    parser.close()
    return re.sub(r"\n{3,}", "\n\n", "".join(parser.parts)).strip()


def normalize_title_tags(tags):
    """规范化完整标签，接受可选的【】外框，不推断缩写。"""
    normalized = set()
    for tag in tags or ():
        value = tag.strip()
        if value.startswith("【") and value.endswith("】"):
            value = value[1:-1].strip()
        if not value or "【" in value or "】" in value:
            raise QueryError("标题标签不能为空，每个参数只填写一个标签")
        normalized.add(value)
    return normalized


def matches_title_tags(subject, tags, mode):
    """按 AND/OR 精确匹配【】内的标签，普通标题文字不参与匹配。"""
    if mode not in ("and", "or"):
        raise QueryError("标题标签匹配模式只支持 and 或 or")
    if not tags:
        return True
    actual = {tag.strip() for tag in re.findall(r"【([^【】]+)】", subject)}
    return tags <= actual if mode == "and" else bool(tags & actual)


def query_rows(client, project, user_id, tracker, page_size=100, raw_description=False,
               title_tags=None, title_tags_mode="or", target_version=None):
    """查询工单完整正文，全部成功后返回三列数据。"""
    rows = []
    tags = normalize_title_tags(title_tags)
    matches_title_tags("", tags, title_tags_mode)
    for issue in list_open_issues(client, project, user_id, tracker, page_size, target_version):
        subject = issue["subject"]
        if isinstance(subject, dict):
            subject = subject["value"]
        # 先按列表标题筛选，避免为不匹配的工单请求详情。
        if not matches_title_tags(subject, tags, title_tags_mode):
            continue
        base = issue_detail(client, issue["id"])
        # 详情中的 assigned_to 是展示字符串；负责人 ID 以列表接口为准。
        if base.get("id") != issue["id"] or base.get("is_closed") is not False:
            raise QueryError(f"#{issue['id']} 的详情标识不一致或已关闭，请重新查询")
        description = base.get("description")
        if not isinstance(description, str):
            raise QueryError(f"#{issue['id']} 的正文格式已变化或无权限读取")
        rows.append([f"#{issue['id']}", subject,
                     description if raw_description else description_text(description)])
    return rows


def issue_base(client, issue_id):
    """读取单个工单的基本信息，不含正文；已关闭的工单也可以读取。

    Returns:
        {"issue_id", "title", "tracker", "status", "is_closed", "parent_id", "created_on"}。
        parent_id 是直接父单号（字符串），没有父单时为 None；created_on 为接口原值（ISO 8601）。
    """
    workspace.validate_issue_id(str(issue_id))
    base = issue_detail(client, int(issue_id))
    if base.get("id") != int(issue_id):
        raise QueryError(f"#{issue_id} 的详情标识不一致或无权限读取")
    subject, parent = base.get("subject"), base.get("parent_id")
    if not isinstance(subject, str) or not subject.strip():
        raise QueryError(f"#{issue_id} 的标题格式已变化")
    if parent is not None and (type(parent) is not int or parent <= 0):
        raise QueryError(f"#{issue_id} 的父单号格式已变化")
    return {"issue_id": str(issue_id), "title": subject, "tracker": base.get("tracker"),
            "status": base.get("status"), "is_closed": base.get("is_closed"),
            "parent_id": str(parent) if parent else None, "created_on": base.get("created_on")}


def render(rows, format_name):
    """输出三列；JSON/CSV 保留原始正文，Markdown 仅转义表格分隔符。"""
    if format_name == "json":
        return json.dumps([HEADERS, *rows], ensure_ascii=False, indent=2) + "\n"
    if format_name == "csv":
        stream = io.StringIO(newline="")
        writer = csv.writer(stream)
        writer.writerow(HEADERS)
        writer.writerows(rows)
        return stream.getvalue()

    def cell(value):
        return (str(value).replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace("|", "&#124;")
                .replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>"))

    table = ["| " + " | ".join(HEADERS) + " |", "| --- | --- | --- |"]
    table.extend("| " + " | ".join(cell(value) for value in row) + " |" for row in rows)
    return "\n".join(table) + "\n"


def markdown_text(value):
    """转义正文中的 Markdown 控制字符，保留原始文字含义。"""
    return re.sub(r"([\\`*{}_\[\]<>#!|])", r"\\\1", value)


def image_extension(data):
    """按内容识别可离线查看的图片，拒绝登录 HTML 和未知文件。"""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return ".webp"
    if data.startswith(b"BM"):
        return ".bmp"
    return None


MARKDOWN_IMAGE = re.compile(r"!\[[^\]\n]*\]\(\s*(?:<([^>\n]+)>|([^\s)]+))(?:\s+\"[^\"\n]*\")?\s*\)")


def issue_document(client, row, local_issue_links):
    """生成一个工单及其图片；失败图片保留远端链接并显式列出。"""
    issue_id, title, description = row
    issue_id = issue_id.removeprefix("#")
    entry = workspace.issue_entry(issue_id, title)
    html_body = bool(re.search(r"<(?:p|div|br|a|img|ul|ol|table|pre|h[1-6])\b", description, re.I))
    parser = DescriptionText()
    if html_body:
        parser.feed(description)
        parser.close()
        sources = parser.images
    else:
        sources = list(dict.fromkeys(urljoin(SITE, m[1] or m[2]) for m in MARKDOWN_IMAGE.finditer(description)))
    replacements = dict(local_issue_links)
    images, failures = {}, []
    for source in sources:
        try:
            data, extension = client.image(source)
            name = "image-" + hashlib.sha256(source.encode("utf-8")).hexdigest()[:20] + extension
            images[name] = data
            replacements[source] = name
        except QueryError as error:
            failures.append({"issue_id": issue_id, "image_number": len(failures) + len(images) + 1,
                             "reason": str(error)})
    if html_body:
        parser = DescriptionText(replacements)
        parser.feed(description)
        parser.close()
        body = re.sub(r"\n{3,}", "\n\n", "".join(parser.parts)).strip()
    else:
        def replace_image(match):
            source = urljoin(SITE, match[1] or match[2])
            destination = replacements.get(source, source)
            label = match[0][2:match[0].index("]")]
            return f"![{label}](<{destination}>)"
        body = MARKDOWN_IMAGE.sub(replace_image, description)
        # 同一图片的普通链接（含相对 URL）也改成本地地址，不碰其他链接。
        def replace_link(match):
            source = urljoin(SITE, match[2] or match[3])
            return f"[{match[1]}](<{replacements[source]}>)" if source in replacements else match[0]
        body = re.sub(r'(?<!!)\[([^\]\n]*)\]\(\s*(?:<([^>\n]+)>|([^\s)]+))(?:\s+"[^"\n]*")?\s*\)',
                      replace_link, body)
    warning = "\n\n> 部分图片下载失败，正文保留原链接；图片内容尚未采集完整。" if failures else ""
    text = f"# {issue_id} {markdown_text(title)}\n\n来源：{SITE}/issues/{issue_id}\n\n{body}{warning}\n"
    return entry, {"issue.md": text.encode("utf-8"), **images}, failures


def save_issues(client, rows, root_arg, config_path, query):
    """所有工单准备完成后统一落盘；保留未返回工单、Mock 及用户辅助文件。"""
    root, personal, _ = workspace.paths(root_arg, config_path)
    entries, changes, warnings = [], [], []
    ids = [row[0].removeprefix("#") for row in rows]
    for issue_id in ids:
        workspace.validate_issue_id(issue_id)
    if len(set(ids)) != len(ids):
        raise QueryError("查询包含重复工单")
    local_links = {SITE + "/issues/" + issue_id: "../" + issue_id + "/issue.md" for issue_id in ids}
    for row in rows:
        entry, files, failures = issue_document(client, row, local_links)
        entries.append(entry)
        warnings.extend(failures)
        for name, data in files.items():
            path = personal / "tasks" / entry["issue_id"] / name
            old = workspace.read_bytes(path)
            if old != data:
                changes.append((path, old, data))
    index = {"fetched_at": datetime.now(timezone.utc).isoformat(), "query": query,
             "tasks": entries, "image_failures": warnings}
    path = personal / "tasks/index.json"
    changes.append((path, workspace.read_bytes(path), workspace.json_bytes(index)))
    # 已追踪工单标题跟随本次实际返回值更新；缺席工单不自动取消追踪。
    tracking_path, old, tracking = workspace.read_tracking(personal)
    if old is not None:
        available = {entry["issue_id"]: entry for entry in entries}
        tracking["tracked_tasks"] = [available.get(item["issue_id"], item) for item in tracking["tracked_tasks"]]
        new = workspace.json_bytes(tracking)
        if old != new:
            changes.append((tracking_path, old, new))
    workspace.apply_changes(changes)
    return {"status": "partial" if warnings else "saved", "query": query, "tasks": entries,
            "index_path": str(path), "image_failures": warnings}


def credentials(config_path, username=None):
    """读取账号配置；实现见 corp_login.load_credentials。"""
    return corp_login.load_credentials(config_path, username)


def main(argv=None):
    """默认落盘并返回简短 JSON 清单；--stdout 保留表格导出能力。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path.home()/".mhxy-workspace/config.json")
    parser.add_argument("--username", help="登录账号；省略时使用配置中的 openid_username")
    parser.add_argument("--root", default=".", help="保存工单的项目根目录")
    parser.add_argument("--stdout", action="store_true", help="仅导出表格，不落盘或下载图片")
    parser.add_argument("--show", metavar="工单号", help="只读取该工单的基本信息（含父单号）并输出 JSON，不落盘")
    parser.add_argument("--user", default="me", help="负责人：me、用户 ID、精确邮箱、账号或显示名")
    parser.add_argument("--tracker", default=DEFAULT_TRACKER, help="精确跟踪标签或 ID；* 表示所有标签")
    parser.add_argument("--target-version", help="目标版本完整名称或 ID，精确匹配；省略则不限版本")
    parser.add_argument("--title-tags", nargs="+", action="extend", metavar="标签",
                        help="标题【完整标签】精确筛选，无缩写；可输入多个或重复此参数")
    parser.add_argument("--title-tags-mode", type=str.lower, choices=["and", "or"], default="or",
                        help="多个标题标签：and 全部满足，or 任一满足（默认）")
    parser.add_argument("--project", default="mhxy")
    parser.add_argument("--format", choices=["markdown", "csv", "json"], default="markdown")
    parser.add_argument("--raw-description", action="store_true", help="保留接口原始 HTML 正文")
    parser.add_argument("--timeout", type=float, default=30)
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    try:
        if args.timeout <= 0 or not args.user.strip() or not args.tracker.strip():
            raise QueryError("超时须大于零，用户和标签不能为空")
        if args.target_version is not None:
            args.target_version = args.target_version.strip()
            if not args.target_version:
                raise QueryError("目标版本不能为空；不限制版本时省略 --target-version")
        normalize_title_tags(args.title_tags)
        if args.show is not None:
            workspace.validate_issue_id(args.show)
        elif not args.stdout:
            workspace.paths(args.root, args.config)
        username, password = credentials(args.config.expanduser(), args.username)
        client = Client(args.timeout)
        current_user = client.login(username, password)
        password = None
        if args.show is not None:
            output = json.dumps(issue_base(client, args.show), ensure_ascii=False, indent=2) + "\n"
            sys.stdout.write(output)
            return 0
        user_id = resolve_user(client, args.user, current_user)
        rows = query_rows(client, args.project, user_id, args.tracker,
                          raw_description=args.raw_description or not args.stdout,
                          title_tags=args.title_tags, title_tags_mode=args.title_tags_mode,
                          target_version=args.target_version)
        result = None
        if args.stdout:
            output = render(rows, args.format)
        else:
            result = save_issues(client, rows, args.root, args.config,
                                 {"project": args.project, "user": args.user, "user_id": user_id,
                                  "tracker": args.tracker, "title_tags": sorted(normalize_title_tags(args.title_tags)),
                                  "title_tags_mode": args.title_tags_mode, "target_version": args.target_version})
            output = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        sys.stdout.write(output)
        return 2 if result and result["image_failures"] else 0
    except corp_login.LoginError as error:
        print(f"查询失败：{error}", file=sys.stderr)
        return 1
    except (workspace.WorkspaceError, OSError) as error:
        print(f"本地保存失败：{error}", file=sys.stderr)
        return 1
    except (AttributeError, KeyError, TypeError, ValueError):
        print("查询失败：接口数据结构已变化，未输出部分结果", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
