import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "lint_wiki.py"
spec = importlib.util.spec_from_file_location("lint_wiki", SCRIPT)
lint_wiki = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lint_wiki)


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def base_vault(tmp_path: Path) -> Path:
    write(
        tmp_path / "9-Meta" / "TAGS.md",
        """---
area: meta
visibility: public
---
# TAGS.md

## 2. 核心白名单

| Tag | 说明 |
|---|---|
| `#编程语言` | x |
| `#概念` | x |
| `#工具` | x |

## 3. 红线清单

| Tag | 说明 |
|---|---|
| `#sdc` | x |
| `#mhxy` | x |

### 3.5 嵌套红线

- `#sdc/*`
以下嵌套路径为红线（公开区 `#工具/Git`、`#工具/VSCode` 等合法）：
- `#工具/打包` `#工具/web2md`

## 4. 历史脏 tag 清理表

| 脏 tag | 频次 | 目标 tag | 说明 |
|---|---|---|---|
| `#language` | 1 | `#编程语言` | x |
""",
    )
    write(
        tmp_path / "Netease" / "AGENTS.md",
        """# Netease

### 4.2 私有区**专属**白名单

| tag | 用途 |
|---|---|
| `#daily-report` | x |
""",
    )
    write(tmp_path / "9-Meta" / "AGENTS.md", "# public rules\n")
    return tmp_path


def issues_by_id(report):
    found = {}
    for issue in report["issues"]:
        found.setdefault(issue["id"], []).append(issue)
    return found


def test_missing_frontmatter_does_not_require_status_created_or_updated(tmp_path):
    vault = base_vault(tmp_path)
    write(
        vault / "2-Wiki" / "编程语言" / "Python.md",
        """---
area: knowledge
visibility: public
tags:
  - 编程语言
---
# Python
""",
    )

    report = lint_wiki.scan_vault(vault)
    by_id = issues_by_id(report)

    python_w2 = [
        issue
        for issue in by_id.get("W2", [])
        if issue["path"] == "2-Wiki/编程语言/Python.md"
    ]
    assert python_w2 == []


def test_index_pages_need_only_basic_frontmatter(tmp_path):
    vault = base_vault(tmp_path)
    write(
        vault / "1-Sessions" / "_index.md",
        """---
area: session
visibility: public
---
# Sessions
""",
    )

    report = lint_wiki.scan_vault(vault)
    findings = [
        issue
        for issue in report["issues"]
        if issue["path"] == "1-Sessions/_index.md"
        and issue["id"] in {"W2", "W8"}
    ]

    assert findings == []


def test_body_hash_words_are_not_wild_tags(tmp_path):
    vault = base_vault(tmp_path)
    write(
        vault / "6-Tools" / "版本控制-SVN.md",
        """---
area: tool
visibility: public
category: 版本控制
tags:
  - 工具/SVN
---
# 合并
正文提到 #提交 和 #解决冲突。
""",
    )

    report = lint_wiki.scan_vault(vault)
    s2 = [
        issue
        for issue in issues_by_id(report).get("S2", [])
        if issue["path"] == "6-Tools/版本控制-SVN.md"
    ]

    assert s2 == []


def test_templates_allow_empty_tag_placeholders(tmp_path):
    vault = base_vault(tmp_path)
    write(
        vault / "9-Meta" / "Templates" / "wiki-page.md",
        """---
area: knowledge
visibility: public
tags:
---
# {{title}}
""",
    )

    report = lint_wiki.scan_vault(vault)
    w2 = [
        issue
        for issue in issues_by_id(report).get("W2", [])
        if issue["path"] == "9-Meta/Templates/wiki-page.md"
    ]

    assert w2 == []


def test_tags_authority_file_does_not_leak_its_own_redline_definitions(tmp_path):
    vault = base_vault(tmp_path)

    report = lint_wiki.scan_vault(vault)
    tag_leaks = [
        issue
        for issue in issues_by_id(report).get("C2", [])
        if issue["path"] == "9-Meta/TAGS.md"
    ]

    assert tag_leaks == []


def test_meta_governance_files_can_describe_private_boundary_rules(tmp_path):
    vault = base_vault(tmp_path)
    write(
        vault / "9-Meta" / "Skills" / "lint-wiki" / "SKILL.md",
        """---
area: meta
visibility: public
---
Public rules mention `Netease/` and examples like `#sdc/*`.
""",
    )

    report = lint_wiki.scan_vault(vault)
    findings = [
        issue
        for issue in report["issues"]
        if issue["path"] == "9-Meta/Skills/lint-wiki/SKILL.md"
        and issue["id"] in {"C1", "C2", "S2"}
    ]

    assert findings == []


def test_hidden_system_entries_are_not_unknown_top_level(tmp_path):
    vault = base_vault(tmp_path)
    write(vault / ".obsidian" / "app.json", "{}")
    write(vault / ".mypy_cache" / "x.txt", "cache")
    write(vault / ".DS_Store", "cache")

    report = lint_wiki.scan_vault(vault)
    w6_paths = [issue["path"] for issue in issues_by_id(report).get("W6", [])]

    assert ".obsidian" not in w6_paths
    assert ".mypy_cache" not in w6_paths
    assert ".DS_Store" not in w6_paths


def test_public_wikilink_resolving_to_netease_is_critical(tmp_path):
    vault = base_vault(tmp_path)
    write(
        vault / "Netease" / "2-Wiki" / "业务" / "私有页.md",
        """---
area: knowledge
visibility: private
tags:
  - daily-report
---
# 私有页
""",
    )
    write(
        vault / "2-Wiki" / "编程语言" / "Public.md",
        """---
area: knowledge
visibility: public
tags:
  - 编程语言
---
See [[私有页]].
""",
    )

    report = lint_wiki.scan_vault(vault)
    c1 = issues_by_id(report).get("C1", [])

    assert any("resolves to Netease/" in issue["problem"] for issue in c1)


def test_image_embeds_are_not_reported_as_broken_wiki_pages(tmp_path):
    vault = base_vault(tmp_path)
    write(
        vault / "2-Wiki" / "编程语言" / "Images.md",
        """---
area: knowledge
visibility: public
tags:
  - 编程语言
---
![[diagram.png]]
""",
    )

    report = lint_wiki.scan_vault(vault)
    w1 = [
        issue
        for issue in issues_by_id(report).get("W1", [])
        if issue["path"] == "2-Wiki/编程语言/Images.md"
    ]

    assert w1 == []


def test_code_snippets_are_not_scanned_as_wikilinks(tmp_path):
    vault = base_vault(tmp_path)
    write(
        vault / "Netease" / "4-Reference" / "sdk.md",
        """---
area: reference
visibility: private
source: docs
---
```python
filters = [['name','=','xxx']]
```
Inline `[['other','=','yyy']]` too.
""",
    )

    report = lint_wiki.scan_vault(vault)
    w1 = [
        issue
        for issue in issues_by_id(report).get("W1", [])
        if issue["path"] == "Netease/4-Reference/sdk.md"
    ]

    assert w1 == []


def test_table_code_and_template_links_are_not_broken_wikilinks(tmp_path):
    vault = base_vault(tmp_path)
    write(
        vault / "Netease" / "4-Reference" / "sdk.md",
        """---
area: reference
visibility: private
source: docs
---
| = | [['name','=','xxx']] |
""",
    )
    write(
        vault / "9-Meta" / "Templates" / "index.md",
        """---
area: meta
visibility: public
---
| item | [[{{path_1}}]] |
""",
    )

    report = lint_wiki.scan_vault(vault)
    w1 = [
        issue
        for issue in issues_by_id(report).get("W1", [])
        if issue["path"] in {"Netease/4-Reference/sdk.md", "9-Meta/Templates/index.md"}
    ]

    assert w1 == []


def test_wikilink_path_suffix_resolves_within_vault(tmp_path):
    vault = base_vault(tmp_path)
    write(
        vault / "Netease" / "2-Wiki" / "业务" / "踩坑集" / "坑.md",
        """---
area: knowledge
visibility: private
tags:
  - daily-report
---
# 坑
""",
    )
    write(
        vault / "Netease" / "2-Wiki" / "业务" / "UI开发" / "入口.md",
        """---
area: knowledge
visibility: private
tags:
  - daily-report
---
See [[踩坑集/坑]].
""",
    )

    report = lint_wiki.scan_vault(vault)
    w1 = [
        issue
        for issue in issues_by_id(report).get("W1", [])
        if issue["path"] == "Netease/2-Wiki/业务/UI开发/入口.md"
    ]

    assert w1 == []


def test_netease_case_visibility_mismatch_detected(tmp_path):
    vault = base_vault(tmp_path)
    write(
        vault / "Netease" / "2-Wiki" / "业务" / "Wrong.md",
        """---
area: knowledge
visibility: public
tags:
  - daily-report
---
# Wrong
""",
    )

    report = lint_wiki.scan_vault(vault)
    c3 = issues_by_id(report).get("C3", [])

    assert any(issue["path"] == "Netease/2-Wiki/业务/Wrong.md" for issue in c3)


def test_non_utf8_markdown_does_not_abort_scan(tmp_path):
    vault = base_vault(tmp_path)
    bad = vault / "2-Wiki" / "编程语言" / "BadEncoding.md"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_bytes(b"---\narea: knowledge\nvisibility: public\ntags:\n  - \xa1\n---\n# bad\n")

    report = lint_wiki.scan_vault(vault)

    assert "issues" in report


def test_public_redline_tag_and_cleanup_suggestion(tmp_path):
    vault = base_vault(tmp_path)
    write(
        vault / "2-Wiki" / "编程语言" / "Leak.md",
        """---
area: knowledge
visibility: public
tags:
  - sdc
  - language
---
# Leak
""",
    )

    report = lint_wiki.scan_vault(vault)
    by_id = issues_by_id(report)

    assert any("sdc" in issue["problem"] for issue in by_id.get("C2", []))
    assert any("编程语言" in issue["suggestion"] for issue in by_id.get("S2", []))


def test_private_redline_tags_are_allowed(tmp_path):
    vault = base_vault(tmp_path)
    write(
        vault / "Netease" / "2-Wiki" / "业务" / "Internal.md",
        """---
area: knowledge
visibility: private
tags:
  - mhxy
  - sdc/大地图
---
# Internal
""",
    )

    report = lint_wiki.scan_vault(vault)
    findings = [
        issue
        for issue in report["issues"]
        if issue["path"] == "Netease/2-Wiki/业务/Internal.md"
        and issue["id"] in {"C2", "S2"}
    ]

    assert findings == []


def test_html_colors_and_markdown_anchors_are_not_tags(tmp_path):
    vault = base_vault(tmp_path)
    write(
        vault / "Netease" / "4-Reference" / "doc.md",
        """---
area: reference
visibility: private
source: docs
---
<span style="background:#f8a5a5;color:#4a0000">新增</span>
| [_index.md](#_indexmd) | changed |
""",
    )

    report = lint_wiki.scan_vault(vault)
    s2 = [
        issue
        for issue in issues_by_id(report).get("S2", [])
        if issue["path"] == "Netease/4-Reference/doc.md"
    ]

    assert s2 == []


def test_excalidraw_plugin_tags_are_ignored(tmp_path):
    vault = base_vault(tmp_path)
    write(
        vault / "9-Meta" / "Excalidraw" / "drawing.excalidraw.md",
        """---
excalidraw-plugin: parsed
tags: [excalidraw]
visibility: public
area: meta
---
# Excalidraw Data
""",
    )

    report = lint_wiki.scan_vault(vault)
    s2 = [
        issue
        for issue in issues_by_id(report).get("S2", [])
        if issue["path"] == "9-Meta/Excalidraw/drawing.excalidraw.md"
    ]

    assert s2 == []


def test_public_nested_tool_tags_from_legal_examples_are_allowed(tmp_path):
    vault = base_vault(tmp_path)
    with (vault / "9-Meta" / "TAGS.md").open("a", encoding="utf-8") as f:
        f.write("\n以下嵌套路径为红线（公开区 `#工具/Git`、`#工具/VSCode` 等合法）：\n")
        f.write("- `#工具/打包` `#工具/web2md`\n")
    write(
        vault / "6-Tools" / "版本控制-Git.md",
        """---
area: tool
visibility: public
category: 版本控制
tags:
  - 工具/Git
---
# Git
""",
    )

    report = lint_wiki.scan_vault(vault)
    findings = [
        issue
        for issue in report["issues"]
        if issue["path"] == "6-Tools/版本控制-Git.md"
        and issue["id"] in {"C2", "S2"}
    ]

    assert findings == []


def test_cli_json_output_shape(tmp_path, capsys):
    vault = base_vault(tmp_path)

    code = lint_wiki.main(["--vault", str(vault), "--json"])
    captured = capsys.readouterr()
    data = json.loads(captured.out)

    assert code == 0
    assert "issues" in data
    assert data["summary"]["critical"] >= 0
