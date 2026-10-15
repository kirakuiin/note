# -*- coding: utf-8 -*-
"""mh-game-mcp HTTP 直连调用助手（MCP 工具未注册时的兜底通道）

用法（Bash 语法；JSON 参数写进 UTF-8 文件，从 stdin 重定向读取）:
    python mcp_call.py get_devices_by_ip < args.json        # args.json: {"ip":""}
    python mcp_call.py execute_command < args.json          # args.json: {"devid":"xxx","command":"$at fightN 5"}

说明:
    - 不要用 PowerShell 管道传 JSON（会带 BOM／转义问题）；文件 + stdin 重定向 + utf-8-sig 最稳
    - 没有 stdin 输入时参数为 {}
    - 退出码：0 成功取到 result；1 参数错误、返回 JSON-RPC error 或响应无法识别（见 mcp_http.call_tool）
"""
import io
import json
import sys

import mcp_http


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("usage: python mcp_call.py <工具名> < <UTF-8参数.json>", file=sys.stderr)
        return 1
    if sys.stdin.isatty():
        args = {}
    else:
        text = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8-sig", errors="replace").read()
        try:
            args = json.loads(text) if text.strip() else {}
        except ValueError as error:
            print(f"参数不是合法 JSON：{error}", file=sys.stderr)
            return 1
    if not isinstance(args, dict):
        print("参数必须是 JSON 对象", file=sys.stderr)
        return 1
    return mcp_http.call_tool(argv[0], args)


if __name__ == "__main__":
    sys.exit(main())
