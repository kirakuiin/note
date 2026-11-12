# 群里报的 popo 工单：自动检查和修复

日期：2026-11-12　版本：0.3.43

## 目标

测试群里有人报 bug（直接 @ 机器人，或引用别人的 mark 消息再 @），popo-agent-service 在绑定的工作区里开无人值守会话处理：

- 不能处理：在群里 @ 用户和提交人说明原因，在 bug 单上追加一条备注，状态不动。
- 能修：停在“待提交”，确认卡片私聊发给用户；用户点“提交”且提交成功后，在 bug 单上追加备注、把状态改成“已完成”，再在群里 @ 用户和提交人说明。

本 spec 写 skill 一侧：提单平台脚本 `popo_bug.py`，以及无人值守模式处理 popo 工单的约定。服务一侧见 popo-agent-service 的 `docs/spec.md`「群里报 bug」。

## 提单平台（已核实，2026-11-12）

- 站点 `https://popomgr.eros.nie.netease.com`。CORP OpenID 登录，跳转链是“站点 `/auth/login` → `auth2.qkit.nie.netease.com`（http）→ `login.netease.com`”，和 eros 统一认证只差中转站，复用 `eros_auth.login`，中转站作为参数。用 skill 配置里保存的账号自动登录，实测不需要验证码。
- 平台机器人把群里“mark @某人 …”消息建成 bug 单：单上 `origin_subject` 是原消息全文，`popo_group_num` 是来源群号。
- 任务（制作内容）：`/api/index/tasks?qa=<账号>` 列出与该账号相关的任务；字段 `popo_group_num`（绑定的群，列表）、`parentid`（策划单号）、`related_person`、`related_redmine`（账号 → 易协作子单号）、`qa`。
- bug 列表：`GET /mgr/task/get_issues_by_task`（`taskid`、`keyword`、分页等），每行有 `_id`、`readable_id`、`origin_subject`、`subject`、`status`、`author`、`followqa`、`popo_group_num`。
- bug 详情：`POST /mgr/get_issue_data`（表单 `_id`、`taskid`），含 `subject`、`img`、`way_text`、`way_img`、`markdown`（备注）。
- 建单：`POST /mgr/task/save_issue`（multipart：`subject`、`img_path`、`taskid`、`_id` 空、`ctype`、`assignee`、`issue_type`、`way_text`、`way_img`、`priority`）。没有提单人字段，提单人就是登录账号。
- 备注：`POST /mgr/task/update_issue {_id, taskid, markdown}`，整段覆盖。
- 人员表：`GET /api/index/init` 的 `person_dict`（按角色分组），每人 `_id`（账号）、`firstname`（如 `W王卓为`）、`mail`。POPO 事件里的发送人是邮箱，账号和邮箱前缀不一定相同（如 `ylyn3265`），要按这张表对照。 /mgr/task/judge_change_status {_id, status, taskid}`；`success` 为真即完成。`ret_code` 2 = 非 QA 改“已完成”需指定跟进 QA，再调 `update_issue {_id, status, taskid, followqa}`；1 = 非 QA 不能关单；3 = 需填未修复原因；4 = 需先改易协作前缀。

## popo_bug.py

```text
popo_bug.py task   --group <群号>
popo_bug.py find   --task <任务ID> --text <引用的原文>
popo_bug.py show   --task <任务ID> --id <bug _id> [--save <项目根>]
popo_bug.py create --task <任务ID> --text <内容> --reporter <报告人：邮箱、账号或姓名> [--assignee <账号>]
popo_bug.py note   --task <任务ID> --id <bug _id> --prefix <已修复|未处理> --text <不超过 20 字>
popo_bug.py status --task <任务ID> --id <bug _id> --to 已完成 [--followqa <账号>]
```

- 输出 JSON；出错时 `{"error": …}`、退出码 1。账号取 `openid_username`，密码由 `corp_login.load_credentials` 读取，不输出。会话 Cookie 只在内存里，每次调用重新登录。
- `task`：与登录账号相关的进行中任务里，`popo_group_num` 含该群的那些。输出 `tasks[]`：`id`、`name`、`planner_id`（`parentid`）、`members`（`related_person` 与 `related_redmine` 账号的并集）、`subtickets`（`related_redmine`）、`qa`、`member_mails`（成员邮箱，按人员表对照）。
- `find`：按 `keyword` 搜任务下还没处理完（新建、描述不清、完成转回）的 bug：`origin_subject`（平台机器人按 mark 建的）或去掉“【群里报告】<报告人>”行后的标题（代建的）归一后与 `--text` 相同；多张取单号最大的；没有时 `bug` 为 null。
- `show`：详情，`author_name` 按人员表取姓名；`--save` 把正文写到 `<项目根>/.mhxy-workspace/bugs/<readable_id>/issue.md`（标题、类型、状态、提单人、所属任务和策划单号、问题描述、重现步骤、已有备注；`[图片]` 按顺序换成本地图片路径，多出的接在段落末尾），图片用不带登录 Cookie 的独立请求下载到同一目录；单张失败不中断，正文里写明原链接，输出 `image_errors`。
- `create`：报告人按人员表换成平台显示的姓名；内容第一行写“【群里报告】<报告人>”，正文接原消息，指派默认登录账号，类型 BUG、优先级 P2。平台不返回新单 ID：按完整标题相等找回，取单号最大的一张，输出新单的 `_id`、`readable_id`。
- `note`：先读出现有备注，在末尾追加一行“<前缀>：<正文>”（不带名字）再整段写回；写回前再读一次，和第一次不同就重新拼接（最多 3 次）。备注正文超过 20 个字时报错，不截断。
- `status`：只接受“已完成”。`ret_code` 2 时用 `--followqa`（缺省为 bug 单原来的跟进 QA）调 `update_issue`；其他失败照实输出 `ret_code`、`retmsg`，不重试。
- `create`、`note`、`status` 是写操作：环境变量 `MHXY_NO_PM_WRITE=1` 时拒绝（与 `pm_update.py --apply` 同一个开关，服务给自动会话都带着它），只有服务自己调用。

## 无人值守处理 popo 工单

提示词写“按无人值守模式处理 popo 工单 <readable_id>”时，按 `unattended.md` 执行，差别如下：

- **单号**：结果文件、处理报告用 `popo-<readable_id>` 作为工单号（如 `popo-297291`），与易协作单号分开。新增 `workspace.validate_issue_key`（正整数或 `popo-` 加正整数），`unattended.py`、`report.py` 用它；`validate_issue_id` 不变，其他脚本仍只认易协作单号。
- **正文**：调用方已用 `popo_bug.py show --save` 写好 `.mhxy-workspace/bugs/<readable_id>/issue.md`，提示词给出路径。
- **分拣**：只有 A 和 C（不会是合并类），标准同 A 类。
- **提交说明**：按 `svn-commit.md`「跟测 bug（popo 工单）」；提单人取正文里的提单人，正文第一行是“【群里报告】<报告人>”时用这个报告人。
- **报告**：`report.py build --issue-id popo-<id> --title "<bug 标题>"`。
- **备注**：`unattended.py result` 加 `--bug-note "<不超过 20 字>"`：待提交时写怎么修的（如“返回键改用原按钮坐标”），需要你处理和放弃时写原因（如“缺少复现步骤”）。不带名字、分支、版本号；调用方用 `popo_bug.py note --prefix 已修复|未处理` 写入。结果文件多一个可选字段 `bug_note`。popo 工单（`popo-` 开头）的任何状态都必须带，其他工单不能带。
- 不写 `pm_update`；会话不调用 `popo_bug.py` 的写命令。

## 验收

- 单元测试：登录跳转白名单含 `auth2.qkit`；`task` 按群过滤与成员并集；`find` 的空白归一；`note` 追加、超长报错、写回前内容变化重拼；`status` 的 `ret_code` 2 走 `followqa`；写命令在 `MHXY_NO_PM_WRITE=1` 时拒绝；`validate_issue_id` 接受 `popo-`；`unattended.py` 的 `bug_note` 校验。
- 全量测试通过。真机：用 `task`、`find`、`show` 读真实数据；写命令只在测试单上试（需要用户提供测试单或同意新建）。

## 变更记录

- 2026-11-12（0.3.43）：初版。
