# -*- coding: utf-8 -*-
"""mh-game-mcp HTTP 直连 execute_code 助手（从文件读多行代码，避开命令行转义/编码坑）

用法:
    python mcp_eval.py <code-file> [devid]

说明:
    - 多行代码写进 UTF-8 文件再执行，比拼 JSON 字符串可靠得多
    - 返回结构: result.ret（最后一行表达式的值）/ result.error（异常栈）/ loginfo（print 输出）
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

with io.open(sys.argv[1], "r", encoding="utf-8") as f:
	code = f.read()
devid = sys.argv[2] if len(sys.argv) > 2 else ""
assert devid, "usage: python mcp_eval.py <code-file> <devid>"

res = post({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
	"name": "execute_code", "arguments": {"devid": devid, "code": code, "need_loginfo": True}}})
print(json.dumps(res.get("result") or res.get("error"), ensure_ascii=False, indent=1))
