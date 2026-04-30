---
area: session
visibility: public
date: 2026-04-29
topic: Python async/await 深入理解
tags:
wiki_pages_touched: 
---
## 背景

用户粘贴了一篇关于 Python async/await 的技术文章，要求消化后存入 wiki。

## 关键讨论

- async/await 是 Python 3.5 引入的异步语法，核心四要素：coroutine、event loop、await、Task
- 常见陷阱：time.sleep() 阻塞事件循环、忘记 await 导致协程不执行、Task 被 GC 回收
- 最佳实践：asyncio.gather() 并发、asyncio.wait_for() 超时、使用 async 原生库（aiohttp、asyncpg）

## 结论

文章内容适合沉淀为 wiki 速查页，涵盖核心概念 + 常见陷阱 + 最佳实践。

## 产出物

- 新建 [[2-Wiki/编程语言/Python-async-await]]

## 后续

- 可补充 asyncio 与 threading 的对比
