"""HTTP 保底脚本的隔离测试：urlopen 替换为假响应，不连接真实服务。"""
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
DIRECTORY = Path(__file__).resolve().parents[1] / "scripts" / "game-debugging"
sys.path.insert(0, str(DIRECTORY))  # 与直接运行脚本时一样，脚本目录在 sys.path 上


def load(name):
    spec = importlib.util.spec_from_file_location(name, DIRECTORY / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


h = load("mcp_http")
call = load("mcp_call")
evaluate = load("mcp_eval")
call.mcp_http = evaluate.mcp_http = h  # 让脚本和测试用同一个模块对象，patch 才能生效

INIT_OK = json.dumps({"jsonrpc": "2.0", "id": 0, "result": {}})


class FakeServer:
    """按顺序返回预设正文，并记录收到的请求。"""

    def __init__(self, *bodies):
        self.bodies, self.requests = list(bodies), []

    def __call__(self, req, timeout):
        self.requests.append(json.loads(req.data))
        return io.BytesIO(self.bodies.pop(0).encode("utf-8"))


class FindResponseTests(unittest.TestCase):
    def test_plain_json(self):
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"ret": 2}})
        self.assertEqual(h.find_response(body, 1)["result"], {"ret": 2})

    def test_sse_skips_notifications_and_other_ids(self):
        body = "\n".join([
            "event: message",
            'data: {"jsonrpc":"2.0","method":"notifications/progress","params":{"progress":1}}',
            "",
            'data: {"jsonrpc":"2.0","id":0,"result":{"old":true}}',
            "",
            "data: not json",
            'data:{"jsonrpc":"2.0","id":1,"error":{"code":-1,"message":"bad"}}',
        ])
        self.assertEqual(h.find_response(body, 1)["error"]["message"], "bad")

    def test_missing_returns_none(self):
        self.assertIsNone(h.find_response("<html>502</html>", 1))
        self.assertIsNone(h.find_response('{"jsonrpc":"2.0","id":1}', 1))


class CallToolTests(unittest.TestCase):
    def run_tool(self, server, *args):
        out, err = io.StringIO(), io.StringIO()
        with patch.object(h.urllib.request, "urlopen", server), patch("sys.stdout", out), patch("sys.stderr", err):
            code = h.call_tool(*args)
        return code, out.getvalue(), err.getvalue()

    def test_prints_result(self):
        server = FakeServer(INIT_OK, "", 'data: {"jsonrpc":"2.0","id":1,"result":{"content":[]}}\n')
        code, out, _ = self.run_tool(server, "init_client", {"devid": "d"})
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), {"content": []})
        self.assertEqual(server.requests[2]["params"], {"name": "init_client", "arguments": {"devid": "d"}})

    def test_error_exits_non_zero(self):
        server = FakeServer(INIT_OK, "", json.dumps({"jsonrpc": "2.0", "id": 1, "error": {"message": "x"}}))
        code, out, _ = self.run_tool(server, "t", {})
        self.assertEqual((code, json.loads(out)), (1, {"message": "x"}))

    def test_unrecognized_body_prints_raw_and_exits_non_zero(self):
        code, out, err = self.run_tool(FakeServer(INIT_OK, "", "Bad Gateway"), "t", {})
        self.assertEqual(code, 1)
        self.assertIn("Bad Gateway", out)
        self.assertIn("tools/call", err)

    def test_failed_handshake_stops_before_call(self):
        server = FakeServer("oops")
        code, out, _ = self.run_tool(server, "t", {})
        self.assertEqual((code, len(server.requests)), (1, 1))
        self.assertIn("oops", out)


class ScriptArgumentTests(unittest.TestCase):
    """参数错误要在联网前发现。"""

    def setUp(self):
        for patcher in (patch.object(h.urllib.request, "urlopen", side_effect=AssertionError("不应联网")),
                        patch("sys.stderr", io.StringIO())):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_eval_requires_devid(self):
        self.assertEqual(evaluate.main(["code.py"]), 1)
        self.assertEqual(evaluate.main(["code.py", ""]), 1)

    def test_eval_missing_file(self):
        self.assertEqual(evaluate.main(["no/such/file.py", "dev"]), 1)

    def test_eval_sends_code(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "c.py"
            path.write_bytes("﻿print('中')\n1".encode("utf-8"))
            with patch.object(h, "call_tool", return_value=0) as call_tool:
                self.assertEqual(evaluate.main([str(path), "dev"]), 0)
        call_tool.assert_called_once_with("execute_code", {"devid": "dev", "code": "print('中')\n1", "need_loginfo": True})

    def test_call_rejects_bad_arguments(self):
        self.assertEqual(call.main([]), 1)
        for raw in (b"{bad", b"[1]"):
            with patch("sys.stdin", io.TextIOWrapper(io.BytesIO(raw), encoding="utf-8")):
                self.assertEqual(call.main(["t"]), 1)

    def test_call_reads_bom_json(self):
        stdin = io.TextIOWrapper(io.BytesIO(b'\xef\xbb\xbf{"ip": ""}'), encoding="utf-8")
        with patch("sys.stdin", stdin), patch.object(h, "call_tool", return_value=0) as call_tool:
            self.assertEqual(call.main(["get_devices_by_ip"]), 0)
        call_tool.assert_called_once_with("get_devices_by_ip", {"ip": ""})


if __name__ == "__main__":
    unittest.main()
