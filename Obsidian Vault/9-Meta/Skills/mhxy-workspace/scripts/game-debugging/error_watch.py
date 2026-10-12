# -*- coding: utf-8 -*-
"""客户端报错收集模板：在一段客户端操作期间收集 ERROR 级别的日志记录（含堆栈）。

不在本机运行。用法见 references/game-debugging.md「收集客户端报错」：读取本文件全文，后面追加
一次调用，整体作为 execute_code 的 code 发送。

- ``error_watch_start()``：在名为 MHXY 的 logging logger 上挂一个内存 handler。客户端 log.py 的
  所有日志都经过这个 logger，异步回调里未捕获的异常也会被记录到这里。
- ``error_watch_finish()``：返回收集到的记录并卸载 handler。

execute_code 用分开的 globals／locals 执行代码，顶层定义的名字对函数不可见。所以两个函数各自
自包含，不引用本文件的其他顶层名字；它们共用的约定（logger 名、状态属性名）在两处保持一致。
状态保存在 logger 对象的 _error_watch_collector 属性中，finish 时删除。只依赖标准库；客户端为 Python 3.11。
"""


def error_watch_start():
    """开始收集报错。

    上一次的收集器没有卸载（例如上次中断）时，先卸载它，并把它已收集的记录放在 stale 中返回。

    Returns:
        {"started": True, "stale": None 或 {"errors": [...], "dropped": 条数, "seconds": 时长}}
    """
    import logging
    import time

    logger = logging.getLogger("MHXY")  # 与 error_watch_finish 一致
    state_attr = "_error_watch_collector"  # 与 error_watch_finish 一致
    record_limit, text_limit = 50, 2000  # 最多保留的记录条数；每条记录保留的末尾字符数

    stale = getattr(logger, state_attr, None)
    if stale is not None:
        logger.removeHandler(stale)
        delattr(logger, state_attr)
        stale = {"errors": stale.records, "dropped": stale.dropped, "seconds": round(time.time() - stale.started, 2)}

    class Collector(logging.Handler):
        """收集 ERROR 及以上日志记录的临时 handler。"""

        def __init__(self):
            super().__init__(logging.ERROR)
            self.started = time.time()
            self.records = []
            self.dropped = 0

        def emit(self, record):
            if len(self.records) >= record_limit:
                self.dropped += 1
                return
            try:
                text = self.format(record)
            except Exception as error:  # 格式化失败也要留下痕迹，不能吞掉
                text = f"{record.levelname} {record.getMessage()!r}（格式化失败：{error!r}）"
            self.records.append({"time": round(record.created - self.started, 2), "text": text[-text_limit:]})

    collector = Collector()
    logger.addHandler(collector)
    setattr(logger, state_attr, collector)
    return {"started": True, "stale": stale}


def error_watch_finish():
    """返回收集到的报错并卸载收集器。

    Returns:
        {"errors": [{"time": 距开始秒数, "text": 记录全文}], "dropped": 超出上限丢弃的条数,
         "seconds": 收集时长}；没有正在收集时返回 {"errors": [], "note": "没有正在进行的收集"}。
    """
    import logging
    import time

    logger = logging.getLogger("MHXY")  # 与 error_watch_start 一致
    state_attr = "_error_watch_collector"  # 与 error_watch_start 一致
    collector = getattr(logger, state_attr, None)
    if collector is None:
        return {"errors": [], "note": "没有正在进行的收集"}
    logger.removeHandler(collector)
    delattr(logger, state_attr)
    return {"errors": collector.records, "dropped": collector.dropped,
            "seconds": round(time.time() - collector.started, 2)}
