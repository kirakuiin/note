# -*- coding: utf-8 -*-
"""改动执行检查的客户端模板：在客户端内追踪目标行并逐个运行用例。

不在本机运行。用法见 references/exec-check.md「执行」：与 scripts/game-debugging/error_watch.py 一起
作为 execute_code 的 code 发送，报错收集由 error_watch 负责，本文件只做行追踪。

execute_code 用分开的 globals／locals 执行代码，顶层定义的名字对函数不可见。所以本函数自包含，
用例函数也要在内部 import 需要的模块。只依赖标准库；客户端为 Python 3.11。
"""


def exec_check_start(targets, cases):
    """运行用例并统计目标行。

    Args:
        targets: {相对路径: [行号]}，取自 diff_lines.py 输出的 files；按完整路径段的后缀匹配代码对象的文件名。
        cases: [(名称, 无参函数)]。每个用例单独捕获异常；用例负责在 finally 中恢复自己改动的状态。

    Returns:
        {"results": {名称: "ok" 或堆栈}, "covered": {路径: "已执行/总数"}, "missing": {路径: [未执行行]}}；
        已有其他追踪器（调试器或网站覆盖率采集）时返回 {"abort": 原因}，不运行任何用例。
    """
    import sys
    import traceback

    text_limit = 2000  # 每个用例堆栈保留的末尾字符数
    if sys.gettrace() is not None:
        return {"abort": f"已有追踪器 {sys.gettrace()!r}，不要同时运行（可能是调试器或网站覆盖率采集）"}

    keys = {path.replace("\\", "/").lower(): set(lines) for path, lines in targets.items()}
    hits = {key: set() for key in keys}
    matched = {}

    def match(code):
        # 不能假定 local 收到的代码对象一定先经过 tracer：缓存未命中时现场判断
        if code not in matched:
            name = code.co_filename.replace("\\", "/").lower()
            # 后缀必须落在路径分隔符上：ui/main.py 不能匹配 newui/main.py
            matched[code] = next((key for key in keys if name == key or name.endswith("/" + key)), None)
        return matched[code]

    def local(frame, event, arg):
        if event == "line":
            key = match(frame.f_code)
            if key is not None:
                hits[key].add(frame.f_lineno)
        return local

    def tracer(frame, event, arg):
        key = match(frame.f_code)
        if key is None:
            return None
        hits[key].add(frame.f_code.co_firstlineno)  # def 行在调用时没有 line 事件
        return local

    results = {}
    sys.settrace(tracer)
    try:
        for name, case in cases:
            try:
                case()
                results[name] = "ok"
            except Exception:
                results[name] = traceback.format_exc()[-text_limit:]
    finally:
        sys.settrace(None)
    return {"results": results,
            "covered": {key: f"{len(keys[key] & hits[key])}/{len(keys[key])}" for key in keys},
            "missing": {key: sorted(keys[key] - hits[key]) for key in keys}}
