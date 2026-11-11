# SVN 更新

仅在用户明确要求更新 SVN 工作副本时读取并执行。初始化、更新 skill 配置、普通开发或只读查看 SVN 状态均不触发。更新用本 skill 的脚本完成，不手写 `svn update`／`svn switch`：

```text
python "<skill>/scripts/svn_update.py" --root "<项目>" [--code-only] [--clean-blockers] [--dry-run]
```

用户已明确要求更新时直接运行，不另行确认，也不需要先 `--dry-run`。资源工作副本很大，命令可能要几分钟，放到后台等待完成。脚本只需要 Python 标准库和本机 svn，不需要模型参与，其他程序（如 popo-agent-service）可以直接调用。

## 范围

- 更新 `--root` 指向的代码工作副本，以及它上层的 `../_test`（当前分支的资源，与代码分开更新容易不一致）。用户本次说只更新代码时加 `--code-only`。`../_test` 不存在或不是独立的工作副本时跳过并在 `resource_skipped` 说明，不自动 checkout。不纳入引擎、全局资源或其他工作副本。
- 要求 `--root` 是已初始化的工作区（备份放在它的 `.mhxy-workspace/` 下）。
- 不靠本地文件夹名称判断分支，一律以 `svn info` 的实际 URL 为准。

## 选择目标

- **周期分支**：实际代码 URL 符合 `wzimage/branchs/<年份>_ship/<类型>_YYYY_MM_DD`（类型见 `workspace.py` 的 `PERIODIC_TYPES`）时，尽量更新到下一个维护周。context 输出的 `branch.kind` 按同一规则判定（`workspace.py` 的 `PERIODIC_BRANCH`）。
  - 目标日期为本地日期之后最近的周二；周二当天取下周二，跨年使用目标日期所属年份。
  - 用 `svn list` 确认真实远端分支，保持仓库与前缀不变。目标日期的分支存在就 `svn switch` 过去；已经在目标 URL 时直接 `svn update`。
  - 目标分支尚未发布时，在同类型已发布分支中选不晚于目标日期、不早于当前分支日期的最新一个；没有更新的候选就保持当前 URL 执行 `svn update`，并在 `target.reason` 说明未到达目标维护周。不退回旧周，也不跳到更远的周。无法列出远端时该工作副本失败并报告原因，不把网络或权限失败当作分支不存在。
- **其他工作副本**：trunk、开发分支及不匹配上述规则的目录，保持当前 URL，直接 `svn update`。
- `../_test` 保持其当前 URL 执行 `svn update`，不根据代码日期切换资源分支。

## 挡路内容的处理

挡住更新的内容由脚本自动处理，不询问用户；处理前先备份到 `<项目>/.mhxy-workspace/backups/<时间>/<工作副本名>/`，只保留最近 5 次：

- `local-changes.patch`：更新前全部本地修改的 `svn diff`（有本地修改就备份，不论是否冲突）。
- `files/<相对路径>`：被换掉或挪走的文件原样保存一份（patch 不含二进制内容和未纳管文件）。

**默认**（不带开关）——只动挡路的内容，不冲突的本地修改保留：

| 情况 | 处理 |
| --- | --- |
| 工作副本被锁 | `svn cleanup` 后继续 |
| 更新产生文本／属性冲突（含更新前就存在的冲突） | 采用服务器版本（`theirs-full`），本地版本在备份里 |
| 树冲突（如本地改了、服务器删了；未纳管目录挡住服务器新增的文件） | 还原本地一侧，跟随服务器，本地内容在备份里 |
| 未纳管文件挡住服务器新增的同名文件 | 内容不同：本地文件存进备份，换成服务器版本；内容相同：直接纳管，不算挡路 |

每一项都是先备份成功再动手，中途任何一步失败就放弃这一项：本地内容保持原样，路径留在 `conflicts` 里并在 `errors` 说明，该工作副本记为失败，由用户手动处理。不自动处理的情况：路径是符号链接或目录联接（无法可靠备份）；入口文件、`.claude/`、`.mhxy-workspace/` 上的树冲突。

**`--clean-blockers`**（维护流程用）——备份后把全部本地修改 revert，再更新或切换；其余同上。revert 新增的文件后，文件留在原地成为未纳管文件。

两种方式都不动：`AGENTS.md`、`CLAUDE.md`、`.claude/`、`.mhxy-workspace/` 和其余未纳管文件。例外：`AGENTS.md` 更新时冲突会采用服务器版本，受管区段随之丢失，脚本随即重新 sync 写回并在 `notes` 说明；写回失败时报错，按提示重新 sync。

## 结果

输出 JSON，退出码 0 全部成功、2 部分完成、1 代码工作副本失败或参数错误：

- `status`：`success`／`partial`／`failed`（`--dry-run` 为 `planned`）；`mode`：`default`／`clean-blockers`；`backup_dir`：本次备份目录，没有备份时为 null。
- `working_copies` 每项：`name`、`path`、`before`／`after`（`url`、`branch`、`revision`）、`target`（`url`、`branch`、`reason`）、`operation`（`update`／`switch`）、`status`（`updated`／`partial`／`failed`，`--dry-run` 为 `planned`）、`local_changes`（更新前有本地修改的条目数，含入口文件）、`locked`（只在 `--dry-run` 时出现：工作副本是否被锁，被锁时实际运行会先 cleanup）、`handled`（`cleanup`、`reverted`、`conflicts_resolved`、`moved_unversioned`）、`conflicts`（处理后仍然冲突的路径）、`external_failures`、`errors`、`notes`。

向用户汇报：每个工作副本的前后分支和版本、周期分支是否到达目标维护周、`handled` 里处理了哪些文件和备份路径、失败和跳过的部分。`handled` 不为空时一定要列出文件，让用户知道哪些本地内容被换掉了、去哪里找回。

- 外链（`svn:externals`）失败不使主工作副本的更新作废：该工作副本记为 `partial`，`external_failures` 给出原文，不自动重试。
- 代码工作副本失败不影响 `../_test` 继续更新；不承诺跨工作副本的原子性。
- `conflicts` 不为空或有 `errors` 时如实报告，不说成成功。脚本不提交，不创建或删除分支。
- 找回被换掉的内容：从 `files/` 拷回，或在工作副本根目录 `svn patch <备份目录>/<工作副本名>/local-changes.patch`。清理个人目录会删掉备份。
