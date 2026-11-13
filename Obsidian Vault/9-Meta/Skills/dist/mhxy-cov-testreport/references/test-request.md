---
name: test-request
description: 在提测系统（newtestreport）上刷新单号、校验测试重点 HTML、预览并保存客户端提测单。
---

# 提测（提交测试）

用户要求提测时读取本文件。提测在提测系统（`https://newtestreport.eros.nie.netease.com`）上填好客户端负责的内容并保存，把提测单预览链接交给用户。

脚本 `<skill>/scripts/testreport.py` 使用 `~/.mhxy-workspace/config.json` 中的 CORP 账号走 eros 统一登录，会话仅保存在内存中。未配置密码且无交互终端时，先让用户运行 `corp_login.py config --username <CORP邮箱> --prompt-password --apply`。

## 字段分工

| 字段 | 来源 |
| --- | --- |
| 单号 | **总单号**。由用户给的任意相关单号（程序单、测试单或总单）经 `prepare` 刷新得到的 `redmineId` |
| 系统名、程序、策划、QA | “刷新”自动带出 |
| Patch 地址、PC 资源地址 | 同一个 Sunshine 打包模板名（模板里包含本次客户端改动的全部内容） |
| 客户端覆盖率地址 | 覆盖率流程中 `coverage_query.py` 输出的 `url`；“刷新”或已有提测单已带出时可沿用 |
| 客户端提测 checklist | 固定：`https://checklist.eros.nie.netease.com/dashboard/checklist/10590` |
| 测试需特别注意 | 根据本次改动、spec 和自测情况总结测试重点（HTML，例如 `<p>…<br/>…</p>`） |
| 测试端口、代码覆盖率、MOS 覆盖率、测试指令、概率接管 | **服务端负责，不填**。代码覆盖率和 MOS 覆盖率是页面必填项，新建且为空时脚本自动填“由服务端填写” |
| “重要覆盖率”、自测情况说明 | 默认不勾选 |

## 流程

1. **准备（只读）**：

   ```bash
   python -X utf8 "<skill>/scripts/testreport.py" prepare --issue-id <单号>
   ```

   输出总单号 `redmineId`、刷新带出的信息，以及该总单下本人已有的提测单（`existing`，含链接、模板和客户端覆盖率）。

   `existing` 只来自提测系统的“我的提测”列表（本人建的提测单）；别人（如服务端）为同一总单建的提测单不会出现在这里。因此 **`existing` 为空时，先问用户这个总单是否已经有别人建的提测单**：有的话请用户给出提测单 ID（`testRequestID`），按更新处理。

2. **补齐信息**：
   - **Patch 模板名**：已有提测单时沿用其模板并请用户确认；没有时若本地 `.mhxy-workspace/config.json` 配有 `patch_template` 可作为候选，否则询问用户 Sunshine 打包模板名。
   - **客户端覆盖率**：优先用本次覆盖率流程 `coverage_query.py` 输出的 `url`；已有提测单或刷新已带出时可沿用；没有跑过覆盖率时，问用户是先跑覆盖率，还是填写无链接原因。
   - **测试需特别注意**：写成简短的 UTF-8 HTML 文件放到临时目录（不要放进 SVN 工作副本）。只允许使用 `<p>`、`<br>`、`<ul>`、`<ol>`、`<li>`、`<strong>`、`<b>`、`<em>`、`<i>`、`<span>`、`<font>` 标签，不能含 Markdown 标记（` ``` `、`**`）、`{{` 占位符或 HTML 注释。

3. **预览（不加 `--apply`）**：

   ```bash
   python -X utf8 "<skill>/scripts/testreport.py" save --redmine-id <总单号> --patch "<模板名>" --cli-cover "<覆盖率 url 或原因>" --attention-file "<UTF-8 HTML 临时文件>" [--test-request-id <已有提测单 ID>]
   ```

   - 已有提测单时**必须**传 `--test-request-id` 更新它，不要重复新建；有多条时问用户更新哪一条。脚本会核对这张提测单存在且属于 `--redmine-id` 指定的总单，不符时直接报错，不会退回新建。
   - 更新时，脚本会保留服务端已填的字段（测试端口、代码／MOS 覆盖率、自测情况、测试指令、概率接管），只覆盖客户端负责的字段。
   - 检查输出中的 `attention_issues`：不为空时先修改临时 HTML 文件再重新预览；存在问题时加 `--apply` 会被脚本拒绝保存。

4. **确认后保存**：
   - 把预览中的关键字段（总单号、系统名、Patch 模板、客户端覆盖率、测试重点、新建还是更新）列给用户。
   - 保存是对外提交，**必须等用户明确确认后**，才在同一命令后加 `--apply` 执行保存。

5. **交付**：
   - 把保存成功后输出的 `link`（提测单预览页）发给用户，并删除临时 HTML 文件。
   - 流程到“保存”为止：**不要“发送”提测单**。发送会发邮件/消息通知策划和 QA，由用户在页面上核对后自己点击发送；交付时提醒用户这一步还没做。
