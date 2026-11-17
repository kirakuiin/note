"""追踪工单策划文档：链接识别、issue.md 改写、文件挑选、xlsx 转换、检出流程；SVN 均为模拟。"""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import sys
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import task_docs as d  # noqa: E402

FILE_URL = "https://svn-xyq.gz.netease.com/svn/products/xy1/design/Z资料片/新PVE玩法/困难模式.xlsx"
DIR_URL = "https://svn-xyq.gz.netease.com/svn/products/xy1/design/R任务系统/搜打撤3v3"
ISSUE = f"# 1 标题\n\n来源：x\n\n[{FILE_URL}](<{FILE_URL}>)\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 16


def xlsx_bytes():
    """最小 xlsx：一个工作表、共享字符串、一张浮动图片锚在 B2。"""
    files = {
        "xl/workbook.xml": '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                           'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                           '<sheets><sheet name="说明" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                                      '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>',
        "xl/sharedStrings.xml": '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                                '<si><t>需求</t></si><si><t>第一行|竖线</t></si></sst>',
        "xl/worksheets/sheet1.xml": '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                                    '<sheetData><row r="1"><c r="A1" t="s"><v>0</v></c></row>'
                                    '<row r="3"><c r="B3" t="s"><v>1</v></c><c r="C3"><v>42</v></c></row>'
                                    '</sheetData></worksheet>',
        "xl/worksheets/_rels/sheet1.xml.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                                               '<Relationship Id="rId1" Target="../drawings/drawing1.xml"/></Relationships>',
        "xl/drawings/drawing1.xml": '<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" '
                                    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
                                    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                                    '<xdr:twoCellAnchor><xdr:from><xdr:col>1</xdr:col><xdr:row>1</xdr:row></xdr:from>'
                                    '<xdr:pic><xdr:blipFill><a:blip r:embed="rId1"/></xdr:blipFill></xdr:pic>'
                                    '</xdr:twoCellAnchor></xdr:wsDr>',
        "xl/drawings/_rels/drawing1.xml.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                                               '<Relationship Id="rId1" Target="../media/image1.png"/></Relationships>',
    }
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, text in files.items():
            archive.writestr(name, text)
        archive.writestr("xl/media/image1.png", PNG)
    return stream.getvalue()


class LinkTests(unittest.TestCase):
    def test_links_are_found_normalized_and_deduplicated(self):
        encoded = d.quote(FILE_URL, safe=":/")
        text = (f"见 {FILE_URL}。\n[a](<{encoded}>)\nsvn://svn-xyq.gz.netease.com/svn/products/xy1/design/X/\n"
                "https://example.com/svn/a/b/c\n")
        self.assertEqual(d.svn_links(text), [FILE_URL, "svn://svn-xyq.gz.netease.com/svn/products/xy1/design/X"])

    def test_link_issue_points_to_local_file_and_is_idempotent(self):
        entries = [{"url": FILE_URL, "kind": "file", "name": "困难模式.xlsx", "path": "docs/新PVE玩法/困难模式.xlsx",
                    "revision": "12", "skipped": [],
                    "documents": [{"name": "困难模式.xlsx", "markdown": "docs/_converted/新PVE玩法/困难模式.xlsx.md"}]}]
        once = d.link_issue(ISSUE, entries, [])
        self.assertIn("](<docs/新PVE玩法/困难模式.xlsx>)", once.split(d.SECTION_BEGIN)[0])
        self.assertIn("Markdown 版：[困难模式.xlsx](<docs/_converted/新PVE玩法/困难模式.xlsx.md>)", once)
        self.assertIn(f"远端：{FILE_URL}", once)
        self.assertEqual(d.link_issue(once, entries, []), once)
        # 小节里的远端地址不重复计入；正文链接文字本身就是 URL 时仍能识别出同一个链接。
        self.assertEqual(d.svn_links(once), [FILE_URL])

    def test_failures_keep_remote_link(self):
        text = d.link_issue(ISSUE, [], [{"url": FILE_URL, "reason": "权限不足"}])
        self.assertIn(f"](<{FILE_URL}>)", text)
        self.assertIn("下载失败，保留远端链接", text)
        self.assertEqual(d.link_issue(ISSUE, [], []), ISSUE)

    def test_skipped_files_are_listed_with_remote_links(self):
        entries = [{"url": DIR_URL, "kind": "dir", "name": "搜打撤3v3", "path": "docs/搜打撤3v3", "revision": "9",
                    "documents": [{"name": "a.md", "markdown": "docs/搜打撤3v3/a.md", "plain": True}],
                    "skipped": [{"path": "ui/big.pdf", "size": 30 * d.MB, "reason": "x", "url": DIR_URL + "/ui/big.pdf"}]}]
        text = d.link_issue(f"[x](<{DIR_URL}>)\n", entries, [])
        self.assertIn("未下载 1 个文件", text)
        self.assertIn(f"[ui/big.pdf](<{DIR_URL}/ui/big.pdf>)（30.0 MB）", text)
        self.assertNotIn("a.md", text)


class PickTests(unittest.TestCase):
    def test_file_and_total_limits(self):
        with patch.object(d, "FILE_LIMIT", 10), patch.object(d, "TOTAL_LIMIT", 15):
            picked, skipped = d.pick_files([("b.md", 8), ("a.pdf", 11), ("c.md", 5), ("d.md", 3)])
        self.assertEqual(picked, ["b.md", "c.md"])
        self.assertEqual([item[0] for item in skipped], ["a.pdf", "d.md"])


class ConvertTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="task-docs-")
        self.task = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_xlsx_table_and_images(self):
        source = self.task / "docs" / "wc" / "需求.xlsx"
        source.parent.mkdir(parents=True)
        source.write_bytes(xlsx_bytes())
        out = self.task / "docs" / d.CONVERTED / "wc"
        result = d.convert(source, out, None, self.task)
        self.assertEqual(result["markdown"], "docs/_converted/wc/需求.xlsx.md")
        text = (out / "需求.xlsx.md").read_text(encoding="utf-8")
        self.assertIn("## 说明", text)
        self.assertIn("| 1 | 需求 |  |  |", text)
        self.assertIn("| 3 |  | 第一行\\|竖线 | 42 |", text)
        self.assertIn("![说明 B2](需求.xlsx_images/s01_img01.png)", text)
        self.assertEqual((out / "需求.xlsx_images" / "s01_img01.png").read_bytes(), PNG)

    def test_only_client_related_sheets_are_converted(self):
        titles = ["onepage", "玩法规则", "战斗设计", "数值设计", "奖励设计", "UI和美术需求", "演算", "修改记录"]
        picked = d.pick_sheets(titles)
        self.assertEqual(picked["sheets"], ["玩法规则", "UI和美术需求"])
        self.assertEqual(len(picked["dropped"]), 6)
        self.assertTrue(d.pick_sheets(["说明", "数值"])["fallback"])
        source = self.task / "a.xlsx"
        source.write_bytes(xlsx_bytes())
        text, pictures = d.xlsx_markdown(source, "img", {"其他"})
        self.assertNotIn("## 说明", text)
        self.assertEqual(pictures, {})
        with patch.object(d, "sheet_titles", return_value=["说明", "数值设计"]), \
                patch.object(d, "SHEET_RULE", d.re.compile("说明")):
            result = d.convert(source, self.task / "o", None, self.task)
        self.assertEqual(result["dropped"], ["数值设计"])
        body = (self.task / "o" / "a.xlsx.md").read_text(encoding="utf-8")
        self.assertIn("未转换：数值设计", body)
        entry = {"url": FILE_URL, "kind": "file", "name": "a.xlsx", "path": "docs/a.xlsx", "revision": "1",
                 "skipped": [], "documents": [result]}
        self.assertIn("（只含：说明；其余 1 张工作表见原件）", d.link_issue(ISSUE, [entry], []))

    def test_unchanged_source_is_not_converted_again(self):
        source = self.task / "a.xlsx"
        source.write_bytes(xlsx_bytes())
        out = self.task / "out"
        d.convert(source, out, None, self.task)
        with patch.object(d, "xlsx_markdown", side_effect=AssertionError("不应重新转换")):
            self.assertIn("markdown", d.convert(source, out, None, self.task))
        source.write_bytes(xlsx_bytes() + b"")  # 内容相同
        with patch.object(d, "xlsx_markdown", return_value=("changed\n", {})) as again:
            (out / "a.xlsx.md").write_text("<!-- source-sha256: " + "0" * 64 + " -->\n", encoding="utf-8")
            d.convert(source, out, None, self.task)
        again.assert_called_once()

    def test_markitdown_formats_and_limits(self):
        pdf = self.task / "a.pdf"
        pdf.write_bytes(b"%PDF")
        self.assertIn("没有 markitdown", d.convert(pdf, self.task / "o", None, self.task)["note"])
        with patch.object(d, "run_markitdown", return_value="# pdf\n"):
            self.assertIn("markdown", d.convert(pdf, self.task / "o", "markitdown", self.task))
        with patch.object(d, "CONVERT_LIMIT", 1):
            self.assertIn("未转换", d.convert(pdf, self.task / "p", "markitdown", self.task)["note"])
        plain = self.task / "b.md"
        plain.write_text("x", encoding="utf-8")
        self.assertTrue(d.convert(plain, self.task / "o", None, self.task)["plain"])
        other = self.task / "c.png"
        other.write_bytes(PNG)
        self.assertIn("不是可转换", d.convert(other, self.task / "o", None, self.task)["note"])


class FakeSvn:
    """模拟一个 SVN 仓库：files 为 {URL: 内容}，目录由文件路径推出。"""

    def __init__(self, files, revision="100"):
        self.files = files
        self.revision = revision
        self.calls = []

    def __call__(self, cwd, *args, timeout=None):
        self.calls.append(args)
        action = args[0]
        if action == "info" and "kind" in args:
            url = d.unquote(args[-1])
            if url in self.files:
                return "file"
            if any(key.startswith(url + "/") for key in self.files):
                return "dir"
            raise d.DocsError("E170000: 路径不存在")
        if action == "info" and "url" in args:
            return (Path(cwd) / ".url").read_text(encoding="utf-8")
        if action == "info":
            return self.revision
        if action == "checkout":
            wc = Path(cwd) / args[-1]
            wc.mkdir()
            (wc / ".url").write_text(d.unquote(args[-2]), encoding="utf-8")
            return ""
        if action == "list":
            url = d.unquote(args[-1])
            entries = "".join(f'<entry kind="file"><name>{key[len(url) + 1:]}</name><size>{len(value)}</size></entry>'
                              for key, value in self.files.items() if key.startswith(url + "/"))
            return f'<?xml version="1.0" encoding="UTF-8"?><lists><list>{entries}</list></lists>'
        if action == "status":
            return ""
        if action == "update":
            base = (Path(cwd) / ".url").read_text(encoding="utf-8")
            for path in [arg for arg in args[1:] if arg not in ("--parents", ".")]:
                target = Path(cwd) / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(self.files[f"{base}/{path}"])
            return ""
        raise AssertionError(args)


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="task-docs-sync-")
        self.task = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_file_link_checks_out_sparse_parent_and_converts(self):
        fake = FakeSvn({FILE_URL: xlsx_bytes()})
        with patch.object(d, "svn", side_effect=fake):
            entries, failures = d.sync_docs(self.task, ISSUE, markitdown="")
        self.assertEqual(failures, [])
        self.assertEqual(entries[0]["path"], "docs/新PVE玩法/困难模式.xlsx")
        self.assertIn(("checkout", "--depth", "empty"), [call[:3] for call in fake.calls])
        self.assertTrue(all(ord(ch) < 128 for call in fake.calls if call[0] in ("checkout", "info", "list")
                            for arg in call if "://" in arg for ch in arg))  # URL 只以 ASCII 传给 svn。
        self.assertTrue((self.task / entries[0]["documents"][0]["markdown"]).is_file())
        manifest = json.loads((self.task / "docs" / d.MANIFEST).read_text(encoding="utf-8"))
        self.assertEqual(manifest["docs"][0]["url"], FILE_URL)

        fake.revision = "101"  # 再同步：沿用工作副本，报告有更新；正文里链接已改成本地也能从 manifest 找回。
        linked = d.link_issue(ISSUE, entries, [])
        with patch.object(d, "svn", side_effect=fake):
            again, _ = d.sync_docs(self.task, linked, markitdown="")
        self.assertEqual([call[0] for call in fake.calls].count("checkout"), 1)
        self.assertEqual(again[0]["url"], FILE_URL)

    def test_directory_link_skips_large_files(self):
        fake = FakeSvn({f"{DIR_URL}/a/说明.md": b"x" * 5, f"{DIR_URL}/ui/big.pdf": b"y" * 50})
        with patch.object(d, "svn", side_effect=fake), patch.object(d, "FILE_LIMIT", 20):
            entries, failures = d.sync_docs(self.task, f"[x](<{DIR_URL}>)", markitdown="")
        self.assertEqual(failures, [])
        self.assertEqual(entries[0]["skipped"][0]["path"], "ui/big.pdf")
        self.assertTrue((self.task / "docs" / "搜打撤3v3" / "a" / "说明.md").is_file())
        self.assertFalse((self.task / "docs" / "搜打撤3v3" / "ui" / "big.pdf").exists())
        self.assertEqual(entries[0]["documents"], [])  # 目录链接只检出，不转 Markdown。
        self.assertFalse((self.task / "docs" / d.CONVERTED).exists())

    def test_one_failed_link_does_not_stop_others(self):
        missing = "https://svn-xyq.gz.netease.com/svn/products/xy1/design/X/没了.xlsx"
        fake = FakeSvn({FILE_URL: xlsx_bytes()})
        with patch.object(d, "svn", side_effect=fake):
            entries, failures = d.sync_docs(self.task, f"{missing}\n{FILE_URL}\n", markitdown="")
        self.assertEqual([item["url"] for item in failures], [missing])
        self.assertEqual(len(entries), 1)

    def test_no_links_creates_nothing(self):
        self.assertEqual(d.sync_docs(self.task, "没有链接"), ([], []))
        self.assertFalse((self.task / "docs").exists())


if __name__ == "__main__":
    unittest.main()
