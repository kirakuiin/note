# -*- coding: utf-8 -*-
"""工作区用例的读取、归属校验、扫描、通过记录和检索。设计见 specs/2026-11-11-case-reuse.md。

case_runner.py（运行、search）、workspace.py（context 的 cases）、report.py（拷贝用例文件）共用本模块。
模块顶层只依赖标准库：precommit 在取未提交改动时才导入（precommit 导入 workspace，workspace 导入本模块）。

工作区用例：<项目>/.mhxy-workspace/cases/<工单号或功能名>/*.json 和 .mhxy-workspace/coverage/<任务目录>/*.json。
cases/reports/（执行器报告）和 cases/runs.json（通过记录）是保留名。
"""
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import time

DIRECTORY = ".mhxy-workspace"
CASES = Path(DIRECTORY) / "cases"
COVERAGE = Path(DIRECTORY) / "coverage"
REPORTS = "reports"  # cases/ 下的执行器报告目录（case_runner.REPORT_DIR）
RUNS_FILE = "runs.json"  # cases/ 下的通过记录
LOCK_WAIT = 10  # 等通过记录锁的最长秒数
LOCK_STALE = 60  # 锁文件超过这个秒数视为残留（写入只需毫秒级）
META_FIELDS = ("issue", "spec", "targets", "keywords")
ISSUE_ID = re.compile(r"^\d+$")
SPEC_HEADING = re.compile(r"^(#+)\s*测试用例\s*$")
CHANGED_ITEMS = {"modified", "added", "replaced", "unversioned"}  # 同 diff_lines.CHANGED_ITEMS


class CaseError(Exception):
    """用例文件读不了、不是有效 JSON 或没有用例。"""


# ---------- 读取 ----------

def load_cases(path):
    """读取用例：.json 为一个用例或用例列表；.md 取「测试用例」一节下的 json 代码块。

    Returns:
        [(来源说明, 用例)]，来源说明形如 `文件名#序号`。
    Raises:
        CaseError: 文件读不了、JSON 无效或找不到用例。
    """
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as error:
        raise CaseError(f"读不了 {path}：{error}") from None
    blocks = spec_blocks(text) if path.suffix.lower() == ".md" else [text]
    cases = []
    for number, block in enumerate(blocks, 1):
        try:
            value = json.loads(block)
        except ValueError as error:
            raise CaseError(f"{path} 第 {number} 个用例块不是有效 JSON：{error}") from None
        for item in value if isinstance(value, list) else [value]:
            cases.append((f"{path.name}#{len(cases) + 1}", item))
    if not cases:
        raise CaseError(f"{path} 中没有用例" + ("（「测试用例」一节下没有 json 代码块）" if blocks == [] else ""))
    return cases


def spec_blocks(text):
    """取 markdown 中「测试用例」标题下（到同级或更高级标题为止）的 ```json 代码块正文。"""
    blocks, level, current = [], None, None
    for line in text.splitlines():
        heading = re.match(r"^(#+)\s", line)
        if current is None and heading and level is not None and len(heading.group(1)) <= level:
            level = None
        if level is None:
            match = SPEC_HEADING.match(line)
            if match:
                level = len(match.group(1))
            continue
        if current is None and line.strip().lower() == "```json":
            current = []
        elif current is not None and line.strip() == "```":
            blocks.append("\n".join(current))
            current = None
        elif current is not None:
            current.append(line)
    return blocks


# ---------- 归属与位置 ----------

def relative(root, path):
    """相对项目根的 / 分隔路径；不在项目根下时返回 None。"""
    try:
        return Path(path).resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        return None


def area(root, path):
    """用例文件所在的工作区区域：`cases`、`coverage`，不在其中返回 None。"""
    rel = relative(root, path)
    if rel is None:
        return None
    for name, base in (("cases", CASES), ("coverage", COVERAGE)):
        if rel.startswith(base.as_posix() + "/"):
            return name
    return None


def meta_problems(case, required):
    """检查归属字段 issue／spec／targets／keywords。required 为真时（工作区用例）四项都必须写。"""
    if not isinstance(case, dict):
        return []
    problems = []
    missing = [field for field in META_FIELDS if field not in case]
    if required and missing:
        problems.append(f"工作区用例要写归属字段 {missing}（issue 工单号或 null、spec 路径或 null、"
                        "targets 测的文件或模块、keywords 检索词）")
    if "issue" in case and not (case["issue"] is None or isinstance(case["issue"], str)
                                and ISSUE_ID.match(case["issue"])):
        problems.append("issue 必须是工单号字符串（纯数字）或 null")
    if "spec" in case and not (case["spec"] is None or isinstance(case["spec"], str) and case["spec"].strip()):
        problems.append("spec 必须是相对项目根的路径或 null")
    if "targets" in case and not (isinstance(case["targets"], list) and case["targets"]
                                  and all(isinstance(item, str) and item.strip() for item in case["targets"])):
        problems.append("targets 必须是非空的字符串列表（文件、目录或模块名）")
    if "keywords" in case and not (isinstance(case["keywords"], list)
                                   and all(isinstance(item, str) and item.strip() for item in case["keywords"])):
        problems.append("keywords 必须是字符串列表")
    return problems


def location_problems(root, path):
    """工作区用例的存放位置：cases/ 下必须在 <工单号或功能名>/ 子目录里，不能放进保留目录。"""
    rel = relative(root, path)
    if rel is None or area(root, path) != "cases":
        return []
    parts = rel.split("/")[len(CASES.parts):]
    if len(parts) == 1:
        return [f"用例文件要放在 {CASES.as_posix()}/<工单号或功能名>/ 下：{rel}"]
    if parts[0] == REPORTS:
        return [f"{CASES.as_posix()}/{REPORTS}/ 是执行器报告目录，不放用例：{rel}"]
    return []


def source_problems(root, path, case):
    """运行前对来源文件的检查：位置，以及归属字段（工作区用例必填，其他来源写了也校验）。"""
    return location_problems(root, path) + meta_problems(case, area(root, path) is not None)


def digest(case):
    """用例内容摘要：规范化 JSON 的 SHA-256 前 16 位，用来判断通过后是否改过。"""
    text = json.dumps(case, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# ---------- 扫描 ----------

def case_files(root):
    """工作区用例文件（不跟随链接）：[(区域, 路径)]，按路径排序。"""
    found = []
    for name, base in (("cases", CASES), ("coverage", COVERAGE)):
        top = Path(root) / base
        if not top.is_dir() or top.is_symlink():
            continue
        for directory, subdirs, files in os.walk(top):
            here = Path(directory)
            if name == "cases" and here == top:
                subdirs[:] = [item for item in subdirs if item != REPORTS]
            subdirs[:] = [item for item in subdirs if not (here / item).is_symlink()]
            for file in files:
                path = here / file
                if path.suffix.lower() != ".json" or path.is_symlink():
                    continue
                if name == "cases" and here == top and file == RUNS_FILE:
                    continue
                found.append((name, path))
    return sorted(found, key=lambda item: str(item[1]))


def looks_like_case(value):
    """覆盖率目录里可能有其他 JSON：只有 {steps: [...]} 或其列表才当作用例。"""
    items = value if isinstance(value, list) else [value]
    return bool(items) and all(isinstance(item, dict) and "steps" in item for item in items)


def scan(root):
    """扫描全部工作区用例。

    Returns:
        (条目列表, 问题列表)。条目：{path, name, issue, spec, targets, keywords, hash}，path 相对项目根。
        问题：{path, problem}。cases/ 下读不了或不合法的都算问题；coverage/ 下不像用例的 JSON 跳过。
    """
    entries, problems = [], []
    for name, path in case_files(root):
        rel = relative(root, path)
        try:
            loaded = load_cases(path)
        except CaseError as error:
            if name == "cases":
                problems.append({"path": rel, "problem": str(error)})
            continue
        if name == "coverage" and not looks_like_case([case for _, case in loaded]):
            continue
        for where, case in loaded:
            issues = location_problems(root, path) + meta_problems(case, True)
            if not isinstance(case, dict) or not isinstance(case.get("name"), str):
                issues.append("用例必须是对象且有 name")
            if issues:
                problems.append({"path": rel, "problem": f"{where}：" + "；".join(issues)})
                continue
            entries.append({"path": rel, "name": case["name"], "issue": case["issue"], "spec": case["spec"],
                            "targets": case["targets"], "keywords": case["keywords"], "hash": digest(case)})
    return entries, problems


# ---------- 通过记录 ----------

def runs_path(root):
    return Path(root) / CASES / RUNS_FILE


def read_runs(root):
    """读取通过记录 {"<来源>#<用例名>": {...}}；文件不存在时为空，损坏时抛 CaseError。"""
    path = runs_path(root)
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise CaseError(f"通过记录无法读取：{path}：{error}") from None
    if not isinstance(value, dict) or not isinstance(value.get("cases"), dict):
        raise CaseError(f"通过记录格式不对：{path}")
    return value["cases"]


def run_key(source, name):
    return f"{source}#{name}"


def record_runs(root, results, report_path, now=None):
    """把一次运行的各用例结果写进通过记录。results 每项需要 source（绝对路径）、name、status、case_hash。

    来源不在项目根下的跳过。用锁文件串行化并发写入。

    Returns:
        问题列表（空表示已写入），由调用方记进报告的 unverified。
    """
    stamp = (now or datetime.now().astimezone()).isoformat(timespec="seconds")
    updates = {}
    for item in results:
        source = relative(root, item["source"]) if item.get("source") else None
        if source is None:
            continue
        entry = {"last_run": stamp, "last_status": item["status"], "report": str(report_path)}
        if item["status"] == "passed":
            entry.update(last_passed=stamp, passed_hash=item["case_hash"])
        updates[run_key(source, item["name"])] = entry
    if not updates:
        return []
    path = runs_path(root)
    lock = path.with_name(RUNS_FILE + ".lock")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not acquire(lock):
            return [f"通过记录被占用超过 {LOCK_WAIT} 秒，本次结果没有记入 {path}"]
    except OSError as error:
        return [f"通过记录无法写入：{path}：{error}"]
    try:
        try:
            runs = read_runs(root)
        except CaseError as error:
            return [f"{error}，本次结果没有记入"]
        for key, entry in updates.items():
            old = runs.get(key, {})
            if entry["last_status"] != "passed":  # 失败不抹掉上次通过的记录
                entry.update({field: old[field] for field in ("last_passed", "passed_hash") if field in old})
            runs[key] = entry
        temp = path.with_name(RUNS_FILE + ".tmp")
        temp.write_text(json.dumps({"cases": runs}, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
        os.replace(temp, path)
        return []
    except OSError as error:
        return [f"通过记录无法写入：{path}：{error}"]
    finally:
        try:
            lock.unlink()
        except OSError:
            pass


def acquire(lock):
    """创建锁文件；超过 LOCK_STALE 秒的残留锁先删除。等不到返回 False。"""
    deadline = time.monotonic() + LOCK_WAIT
    while True:
        try:
            os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            return True
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime > LOCK_STALE:
                    lock.unlink()
                    continue
            except OSError:
                continue
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.1)


def with_runs(entries, runs):
    """给扫描条目补上运行记录：last_status、last_passed、changed_since_pass。"""
    result = []
    for entry in entries:
        run = runs.get(run_key(entry["path"], entry["name"]), {})
        item = {key: value for key, value in entry.items() if key != "hash"}
        item["last_status"] = run.get("last_status")
        item["last_passed"] = run.get("last_passed")
        item["changed_since_pass"] = bool(run.get("passed_hash")) and run["passed_hash"] != entry["hash"]
        result.append(item)
    return result


# ---------- 检索 ----------

def normalize(path):
    path = path.replace("\\", "/").strip().lower()
    while path.startswith("./"):
        path = path[2:]
    return path


def target_matches(target, file):
    """targets 中的一项是否对应文件 file（相对项目根）：路径相同或互为结尾、目录前缀、模块名等于文件名。"""
    target, file = normalize(target), normalize(file)
    if not target or not file:
        return False
    if target.endswith("/"):
        return file.startswith(target) or ("/" + target) in ("/" + file)
    if target == file or file.endswith("/" + target) or target.endswith("/" + file):
        return True
    if "/" not in target and "." not in target:
        return Path(file).stem == target
    return False


def term_matches(entry, term):
    text = " ".join([entry["name"], entry["issue"] or "", *entry["keywords"], *entry["targets"]]).lower()
    return term.lower() in text


def changed_files(root):
    """svn status 中待提交的文件（同 precommit 的范围，未纳入版本控制的目录展开为其中的文件）。

    Raises:
        CaseError: svn 不可用或不是工作副本（不能当作“没有改动”）。
    """
    import precommit  # 延迟导入：precommit → workspace → case_store
    try:
        entries = precommit.svn_status(Path(root))
    except precommit.PrecheckError as error:
        raise CaseError(f"取不到未提交改动：{error}") from None
    files = []
    for entry in entries:
        if entry["item"] not in CHANGED_ITEMS or not precommit.in_scope(entry):
            continue
        path = Path(root) / entry["path"]
        if entry["item"] == "unversioned" and path.is_dir():
            files.extend(item.relative_to(root).as_posix() for item in path.rglob("*") if item.is_file())
        elif not path.is_dir():
            files.append(entry["path"])
    return sorted(set(files))


def find(root, issue=None, files=(), terms=(), changed=None):
    """按条件检索工作区用例，条件同时满足才命中。changed 为未提交文件列表（None 表示不按改动查）。

    Returns:
        {"cases": [...], "problems": [...]}
    """
    entries, problems = scan(root)
    runs = read_runs(root)
    found = []
    for entry in with_runs(entries, runs):
        if issue is not None and entry["issue"] != issue:
            continue
        if not all(any(target_matches(target, file) for target in entry["targets"]) for file in files):
            continue
        if changed is not None and not any(target_matches(target, file)
                                           for target in entry["targets"] for file in changed):
            continue
        if not all(term_matches(entry, term) for term in terms):
            continue
        found.append(entry)
    return {"cases": found, "problems": problems}


def context_summary(root, issue_ids):
    """context 用的精简汇总：工作区用例总数、问题文件数，以及追踪工单各自的用例。"""
    entries, problems = scan(root)
    runs = read_runs(root)
    items = with_runs(entries, runs)
    tracked = []
    for issue_id in issue_ids:
        own = [item for item in items if item["issue"] == issue_id]
        if not own:
            continue
        passed = [item["last_passed"] for item in own if item["last_passed"] and not item["changed_since_pass"]]
        tracked.append({"issue_id": issue_id, "count": len(own), "passed": len(passed),
                        "last_passed": max(passed) if passed else None,
                        "files": sorted({item["path"] for item in own})})
    return {"total": len(items), "problem_files": len({item["path"] for item in problems}), "tracked": tracked}
