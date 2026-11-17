# 复用目录检出：协议不一致和入口文件冲突

日期：2026-11-17　版本：0.3.52

## 问题（2026-11-17 复用 magicbuff 目录检出 wzw_2026_11_17_zyl_hard 时遇到）

- `_test` 旧工作副本是 `https://` 检出，新分支资源是 `svn://`。`cross_repository_folders` 按 UUID 判断为同一仓库，计划直接 switch；`svn switch` 要求仓库根 URL 完全一致，报 E155025。手动 `svn relocate` 后 switch 成功。
- `mhimage\AGENTS.md` 在 ignore-on-commit 里，本地修改只有受管区段；`inspect_reuse` 通过 `local_only` 放行，`switch --force` 合并时和新分支末尾的改动冲突。

## 改动（scripts/branch.py）

- `relocations(reuse, urls, replace)`：对 mhimage 和要 switch 的资源目录比较本地与目标的 `repos-root-url`；不同且 `repos-uuid` 相同时返回 `{目录: (本地根, 目标根)}`。UUID 不同的不处理（资源目录仍由 `cross_repository_folders` 挪开重检）。
- `entry_file_steps(reuse)`：逐个检查 `mhimage/AGENTS.md`、`CLAUDE.md` 的 svn 状态。
  - 无修改：跳过。
  - `M`：`svn cat -r BASE` 与当前内容各自去掉受管区段（统一 CRLF/LF、忽略末尾空白）后相同 → `svn revert`；不同 → 拒绝。
  - `?`：去掉受管区段后为空 → 计划删除（记录 sha256，执行时不一致就停止）；否则拒绝。
  - 其他状态（C、A、D 等）→ 拒绝。
- `checkout_plan`：每个 switch 的目录顺序为 cleanup → relocate（需要时）→ 入口文件还原/删除（仅 mhimage）→ switch。
- 预览新增 `checks.relocated_working_copies`、`checks.entry_files_reset`；有入口文件步骤时警告“检出后需要初始化（sync）才会恢复入口规则”。
- 新增步骤类型 `remove_entry`。

## 文档

`references/branch.md`「检出到本地」第 2 步补充 relocate 和入口文件处理。

## 验收

- 单元测试 `tests/test_branch_reuse_switch.py`：协议不同生成 relocate；根相同或 UUID 不同不 relocate；只差受管区段时 revert 在 switch 前；BASE 里已有旧区段仍算只差区段；区段外改动、冲突状态拒绝；未纳管只含区段时删除、预览后改动拒绝删除；未纳管有其他内容拒绝；未修改不生成步骤。
- `tests/test_branch.py`、`tests/test_branch_reuse_clean.py` 原有用例通过（`test_same_directory_reuse_previews_and_executes` 补 mock `svn_info`，避免真实查询仓库根）。
- 真实工作副本只读核对：`D:\workspace\trunk` 的 mhimage（https）对 svn:// 目标计划 relocate；已切到 svn:// 的新分支目录不计划。
