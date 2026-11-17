# -*- coding: utf-8 -*-
"""并行运行本 skill 的测试（只依赖标准库和 pytest）。

    python -B tests/run.py            # 全量，按测试拆到多个进程并行
    python -B tests/run.py --fast     # 跳过真实 svn 的测试（MHXY_TEST_SKIP_SVN=1），改动不涉及 SVN 时用
    python -B tests/run.py -k merge   # 额外参数原样传给每个 pytest 进程

先收集全部测试 ID，再轮流分给各进程，让同一文件里的慢测试分散开。各测试本来就用独立的临时目录，
可以并行。退出码：0 全部通过；1 有失败或收集失败。
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
BASE = [sys.executable, "-B", "-m", "pytest", "-p", "no:cacheprovider"]
FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)
MAX_ARGS_CHARS = 24000  # Windows 命令行上限 32767，留出余量。


def run(args, env):
    completed = subprocess.run(args, cwd=ROOT, env=env, capture_output=True, creationflags=FLAGS)
    output = (completed.stdout + completed.stderr).decode("utf-8", "replace")
    return completed.returncode, output


def collect(env, extra):
    code, output = run([*BASE, "--collect-only", "-q", *extra, "tests"], env)
    ids = [line.strip() for line in output.splitlines() if "::" in line and not line.startswith(" ")]
    if code not in (0, 5):
        sys.stdout.write(output)
        raise SystemExit(1)
    return ids


def shard(ids, workers):
    """轮流分配；某个分片的命令行过长时再拆开。"""
    shards = [ids[index::workers] for index in range(workers)]
    result = []
    for part in shards:
        chunk, size = [], 0
        for test_id in part:
            if chunk and size + len(test_id) + 3 > MAX_ARGS_CHARS:
                result.append(chunk)
                chunk, size = [], 0
            chunk.append(test_id)
            size += len(test_id) + 3
        if chunk:
            result.append(chunk)
    return result


def summary_line(output):
    lines = [line for line in output.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fast", action="store_true", help="跳过真实 svn 的测试")
    parser.add_argument("--workers", type=int, default=min(os.cpu_count() or 4, 16), help="并行进程数")
    args, extra = parser.parse_known_args(argv)
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"}
    if args.fast:
        env["MHXY_TEST_SKIP_SVN"] = "1"
    started = time.monotonic()
    ids = collect(env, extra)
    if not ids:
        print("没有收集到测试")
        return 1
    shards = shard(ids, max(1, min(args.workers, len(ids))))
    with ThreadPoolExecutor(max_workers=len(shards)) as pool:
        results = list(pool.map(lambda part: run([*BASE, "-q", *extra, *part], env), shards))
    failed = [(code, output) for code, output in results if code not in (0, 5)]
    for code, output in failed:
        sys.stdout.write(output)
        sys.stdout.write("\n")
    for index, (code, output) in enumerate(results, 1):
        print(f"[{index}/{len(results)}] {summary_line(output)}")
    elapsed = time.monotonic() - started
    mode = "快速（跳过真实 svn）" if args.fast else "全量"
    print(f"{mode}：{len(ids)} 个测试，{len(shards)} 个进程，{'有失败' if failed else '全部通过'}，用时 {elapsed:.0f} 秒")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
