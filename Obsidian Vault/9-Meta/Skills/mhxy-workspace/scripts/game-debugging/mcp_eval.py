# -*- coding: utf-8 -*-
"""mh-game-mcp HTTP 直连 execute_code 助手（从文件读多行代码，避开命令行转义/编码坑）

用法:
    python mcp_eval.py <code-file> <devid>

说明:
    - 多行代码写进 UTF-8 文件再执行，比拼 JSON 字符串可靠得多
    - 返回结构: result.ret（最后一行表达式的值）/ result.error（异常栈）/ loginfo（print 输出）
    - 退出码：0 成功取到 result；1 参数错误、返回 JSON-RPC error 或响应无法识别（见 mcp_http.call_tool）
"""
import io
import sys

import mcp_http


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2 or not argv[1]:
        print("usage: python mcp_eval.py <code-file> <devid>", file=sys.stderr)
        return 1
    try:
        with io.open(argv[0], "r", encoding="utf-8-sig") as f:
            code = f.read()
    except OSError as error:
        print(f"无法读取代码文件：{error}", file=sys.stderr)
        return 1
    return mcp_http.call_tool("execute_code", {"devid": argv[1], "code": code, "need_loginfo": True})


if __name__ == "__main__":
    sys.exit(main())
