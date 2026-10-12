#!/usr/bin/env python3
"""提测（提交测试）：在 newtestreport 提测系统上准备并保存客户端提测单。

流程说明见 references/test-request.md。两个子命令：
  prepare  登录并“刷新”单号，列出带出的信息和该总单已有的提测记录（只读）。
  save     组装提测单；默认只预览，加 --apply 才保存，成功后输出提测单链接。

登录使用用户级配置中的 CORP 账号（eros 统一登录），会话只在内存中。
退出码：0 成功；1 失败。
"""
import argparse
import json
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import corp_login  # noqa: E402
from corp_login import LoginError  # noqa: E402
import eros_auth  # noqa: E402

SITE = "https://newtestreport.eros.nie.netease.com"
CHECKLIST = "https://checklist.eros.nie.netease.com/dashboard/checklist/10590"  # 客户端提测 checklist，固定值。
SERVER_PLACEHOLDER = "由服务端填写"  # 服务端负责的必填覆盖率字段为空时填写的原因（页面要求“无链接请填写原因”）。
# 提测单中由服务端负责、客户端更新已有提测单时必须保留原值的字段。
SERVER_FIELDS = ("testPort", "axName", "axCrossServer", "coverPath", "MOScoverPath", "selfTest",
                 "htEngineVer", "at_content", "pro_content")
JSON_LIST_FIELDS = ("svrCoder", "cliCoder", "dutyDesign", "dutyQA")
# “测试需特别注意”允许的排版标签；其他标签多半是生成内容时混入的残留，保存前必须清掉。
# 与 references/test-request.md「流程」第 3 步列出的标签一致，修改时两处同步。
ATTENTION_TAGS = {"p", "br", "ul", "ol", "li", "strong", "b", "em", "i", "span", "font"}


class TestReportError(LoginError):
    """可直接显示的提测错误；不包含密码、Cookie 或服务器原始响应。"""


class Client:
    """已登录的提测系统会话；只提供本流程用到的接口。"""

    def __init__(self, opener, timeout=30):
        self.opener = opener  # eros_auth.login 返回的 opener，Cookie 只在内存中。
        self.timeout = timeout

    def _read(self, path, params=None, data=None):
        url = SITE + path + ("?" + urlencode(params) if params else "")
        headers = {"Content-Type": "application/x-www-form-urlencoded"} if data is not None else {}
        try:
            with self.opener.open(Request(url, data=data, headers=headers), timeout=self.timeout) as response:
                if "/auth/login" in response.url:
                    raise TestReportError("提测系统会话失效，请重试")
                return response.read().decode("utf-8", "replace")
        except HTTPError as error:
            raise TestReportError(f"提测系统返回 HTTP {error.code}") from None
        except (URLError, OSError):
            raise TestReportError("提测系统网络请求失败") from None

    def redmine_info(self, issue_id):
        """“刷新”：返回单号的易协作信息（含 root_id 总单号、程序、策划、QA、覆盖率）。"""
        try:
            return json.loads(self._read("/testreport/redmine_info", {"id": issue_id}))
        except ValueError:
            raise TestReportError("刷新结果不是 JSON，接口可能已变化") from None

    def my_requests(self):
        """解析“我的提测”列表，返回 [{"redmineId", "testRequestID"}]（同一行取第一个提测 ID）。"""
        html = self._read("/testreport/listMyTestRequest")
        rows = []
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
            issue = re.search(r"/issues/(\d+)", row)
            request = re.search(r"testRequestID=(\d+)", row)
            if issue and request:
                rows.append({"redmineId": issue[1], "testRequestID": request[1]})
        return rows

    def get_request(self, request_id):
        """读取已有提测单的全部字段。"""
        try:
            value = json.loads(self._read("/testreport/getTestRequest", {"testRequestID": request_id}))
            return json.loads(value) if isinstance(value, str) else value
        except ValueError:
            raise TestReportError("提测单数据不是 JSON，接口可能已变化") from None

    def save(self, fields):
        """保存提测单，返回提测单 ID。"""
        request_id = self._read("/testreport/saveTestRequest", data=urlencode(fields).encode()).strip().strip('"')
        if not re.fullmatch(r"\d+", request_id):
            raise TestReportError("保存结果异常，未返回提测单 ID")
        return request_id


def preview_link(request_id):
    return f"{SITE}/testreport/preViewTestRequest?testRequestID={request_id}"


def refreshed_fields(info):
    """把“刷新”结果映射为提测单字段，与网页 onRefreshRedmine 的映射一致。"""
    fields = {"sysName": info.get("subject") or "", "svrCoder": info.get("svrCoder") or [],
              "cliCoder": info.get("cliCoder") or [], "dutyDesign": [info["cehua"]] if info.get("cehua") else [],
              "dutyQA": info.get("qa") or [], "coverPath": info.get("cover") or "", "MOScoverPath": "", "CLIcoverPath": ""}
    pycover = info.get("pycover") or {}
    if pycover.get("url"):
        fields["MOScoverPath" if pycover.get("tag") == "mhxy" else "CLIcoverPath"] = pycover["url"]
    return fields


def build_fields(redmine_id, info, existing, patch, cli_cover, attention):
    """组装保存参数。

    新建时以“刷新”结果为基础；更新已有提测单时以原记录为基础，保留 SERVER_FIELDS
    （服务端负责的内容），只覆盖客户端负责的字段。

    Args:
        redmine_id: 总单号。
        info: redmine_info 返回值。
        existing: 已有提测单的字段，新建时为 None。
        patch: Sunshine 打包模板名，同时作为 Patch 地址和 PC 资源地址。
        cli_cover: 客户端覆盖率地址；为空时沿用刷新或原记录中的值。
        attention: “测试需特别注意”的 HTML；为空时沿用原记录。

    Raises:
        TestReportError: 必填项缺失（与网页保存前的检查一致）。
    """
    base = dict(existing or {})
    for key, value in refreshed_fields(info).items():
        if not existing or (key not in SERVER_FIELDS and not base.get(key)):
            base[key] = value
    fields = {
        "testRequestID": str((existing or {}).get("_id") or ""), "redmineId": str(redmine_id),
        "sysName": base.get("sysName", ""), "testRequestName": base.get("sysName", ""), "uidocPath": base.get("uidocPath") or "无",
        **{key: json.dumps(base.get(key) or [], ensure_ascii=False) for key in JSON_LIST_FIELDS},
        "testPort": base.get("testPort", ""), "axName": base.get("axName", ""),
        "axCrossServer": str(base.get("axCrossServer") or "0"),
        "patch": patch or base.get("patch", ""), "pcSrc": patch or base.get("pcSrc", ""),
        "selfTest": str(base.get("selfTest") or "0"), "CliCheckListPath": CHECKLIST,
        "htEngineVer": base.get("htEngineVer", ""),
        "coverPath": base.get("coverPath") or SERVER_PLACEHOLDER, "MOScoverPath": base.get("MOScoverPath") or SERVER_PLACEHOLDER,
        "CLIcoverPath": cli_cover or base.get("CLIcoverPath", ""),
        "cli_checked": "on" if str(base.get("cli_checked")).lower() in ("on", "true") else "",
        "attition": attention or base.get("attition", ""),
        "at_content": base.get("at_content", ""), "pro_content": base.get("pro_content", ""),
    }
    missing = [label for label, ok in (
        ("单号必须是纯数字", re.fullmatch(r"\d+", fields["redmineId"])), ("系统名", fields["sysName"]),
        ("服务端或客户端程序", base.get("svrCoder") or base.get("cliCoder")), ("策划", base.get("dutyDesign")),
        ("QA", base.get("dutyQA")), ("Patch 模板", fields["patch"]),
        ("客户端覆盖率地址（没有链接时填写原因）", fields["CLIcoverPath"]), ("测试需特别注意", fields["attition"])) if not ok]
    if missing:
        raise TestReportError("缺少：" + "、".join(missing))
    return fields


def attention_issues(html):
    """检查“测试需特别注意”的 HTML，返回问题列表（空列表表示可以保存）。

    只允许 ATTENTION_TAGS 中的标签；残留的 Markdown 标记（``` 或 **）、模板占位符和
    HTML 注释也视为问题。只做检查，不自动修改内容。
    """
    issues = []
    for tag in sorted({name.lower() for name in re.findall(r"</?\s*([A-Za-z][\w:-]*)", html)} - ATTENTION_TAGS):
        issues.append(f"不允许的标签 <{tag}>")
    for marker, label in (("```", "Markdown 代码块标记"), ("**", "Markdown 粗体标记"),
                          ("{{", "模板占位符"), ("<!--", "HTML 注释")):
        if marker in html:
            issues.append(f"残留的{label} {marker}")
    return issues


def connect(config):
    username, password = corp_login.load_credentials(config)
    try:
        return Client(eros_auth.login(SITE, username, password))
    finally:
        password = None


def prepare(client, issue_id):
    """刷新单号并找出其总单和已有提测记录（只读）。"""
    info = client.redmine_info(issue_id)
    root = str(info.get("root_id") or issue_id)
    if root != str(issue_id):
        info = client.redmine_info(root)
    existing = []
    for row in client.my_requests():
        if row["redmineId"] == root and row["testRequestID"] not in {e["testRequestID"] for e in existing}:
            record = client.get_request(row["testRequestID"])
            existing.append({"testRequestID": row["testRequestID"], "link": preview_link(row["testRequestID"]),
                             "patch": record.get("patch", ""), "CLIcoverPath": record.get("CLIcoverPath", ""),
                             "sendTime": record.get("sendTime", "")})
    return {"input_issue": str(issue_id), "redmineId": root, "refreshed": refreshed_fields(info),
            "output_type": info.get("output_type", ""), "version": info.get("version", ""), "existing": existing}


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=("prepare", "save"))
    parser.add_argument("--issue-id", help="prepare：任意相关单号（程序单、总单等）")
    parser.add_argument("--redmine-id", help="save：总单号（prepare 输出的 redmineId）")
    parser.add_argument("--test-request-id", help="save：更新已有提测单；省略则新建")
    parser.add_argument("--patch", help="save：Sunshine 打包模板名，同时用于 Patch 地址和 PC 资源地址")
    parser.add_argument("--cli-cover", help="save：客户端覆盖率地址（coverage_query.py 输出的 url）")
    parser.add_argument("--attention-file", type=Path, help="save：“测试需特别注意”HTML 文件（UTF-8）")
    parser.add_argument("--apply", action="store_true", help="save：确认后实际保存")
    parser.add_argument("--config", type=Path, default=Path.home() / ".mhxy-workspace/config.json")
    args = parser.parse_args()
    try:
        client = connect(args.config)
        if args.action == "prepare":
            if not args.issue_id:
                raise TestReportError("prepare 需要 --issue-id")
            result = prepare(client, args.issue_id)
        else:
            if not args.redmine_id:
                raise TestReportError("save 需要 --redmine-id")
            attention = args.attention_file.read_text(encoding="utf-8").strip() if args.attention_file else ""
            existing = client.get_request(args.test_request_id) if args.test_request_id else None
            fields = build_fields(args.redmine_id, client.redmine_info(args.redmine_id), existing,
                                  args.patch, args.cli_cover, attention)
            issues = attention_issues(fields["attition"])
            result = {"applied": args.apply, "mode": "更新" if existing else "新建", "fields": fields,
                      "attention_issues": issues}
            if args.apply and issues:
                raise TestReportError("“测试需特别注意”内容有问题，未保存：" + "；".join(issues))
            if args.apply:
                request_id = client.save(fields)
                result.update(testRequestID=request_id, link=preview_link(request_id))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (LoginError, OSError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
