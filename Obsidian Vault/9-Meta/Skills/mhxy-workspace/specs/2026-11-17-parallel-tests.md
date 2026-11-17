# 测试并行与快速档

日期：2026-11-17　版本：0.3.57

## 目标

skill 全量测试（608 个）串行约 380 秒，最慢的 40 个约 220 秒都是真实调用 svn 的测试（`tests/svn_fixture.py` 每个测试新建 file:// 仓库再 import/copy/checkout/commit）。目标：全量降到 2 分钟以内，并提供只跑非 svn 测试的快速档。

## 做法

- 并行用 pytest-xdist（用户 2026-11-17 自行安装，认可用第三方插件代替自写调度）：`-n auto --dist worksteal`。xdist 只是测试依赖，脚本本身仍只依赖标准库。曾试过自写的 `tests/run.py`（收集后按 ID 轮流分到 16 个子进程，95 秒），改用 xdist 后删除。
- 快速档：`tests/conftest.py` 新增 `--skip-svn` 选项，在 `pytest_configure` 里设置 `MHXY_TEST_SKIP_SVN=1`（xdist 的 worker 各自执行一次）；`svn_fixture.AVAILABLE` 在该变量非空且不为 0 时为假，`requires_svn` 标记的测试跳过。
- 原先自带 `skipUnless(shutil.which("svn"))` 的三处真实 svn 测试改用 `svn_fixture.requires_svn`，一并纳入开关：`test_precommit.py`（属性改动后的 review 标记）、`test_svn_commit.py::LocalRepositoryTests`、`test_workspace.py`（真实工作副本的 merge_pending 检测）。
- 并行下暴露的时序问题（不改被测行为，只放宽测试的等待余量）：`test_codex_cli.py` 的探针默认静默上限 0.4 秒，20 个 worker 并发时子进程 Python 启动就会超过，`test_output_refreshes_idle_and_records_session` 被误判超时。改为静默上限 3 秒、每 0.8 秒输出一次共 5 次（总时长仍超过上限，依旧能证明输出刷新计时）；`test_cancel_stops_process` 的静默上限也放宽到 60 秒，保证取消先于超时。
- 未发现固定路径、环境变量或 `~/.mhxy-workspace` 等共享状态冲突；各测试本来就用独立临时目录。
- `SKILL.md`「维护本 skill」：测试命令改为 xdist 全量和 `--skip-svn` 快速档，保留串行写法用于单文件调试或没有 xdist 时，并写明新测试的并行约束。

## 用时（本机 20 核）

| 方式 | 结果 | 用时 |
| --- | --- | --- |
| 串行全量（改动前） | 608 通过 | 约 380 秒 |
| 串行 + 跳过 svn | 554 通过、54 跳过 | 150 秒 |
| 自写调度 `run.py`，16 进程 | 608 通过 | 95 秒 |
| xdist `--dist load` | 608 通过 | 88 秒 |
| xdist `--dist worksteal`（采用） | 608 通过 | 78–83 秒 |
| xdist worksteal + `--skip-svn`（采用） | 554 通过、54 跳过 | 37 秒 |

## 限制

- 需要安装 pytest-xdist；没有时去掉 `-n auto --dist worksteal` 串行运行。
- 快速档跳过的只是真实调用 svn 的测试；`test_workspace.py` 等仍会起 Python／svn 子进程（例如对非工作副本运行 `svn info`），这部分串行约 150 秒，是快速档剩余的主要耗时。
- 未做“同一测试类复用 svn 仓库模板”的优化：并行后已达目标，留作以后需要时再做（优先 `test_svn_merge.py`）。
