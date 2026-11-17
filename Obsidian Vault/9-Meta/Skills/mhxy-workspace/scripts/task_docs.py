"""追踪工单的策划文档：把正文里的 SVN 链接检出到工单目录的 docs/，转成 Markdown，并改写 issue.md 的链接。

布局（都在 .mhxy-workspace/tasks/<工单号>/ 下）：
- docs/<目录名>/：SVN 稀疏工作副本。链接是文件时检出它所在目录（--depth empty）再只取这个文件；
  链接是目录时检出该目录这一层的文件（--depth files）。同名目录对应不同 URL 时加 -2、-3 后缀。
- docs/_converted/<目录名>/<文件名>.md 和 <文件名>_images/：xlsx 等转出的 Markdown，每次同步都重新生成。
- docs/manifest.json：链接与本地路径、版本号的对应。

只用标准库：xlsx 自己解析；docx、pptx、pdf、xls 在本机装有 markitdown 时才转换，否则注明未转换。
"""
import json
from pathlib import Path
import posixpath
import re
import shutil
import subprocess
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree
import zipfile

DOCS = "docs"
CONVERTED = "_converted"
MANIFEST = "manifest.json"
SECTION_BEGIN = "<!-- task-docs:begin -->"
SECTION_END = "<!-- task-docs:end -->"
SVN_TIMEOUT = 1800
INFO_TIMEOUT = 120
# 设计文档所在的 SVN 主机；正文里其他链接不处理。
SVN_URL = re.compile(r"(?:https?|svn)://svn[\w.-]*\.netease\.com/svn/[^\s<>()\"'\]\[|]+")
TRAILING = ".,;:!?，。；：！？、）)"
MARKITDOWN_SUFFIXES = {".docx", ".pptx", ".pdf", ".xls"}
PLAIN_SUFFIXES = {".md", ".txt"}

NS = {
    "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
    "xdr": "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "etc": "http://www.wps.cn/officeDocument/2017/etCustomData",
}
R_ID = f"{{{NS['r']}}}id"
R_EMBED = f"{{{NS['r']}}}embed"


class DocsError(Exception):
    """单个链接无法检出、更新或转换。"""


def decode(data):
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("gb18030", "replace")


def svn(cwd, *args, timeout=INFO_TIMEOUT):
    """运行 svn 并在失败时抛出 DocsError（带 svn 原始提示）。"""
    try:
        completed = subprocess.run(["svn", *map(str, args), "--non-interactive"], cwd=cwd, capture_output=True,
                                   timeout=timeout, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        raise DocsError(f"svn {args[0]} 超过 {timeout} 秒未结束") from None
    except (OSError, subprocess.SubprocessError) as error:
        raise DocsError(f"svn 不可用：{error}") from None
    if completed.returncode:
        detail = decode(completed.stderr).strip() or decode(completed.stdout).strip()
        raise DocsError(detail or f"svn {args[0]} 失败，退出码 {completed.returncode}")
    return decode(completed.stdout).strip()


# ---------- 链接识别与 issue.md 改写 ----------

def strip_section(text):
    """去掉之前写入的策划文档小节，避免把其中列出的远端地址再当成正文链接。"""
    start, end = text.find(SECTION_BEGIN), text.find(SECTION_END)
    if start == -1 or end < start:
        return text
    return (text[:start].rstrip("\n") + "\n" + text[end + len(SECTION_END):].lstrip("\n")).rstrip("\n") + "\n"


def normalize_url(url):
    """去掉末尾标点和斜杠、解开百分号编码，作为同一链接的比较键。"""
    url = url.strip().rstrip(TRAILING).rstrip("/")
    return unquote(url)


def svn_links(text):
    """按出现顺序返回正文中的 SVN 链接（已规范化、去重）。"""
    links = []
    for match in SVN_URL.finditer(strip_section(text)):
        url = normalize_url(match[0])
        if url not in links and urlsplit(url).path.rstrip("/").count("/") >= 2:
            links.append(url)
    return links


def link_issue(text, entries, failures):
    """把正文里指向已检出文档的链接改成本地路径，并在末尾写入（或替换）策划文档小节。"""
    body = strip_section(text)
    local = {entry["url"]: entry["path"] for entry in entries}

    def replace(match):
        target = match[1] or match[2]
        key = normalize_url(target)
        return f"](<{local[key]}>)" if key in local else match[0]

    body = re.sub(r"\]\(\s*(?:<([^>\n]+)>|([^\s)]+))\s*\)", replace, body)
    if not entries and not failures:
        return body
    lines = [SECTION_BEGIN, "## 策划文档（本地检出）", ""]
    for entry in entries:
        kind = "目录" if entry["kind"] == "dir" else "文件"
        if entry.get("depth") == "files":
            kind += f"，超过 {DIR_LIMIT // 2 ** 20} MB，只检出了顶层文件"
        lines.append(f"- [{entry['name']}](<{entry['path']}>)（{kind}，r{entry['revision']}）")
        for doc in entry["documents"]:
            if doc.get("plain"):
                continue  # md、txt 本身可读，目录或文件链接已经指向它。
            if doc.get("markdown"):
                lines.append(f"  - Markdown 版：[{doc['name']}](<{doc['markdown']}>)")
            elif doc.get("note") and entry["kind"] == "file":
                lines.append(f"  - {doc['name']}：{doc['note']}")
        lines.append(f"  - 远端：{entry['url']}")
    for failure in failures:
        lines.append(f"- 下载失败，保留远端链接：{failure['url']}（{failure['reason']}）")
    lines += ["", "本地文件是 SVN 稀疏工作副本：重新获取任务时会 svn update，并重新生成 Markdown 版。", SECTION_END]
    return body.rstrip("\n") + "\n\n" + "\n".join(lines) + "\n"


# ---------- 检出与更新 ----------

def read_manifest(docs):
    path = docs / MANIFEST
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {item["url"]: item for item in value.get("docs", []) if isinstance(item, dict) and "url" in item}


def write_manifest(docs, entries):
    data = json.dumps({"docs": entries}, ensure_ascii=False, indent=2) + "\n"
    path = docs / MANIFEST
    if not path.is_file() or path.read_text(encoding="utf-8") != data:
        path.write_text(data, encoding="utf-8")


def checkout_dir(docs, parent_url, used):
    """返回 parent_url 对应的稀疏工作副本目录名；已有就复用，没有就新建（不检出任何内容）。"""
    base = posixpath.basename(urlsplit(parent_url).path.rstrip("/")) or "root"
    base = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", base)
    for index in range(1, 100):
        name = base if index == 1 else f"{base}-{index}"
        path = docs / name
        if name in used and used[name] != parent_url:
            continue
        if path.exists():
            try:
                existing = normalize_url(svn(path, "info", "--show-item", "url", "."))
            except DocsError:
                continue
            if existing != parent_url:
                continue
        used[name] = parent_url
        return name
    raise DocsError(f"无法为 {parent_url} 分配本地目录")


def ensure_clean(path):
    """本地有修改的不更新，避免覆盖用户在副本里做的改动。"""
    status = svn(path.parent if path.is_file() else path, "status", "--ignore-externals", path.name if path.is_file() else ".")
    changed = [line for line in status.splitlines() if line.strip() and line[0] in "MACDR!~"]
    if changed:
        raise DocsError(f"本地有修改，未更新：{path}")


def encoded(url):
    """传给 svn 的 URL 一律百分号编码成 ASCII：直接传中文时 svn 可能按系统代码页误转，报路径不存在。"""
    return quote(url, safe=":/@!$&'()*+,;=~-._")


def tree_size(url):
    """目录下全部文件的总字节数（svn list -R -v 的第 3 列）。"""
    total = 0
    for line in svn(None, "list", "-R", "-v", encoded(url), timeout=SVN_TIMEOUT).splitlines():
        parts = line.split()
        if len(parts) > 5 and parts[2].isdigit() and not line.rstrip().endswith("/"):
            total += int(parts[2])
    return total


def sync_link(docs, url, used, previous=None):
    """检出或更新一个链接，返回 manifest 条目（不含转换结果）。

    文件：检出所在目录（--depth empty）后只取这个文件。目录：默认整个检出；总大小超过 DIR_LIMIT 时
    只检出顶层文件（--depth files）并在条目里注明。深度在首次检出时决定，之后沿用。
    """
    kind = svn(None, "info", "--show-item", "kind", encoded(url))
    if kind not in ("file", "dir"):
        raise DocsError(f"无法识别的 SVN 节点类型：{kind}")
    parent_url = posixpath.dirname(url) if kind == "file" else url
    name = checkout_dir(docs, parent_url, used)
    wc = docs / name
    depth = "empty"
    if kind == "dir":
        depth = (previous or {}).get("depth") or ("infinity" if tree_size(url) <= DIR_LIMIT else "files")
    if not wc.exists():
        svn(docs, "checkout", "--depth", "empty" if kind == "file" else depth, encoded(parent_url), name,
            timeout=SVN_TIMEOUT)
    filename = posixpath.basename(url) if kind == "file" else None
    target = wc / filename if filename else wc
    if target.exists():
        ensure_clean(target)
    before = svn(wc, "info", "--show-item", "last-changed-revision", filename or ".") if target.exists() else None
    if kind == "file":
        svn(wc, "update", filename, timeout=SVN_TIMEOUT)
    else:
        svn(wc, "update", "--set-depth", depth, ".", timeout=SVN_TIMEOUT)
    if not target.exists():
        raise DocsError(f"更新后本地没有 {target.name}")
    revision = svn(wc, "info", "--show-item", "last-changed-revision", filename or ".")
    if kind == "file":
        files = [target]
    else:
        files = sorted(p for p in wc.rglob("*") if p.is_file() and ".svn" not in p.relative_to(wc).parts)
    entry = {"url": url, "kind": kind, "name": target.name,
             "path": f"{DOCS}/{name}" + (f"/{filename}" if filename else ""),
             "revision": revision, "updated": before is not None and before != revision, "files": files,
             "checkout": name}
    if kind == "dir":
        entry["depth"] = depth
    return entry


def sync_docs(task_dir, text, markitdown=None):
    """检出或更新 text 里的全部 SVN 链接（含 manifest 里已有的），重新生成 Markdown 版。

    Returns:
        (entries, failures)：entries 是写进 manifest 的条目，failures 是 [{"url", "reason"}]。
        没有链接时不创建 docs/。
    """
    docs = Path(task_dir) / DOCS
    previous = read_manifest(docs)
    links = svn_links(text)
    links += [url for url in previous if url not in links]
    if not links:
        return [], []
    docs.mkdir(parents=True, exist_ok=True)
    used = {item["checkout"]: posixpath.dirname(item["url"]) if item.get("kind") == "file" else item["url"]
            for item in previous.values() if item.get("checkout")}
    entries, failures = [], []
    converter = markitdown if markitdown is not None else shutil.which("markitdown")
    for url in links:
        try:
            entry = sync_link(docs, url, used, previous.get(url))
        except DocsError as error:
            failures.append({"url": url, "reason": str(error)})
            continue
        documents = []
        wc = docs / entry["checkout"]
        for path in entry.pop("files"):
            out_dir = docs / CONVERTED / entry["checkout"] / path.parent.relative_to(wc)
            documents.append(convert(path, out_dir, converter, Path(task_dir)))
        entry["documents"] = documents
        entries.append(entry)
    write_manifest(docs, entries)
    return entries, failures


# ---------- 转换 ----------

def convert(path, out_dir, markitdown, task_dir):
    """把一个文件转成 Markdown，返回 {"name", "markdown"} 或 {"name", "note"}；路径相对工单目录。"""
    suffix = path.suffix.lower()
    if suffix in PLAIN_SUFFIXES:
        return {"name": path.name, "markdown": path.relative_to(task_dir).as_posix(), "plain": True}
    target = out_dir / (path.name + ".md")
    images = out_dir / (path.name + "_images")
    try:
        if suffix == ".xlsx":
            text, pictures = xlsx_markdown(path, images.name)
        elif suffix in MARKITDOWN_SUFFIXES and markitdown:
            text, pictures = run_markitdown(markitdown, path), {}
        elif suffix in MARKITDOWN_SUFFIXES:
            return {"name": path.name, "note": "未转换（本机没有 markitdown）"}
        else:
            return {"name": path.name, "note": "不是可转换的文档，未转换"}
    except (DocsError, OSError, zipfile.BadZipFile, ElementTree.ParseError, KeyError, ValueError) as error:
        return {"name": path.name, "note": f"转换失败：{error}"}
    out_dir.mkdir(parents=True, exist_ok=True)
    if images.exists():
        shutil.rmtree(images)
    if pictures:
        images.mkdir()
        for name, data in pictures.items():
            (images / name).write_bytes(data)
    header = f"<!-- 由 {path.name} 自动生成，重新获取任务时覆盖，不要手工修改 -->\n\n"
    data = (header + text).encode("utf-8")
    if not target.is_file() or target.read_bytes() != data:
        target.write_bytes(data)
    return {"name": path.name, "markdown": target.relative_to(task_dir).as_posix()}


def run_markitdown(command, path):
    try:
        completed = subprocess.run([command, str(path)], capture_output=True, timeout=600,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError) as error:
        raise DocsError(f"markitdown 无法运行：{error}") from None
    if completed.returncode:
        raise DocsError(decode(completed.stderr).strip()[-300:] or "markitdown 失败")
    return decode(completed.stdout)


def zip_xml(archive, name):
    return ElementTree.fromstring(archive.read(name))


def rels(archive, part):
    """读取 part 的关系表：{rId: 目标 part 的包内路径}。"""
    folder, base = posixpath.split(part)
    rel_path = posixpath.join(folder, "_rels", base + ".rels")
    if rel_path not in archive.namelist():
        return {}
    result = {}
    for rel in zip_xml(archive, rel_path).findall("rel:Relationship", NS):
        target = rel.get("Target", "")
        if rel.get("TargetMode") == "External":
            continue
        result[rel.get("Id")] = posixpath.normpath(target.lstrip("/") if target.startswith("/")
                                                   else posixpath.join(folder, target))
    return result


def column_index(ref):
    letters = re.match(r"[A-Z]+", ref)[0]
    value = 0
    for char in letters:
        value = value * 26 + ord(char) - 64
    return value - 1


def column_name(index):
    name = ""
    index += 1
    while index:
        index, rest = divmod(index - 1, 26)
        name = chr(65 + rest) + name
    return name


def cell_text(cell, shared):
    kind = cell.get("t")
    if kind == "inlineStr":
        return "".join(node.text or "" for node in cell.iter(f"{{{NS['m']}}}t"))
    value = cell.find("m:v", NS)
    text = value.text if value is not None and value.text is not None else ""
    if kind == "s" and text:
        return shared[int(text)]
    if kind == "b":
        return "TRUE" if text == "1" else "FALSE"
    return text


def table_cell(value):
    return value.replace("\\", "\\\\").replace("|", "\\|").replace("\r\n", "\n").replace("\n", "<br>").strip()


def xlsx_markdown(path, images_dir):
    """xlsx 转 Markdown：每个工作表一个表格，图片按锚点单元格放在表后（WPS 单元格图片放进单元格）。"""
    pictures = {}
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        shared = []
        if "xl/sharedStrings.xml" in names:
            for item in zip_xml(archive, "xl/sharedStrings.xml").findall("m:si", NS):
                shared.append("".join(node.text or "" for node in item.iter(f"{{{NS['m']}}}t")))
        workbook = zip_xml(archive, "xl/workbook.xml")
        workbook_rels = rels(archive, "xl/workbook.xml")
        cell_images = wps_cell_images(archive, names)
        out = [f"# {path.name}", ""]
        for number, sheet in enumerate(workbook.findall("m:sheets/m:sheet", NS), 1):
            title = sheet.get("name")
            part = workbook_rels.get(sheet.get(R_ID))
            if not part or part not in names:
                continue
            root = zip_xml(archive, part)
            grid = {}
            prefix = f"s{number:02d}"
            for cell in root.iter(f"{{{NS['m']}}}c"):
                ref = cell.get("r")
                if not ref:
                    continue
                row = int(re.search(r"\d+", ref)[0])
                col = column_index(ref)
                formula = cell.find("m:f", NS)
                text = cell_text(cell, shared)
                match = re.search(r'DISPIMG\("([^"]+)"', (formula.text or "") if formula is not None else "")
                if match and match[1] in cell_images:
                    data, extension = cell_images[match[1]]
                    image = f"{prefix}_cell{len(pictures) + 1:02d}{extension}"
                    pictures[image] = data
                    text = f"![]({images_dir}/{image})"
                else:
                    text = table_cell(text)
                if text:
                    grid[(row, col)] = text
            out += [f"## {title}", ""]
            if grid:
                rows = sorted({row for row, _ in grid})
                cols = range(min(col for _, col in grid), max(col for _, col in grid) + 1)
                out.append("| 行 | " + " | ".join(column_name(col) for col in cols) + " |")
                out.append("| --- |" + " --- |" * len(cols))
                for row in rows:
                    out.append(f"| {row} | " + " | ".join(grid.get((row, col), "") for col in cols) + " |")
                out.append("")
            else:
                out += ["（空表）", ""]
            for index, (anchor, data, extension) in enumerate(sheet_drawings(archive, part, names), 1):
                image = f"{prefix}_img{index:02d}{extension}"
                pictures[image] = data
                out += [f"![{title} {anchor}]({images_dir}/{image})", f"（图片锚点：{anchor}）", ""]
    return "\n".join(out).rstrip("\n") + "\n", pictures


def image_suffix(name):
    suffix = posixpath.splitext(name)[1].lower()
    return suffix if suffix in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".emf", ".wmf") else ".bin"


def sheet_drawings(archive, sheet_part, names):
    """返回工作表浮动图片 [(锚点单元格, 数据, 扩展名)]，按锚点行列排序。"""
    result = []
    for drawing in rels(archive, sheet_part).values():
        if "/drawings/" not in drawing or drawing not in names:
            continue
        media = rels(archive, drawing)
        root = zip_xml(archive, drawing)
        for anchor in list(root):
            start = anchor.find("xdr:from", NS)
            if start is not None:
                row = int(start.find("xdr:row", NS).text) + 1
                col = int(start.find("xdr:col", NS).text)
                where, order = f"{column_name(col)}{row}", (row, col)
            else:
                where, order = "浮动", (0, 0)
            for blip in anchor.iter(f"{{{NS['a']}}}blip"):
                target = media.get(blip.get(R_EMBED))
                if target and target in names:
                    result.append((order, where, archive.read(target), image_suffix(target)))
    result.sort(key=lambda item: item[0])
    return [(where, data, suffix) for _, where, data, suffix in result]


def wps_cell_images(archive, names):
    """WPS 嵌入单元格的图片：{图片名: (数据, 扩展名)}，单元格公式里是 DISPIMG("图片名", 1)。"""
    part = "xl/cellimages.xml"
    if part not in names:
        return {}
    media = rels(archive, part)
    result = {}
    for pic in zip_xml(archive, part).iter(f"{{{NS['xdr']}}}pic"):
        props = pic.find("xdr:nvPicPr/xdr:cNvPr", NS)
        blip = next(pic.iter(f"{{{NS['a']}}}blip"), None)
        if props is None or blip is None:
            continue
        target = media.get(blip.get(R_EMBED))
        if target and target in names:
            result[props.get("name")] = (archive.read(target), image_suffix(target))
    return result
