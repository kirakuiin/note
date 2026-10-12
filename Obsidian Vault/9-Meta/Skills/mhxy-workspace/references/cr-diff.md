# 提 CR（生成并上传 CR diff）

用户要求提 CR、生成 CR diff 或提交代码审查时读取本文件。一般只有制作单走这个流程，而且必须由用户发起，不要主动执行。本流程把**已提交**的改动上传到 reviewboard，给其他人 review；它和 `code-review.md`（交付前由子代理做的审查循环）是两件事。

脚本 `scripts/cr_diff.py` 复刻 MHCoder 插件的「生成 CR DIFF」，区别是自动选择 revision。查工单需要用户级配置里的 CORP 账号；没有已存密码、又没有交互终端时，按 workspace-management.md「密码」处理。

## 脚本做什么

- **选提交**：在当前分支（`--stop-on-copy`，从工单创建前一天开始）找出作者是本人（CORP 邮箱前缀）、说明里含 `#工单号` 的提交，`finish #工单号` 的写法也算。
- **生成 diff**：和插件一样，对整个分支取「第一个提交的前一版 → 最后一个提交」的 diff，只保留这些提交改过的文件，并排除 `data/`（导表）。diff 按 svn 的原始输出保存，不转码。
- **他人改动**：这段范围内如果别人也改过同一文件，这些改动会混进 diff。脚本把这类提交列在 `others_in_range` 里，只作提示。
- **表单字段**：

  | 字段 | 取值 |
  | --- | --- |
  | `review_title` | `#工单号 工单名`，可用 `--title` 覆盖 |
  | `time_request` | 外测、全服、期望完成时间都填明天 |
  | `testing_done` | 工单的直接父单号；没有父单时问用户，用 `--testing-done` 传入 |
  | `review_desc` | agent 撰写，见下方第 2 步 |
  | `real_user`、`from_url` | CORP 邮箱前缀、当前分支的仓库 URL |

- **上传**：Jenkins 任务的地址和凭据在上传时从本机最新版的 MHCoder 插件（VS Code 或 Cursor）里读取，不保存、不输出。没有装插件时无法上传，请用户先安装。

## 流程

1. **选定工单**：用追踪工单（context 的 `tracked_tasks`）。只有一个时直接用，并在预览里写明；有多个或没有时先问用户。
2. **准备（只读）**：

   ```text
   python "<skill>/scripts/cr_diff.py" prepare --root "." --issue <工单号>
   ```

   diff 和清单保存在 `.mhxy-workspace/code-review/<工单号>/`。读一遍输出的 `files`、`others_in_range` 和 diff，再写 `review_desc`：
   - 分点说明这次改了什么，总长不超过 200 字；
   - 保存到临时文件（UTF-8，不要放进工作副本）。
3. **预览**：

   ```text
   python "<skill>/scripts/cr_diff.py" upload --root "." --issue <工单号> --desc-file "<描述文件>"
   ```

   把以下内容列给用户：工单号、revision 列表、文件清单（排除了哪些 `data/` 文件）、`others_in_range`、全部字段。
4. **确认后上传**：上传是对外提交，必须等用户明确确认后，才在同一命令后加 `--apply`。脚本会跟踪本次触发的 Jenkins 构建，输出 `build_url`、`result`，能从构建日志里找到 review 链接时也输出 `review_url`。
5. **交付**：
   - `result` 为 `SUCCESS`：给出 `review_url`；没有链接时请用户查看 POPO 通知。
   - 其他结果、或等待超时（退出码 2）：把 `build_url` 和 `console_tail` 告诉用户，不要自行重试。插件的说明提到，没有 CR 权限时构建也可能显示成功，所以最终以 POPO 通知为准。

脚本报错时按提示处理，不要绕过：
- 找不到提交：核对工单号和当前分支。
- diff 在 prepare 之后被改动，或分支变了：重新运行 prepare。
- 描述超长：精简后重新预览。
