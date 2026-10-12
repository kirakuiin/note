"""客户端报错收集模板的测试：在本机 Python 中运行，模拟客户端的 MHXY logger。"""
import importlib.util
import logging
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
PATH = Path(__file__).resolve().parents[1] / "scripts" / "game-debugging" / "error_watch.py"
spec = importlib.util.spec_from_file_location("error_watch", PATH)
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)

LOGGER = logging.getLogger("MHXY")
STATE_ATTR = "_error_watch_collector"


class ErrorWatchTests(unittest.TestCase):
    def setUp(self):
        self.handlers = list(LOGGER.handlers)
        self.addCleanup(w.error_watch_finish)  # 失败时也卸载，避免影响其他测试

    def test_collects_error_records_until_finish(self):
        self.assertEqual(w.error_watch_start(), {"started": True, "stale": None})
        LOGGER.error("first")
        try:
            raise RuntimeError("later")
        except RuntimeError:
            LOGGER.exception("in callback")  # 模拟之后几帧才执行的回调报错
        LOGGER.warning("warning is ignored")
        result = w.error_watch_finish()
        texts = [r["text"] for r in result["errors"]]
        self.assertEqual(len(texts), 2)
        self.assertEqual(texts[0], "first")
        self.assertIn("RuntimeError: later", texts[1])
        self.assertEqual(result["dropped"], 0)
        self.assertEqual(LOGGER.handlers, self.handlers)
        self.assertFalse(hasattr(LOGGER, STATE_ATTR))
        self.assertEqual(w.error_watch_finish()["note"], "没有正在进行的收集")

    def test_start_replaces_stale_collector(self):
        w.error_watch_start()
        LOGGER.error("left over")
        result = w.error_watch_start()
        self.assertEqual([r["text"] for r in result["stale"]["errors"]], ["left over"])
        self.assertEqual(len(LOGGER.handlers), len(self.handlers) + 1)  # 旧的已卸载，只剩新的
        LOGGER.error("fresh")
        self.assertEqual([r["text"] for r in w.error_watch_finish()["errors"]], ["fresh"])

    def test_limits_record_count(self):
        w.error_watch_start()
        for i in range(55):
            LOGGER.error("e%d", i)
        result = w.error_watch_finish()
        self.assertEqual(len(result["errors"]), 50)
        self.assertEqual(result["dropped"], 5)

    def test_runs_like_execute_code(self):
        # execute_code 用分开的 globals／locals 执行，顶层名字对函数不可见
        source = PATH.read_text(encoding="utf-8")

        def run(call):
            scope_globals, scope_locals = {"__builtins__": __builtins__}, {}
            exec(source, scope_globals, scope_locals)
            return eval(call, scope_globals, scope_locals)

        self.assertTrue(run("error_watch_start()")["started"])
        LOGGER.error("between calls")
        self.assertEqual([r["text"] for r in run("error_watch_finish()")["errors"]], ["between calls"])


if __name__ == "__main__":
    unittest.main()
