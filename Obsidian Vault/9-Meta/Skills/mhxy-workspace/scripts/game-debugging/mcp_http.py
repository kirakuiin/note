# -*- coding: utf-8 -*-
"""mh-game-mcp HTTP 直连的公共部分：握手、调用工具、解析响应。供 mcp_call.py 和 mcp_eval.py 导入。

mh-game-mcp 为无状态 streamableHttp 服务，直接 POST JSON-RPC 即可，无需 session id。
响应可能是普通 JSON，也可能是 SSE（多个 ``data:`` 事件，其中可能夹带通知或进度）。
"""
import json
import sys
import urllib.request

URL = "https://mh-game-mcp.eros.nie.netease.com/mcp"
TIMEOUT = 300  # 秒；execute_code 可能执行较久
INIT_ID, CALL_ID = 0, 1


def post(payload):
    """POST 一条 JSON-RPC 消息，返回响应正文（UTF-8 文本，通知的响应可能为空）。"""
    req = urllib.request.Request(
        URL, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read().decode("utf-8")


def find_response(body, request_id):
    """从响应正文中取出 id 为 request_id 的 JSON-RPC 响应；找不到返回 None。

    普通 JSON 正文直接解析（可以是单条消息或批量数组）；否则按 SSE 逐个检查 ``data:`` 事件，
    跳过通知、进度等 id 不符或无法解析的事件。
    """
    try:
        candidates = [json.loads(body)]
    except ValueError:
        candidates = []
        for line in body.splitlines():
            if line.startswith("data:"):
                try:
                    candidates.append(json.loads(line[5:].strip()))
                except ValueError:
                    continue
    for message in candidates:
        for item in message if isinstance(message, list) else [message]:
            if isinstance(item, dict) and item.get("id") == request_id and ("result" in item or "error" in item):
                return item
    return None


def call_tool(name, arguments):
    """握手后调用一个工具，把结果打印到 stdout，返回退出码。

    握手不能代替 init_client。

    Returns:
        0：打印了 result；1：打印了 JSON-RPC error，或响应里找不到对应 id 的结果（此时打印原始正文）。
    """
    body = post({"jsonrpc": "2.0", "id": INIT_ID, "method": "initialize", "params": {
        "protocolVersion": "2024-11-05", "capabilities": {},
        "clientInfo": {"name": "claude-code-cli", "version": "1.0"}}})
    if find_response(body, INIT_ID) is None:
        return report_raw("initialize", body)
    post({"jsonrpc": "2.0", "method": "notifications/initialized"})

    body = post({"jsonrpc": "2.0", "id": CALL_ID, "method": "tools/call",
                 "params": {"name": name, "arguments": arguments}})
    response = find_response(body, CALL_ID)
    if response is None:
        return report_raw("tools/call", body)
    key = "result" if "result" in response else "error"
    print(json.dumps(response[key], ensure_ascii=False, indent=1))
    return 0 if key == "result" else 1


def report_raw(method, body):
    """响应无法识别时打印原始正文，返回退出码 1。"""
    print(f"{method} 的响应中没有 result 或 error，原始内容如下：", file=sys.stderr)
    print(body)
    return 1
