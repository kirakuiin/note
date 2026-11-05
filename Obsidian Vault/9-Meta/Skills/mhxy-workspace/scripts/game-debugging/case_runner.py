# -*- coding: utf-8 -*-
"""真机用例执行器：按声明式 JSON 用例文件，在一台客户端上一次跑完并输出报告。

用法见 references/game-debugging.md「用例执行器」，设计见 specs/2026-11-05-case-runner.md。

    python -X utf8 case_runner.py run --root <项目> --devid <设备ID> <用例.json | spec.md> ...

- 不选设备、不加设备锁：由调用方（test 任务的主会话，或主线程直接回归时的 codex_cli.py lock）负责。
- 每次运行先 init_client 一次；每个用例自动开始报错收集、安装 Mock，执行步骤，
  最后在 finally 中等待延迟回调、逆序还原 Mock、核对监听、结束报错收集。
- 报告输出到 stdout，并保存到 <项目>/.mhxy-workspace/cases/reports/。退出码：0 通过，1 失败，2 受阻。

客户端代码约定同 execute_code：顶层定义的名字对函数不可见，最后一行的裸表达式是返回值。
"""
import argparse
import json
from pathlib import Path
import re
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "exec-check"))
import mcp_http  # noqa: E402

ERROR_WATCH = HERE / "error_watch.py"
EXEC_TRACE = HERE.parent / "exec-check" / "exec_trace.py"
REPORT_DIR = Path(".mhxy-workspace") / "cases" / "reports"
TEXT_LIMIT = 2000  # 报告中每个返回值、报错保留的字符数
STEP_TYPES = ("exec", "gm", "mcp", "wait_for", "assert", "exec_check")
# 每种步骤除类型键外允许的选项
STEP_OPTIONS = {"exec": {"save_as"}, "gm": set(), "mcp": {"args", "save_as"}, "wait_for": set(),
                "assert": {"message"}, "exec_check": set()}
SPEC_HEADING = re.compile(r"^(#+)\s*测试用例\s*$")
PLACEHOLDER = re.compile(r"\{(devid|root|(?:vars|args)\.[A-Za-z_]\w*)\}")

# wait_for 预设：领域 → 名字 → 客户端表达式（单个表达式，可用 {args.名字}）。
# 新玩法只在这里加预设，不改执行流程；每个预设都要在真机上验证过再加入。
PRESETS = {
    "war": {
        # utils3.is_in_war 即 event.IS_IN_WAR()，客户端各处判断是否在战斗中都用它
        "war_in": "__import__('utils3').is_in_war()",
        "war_out": "not __import__('utils3').is_in_war()",
        # war.Turn 是客户端当前回合数，进入战斗时从 1 开始
        "war_turn": "__import__('utils3').is_in_war() and __import__('war').Turn >= {args.n}",
        # 命令队列为空：本回合的表演播完，等待下指令或下一回合数据
        "war_idle": "__import__('utils3').is_in_war() and not __import__('war').Cmds",
    },
}
PRESET_INDEX = {name: expr for group in PRESETS.values() for name, expr in group.items()}

# 各事件当前的监听数量；用于核对 Mock 期间新增、未解除的监听
LISTENER_PROBE = ("(lambda e: {k: len(v.listeners) for k, v in vars(e).items() "
                  "if isinstance(getattr(v, 'listeners', None), list)})(__import__('event'))")

# patch 型 Mock 的安装、还原代码。备份存在 sys._mhxy_case_mocks（{名字: (对象, 属性, 原来是否有, 原值, 新值)}），
# 跨多次 execute_code 仍在；只看对象自己的 __dict__，类上继承来的属性还原时删除而不是写回。
PATCH_INSTALL = '''def _install(name, target, value_src):
	import importlib
	import sys
	store = sys.__dict__.setdefault("_mhxy_case_mocks", {})
	if name in store:
		raise RuntimeError(f"Mock {name} 已有安装记录，可能是上次运行没有还原")
	parts = target.split(".")
	for i in range(len(parts) - 1, 0, -1):
		try:
			obj = importlib.import_module(".".join(parts[:i]))
			break
		except ImportError:
			continue
	else:
		raise ImportError(f"找不到 {target} 所在的模块")
	for part in parts[i:-1]:
		obj = getattr(obj, part)
	attr = parts[-1]
	had = attr in vars(obj)
	old = vars(obj).get(attr)
	value = eval(value_src, {"orig": getattr(obj, attr, None)})
	store[name] = (obj, attr, had, old, value)  # 先登记再替换：替换失败时还原也只是写回原值
	setattr(obj, attr, value)
	return "installed"
_install(%r, %r, %r)'''

PATCH_RESTORE = '''def _restore(name):
	import sys
	store = sys.__dict__.get("_mhxy_case_mocks", {})
	if name not in store:
		return {"restored": False, "reason": "没有安装记录"}
	obj, attr, had, old, value = store.pop(name)
	if not store:
		del sys._mhxy_case_mocks
	if had:
		setattr(obj, attr, old)
		return {"restored": vars(obj).get(attr) is old}
	if attr in vars(obj):
		delattr(obj, attr)
	return {"restored": attr not in vars(obj)}
_restore(%r)'''


class CaseError(Exception):
    """用例文件或参数不合法（运行前发现，不连接客户端）。"""


# ---------- 用例文件 ----------

def load_cases(path):
    """读取用例：.json 为一个用例或用例列表；.md 取「测试用例」一节下的 json 代码块。

    Returns:
        [(来源说明, 用例 dict)]
    Raises:
        CaseError: 文件读不了、JSON 无效或找不到用例。
    """
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as error:
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


def validate(case):
    """检查用例结构，返回问题列表（空表示合法）。不检查客户端代码本身。"""
    if not isinstance(case, dict):
        return ["用例必须是对象"]
    problems = []
    unknown = set(case) - {"name", "mocks", "steps", "settle"}
    if unknown:
        problems.append(f"未知字段：{sorted(unknown)}")
    if not isinstance(case.get("name"), str) or not case["name"].strip():
        problems.append("缺少 name")
    names = set()
    for index, mock in enumerate(case.get("mocks", []), 1):
        where = f"mocks[{index}]"
        if not isinstance(mock, dict) or not isinstance(mock.get("name"), str):
            problems.append(f"{where}：需要对象和 name")
            continue
        if mock["name"] in names:
            problems.append(f"{where}：name 重复")
        names.add(mock["name"])
        if set(mock) == {"name", "patch", "value"}:
            if not isinstance(mock["patch"], str) or mock["patch"].count(".") < 1:
                problems.append(f"{where}：patch 写成 模块.属性")
        elif set(mock) != {"name", "install", "restore"}:
            problems.append(f"{where}：只能是 name+patch+value 或 name+install+restore")
    steps = case.get("steps")
    if not isinstance(steps, list) or not steps:
        problems.append("steps 必须是非空列表")
        steps = []
    for index, step in enumerate(steps, 1):
        problems += [f"steps[{index}]：{problem}" for problem in validate_step(step)]
    if "settle" in case and not isinstance(case["settle"], (int, float)):
        problems.append("settle 必须是秒数")
    return problems


def validate_step(step):
    if not isinstance(step, dict):
        return ["步骤必须是对象"]
    kinds = [key for key in step if key in STEP_TYPES]
    if len(kinds) != 1:
        return [f"必须恰好有一个步骤类型（{'/'.join(STEP_TYPES)}），实际：{kinds or list(step)}"]
    kind = kinds[0]
    value, problems = step[kind], []
    extra = set(step) - {kind} - STEP_OPTIONS[kind]
    if extra:
        problems.append(f"{kind} 不支持选项 {sorted(extra)}")
    if kind in ("exec", "gm", "mcp", "assert") and not (isinstance(value, str) and value.strip()):
        problems.append(f"{kind} 的值必须是非空字符串")
    if kind == "mcp" and not isinstance(step.get("args", {}), dict):
        problems.append("mcp 的 args 必须是对象")
    if kind == "wait_for":
        if not isinstance(value, dict) or ("expr" in value) == ("preset" in value):
            problems.append("wait_for 需要 expr 或 preset 二选一")
        elif "preset" in value and value["preset"] not in PRESET_INDEX:
            problems.append(f"未知预设 {value['preset']}，可用：{sorted(PRESET_INDEX)}")
        elif set(value) - {"expr", "preset", "args", "timeout", "interval"}:
            problems.append(f"wait_for 未知字段 {sorted(set(value) - {'expr', 'preset', 'args', 'timeout', 'interval'})}")
    if kind == "exec_check":
        if not isinstance(value, dict) or not isinstance(value.get("cases"), str):
            problems.append("exec_check 需要 cases（定义 CASES 的客户端代码）")
        elif not isinstance(value.get("files", []), list):
            problems.append("exec_check 的 files 必须是列表")
    return problems


def render(text, context, code):
    """替换占位符：{devid}、{root} 原样代入；{vars.x}、{args.x} 在代码里代入 repr()，在其他文本里代入 str()。

    其他花括号（字典、f-string）不动。引用未定义的变量抛 KeyError。
    """
    def replace(match):
        key = match.group(1)
        if key in ("devid", "root"):
            return str(context[key])
        group, name = key.split(".", 1)
        value = context[group][name]
        return repr(value) if code else str(value)
    return PLACEHOLDER.sub(replace, text)


def render_args(value, context):
    """递归替换 mcp 参数中字符串里的占位符（按非代码文本处理）。"""
    if isinstance(value, str):
        return render(value, context, code=False)
    if isinstance(value, dict):
        return {key: render_args(item, context) for key, item in value.items()}
    if isinstance(value, list):
        return [render_args(item, context) for item in value]
    return value


def clip(value):
    """报告里的返回值：能 JSON 序列化且不长就原样保留，否则截断为字符串。"""
    text = json.dumps(value, ensure_ascii=False, default=repr)
    return value if len(text) <= TEXT_LIMIT else text[:TEXT_LIMIT] + "…（已截断）"


# ---------- 与客户端交互 ----------

class Client:
    """一台设备上的调用通道：握手一次，记录每个实际下发的调用（executed）。"""

    def __init__(self, devid):
        self.devid = devid
        self.executed = []
        self.ready = False

    def tool(self, name, arguments, label=None):
        """调用工具并返回载荷；先记入 executed，调用失败（含超时）时也能看到下发过什么。"""
        entry = {"tool": name, "arguments": arguments}
        if label:
            entry["label"] = label
        self.executed.append(entry)
        if not self.ready:
            mcp_http.initialize("case-runner")
            self.ready = True
        return mcp_http.call(name, arguments, handshake=False)

    def run(self, code, label=None, log_code=None):
        """execute_code，返回 {"ret", "error", "loginfo", 以及载荷附带的 ui_events／client_event}。

        log_code 用于 executed 中代替冗长的模板全文（例如“<error_watch.py 全文>”），实际仍发送 code。
        """
        arguments = {"devid": self.devid, "code": code, "need_loginfo": True}
        payload = self.tool("execute_code", arguments, label)
        if log_code is not None:
            self.executed[-1]["arguments"] = dict(arguments, code=log_code)
        inner = payload.get("result", payload) if isinstance(payload, dict) and "ret" not in payload else payload
        if not isinstance(inner, dict):
            raise mcp_http.McpError(f"execute_code 结果无法识别：{str(payload)[:200]}")
        out = {"ret": inner.get("ret"), "error": inner.get("error"), "loginfo": inner.get("loginfo")}
        for key in ("ui_events", "client_event"):
            if isinstance(payload, dict) and payload.get(key):
                out[key] = payload[key]
        return out


def template(path, call):
    """模板文件全文 + 调用行，以及写进 executed 的简写。"""
    return path.read_text(encoding="utf-8") + "\n" + call, f"<{path.name} 全文>\n{call}"


# ---------- 执行 ----------

class StepFailed(Exception):
    """步骤失败：断言不成立、客户端报错、等待超时或调用失败。"""

    def __init__(self, message, record=None):
        super().__init__(message)
        self.record = record or {}


def run_case(client, root, case, settle_default):
    """执行一个用例，返回报告 dict。任何情况下都会尝试还原 Mock 并结束报错收集。"""
    context = {"devid": client.devid, "root": str(root), "vars": {}, "args": {}}
    report = {"name": case["name"], "steps": [], "mocks": [], "errors": [], "unverified": []}
    start = time.time()
    failure = None
    installed = []  # 已安装（或安装中途失败、状态不明）的 Mock，收尾时逆序还原
    baseline = None
    watching = False
    try:
        code, log = template(ERROR_WATCH, "error_watch_start()")
        started = client.run(code, "开始报错收集", log)
        if started["error"]:
            raise StepFailed(f"开始报错收集失败：{started['error']}")
        watching = True
        stale = (started["ret"] or {}).get("stale")
        if stale:
            report["unverified"].append(f"上次未结束的报错收集残留（不属于本次）：{clip(stale)}")

        if case.get("mocks"):
            probe = client.run(LISTENER_PROBE, "记录事件监听基线")
            baseline = probe["ret"] if not probe["error"] and isinstance(probe["ret"], dict) else None
            if baseline is None:
                report["unverified"].append(f"读不到事件监听基线，无法核对监听残留：{probe['error']}")
        for mock in case.get("mocks", []):
            installed.append(mock)
            result = client.run(install_code(mock, context), f"安装 Mock {mock['name']}")
            report["mocks"].append({"name": mock["name"], "install": clip(result["ret"]), "error": result["error"]})
            if result["error"]:
                raise StepFailed(f"安装 Mock {mock['name']} 失败：{result['error']}")

        for index, step in enumerate(case["steps"], 1):
            record = {"index": index}
            report["steps"].append(record)
            began = time.time()
            try:
                run_step(client, root, step, context, record)
            finally:
                record["seconds"] = round(time.time() - began, 2)
    except StepFailed as error:
        failure = str(error)
    except (mcp_http.McpError, OSError, KeyError) as error:
        failure = f"{type(error).__name__}: {error}"
    finally:
        restoration = finish(client, case, context, report, installed, baseline, watching, settle_default)
    if failure:
        report["failure"] = failure
    report["restoration"] = restoration
    report["seconds"] = round(time.time() - start, 2)
    report["status"] = "passed" if not failure and not report["errors"] and restoration != "unknown" else "failed"
    return report


def install_code(mock, context):
    if "patch" in mock:
        return PATCH_INSTALL % (mock["name"], mock["patch"], render(mock["value"], context, code=True))
    return render(mock["install"], context, code=True)


def restore_code(mock, context):
    if "patch" in mock:
        return PATCH_RESTORE % (mock["name"],)
    return render(mock["restore"], context, code=True)


def run_step(client, root, step, context, record):
    """执行一步并把结果写进 record；失败抛 StepFailed。"""
    kind = next(key for key in step if key in STEP_TYPES)
    record["type"] = kind
    if kind == "exec":
        result = client.run(render(step["exec"], context, code=True), f"步骤 {record['index']}")
        record.update(result_fields(result))
        if result["error"]:
            raise StepFailed(f"步骤 {record['index']} 客户端报错")
        if "save_as" in step:
            context["vars"][step["save_as"]] = result["ret"]
    elif kind == "assert":
        result = client.run(render(step["assert"], context, code=True), f"断言 {record['index']}")
        record.update(result_fields(result))
        if result["error"] or not result["ret"]:
            record["message"] = step.get("message", step["assert"])
            raise StepFailed(f"断言失败：{record['message']}")
    elif kind == "gm":
        command = render(step["gm"], context, code=False)
        record["command"] = command
        record["ret"] = clip(client.tool("execute_command", {"devid": client.devid, "command": command}))
    elif kind == "mcp":
        payload = client.tool(step["mcp"], render_args(step.get("args", {}), context))
        record["ret"] = clip(payload)
        if "save_as" in step:
            context["vars"][step["save_as"]] = payload
    elif kind == "wait_for":
        wait_for(client, step["wait_for"], context, record)
    elif kind == "exec_check":
        exec_check(client, root, step["exec_check"], context, record)


def result_fields(result):
    fields = {"ret": clip(result["ret"])}
    for key in ("error", "loginfo", "ui_events", "client_event"):
        if result.get(key):
            fields[key] = clip(result[key])
    return fields


def wait_for(client, spec, context, record):
    """在本机轮询客户端表达式直到为真；超时或表达式报错即失败。不在客户端主线程等待。"""
    args = spec.get("args", {})
    if "preset" in spec:
        record["preset"] = spec["preset"]
        expr = render(PRESET_INDEX[spec["preset"]], dict(context, args=args), code=True)
    else:
        expr = render(spec["expr"], context, code=True)
    timeout, interval = spec.get("timeout", 30), spec.get("interval", 0.5)
    deadline, polls = time.time() + timeout, 0
    while True:
        polls += 1
        # 只记录第一次轮询，避免 executed 被重复的轮询淹没
        result = client.run(expr, f"等待 {record['index']}") if polls == 1 else client_quiet(client, expr)
        if result["error"]:
            record.update(result_fields(result))
            raise StepFailed(f"等待条件报错（第 {polls} 次轮询）")
        if result["ret"]:
            record.update({"ret": clip(result["ret"]), "polls": polls})
            return
        if time.time() >= deadline:
            record.update({"ret": clip(result["ret"]), "polls": polls})
            raise StepFailed(f"等待超时（{timeout} 秒，{polls} 次轮询）：{expr}")
        time.sleep(interval)


def client_quiet(client, expr):
    """与 client.run 相同，但不追加 executed 记录（轮询的重复调用）。"""
    size = len(client.executed)
    try:
        return client.run(expr)
    finally:
        del client.executed[size:]


def exec_check(client, root, spec, context, record):
    """改动执行检查：目标行取自 diff_lines.collect，用 exec_trace.py 在一次调用里跑完 CASES。

    没执行到的行写进 record["missing"]，由 run_case 汇总到 unverified，不算失败；用例报错算失败。
    """
    import diff_lines  # 只有这一步需要 svn 和 3.11 的行号表，延迟导入
    rels = spec.get("files") or diff_lines.changed_py_files(root)
    collected = diff_lines.collect(root, rels)
    record["targets"] = {"total": collected["total"], "skipped": collected["skipped"], "warnings": collected["warnings"]}
    call = f"exec_check_start({collected['files']!r}, CASES)"
    trace, _ = template(EXEC_TRACE, call)
    code = trace + "\n" + render(spec["cases"], context, code=True) + "\n" + call
    log = f"<exec_trace.py 全文>\n{render(spec['cases'], context, code=True)}\n{call}"
    result = client.run(code, f"执行检查 {record['index']}", log)
    record.update(result_fields(result))
    ret = result["ret"] if isinstance(result["ret"], dict) else {}
    if result["error"] or "abort" in ret:
        raise StepFailed(f"执行检查没有运行：{result['error'] or ret.get('abort')}")
    record["missing"] = {path: lines for path, lines in ret.get("missing", {}).items() if lines}
    bad = {name: text for name, text in ret.get("results", {}).items() if text != "ok"}
    if bad:
        raise StepFailed(f"执行检查用例报错：{sorted(bad)}")


def finish(client, case, context, report, installed, baseline, watching, settle_default):
    """收尾：等待延迟回调，逆序还原 Mock，核对监听，结束报错收集。返回 restoration。

    每一项单独捕获失败，前一项失败不影响后一项；还原失败或无法核对的记为 unknown。
    """
    time.sleep(case.get("settle", settle_default))
    restored_all = True
    for mock in reversed(installed):
        entry = next((item for item in report["mocks"] if item["name"] == mock["name"]), None)
        if entry is None:
            entry = {"name": mock["name"]}
            report["mocks"].append(entry)
        try:
            result = client.run(restore_code(mock, context), f"还原 Mock {mock['name']}")
            ret = result["ret"]
            if "patch" in mock:
                # 安装在登记之前就失败（模块找不到、value 报错）时客户端没有任何改动，不需要还原
                never = entry.get("error") and isinstance(ret, dict) and ret.get("reason") == "没有安装记录"
                ok = not result["error"] and isinstance(ret, dict) and (ret.get("restored") or never)
            else:
                ok = not result["error"] and ret is True  # restore 代码最后一行要返回核对结果 True
            entry.update({"restore": clip(ret), "restore_error": result["error"], "restored": bool(ok)})
        except (mcp_http.McpError, OSError) as error:
            entry.update({"restore_error": f"{type(error).__name__}: {error}", "restored": False})
        restored_all = restored_all and entry["restored"]
    if baseline is not None:
        try:
            after = client.run(LISTENER_PROBE, "核对事件监听")
            grown = {name: [baseline.get(name, 0), count] for name, count in (after["ret"] or {}).items()
                     if count > baseline.get(name, 0)}
            if after["error"]:
                report["unverified"].append(f"核对事件监听失败：{after['error']}")
            elif grown:
                report["unverified"].append(f"事件监听比基线多（前后数量，可能是被测代码正常注册，也可能是 Mock 残留）：{grown}")
        except (mcp_http.McpError, OSError) as error:
            report["unverified"].append(f"核对事件监听失败：{error}")
    if watching:
        try:
            code, log = template(ERROR_WATCH, "error_watch_finish()")
            result = client.run(code, "结束报错收集", log)
            collected = result["ret"] if isinstance(result["ret"], dict) else {}
            report["errors"] = [item.get("text", str(item)) for item in collected.get("errors", [])]
            if collected.get("dropped"):
                report["unverified"].append(f"报错过多，另有 {collected['dropped']} 条被丢弃")
            if result["error"]:
                report["unverified"].append(f"结束报错收集失败：{result['error']}")
        except (mcp_http.McpError, OSError) as error:
            report["unverified"].append(f"结束报错收集失败，收集器可能仍挂在客户端上：{error}")
    for step in report["steps"]:
        for path, lines in step.get("missing", {}).items():
            report["unverified"].append(f"步骤 {step['index']} 执行检查未执行到：{path} {lines}")
    if not installed:
        return "not_needed"
    return "restored" if restored_all else "unknown"


def summarize(reports, blocked=None):
    """汇总为 test 结果字段（status／cases／errors／unverified／restoration）加明细。"""
    if blocked:
        return {"status": "blocked", "cases": [], "errors": [blocked], "unverified": [],
                "restoration": "not_needed", "results": [], "executed": []}
    restorations = {item["restoration"] for item in reports}
    restoration = ("unknown" if "unknown" in restorations else
                   "restored" if "restored" in restorations else "not_needed")
    return {
        "status": "passed" if all(item["status"] == "passed" for item in reports) else "failed",
        "cases": [f"{item['name']}：{item['status']}（{item['seconds']} 秒）"
                  + (f"，{item['failure']}" if item.get("failure") else "") for item in reports],
        "errors": [f"{item['name']}：{text}" for item in reports for text in item["errors"]],
        "unverified": [f"{item['name']}：{text}" for item in reports for text in item["unverified"]],
        "restoration": restoration,
        "results": reports,
    }


def run(root, devid, sources, settle=2.0, init=True):
    """校验全部用例后依次执行，返回汇总报告。用例文件有问题时不连接客户端，直接 blocked。"""
    cases = []
    try:
        for source in sources:
            cases += load_cases(source)
    except CaseError as error:
        return summarize([], str(error))
    problems = [f"{where}：{problem}" for where, case in cases for problem in validate(case)]
    if problems:
        return summarize([], "用例文件不合法：" + "；".join(problems))
    client = Client(devid)
    if init:
        try:
            client.tool("init_client", {"devid": devid})
        except (mcp_http.McpError, OSError) as error:
            report = summarize([], f"init_client 失败：{error}")
            report["executed"] = client.executed
            return report
    reports = [run_case(client, root, case, settle) for _, case in cases]
    report = summarize(reports)
    report["executed"] = client.executed
    return report


def save(root, report):
    directory = Path(root) / REPORT_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (time.strftime("%Y%m%d-%H%M%S") + ".json")
    path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description="真机用例执行器")
    sub = parser.add_subparsers(dest="command", required=True)
    runner = sub.add_parser("run", help="执行用例文件（.json）或 spec 中「测试用例」一节（.md）")
    runner.add_argument("--root", required=True, help="项目根目录（mhimage）")
    runner.add_argument("--devid", required=True)
    runner.add_argument("--settle", type=float, default=2.0, help="收尾前等待延迟回调的秒数，用例可用 settle 覆盖")
    runner.add_argument("--no-init", action="store_true", help="同一任务已调用过 init_client 时跳过")
    runner.add_argument("sources", nargs="+")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    report = run(root, args.devid, args.sources, args.settle, not args.no_init)
    report["report_path"] = str(save(root, report))
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return {"passed": 0, "failed": 1}.get(report["status"], 2)


if __name__ == "__main__":
    sys.exit(main())
