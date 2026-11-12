# 打 patch（开发分支）

用户要求给当前开发分支打 patch（出包）、新建打包模板或查打包进度时读取本文件。打出的模板名就是提测单的「Patch 地址」「PC 资源地址」（见 `test-request.md`）。

**只用于开发分支**（脚本在 `wzimage/branchs/<年>_dev/<分支>`）。外放分支有单独流程，trunk 和周期分支也不适用：脚本识别到不是开发分支会直接报错，不要换参数绕过。

脚本 `scripts/patch.py` 直连打包服务 mh-patch-mcp，不需要在 Claude／Codex 里配置这个 MCP。命令都带 `--root <项目>`（`tables`、`status` 除外）；资源工作副本取 `<项目>/../_test`。

## 令牌

打包服务按令牌（`X-Access-Token`）识别用户：打包人、打包完成后的 popo 通知都发给令牌的主人。令牌存在用户级配置 `patch_token`，只能隐藏输入（交互终端规则同 workspace-management.md「密码」）：

```text
python "<skill>/scripts/workspace.py" config --prompt-patch-token --apply
```

- 输出报“没有配置打包令牌”或“打包令牌无效或已过期”时，请用户取新令牌后按上面的命令设置，不要重试，也不要用其他令牌代替。
- 用 CORP 账号密码登录 eros 得到的 jwt 不能当令牌用（服务会拒绝）。

## 流程

1. **准备（只读）**：

   ```text
   python "<skill>/scripts/patch.py" prepare --root "<项目>" [--name <模板名>]
   ```

   模板名取 `--name`，否则取工作区配置 `patch_template`。按输出的 `next` 继续：
   - `name`：还没有模板名。`candidates` 是脚本地址等于本分支的已有模板，有就请用户从中选；没有就拟一个**中文**模板名：参考分支名的含义（如 `wzw_2026_11_10_hancu_effect` → “寒促特效”）、追踪工单标题和最近的 spec 标题，简短、能看出是什么需求。把拟的名字给用户确认或修改，然后带 `--name` 重新 prepare。
   - `create`：模板不存在，走第 2 步。
   - `start`：模板存在且绑定本分支，走第 3 步。
   - `stop`：模板绑定的是别的分支。把 `errors` 告诉用户，由用户在 Sunshine 上处理或换名字，不要在这里改模板。
   - `warnings` 里的内容（模糊命中、资源地址不同）都要转告用户。

2. **新建模板**：模板会自动填本分支的脚本和资源地址；导表默认不导。
   - 用户要导表时，先查选项，请用户挑选：`patch.py tables --issue-id <总单号>`，把选中的 `options` 序号逐个用 `--table` 传入。
   - 预览：`patch.py create --root "<项目>" --name <模板名> [--issue-id <总单号>] [--table <序号>]...`，输出的 `job.arguments` 是要传给服务的全部参数。
   - 把模板名、脚本地址、资源地址、导表（不导表时写“不导表”）列给用户；**用户确认后**在同一命令后加 `--apply`。只建模板，不打包。
   - 成功后模板名自动记到工作区配置 `patch_template`。

3. **打包**：
   - 预览：`patch.py start --root "<项目>" [--name <模板名>]`。把模板名、绑定的分支、上次打包（`package`：时间、打包人、各仓库 revision）列给用户；可以顺带说明本分支在上次打包之后有没有新的提交（`svn log -r <上次 revision>:HEAD` 只读查询）。
   - **用户确认后**加 `--apply` 发起。打包在服务端后台执行，完成后服务会给打包人发 popo 通知；输出里有 `job.result.job_id`。

4. **查进度**：`patch.py status --job-id <job_id>`；忘了 job_id 时 `patch.py status --recent`。`job.status` 为 `pending`／`running` 时稍后再查，不要循环轮询；`success` 时把 `script_url`、`res_url` 交给用户；`failed` 时报告 `error`，需要分析时加 `--raw` 看完整打包日志。

建模板和打包每次都要用户确认，上一次的确认不延续到下一次；网络超时时请求可能已经执行，先 prepare 或 status 查清再决定，不要直接重试。

## 输出

每个子命令输出一个 JSON 对象，字段固定（不适用的为 null 或空列表）：`action`、`applied`、`branch`（`name`、`script_svn`、`res_svn`）、`template`（`name`、`exists`、地址、`matches_branch`）、`package`（上次打包）、`job`（`tool`、`arguments`、`result` 或任务状态）、`candidates`、`tables`、`next`、`warnings`、`errors`。

退出码：0 成功（含预览）；1 失败且没有改动远端；2 远端已改（模板已建或打包已发起），但后续步骤失败——按 `errors` 说明，不要重新建模板或再次发起打包。

以后接入 popo-agent-service 时，直接运行本脚本并读取这份 JSON 发通知，不需要改脚本。
