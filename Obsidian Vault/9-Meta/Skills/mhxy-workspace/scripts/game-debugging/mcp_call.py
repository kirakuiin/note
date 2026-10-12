# -*- coding: utf-8 -*-
"""mh-game-mcp HTTP 直连调用助手（MCP 工具未注册时的兜底通道）

用法:
    echo '{"ip":""}' | python mcp_call.py get_devices_by_ip
    '{"devid":"xxx","command":"$at fightN 5"}' | python mcp_call.py execute_command

说明:
    - mh-game-mcp 为无状态 streamableHttp 服务，直接 POST JSON-RPC 即可，无需 session id
    - JSON 参数从 stdin 读取（PowerShell 管道会带 BOM/转义问题，stdin + utf-8-sig 最稳）
"""
import json, sys, io, urllib.request

URL = "https://mh-game-mcp.eros.nie.netease.com/mcp"

def post(payload):
	req = urllib.request.Request(
		URL, data=json.dumps(payload).encode("utf-8"),
		headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"})
	with urllib.request.urlopen(req, timeout=300) as r:
		body = r.read().decode("utf-8")
	for line in body.splitlines():
		if line.startswith("data: "):
			return json.loads(line[6:])
	return {"raw": body}

post({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {
	"protocolVersion": "2024-11-05", "capabilities": {},
	"clientInfo": {"name": "claude-code-cli", "version": "1.0"}}})
post({"jsonrpc": "2.0", "method": "notifications/initialized"})

tool = sys.argv[1]
stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8-sig", errors="replace")
args = json.loads(stdin.read()) if not sys.stdin.isatty() else {}
res = post({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
			"params": {"name": tool, "arguments": args}})
print(json.dumps(res.get("result") or res.get("error"), ensure_ascii=False, indent=1))
