# 打 patch（开发分支）

用户要求给当前开发分支打 patch（出包）、新建打包模板或查打包进度时读取本文件。打出的模板名就是提测单的「Patch 地址」「PC 资源地址」（见 `test-request.md`）。

**只用于开发分支**（脚本在 `wzimage/branchs/<年>_dev/<分支>`）。外放分支有单独流程，trunk 和周期分支也不适用：脚本识别到不是开发分支会直接报错，不要换参数绕过。

脚本 `scripts/patch.py` 直连打包服务 mh-patch-mcp，不需要在 Claude／Codex 里配置这个 MCP。命令都带 `--root <项目>`（`tables`、`status` 除外）；资源工作副本取 `<项目>/../_test`，它必须在 `share/patch` 仓库下，可以和脚本分支不同名（这时输出里有提醒，转告用户确认是本需求的资源）。

## 令牌

打包服务按令牌（`X-Access-Token`）识别用户：打包人、打包完成后的 popo 通知都发给令牌的主人。令牌由脚本每次运行时向本机 CodeMaker Hub 现取（`codemaker-hub-gui.exe mcp-token-helper`，与 OpenForge 的 MCP 代理同一来源），不保存、不输出；服务判定令牌失效时脚本自动续签一次再试。

- 报“没有找到 CodeMaker Hub”“没有返回打包令牌”“拒绝了续签后的令牌”时，请用户确认 Hub 已安装、正在运行并已登录；Hub 装在自定义目录时设置环境变量 `CODEMAKER_HUB_AUTH_HELPER_BIN` 指向 `codemaker-hub-gui.exe`。不要改用其他来源的令牌。
- CORP 账号密码登录 eros 得到的 jwt、写在 MCP 配置里的静态令牌都不能用（前者服务不认，后者一天内过期）。

## 流程

1. **准备（只读）**：

   ```text
   python "<skill>/scripts/patch.py" prepare --root "<项目>" [--name <模板名>]
   ```

   模板名取 `--name`，否则取工作区配置 `patch_template`。按输出的 `next` 继续：
   - `name`：还没有模板名。`candidates` 是按分支名搜到、脚本地址等于本分支的已有模板（服务只搜模板名和描述，所以搜不到不代表没有；用户记得已有模板时请他给出名字），有就请用户从中选；没有就拟一个**中文**模板名：参考分支名的含义（如 `wzw_2026_11_10_hancu_effect` → “寒促特效”）、追踪工单标题和最近的 spec 标题，简短、能看出是什么需求。把拟的名字给用户确认或修改，然后带 `--name` 重新 prepare。
   - `create`：没有这个名字的模板，走第 2 步。模板名只按精确名称判断；有名称相近的模板时 `candidates` 会列出来，先问用户其中是不是本需求的模板。
   - `start`：模板存在且绑定本分支，走第 3 步。
   - `stop`：模板绑定的是别的分支。把 `errors` 告诉用户，由用户在 Sunshine 上处理或换名字，不要在这里改模板。
   - `warnings` 里的内容（模糊命中、资源地址不同）都要转告用户。

2. **新建模板**：模板会自动填本分支的脚本和资源地址；导表默认不导。
   - **必须传易协作总单号**（没有父单的那张，用 `pm_issues.py --show <单号>` 看 `parent_id` 确认；用户给的是子单时往上找）。单号为 0 时服务会无视传入的地址、写入一个固定的他人分支，脚本因此拒绝不带单号的 create。
   - 服务给模板起的名字是“#<总单号> ”加截到 10 个字符的标题（如“#865118 wzw寒促特效”），所以拟名时标题控制在 10 个字符内，不必再加日期；预览里的 `job.expected_name` 就是最终名字，以后 prepare、start 都用这个完整名字。
   - 用户要导表时，先查选项，请用户挑选：`patch.py tables --issue-id <总单号>`，把选中的 `options` 序号逐个用 `--table` 传入。
   - 预览：`patch.py create --root "<项目>" --name <标题> --issue-id <总单号> [--table <序号>]...`，输出的 `job.arguments` 是要传给服务的全部参数。
   - 把最终模板名、总单号、脚本地址、资源地址、导表（不导表时写“不导表”）列给用户；**用户确认后**在同一命令后加 `--apply`。只建模板，不打包。
   - 新模板要过一两分钟才查得到，脚本会等最多 5 分钟再读回核对地址。核对通过后模板名自动记到工作区配置 `patch_template`；读回地址不对时退出码 2，这个模板不能用来打包，告诉用户在 Sunshine 上删掉。

3. **打包**：
   - **不需要用户确认**（用户 2026-11-12 定）：模板存在且绑定本分支（`prepare` 的 `next` 为 `start`）时，直接 `patch.py start --root "<项目>" [--name <模板名>] --apply` 发起。没有模板（`next` 为 `name`／`create`）时不打包，按第 1、2 步问用户。
   - 发起后把模板名、绑定的分支、上次打包（`package`：时间、打包人、各仓库 revision）和 `job.result.job_id` 告诉用户；可以顺带说明本分支在上次打包之后有没有新的提交（`svn log -r <上次 revision>:HEAD` 只读查询）。打包在服务端后台执行，完成后服务会给打包人发 popo 通知。

4. **查进度**：`patch.py status --job-id <job_id>`；忘了 job_id 时 `patch.py status --recent`。`job.status` 为 `pending`／`running` 时稍后再查，不要循环轮询；`success` 时把 `script_url`、`res_url` 交给用户；`failed` 时报告 `error`，需要分析时加 `--raw` 看完整打包日志。

建模板每次都要用户确认，上一次的确认不延续到下一次；已有模板时打包不需要确认。发起打包前用 `status --recent` 看同一模板有没有 `pending`／`running` 的任务，有就报告进度，不重复发起。网络超时时请求可能已经执行，先 prepare 或 status 查清再决定，不要直接重试。

## 输出

每个子命令输出一个 JSON 对象，字段固定（不适用的为 null 或空列表）：`action`、`applied`、`branch`（`name`、`script_svn`、`res_svn`）、`template`（`name`、`exists`、地址、`matches_branch`）、`package`（上次打包）、`job`（`tool`、`arguments`、`result` 或任务状态）、`candidates`、`tables`、`next`、`warnings`、`errors`。

退出码：0 成功（含预览）；1 失败且没有改动远端；2 远端已改（模板已建或打包已发起），但后续步骤失败——按 `errors` 说明，不要重新建模板或再次发起打包。

以后接入 popo-agent-service 时，直接运行本脚本并读取这份 JSON 发通知，不需要改脚本。
