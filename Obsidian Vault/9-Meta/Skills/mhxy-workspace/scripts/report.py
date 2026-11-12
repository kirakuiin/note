#!/usr/bin/env python3
"""生成工单处理报告：一个可以整体拷走的文件夹（index.html 加 media/）。

    report.py build  --root <项目> --issue-id <工单号> --analysis-file <问题定位.md> --solution-file <处理方案.md> [...]
    report.py commit --root <项目> --issue-id <工单号> --revision <版本号>

会话只提供“问题定位”和“处理方案”两段文字；工单信息、改动和 diff、提交前自检、用例执行器报告、
本次跑过的用例文件（拷进 cases/，报告拷到别处也能重跑）、截图录屏、提交说明都由脚本收集。输出 JSON 只给路径和统计，不含 diff 和页面内容。
报告位于 <项目>/.mhxy-workspace/reports/<工单号>/，重新 build 会整体重建；report.json 保存渲染数据，
供 commit 补版本号后重新渲染。只读 SVN（status、diff），不修改工作副本。
"""
import argparse
from datetime import datetime
import html
import json
import os
from pathlib import Path
import re
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import case_store  # noqa: E402
import precommit  # noqa: E402
import workspace  # noqa: E402

REPORTS = "reports"  # 个人目录下的报告目录，每个工单一个子目录。
DATA_FILE = "report.json"
STATUSES = ("待提交", "需要你处理", "放弃", "等前一单提交")  # build 可用的状态，与 unattended.py 一致
COMMITTED = "已提交"  # 只由 commit 设置
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")
VIDEO_SUFFIXES = (".mp4", ".webm")
CASE_REPORTS = Path(workspace.DIRECTORY) / "cases" / "reports"  # 见 case_runner.REPORT_DIR
CASE_DIR = "cases"  # 报告文件夹里存放用例文件的子目录
DIFF_LINE_LIMIT = 3000  # 单个文件 diff 最多保留的行数，超出截断并注明。
NEW_FILE_BYTES = 200_000  # 未纳管的新文件超过这个大小不内嵌内容。


class ReportError(Exception):
    """可直接呈现给用户的报告生成错误。"""


def read_text(path, label):
    """读取会话提供的文本文件（UTF-8／UTF-16／GB18030），内容不能为空。"""
    try:
        text = workspace.decode_document(Path(path).read_bytes())[0].strip()
    except (OSError, workspace.WorkspaceError) as error:
        raise ReportError(f"无法读取{label}：{path}：{error}") from None
    if not text:
        raise ReportError(f"{label}为空：{path}")
    return text


def issue_title(personal, issue_id, given=None):
    """工单标题：命令行给出的优先，其次追踪记录，再次最近一次查询的清单；都没有时报错。"""
    if given and given.strip():
        return given.strip()
    candidates = []
    try:
        candidates += workspace.read_tracking(personal)[2]["tracked_tasks"]
    except (workspace.WorkspaceError, OSError):
        pass
    try:
        raw = workspace.read_bytes(personal / "tasks/index.json")
        tasks = workspace.parse_json(raw, "tasks/index.json").get("tasks") if raw is not None else None
        candidates += [item for item in tasks or [] if isinstance(item, dict)]
    except (workspace.WorkspaceError, OSError):
        pass
    for item in candidates:
        if item.get("issue_id") == issue_id and isinstance(item.get("title"), str):
            return item["title"]
    raise ReportError(f"找不到工单 {issue_id} 的标题（未追踪，也不在最近的查询清单中），请用 --title 给出")


def clip_lines(text):
    lines = text.splitlines()
    if len(lines) <= DIFF_LINE_LIMIT:
        return text, False
    return "\n".join(lines[:DIFF_LINE_LIMIT]), True


def collect_changes(root, only=()):
    """收集待提交的改动：[{"path", "state", "diff", "truncated"}]，以及提交前自检的结论。

    范围与 precommit 一致（不含本地辅助文件、导表数据和 ignore-on-commit 中的改动），另加未纳管的文件
    （新文件以整份内容作为 diff）。only 不为空时只保留其中列出的路径。
    """
    entries = precommit.svn_status(root)
    wanted = {str(item).replace("\\", "/").strip("/") for item in only}
    changes = []
    for entry in sorted(entries, key=lambda item: item["path"]):
        path, item = entry["path"], entry["item"]
        if not precommit.in_scope(entry) or (wanted and path not in wanted):
            continue
        local = root / path
        if item == "unversioned":
            if local.is_dir():
                changes.append({"path": path + "/", "state": "新目录（未纳管）", "diff": "", "truncated": False})
                continue
            try:
                data = local.read_bytes()
                if len(data) > NEW_FILE_BYTES or b"\x00" in data:
                    body, truncated = "（二进制或过大的新文件，未内嵌内容）", False
                else:
                    body, truncated = clip_lines("\n".join(
                        "+" + line for line in precommit.decode_output(data).splitlines()))
            except OSError as error:
                body, truncated = f"（无法读取：{error}）", False
            changes.append({"path": path, "state": "新增（未纳管）", "diff": body, "truncated": truncated})
        elif item in precommit.CHANGED_ITEMS or entry["props"] == "modified":
            state = {"modified": "修改", "added": "新增", "deleted": "删除", "replaced": "替换"}.get(item, "属性修改")
            try:
                # 路径含 @ 时末尾补 @，避免被当作 peg 版本。
                raw = precommit.run_svn(root, "diff", path + "@" if "@" in path else path, timeout=120)
                body, truncated = clip_lines(precommit.decode_output(raw).replace("\r\n", "\n").strip("\n"))
            except precommit.PrecheckError as error:
                body, truncated = f"（svn diff 失败：{error}）", False
            changes.append({"path": path, "state": state, "diff": body, "truncated": truncated})
    missing = sorted(wanted - {change["path"].rstrip("/") for change in changes})
    if missing:
        raise ReportError("以下 --path 没有本地改动或不在可提交范围内：" + "、".join(missing))
    classified = precommit.classify(entries)
    blocking, warnings, _ = precommit.check_sources(root, precommit.source_files(root, entries))
    precheck = {"blocking": classified["blocking"] + blocking,
                "warnings": warnings + precommit.check_leftovers(root, entries)}
    return changes, precheck


def resolve_case_reports(root, values):
    """把 --case-report 的值解析为报告文件；`latest` 表示用例报告目录中最新的一份。"""
    found = []
    for value in values:
        if value == "latest":
            directory = root / CASE_REPORTS
            candidates = sorted(directory.glob("*.json"), key=lambda p: p.stat().st_mtime) if directory.is_dir() else []
            if not candidates:
                raise ReportError(f"没有用例执行器报告：{directory}")
            path = candidates[-1]
        else:
            path = Path(value) if Path(value).is_absolute() else root / value
        if not path.is_file():
            raise ReportError(f"用例执行器报告不存在：{path}")
        if path.resolve() not in [item.resolve() for item in found]:
            found.append(path)
    return found


def load_case_report(path):
    """读取一份用例执行器报告，只取结论字段和用例来源（sources）；同名目录里的截图和录屏作为证据返回。"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ReportError(f"用例执行器报告无法读取：{path}：{error}") from None
    if not isinstance(data, dict) or "status" not in data:
        raise ReportError(f"不是用例执行器报告（缺少 status）：{path}")

    def strings(key):
        value = data.get(key)
        return [str(item) for item in value] if isinstance(value, list) else []

    summary = {"name": path.stem, "status": str(data["status"]), "cases": strings("cases"),
               "errors": strings("errors"), "unverified": strings("unverified"),
               "restoration": str(data.get("restoration", "")),
               "sources": [str(item) for item in data.get("sources", []) if isinstance(item, str)]}
    media_dir = path.with_suffix("")
    media = sorted(item for item in media_dir.iterdir()
                   if item.is_file() and item.suffix.lower() in IMAGE_SUFFIXES + VIDEO_SUFFIXES) \
        if media_dir.is_dir() else []
    return summary, media


def copy_media(sources, target, prefix):
    """把媒体文件拷进报告的 media/，返回 [{"file", "kind", "caption"}]；重名时加序号。"""
    items = []
    for number, source in enumerate(sources, 1):
        source = Path(source)
        suffix = source.suffix.lower()
        if suffix not in IMAGE_SUFFIXES + VIDEO_SUFFIXES:
            raise ReportError(f"不支持的媒体类型（只收图片和 mp4／webm）：{source}")
        if not source.is_file():
            raise ReportError(f"媒体文件不存在：{source}")
        target.mkdir(parents=True, exist_ok=True)
        name = f"{prefix}{number:02d}_{re.sub(r'[^0-9A-Za-z._-]+', '_', source.name)}"
        shutil.copyfile(source, target / name)
        items.append({"file": f"media/{name}", "kind": "video" if suffix in VIDEO_SUFFIXES else "image",
                      "caption": source.stem})
    return items


def copy_cases(sources, target):
    """把用例来源拷进报告的 cases/：.json 原样拷贝，spec（.md）只取「测试用例」一节写成 <spec 名>.json。

    Returns:
        [{"file": "cases/<文件名>", "source": 原路径}]，同一来源只拷一次，重名时加序号。
    """
    items, seen, names = [], set(), set()
    for source in sources:
        source = Path(source)
        key = str(source.resolve()).lower()
        if key in seen:
            continue
        seen.add(key)
        if not source.is_file():
            raise ReportError(f"用例文件不存在（用例执行器报告记录的来源）：{source}")
        stem = re.sub(r"[^\w.-]+", "_", source.stem).strip("._") or "case"
        name, number = f"{stem}.json", 1
        while name.lower() in names:
            number += 1
            name = f"{stem}_{number}.json"
        names.add(name.lower())
        target.mkdir(parents=True, exist_ok=True)
        if source.suffix.lower() == ".md":
            try:
                cases = [case for _, case in case_store.load_cases(source)]
            except case_store.CaseError as error:
                raise ReportError(str(error)) from None
            (target / name).write_text(json.dumps(cases, ensure_ascii=False, indent=1), encoding="utf-8")
        else:
            shutil.copyfile(source, target / name)
        items.append({"file": f"{CASE_DIR}/{name}", "source": str(source)})
    return items


INLINE = re.compile(r"`([^`]+)`|\*\*(.+?)\*\*")  # 一次扫描：行内代码里的 ** 不再当粗体


def render_text(text):
    """把会话写的简单 Markdown（段落、列表、代码块、行内代码、粗体）转成 HTML；其余原样转义。"""
    def inline(line):
        return INLINE.sub(lambda match: f"<code>{match[1]}</code>" if match[1] is not None
                          else f"<strong>{match[2]}</strong>", html.escape(line, quote=False))

    parts, paragraph, items, ordered, code = [], [], [], False, None

    def flush():
        nonlocal paragraph, items
        if paragraph:
            parts.append("<p>" + "<br>".join(paragraph) + "</p>")
            paragraph = []
        if items:
            tag = "ol" if ordered else "ul"
            parts.append(f"<{tag}>" + "".join(f"<li>{item}</li>" for item in items) + f"</{tag}>")
            items = []

    for raw in text.replace("\r\n", "\n").split("\n"):
        if code is not None:
            if raw.strip().startswith("```"):
                parts.append("<pre class=\"code\">" + html.escape("\n".join(code), quote=False) + "</pre>")
                code = None
            else:
                code.append(raw)
            continue
        line = raw.strip()
        if line.startswith("```"):
            flush()
            code = []
            continue
        bullet = re.match(r"^(?:[-*+]|(\d+)[.)])\s+(.*)$", line)
        heading = re.match(r"^#{1,6}\s+(.*)$", line)
        if not line:
            flush()
        elif heading:
            flush()
            parts.append(f"<h3>{inline(heading[1])}</h3>")
        elif bullet:
            if paragraph or (items and ordered != bool(bullet[1])):
                flush()
            ordered = bool(bullet[1])
            items.append(inline(bullet[2]))
        else:
            if items:
                flush()
            paragraph.append(inline(line))
    if code is not None:
        parts.append("<pre class=\"code\">" + html.escape("\n".join(code), quote=False) + "</pre>")
    flush()
    return "\n".join(parts)


def render_diff(text):
    rows = []
    for line in text.split("\n"):
        kind = ("meta" if line.startswith(("Index: ", "====", "--- ", "+++ ", "Property changes", "___"))
                else "hunk" if line.startswith("@@")
                else "add" if line.startswith("+") else "del" if line.startswith("-") else "")
        rows.append(f"<span class=\"l {kind}\">{html.escape(line, quote=False) or ' '}</span>")
    return "<pre class=\"diff\">" + "\n".join(rows) + "</pre>"


def render_media(items):
    figures = []
    for item in items:
        source = html.escape(item["file"])
        body = (f"<video controls preload=\"metadata\" src=\"{source}\"></video>" if item["kind"] == "video"
                else f"<a href=\"{source}\"><img loading=\"lazy\" src=\"{source}\" alt=\"{html.escape(item['caption'])}\"></a>")
        figures.append(f"<figure>{body}<figcaption>{html.escape(item['caption'])}</figcaption></figure>")
    return "<div class=\"media\">" + "".join(figures) + "</div>"


def bullet_list(items, css=""):
    return f"<ul class=\"{css}\">" + "".join(f"<li>{html.escape(item, quote=False)}</li>" for item in items) + "</ul>"


CSS = """
:root{--bg:#f5f6f8;--card:#fff;--text:#1d2129;--muted:#6b7280;--line:#e5e7eb;--accent:#2563eb;
--ok:#15803d;--ok-bg:#dcfce7;--warn:#b45309;--warn-bg:#fef3c7;--bad:#b91c1c;--bad-bg:#fee2e2;
--add:#e6f6ea;--del:#fdeaea;--code:#f3f4f6}
@media (prefers-color-scheme:dark){:root{--bg:#111318;--card:#1b1e25;--text:#e5e7eb;--muted:#9ca3af;--line:#2d313a;
--accent:#7aa2ff;--ok:#4ade80;--ok-bg:#123222;--warn:#fbbf24;--warn-bg:#3a2c0b;--bad:#f87171;--bad-bg:#3b1516;
--add:#12301c;--del:#3a1719;--code:#262a33}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:15px/1.7 "Segoe UI","Microsoft YaHei",system-ui,sans-serif}
main{max-width:980px;margin:0 auto;padding:28px 16px 56px}
header{margin-bottom:20px}
h1{font-size:22px;line-height:1.4;margin:6px 0 10px}
h2{font-size:16px;margin:0 0 12px;padding-left:10px;border-left:3px solid var(--accent)}
h3{font-size:15px;margin:14px 0 6px}
.id{color:var(--muted);font-size:13px;letter-spacing:.02em}
.meta{display:flex;flex-wrap:wrap;gap:6px 18px;color:var(--muted);font-size:13px}
.meta b{color:var(--text);font-weight:600}
.pill{display:inline-block;padding:1px 10px;border-radius:999px;font-size:12px;font-weight:600;vertical-align:middle}
.ok{color:var(--ok);background:var(--ok-bg)}.warn{color:var(--warn);background:var(--warn-bg)}
.bad{color:var(--bad);background:var(--bad-bg)}
section{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:18px 20px;margin-bottom:16px}
p{margin:0 0 10px}ul,ol{margin:0 0 10px;padding-left:22px}
code{background:var(--code);border-radius:4px;padding:1px 5px;font:13px/1.5 Consolas,"Cascadia Mono",monospace}
pre{margin:0 0 10px;overflow:auto;border-radius:8px;font:12.5px/1.55 Consolas,"Cascadia Mono",monospace}
pre.code,pre.msg{background:var(--code);padding:10px 12px;white-space:pre-wrap;word-break:break-word}
pre.diff{border:1px solid var(--line);padding:6px 0;max-height:560px}
pre.diff .l{display:block;padding:0 12px;white-space:pre}
.l.add{background:var(--add)}.l.del{background:var(--del)}.l.hunk{color:var(--accent)}.l.meta{color:var(--muted)}
table{width:100%;border-collapse:collapse;margin-bottom:12px;font-size:14px}
td,th{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:500;font-size:13px}
td.path{font-family:Consolas,"Cascadia Mono",monospace;font-size:13px;word-break:break-all}
details{border:1px solid var(--line);border-radius:8px;margin-bottom:8px}
summary{cursor:pointer;padding:8px 12px;font:13px Consolas,"Cascadia Mono",monospace;word-break:break-all}
details[open] summary{border-bottom:1px solid var(--line)}
details pre.diff{border:0;border-radius:0 0 8px 8px;margin:0}
.note{color:var(--muted);font-size:13px}
.media{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px}
figure{margin:0}img,video{width:100%;border-radius:8px;border:1px solid var(--line);background:#000;display:block}
figcaption{color:var(--muted);font-size:12.5px;margin-top:4px;word-break:break-all}
ul.bad-list li{color:var(--bad)}ul.warn-list li{color:var(--warn)}
footer{color:var(--muted);font-size:12px;text-align:center;margin-top:24px}
"""


def render_page(data):
    """按固定模板渲染整页；data 即 report.json 的内容。"""
    escape = html.escape
    status_class = {"待提交": "warn", COMMITTED: "ok", "需要你处理": "bad", "放弃": "bad",
                    "等前一单提交": "warn"}.get(data["status"], "warn")
    branch = data.get("branch") or {}
    meta = [f"<span>分支 <b>{escape(branch.get('name') or '未知')}</b>"
            + (f"（{escape(branch['kind'])}）" if branch.get("kind") else "") + "</span>",
            f"<span>生成时间 <b>{escape(data['generated_at'])}</b></span>"]
    if data.get("revision"):
        meta.append(f"<span>提交版本 <b>r{escape(str(data['revision']))}</b></span>")
    sections = []

    def section(title, body):
        sections.append(f"<section><h2>{escape(title)}</h2>\n{body}\n</section>")

    analysis = render_text(data["analysis"])
    if data["problem_media"]:
        analysis += "\n<h3>问题现象</h3>\n" + render_media(data["problem_media"])
    section("问题定位", analysis)
    section("处理方案", render_text(data["solution"]))

    changes = data["changes"]
    if changes:
        rows = "".join(f"<tr><td class=\"path\">{escape(item['path'])}</td><td>{escape(item['state'])}</td></tr>"
                       for item in changes)
        body = f"<table><tr><th>文件（{len(changes)}）</th><th>状态</th></tr>{rows}</table>"
        for item in changes:
            if not item["diff"]:
                continue
            note = "<p class=\"note\">&nbsp;&nbsp;diff 过长，已截断。</p>" if item["truncated"] else ""
            body += (f"<details><summary>{escape(item['path'])}</summary>{render_diff(item['diff'])}{note}</details>")
    else:
        body = "<p class=\"note\">生成报告时没有待提交的改动。</p>"
    section("改动", body)

    check = []
    precheck = data["precheck"]
    if precheck["blocking"]:
        check.append("<h3>提交前自检 <span class=\"pill bad\">有阻断问题</span></h3>" + bullet_list(precheck["blocking"], "bad-list"))
    else:
        check.append("<h3>提交前自检 <span class=\"pill ok\">无阻断问题</span></h3>")
    if precheck["warnings"]:
        check.append("<p class=\"note\">警告：</p>" + bullet_list(precheck["warnings"], "warn-list"))
    for case in data["case_reports"]:
        css = "ok" if case["status"] == "passed" else "bad"
        check.append(f"<h3>真机用例 {escape(case['name'])} <span class=\"pill {css}\">{escape(case['status'])}</span></h3>")
        if case["cases"]:
            check.append(bullet_list(case["cases"]))
        if case["errors"]:
            check.append("<p class=\"note\">报错：</p>" + bullet_list(case["errors"], "bad-list"))
        if case["unverified"]:
            check.append("<p class=\"note\">未验证：</p>" + bullet_list(case["unverified"], "warn-list"))
        if case["restoration"]:
            check.append(f"<p class=\"note\">环境还原：{escape(case['restoration'])}</p>")
    if not data["case_reports"]:
        check.append("<p class=\"note\">没有附真机用例报告。</p>")
    if data.get("case_files"):
        links = "".join(f"<li><a href=\"{escape(item['file'])}\">{escape(item['file'])}</a>"
                        f" <span class=\"note\">（{escape(item['source'])}）</span></li>" for item in data["case_files"])
        command = ('python -X utf8 "&lt;skill&gt;/scripts/game-debugging/case_runner.py" run --root "&lt;项目&gt;" '
                   '--devid "&lt;设备ID&gt;" ' + " ".join(escape(item["file"]) for item in data["case_files"]))
        check.append(f"<h3>用例文件</h3><ul>{links}</ul><p class=\"note\">在报告文件夹里重跑：</p>"
                     f"<pre class=\"msg\">{command}</pre>")
    if data.get("self_check"):
        check.append("<h3>补充说明</h3>" + render_text(data["self_check"]))
    section("自检结果", "\n".join(check))

    section("截图和录屏", render_media(data["media"]) if data["media"]
            else "<p class=\"note\">没有修复后的截图或录屏。</p>")

    if data.get("commit_message"):
        message = f"<pre class=\"msg\">{escape(data['commit_message'], quote=False)}</pre>"
        message += (f"<p>已提交，版本 <b>r{escape(str(data['revision']))}</b>。</p>" if data.get("revision")
                    else "<p class=\"note\">尚未提交。</p>")
    else:
        message = "<p class=\"note\">没有拟定提交说明。</p>"
    section("提交说明", message)

    title = f"#{data['issue_id']} {data['title']}"
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)} · 处理报告</title>
<style>{CSS}</style></head>
<body><main>
<header><div class="id">工单 #{escape(data['issue_id'])} · 处理报告</div>
<h1>{escape(data['title'])} <span class="pill {status_class}">{escape(data['status'])}</span></h1>
<div class="meta">{''.join(meta)}</div></header>
{chr(10).join(sections)}
<footer>由 mhxy-workspace report.py 生成</footer>
</main></body></html>
"""


def report_dir(personal, issue_id):
    target = personal / REPORTS / issue_id
    workspace.no_links(target)
    return target


def write_report(target, data):
    workspace.atomic_write(target / DATA_FILE, workspace.json_bytes(data))
    workspace.atomic_write(target / "index.html", render_page(data).encode("utf-8"))


def clear_report(target):
    """重建前删除旧报告的内容；只删本目录下的普通文件、media/ 和 cases/，遇到链接或其他内容就停止。"""
    if not target.exists():
        return
    for path in sorted(target.rglob("*"), reverse=True):
        workspace.no_links(path)
        relative = path.relative_to(target).parts
        if path.is_dir():
            if relative not in (("media",), (CASE_DIR,)):
                raise ReportError(f"报告目录里有不认识的子目录，请先处理：{path}")
            path.rmdir()
        elif len(relative) == 1 and relative[0] in (DATA_FILE, "index.html") or relative[0] in ("media", CASE_DIR):
            path.unlink()
        else:
            raise ReportError(f"报告目录里有不认识的文件，请先处理：{path}")


def build(args):
    root, personal, _ = workspace.paths(args.root, args.global_config)
    workspace.require_initialized(root)
    workspace.validate_issue_key(args.issue_id)
    if args.status not in STATUSES:
        raise ReportError(f"--status 只能是：{'、'.join(STATUSES)}（{COMMITTED}由 commit 设置）")
    data = {
        "issue_id": args.issue_id,
        "title": issue_title(personal, args.issue_id, args.title),
        "status": args.status,
        "branch": workspace.svn_branch(root),
        "generated_at": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M"),
        "analysis": read_text(args.analysis_file, "问题定位"),
        "solution": read_text(args.solution_file, "处理方案"),
        "self_check": read_text(args.self_check_file, "自检补充说明") if args.self_check_file else "",
        "commit_message": read_text(args.message_file, "提交说明") if args.message_file else "",
        "revision": None,
    }
    try:
        data["changes"], data["precheck"] = collect_changes(root, args.path)
    except precommit.PrecheckError as error:
        raise ReportError(f"无法收集改动：{error}") from None
    case_media, case_sources, data["case_reports"] = [], [], []
    for path in resolve_case_reports(root, args.case_report):
        summary, media = load_case_report(path)
        data["case_reports"].append(summary)
        case_media += media
        case_sources += summary["sources"]
    extra = [Path(item) if Path(item).is_absolute() else root / item for item in args.media]
    problem = [Path(item) if Path(item).is_absolute() else root / item for item in args.problem_media]
    target = report_dir(personal, args.issue_id)
    clear_report(target)
    target.mkdir(parents=True, exist_ok=True)
    data["media"] = copy_media(case_media + extra, target / "media", "after")
    data["problem_media"] = copy_media(problem, target / "media", "problem")
    data["case_files"] = copy_cases(case_sources, target / CASE_DIR)
    write_report(target, data)
    return summary_result(target, data)


def summary_result(target, data):
    return {"action": "report", "report_dir": str(target), "index": str(target / "index.html"),
            "issue_id": data["issue_id"], "title": data["title"], "status": data["status"],
            "changed_files": [item["path"] for item in data["changes"]],
            "blocking": len(data["precheck"]["blocking"]), "warnings": len(data["precheck"]["warnings"]),
            "case_reports": [f"{item['name']}：{item['status']}" for item in data["case_reports"]],
            "media": len(data["media"]), "problem_media": len(data["problem_media"]),
            "case_files": [item["file"] for item in data.get("case_files", [])],
            "revision": data.get("revision")}


def commit(args):
    """提交后补版本号：状态改为已提交并重新渲染，其余内容不变。"""
    root, personal, _ = workspace.paths(args.root, args.global_config)
    workspace.require_initialized(root)
    workspace.validate_issue_key(args.issue_id)
    if not re.fullmatch(r"[1-9]\d*", args.revision or ""):
        raise ReportError("--revision 必须是正整数版本号")
    target = report_dir(personal, args.issue_id)
    raw = workspace.read_bytes(target / DATA_FILE)
    if raw is None:
        raise ReportError(f"工单 {args.issue_id} 还没有处理报告：{target}")
    data = workspace.parse_json(raw, target / DATA_FILE)
    data["revision"], data["status"] = int(args.revision), COMMITTED
    write_report(target, data)
    return summary_result(target, data)


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="action", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", default=os.getcwd())
    common.add_argument("--issue-id", required=True)
    common.add_argument("--global-config", default=str(Path.home() / workspace.DIRECTORY / "config.json"))
    builder = commands.add_parser("build", parents=[common], help="生成或重建处理报告")
    builder.add_argument("--analysis-file", required=True, help="问题定位（UTF-8 文本，可用简单 Markdown）")
    builder.add_argument("--solution-file", required=True, help="处理方案（同上）")
    builder.add_argument("--title", help="工单标题；省略时取追踪记录或最近的查询清单")
    builder.add_argument("--status", default="待提交", help="、".join(STATUSES))
    builder.add_argument("--message-file", help="拟定的提交说明")
    builder.add_argument("--self-check-file", help="自检的补充说明（如单元测试结果）")
    builder.add_argument("--path", action="append", default=[], help="只收这些文件的改动，可重复；省略时收全部待提交改动")
    builder.add_argument("--case-report", action="append", default=[],
                         help="用例执行器报告路径，或 latest（最新一份），可重复；同名目录中的截图录屏一并收入")
    builder.add_argument("--media", action="append", default=[], help="额外的修复后截图或录屏，可重复")
    builder.add_argument("--problem-media", action="append", default=[], help="工单自带的问题截图，放进问题定位，可重复")
    committer = commands.add_parser("commit", parents=[common], help="提交后补版本号")
    committer.add_argument("--revision", required=True)
    args = parser.parse_args(argv)
    try:
        result = build(args) if args.action == "build" else commit(args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ReportError, workspace.WorkspaceError, OSError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
