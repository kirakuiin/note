#!/usr/bin/env python3
"""提 CR：把本人在当前分支为某工单提交的改动生成 CR diff，经 Jenkins 上传到 reviewboard。

流程说明见 references/cr-diff.md。复刻 MHCoder 插件「生成 CR DIFF」，但自动选择 revision：
  prepare  只读：查工单（标题、父单号），找出本人提交，生成 diff 和清单，存到
           .mhxy-workspace/code-review/<工单号>/，输出预览。
  upload   组装上传参数；默认只预览，加 --apply 才上传，并跟踪本次触发的构建。

Jenkins 地址和凭据在上传时从本机已安装的 MHCoder 插件中读取，不保存、不输出。
退出码：0 成功；1 失败；2 已上传但构建未成功或结果未确认。
"""
import argparse
import base64
from datetime import date, datetime, timedelta
import hashlib
import json
from pathlib import Path
import re
import secrets
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlencode, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from xml.etree import ElementTree

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import corp_login  # noqa: E402
import pm_issues  # noqa: E402
import precommit  # noqa: E402
import workspace  # noqa: E402

OUTPUT_DIRECTORY = "code-review"  # 个人目录下的子目录，每个工单一个文件夹。
DIFF_FILE = "crDiff.diff"  # 与插件上传的文件名一致。
MANIFEST_FILE = "manifest.json"
DESC_LIMIT = 200  # review_desc 的最大字符数；与 references/cr-diff.md 一致，修改时两处同步。
# MHCoder 插件的安装位置和实现 CR 上传的文件；插件升级改了结构时，plugin_endpoint 会报错。
PLUGIN_DIRS = ("~/.vscode/extensions", "~/.cursor/extensions")
PLUGIN_NAME = re.compile(r"mhxy2\.mhcoder-(\d+)\.(\d+)\.(\d+)")
PLUGIN_FILE = "client/out/modules/MHToolsWebview/MHToolsWebviewManager.js"
REVIEW_URL = re.compile(r"https?://reviewboard\.mhxy\.netease\.com/r/\d+/?")
POLL_SECONDS = 2


class CrError(Exception):
    """可直接显示的错误；不包含凭据或服务器原始响应。"""


# ---------------------------------------------------------------- 收集提交与 diff


def branch_info(root):
    """读取工作副本的仓库 URL 和仓库内路径（如 `/products/.../wzw_x`）。"""
    tree = ElementTree.fromstring(precommit.run_svn(root, "info", "--xml", "."))
    url, relative = tree.findtext("entry/url"), tree.findtext("entry/relative-url")
    if not url or not relative or not relative.startswith("^/"):
        raise CrError("无法读取工作副本的仓库地址")
    return {"url": url, "path": relative[1:].rstrip("/")}


def branch_relative(repo_path, branch_path):
    """把日志里的仓库内路径转成分支内相对路径；不在分支内时返回 None。"""
    prefix = branch_path + "/"
    return repo_path[len(prefix):] if repo_path and repo_path.startswith(prefix) else None


def is_excluded(rel):
    """导表数据（data/）不参加 CR。"""
    return rel.split("/", 1)[0] == precommit.DATA_DIRECTORY


def own_commits(log_xml, issue_id, author, branch_path):
    """从 svn log -v 的 XML 中挑出本人为该工单的提交。

    说明里含 `#工单号`（后面不能紧跟数字，`finish #` 写法也算）且作者为本人才算。

    Returns:
        (revisions 升序列表, {相对路径: 动作集合}, 整体复制进来的目录集合)
    """
    pattern = re.compile(rf"#{issue_id}(?!\d)")
    revisions, files, copied_dirs = [], {}, set()
    for entry in ElementTree.fromstring(log_xml).iter("logentry"):
        if (entry.findtext("author") or "").lower() != author.lower() or not pattern.search(entry.findtext("msg") or ""):
            continue
        revisions.append(int(entry.get("revision")))
        for node in entry.iter("path"):
            rel = branch_relative(node.text, branch_path)
            if not rel:
                continue
            if node.get("kind") == "dir":
                # 复制进来的目录在日志里只记目录本身，里面的文件要按目录前缀从 diff 中取。
                if node.get("action") in ("A", "R") and node.get("copyfrom-path"):
                    copied_dirs.add(rel)
                continue
            files.setdefault(rel, set()).add(node.get("action"))
    return sorted(set(revisions)), files, copied_dirs


def others_in_range(log_xml, own_revisions, selected):
    """范围内他人（或本人其他工单）也改过所选文件的提交；它们的改动会混进 diff。"""
    found = []
    for entry in ElementTree.fromstring(log_xml).iter("logentry"):
        revision = int(entry.get("revision"))
        if revision in own_revisions:
            continue
        touched = sorted({node.text for node in entry.iter("path")} & set(selected))
        if touched:
            found.append({"revision": revision, "author": entry.findtext("author"), "files": touched})
    return found


def decode_path(raw):
    """diff 头中的路径：svn 按系统代码页输出，中文 Windows 上一般是 GBK。"""
    for encoding in ("utf-8", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            pass
    return raw.decode("utf-8", "replace")


def split_chunks(diff):
    """按 `Index: ` 行把 svn diff 切成 [(相对路径, 原始字节)]，字节保持原样不转码。"""
    starts = [match.start() for match in re.finditer(rb"(?m)^Index: ", diff)]
    chunks = []
    for index, start in enumerate(starts):
        chunk = diff[start:starts[index + 1] if index + 1 < len(starts) else len(diff)]
        header = chunk.split(b"\n", 1)[0].rstrip(b"\r")
        chunks.append((decode_path(header[len(b"Index: "):]), chunk))
    return chunks


def select_chunks(chunks, files, copied_dirs):
    """保留本人提交改过的文件（含复制进来的目录下的文件）。"""
    def wanted(path):
        return path in files or any(path.startswith(d + "/") for d in copied_dirs)
    return [(path, chunk) for path, chunk in chunks if wanted(path)]


def log_xml(root, url, *args):
    """只读查询分支日志（含改动路径）；`--stop-on-copy` 让查询不越过分支的创建点。"""
    return precommit.run_svn(root, "log", "--xml", "-v", "--stop-on-copy", *args, url)


def collect(root, issue, author):
    """找出提交并生成 diff。

    revision 范围照插件：首个提交的前一版到最后一个提交，对整个分支做 diff，
    再只保留这些提交改过、且不在 data/ 下的文件。

    Raises:
        CrError: 没有找到提交，或筛选后没有可审查的改动。
    """
    branch = branch_info(root)
    created = (issue.get("created_on") or "")[:10]
    try:
        since = date.fromisoformat(created) - timedelta(days=1)  # 留一天余量，避免时区差漏掉提交
    except ValueError:
        raise CrError("工单创建时间格式已变化") from None
    revisions, files, copied_dirs = own_commits(
        log_xml(root, branch["url"], "--search", f"#{issue['issue_id']}", "-r", f"{{{since.isoformat()}}}:HEAD"),
        issue["issue_id"], author, branch["path"])
    if not revisions:
        raise CrError(f"当前分支没有找到 {author} 提交的 #{issue['issue_id']} 记录")
    previous, last = revisions[0] - 1, revisions[-1]
    excluded = sorted(path for path in files if is_excluded(path))
    files = {path: actions for path, actions in files.items() if not is_excluded(path)}
    copied_dirs = {d for d in copied_dirs if not is_excluded(d)}
    diff = precommit.run_svn(root, "diff", "--internal-diff", "-r", f"{previous}:{last}", branch["url"])
    chunks = select_chunks(split_chunks(diff), files, copied_dirs)
    if not chunks:
        raise CrError("排除 data/ 后没有可审查的改动")
    included = [path for path, _ in chunks]
    repo_paths = {branch["path"] + "/" + path for path in included}
    others = others_in_range(log_xml(root, branch["url"], "-r", f"{previous + 1}:{last}"), set(revisions), repo_paths)
    for item in others:
        item["files"] = [branch_relative(path, branch["path"]) for path in item["files"]]
    return {"branch": branch["url"], "revisions": revisions, "range": f"{previous}:{last}",
            "files": included, "excluded_data": excluded,
            "not_in_diff": sorted(set(files) - set(included)), "others_in_range": others,
            "diff": b"".join(chunk for _, chunk in chunks)}


# ---------------------------------------------------------------- 表单字段


def account(config_values):
    """real_user 用 CORP 邮箱前缀。"""
    return corp_login.account_prefix(config_values.get("openid_username"))


def base_fields(manifest, title=None, testing_done=None, today=None):
    """除 review_desc 外的表单字段；没有父单号又没有指定时 testing_done 为 None。"""
    tomorrow = ((today or date.today()) + timedelta(days=1)).isoformat()
    return {"from_url": manifest["branch"],
            "review_title": title or f"#{manifest['issue']['issue_id']} {manifest['issue']['title']}",
            "time_request": "|".join([tomorrow] * 3),  # 外测、全服、期望完成时间
            "testing_done": testing_done or manifest["issue"]["parent_id"], "real_user": manifest["real_user"]}


def form_fields(manifest, desc, title=None, testing_done=None, today=None):
    """组装上传的全部表单字段（不含 token）。

    Raises:
        CrError: 描述为空或超长、testing_done 缺失或不是工单号。
    """
    desc = (desc or "").strip()
    if not desc:
        raise CrError("review_desc 不能为空")
    if len(desc) > DESC_LIMIT:
        raise CrError(f"review_desc 有 {len(desc)} 字，超过 {DESC_LIMIT} 字")
    fields = base_fields(manifest, title, testing_done, today)
    if not fields["testing_done"] or not re.fullmatch(r"[1-9]\d*", fields["testing_done"]):
        raise CrError("工单没有父单号，请用 --testing-done 指定")
    return {**fields, "review_desc": desc}


# ---------------------------------------------------------------- Jenkins


def plugin_endpoint(dirs=PLUGIN_DIRS):
    """从本机最新版 MHCoder 插件读取 Jenkins 任务地址、账号和触发 token。"""
    candidates = []
    for base in dirs:
        base = Path(base).expanduser()
        for folder in base.glob("mhxy2.mhcoder-*") if base.is_dir() else ():
            match = PLUGIN_NAME.fullmatch(folder.name)
            if match and (folder / PLUGIN_FILE).is_file():
                candidates.append((tuple(map(int, match.groups())), folder / PLUGIN_FILE))
    if not candidates:
        raise CrError("没有找到 MHCoder 插件（VS Code 或 Cursor），无法读取 CR 上传配置")
    source = max(candidates)[1].read_text(encoding="utf-8")
    url = re.search(r"const url = '(https?://[^']+/buildWithParameters)'", source)
    token = re.search(r"const token = '([^']+)'", source)
    parts = urlsplit(url[1]) if url else None
    if not parts or not token or not parts.username or not parts.password:
        raise CrError("MHCoder 插件的 CR 上传配置格式已变化")
    netloc = parts.hostname + (f":{parts.port}" if parts.port else "")
    job = urlunsplit((parts.scheme, netloc, parts.path[:-len("/buildWithParameters")], "", ""))
    return {"job": job, "user": unquote(parts.username), "password": unquote(parts.password), "token": token[1]}


class NoRedirects(HTTPRedirectHandler):
    """带凭据的请求不跟随跳转，避免把认证头发到别处。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise CrError("Jenkins 返回了跳转，已停止")


class Jenkins:
    """只访问插件里那个 Jenkins 任务所在的站点。"""

    def __init__(self, endpoint, timeout=30, opener=None):
        self.job = endpoint["job"]
        self.netloc = urlsplit(self.job).netloc
        self.auth = "Basic " + base64.b64encode(f"{endpoint['user']}:{endpoint['password']}".encode()).decode()
        self.timeout = timeout
        self.opener = opener or build_opener(NoRedirects())

    def open(self, url, data=None, headers=None):
        """返回 (响应头, 正文字节)。"""
        if urlsplit(url).netloc != self.netloc:
            raise CrError("Jenkins 返回了其他站点的地址，已停止")
        request = Request(url, data=data, headers={"Authorization": self.auth, **(headers or {})})
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                return response.headers, response.read(8 * 1024 * 1024)
        except HTTPError as error:
            raise CrError(f"Jenkins 返回 HTTP {error.code}") from None
        except (URLError, OSError):
            raise CrError("Jenkins 网络请求失败") from None

    def json(self, url):
        """读取 Jenkins 的 JSON 接口。"""
        try:
            return json.loads(self.open(url)[1])
        except ValueError:
            raise CrError("Jenkins 返回的不是 JSON") from None

    def trigger(self, token, fields, diff):
        """照插件的请求格式触发构建：参数放在 URL 上，diff 作为 client_diff.dat 文件上传。

        Returns:
            队列项地址（以 / 结尾）。
        """
        boundary = "----mhxyCrDiff" + secrets.token_hex(12)
        body = (f'--{boundary}\r\nContent-Disposition: form-data; name="client_diff.dat"; filename="{DIFF_FILE}"\r\n'
                "Content-Type: application/octet-stream\r\n\r\n").encode() + diff + f"\r\n--{boundary}--\r\n".encode()
        query = urlencode({"token": token, **fields}, quote_via=quote)
        headers, _ = self.open(f"{self.job}/buildWithParameters?{query}", body,
                               {"Content-Type": f"multipart/form-data; boundary={boundary}"})
        location = headers.get("Location") or ""
        if "/queue/item/" not in location:
            raise CrError("Jenkins 没有返回队列地址，无法确认是否已触发")
        return location.rstrip("/") + "/"

    def follow(self, queue_url, wait=300, sleep=time.sleep):
        """等本次触发的构建结束，返回构建结果；超时时 result 为 None。"""
        deadline = time.monotonic() + wait
        build_url = None
        while build_url is None:
            item = self.json(queue_url + "api/json")
            if item.get("cancelled"):
                raise CrError("Jenkins 队列中的构建已被取消")
            build_url = (item.get("executable") or {}).get("url")
            if build_url is None:
                if time.monotonic() > deadline:
                    return {"queue_url": queue_url, "build_url": None, "result": None, "review_url": None}
                sleep(POLL_SECONDS)
        build_url = build_url.rstrip("/") + "/"
        while True:
            build = self.json(build_url + "api/json?tree=number,result,building")
            if not build.get("building") and build.get("result"):
                break
            if time.monotonic() > deadline:
                return {"queue_url": queue_url, "build_url": build_url, "result": None, "review_url": None}
            sleep(POLL_SECONDS)
        console = self.open(build_url + "consoleText")[1].decode("utf-8", "replace")
        review = REVIEW_URL.findall(console)
        return {"queue_url": queue_url, "build_url": build_url, "result": build["result"],
                "review_url": review[-1] if review else None,
                "console_tail": console.splitlines()[-15:] if build["result"] != "SUCCESS" else []}


# ---------------------------------------------------------------- 命令


def output_dir(personal, issue_id):
    """该工单的 diff 和清单所在目录；工单号同时用作目录名，先校验。"""
    workspace.validate_issue_id(issue_id)
    return personal / OUTPUT_DIRECTORY / issue_id


def prepare(root_arg, config, issue_id, lookup=None):
    """只读查询并生成 diff 和清单；lookup 用于测试替换工单查询。"""
    root, personal, _ = workspace.paths(root_arg, config)
    author = account(workspace.load_config(root_arg, config))
    issue = (lookup or remote_issue)(config, issue_id)
    collected = collect(root, issue, author)
    diff = collected.pop("diff")
    manifest = {"issue": {key: issue[key] for key in ("issue_id", "title", "parent_id", "tracker", "status")},
                "real_user": author, **collected, "diff_sha256": hashlib.sha256(diff).hexdigest(),
                "prepared_at": datetime.now().astimezone().isoformat(timespec="seconds")}
    folder = output_dir(personal, issue_id)
    changes = []
    for name, data in ((DIFF_FILE, diff), (MANIFEST_FILE, workspace.json_bytes(manifest))):
        old = workspace.read_bytes(folder / name)
        if old != data:
            changes.append((folder / name, old, data))
    workspace.apply_changes(changes)
    return {**manifest, "diff_path": (folder / DIFF_FILE).relative_to(root).as_posix(), "diff_bytes": len(diff),
            "fields": base_fields(manifest)}


def remote_issue(config, issue_id):
    """用用户级配置的 CORP 账号登录易协作，读取工单基本信息（见 pm_issues.issue_base）。"""
    username, password = pm_issues.credentials(config)
    client = pm_issues.Client()
    try:
        client.login(username, password)
    finally:
        password = None
    return pm_issues.issue_base(client, issue_id)


def load_prepared(root_arg, config, issue_id):
    """读取 prepare 的结果，并核对 diff 未被改动、工作副本仍是同一分支。"""
    root, personal, _ = workspace.paths(root_arg, config)
    folder = output_dir(personal, issue_id)
    raw, diff = workspace.read_bytes(folder / MANIFEST_FILE), workspace.read_bytes(folder / DIFF_FILE)
    if raw is None or diff is None:
        raise CrError("请先运行 prepare 生成 diff")
    manifest = workspace.parse_json(raw, folder / MANIFEST_FILE)
    if hashlib.sha256(diff).hexdigest() != manifest.get("diff_sha256"):
        raise CrError("diff 文件在 prepare 之后被改动，请重新运行 prepare")
    if manifest.get("issue", {}).get("issue_id") != issue_id:
        raise CrError("清单里的工单号不一致，请重新运行 prepare")
    if branch_info(root)["url"] != manifest.get("branch"):
        raise CrError("工作副本的分支和 prepare 时不同，请重新运行 prepare")
    return manifest, diff


def upload(root_arg, config, issue_id, desc, title=None, testing_done=None, apply=False,
           endpoint=None, jenkins=None, wait=300):
    """预览或上传；endpoint、jenkins 用于测试替换。"""
    manifest, diff = load_prepared(root_arg, config, issue_id)
    fields = form_fields(manifest, desc, title, testing_done)
    result = {"applied": apply, "fields": fields, "revisions": manifest["revisions"], "files": manifest["files"],
              "diff_bytes": len(diff)}
    if not apply:
        return result
    endpoint = endpoint or plugin_endpoint()
    jenkins = jenkins or Jenkins(endpoint)
    result["build"] = jenkins.follow(jenkins.trigger(endpoint["token"], fields, diff), wait)
    return result


def main(argv=None):
    """解析命令行，结果以 JSON 输出到标准输出，错误以 JSON 输出到标准错误。"""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=("prepare", "upload"))
    parser.add_argument("--root", default=".")
    parser.add_argument("--issue", required=True, help="工单号（追踪的程序单）")
    parser.add_argument("--desc-file", type=Path, help=f"upload：review_desc 文本文件（UTF-8，不超过 {DESC_LIMIT} 字）")
    parser.add_argument("--title", help="upload：覆盖默认标题「#工单号 工单名」")
    parser.add_argument("--testing-done", help="upload：工单没有父单时指定")
    parser.add_argument("--apply", action="store_true", help="upload：确认后实际上传")
    parser.add_argument("--wait", type=int, default=300, help="upload：等待构建结束的最长秒数")
    parser.add_argument("--config", type=Path, default=Path.home() / ".mhxy-workspace/config.json")
    args = parser.parse_args(argv)
    try:
        if args.action == "prepare":
            result = prepare(args.root, args.config, args.issue)
        else:
            if not args.desc_file:
                raise CrError("upload 需要 --desc-file")
            desc = args.desc_file.read_text(encoding="utf-8-sig")
            result = upload(args.root, args.config, args.issue, desc, args.title, args.testing_done,
                            args.apply, wait=args.wait)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        build = result.get("build")
        return 2 if build and build["result"] != "SUCCESS" else 0
    except (CrError, corp_login.LoginError, workspace.WorkspaceError, precommit.PrecheckError,
            ElementTree.ParseError, OSError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
