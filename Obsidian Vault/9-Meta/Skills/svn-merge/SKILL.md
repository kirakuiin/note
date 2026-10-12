---
name: svn-merge
description: 安全执行 Subversion（SVN）分支合并、周维护分支同步、长生命周期分支迁移到新分支、按修订逐个重放和冲突处理，并强制正式分支提交日志规范。用于用户要求 svn merge、SVN 分支合并、只给源分支但未给修订号的周维护合并、按指定修订或日志描述合并少量改动、推导 eligible 修订范围、保留 svn:mergeinfo、处理冲突、准备或执行合并提交时。所有会修改工作副本的 merge、replay、冲突自动处理和提交都必须调用本技能自带的 scripts/svn_merge.py；不要手写原生 svn merge 命令来落地改动。
---

# SVN 合并

使用本技能处理任何非平凡 SVN 合并。优先保留 SVN 原生 mergeinfo，不要用复制文件或手工打补丁模拟合并。

除 `svn info`、`svn status`、`svn update`、`svn log`、`svn mergeinfo`、`svn diff`、`svn cleanup` 这类检查/恢复命令外，所有会修改目标工作副本的 merge 操作都必须通过 `<skill-dir>\scripts\svn_merge.py` 执行。不要在主代理里手写 `svn merge` 或 `svn merge --dry-run` 作为落地路径；脚本会在 `replay` 中统一执行 dry-run、真实 merge、编码冲突自动处理和摘要校验。`replay` 默认只把结果保留在工作副本供检查，只有使用者明确要求提交时才可传 `--commit`，由脚本生成提交消息、执行提交并校验日志。

## 强制前置步骤

每次执行真实合并、逐版本重放或提交前，必须先完成以下步骤。

1. 显式提示使用者即将把目标工作副本切到 HTTPS。
   - 提示文本必须包含：`我会先把目标 SVN 工作副本 relocate 到 HTTPS，避免 SVN 客户端反复弹验证。如果当前 URL 已经是 HTTPS，我会说明无需变更。`
   - 用 `svn info <target-wc>` 获取当前 URL 和工作副本根目录。
   - 当前 URL 不是 HTTPS 时，优先只把协议替换为 `https://`，再执行：

```powershell
svn relocate "<old-url>" "<https-url>" "<target-wc>"
```

   - 如果协议替换后仓库根路径不确定，先停下来让使用者确认 HTTPS URL，不要猜。

2. 向使用者确认源路径和脚本预览范围。
   - 无论使用者是否提供修订号，都必须先推导候选合并修订，再用 `svn_merge.py eligible`、`svn_merge.py replay --plan-only` 或只读日志/mergeinfo 命令展示候选计划。
   - 必须展示候选修订来源：使用者明确指定、按日志描述匹配、或从 `svn mergeinfo --show-revs eligible` 推导。
   - 预览后必须展示源路径、目标工作副本、目标 URL、最终建议合并的修订范围或修订列表、跳过修订、文档目录和计划摘要。确认后由 `svn_merge.py replay` 执行脚本内 dry-run 和真实 merge，默认停在待检查状态。
   - 真实 `svn_merge.py replay` 前必须等使用者明确确认。定向合并默认停在待检查状态；分支同步、周维护和长期分支迁移的计划确认视为提交确认，真实 replay 必须显式传 `--commit`。

3. 确认合并文档目录。
   - 如果使用者没有显式提供合并文档目录，直接在目标工作副本根目录创建 `mergedocs/`。
   - 必须显式提示：`使用者没有提供合并文档目录，我会使用 <target-wc>\mergedocs\ 保存冲突记录、风险记录和提交消息文件。`
   - 提交消息文件放在 `<doc-root>\messages\`。

## 必要输入

- 源分支 URL：包含要合并或重放的改动。
- 目标分支工作副本路径：接收改动的本地工作副本。
- 合并意图：
  - 定向合并：使用者给出修订号、修订范围、或能匹配到日志的描述。
  - 周维护/分支同步：使用者只给源分支，要求把该分支尚未合入目标的改动合过来。
- 可选跳过列表：不需要合并或已知有问题的修订。
- 合并文档目录：由使用者提供；没有提供时使用 `<target-wc>\mergedocs\`。
- 可选目标分支 URL：缺省时从 `svn info <target-wc>` 推导。

缺少源路径或目标工作副本时，先询问使用者。缺少修订号不是阻塞项；按周维护/分支同步处理，用 `svn_merge.py eligible` 或 `svn mergeinfo --show-revs eligible` 推导候选修订。计划分析可以先做，但真实 `svn_merge.py replay` 和提交不能越过确认。

## 通用检查

1. 确认目标工作副本根目录和 URL：

```powershell
svn info "<target-wc>"
```

2. 按强制前置步骤 relocate 到 HTTPS。

3. 确认工作副本干净：

```powershell
svn status "<target-wc>"
```

   - 版本控制内的本地修改、锁、冲突、缺失项都必须先处理。
   - 可以忽略 `X` externals 和无关的 `?` 临时文件，但要在汇报中说明。

4. 更新目标工作副本：

```powershell
svn update --ignore-externals "<target-wc>"
```

5. 准备文档目录：

```powershell
New-Item -ItemType Directory -Force "<target-wc>\mergedocs\messages" | Out-Null
```

## 选择工作流

- 定向合并：使用者给出修订号、修订范围或日志描述时，先把输入解析成明确修订列表，再用 `svn_merge.py replay --revs ... --plan-only` 预览。
- 周维护/分支同步：使用者只给源分支时，先用 `svn_merge.py eligible` 或 `svn mergeinfo --show-revs eligible` 推导目标尚未合入的修订，再用 `svn_merge.py replay --eligible --plan-only` 预览；使用者确认计划后，默认用 `--commit` 自动逐组提交。
- 旧长期分支合并到新分支：先检查旧分支 copy revision，再用 eligible 修订和日志确认真正要迁移的分支本地改动。
- 逐版本重放：使用 `scripts/svn_merge.py`，按明确修订或 eligible 修订执行 dry-run、merge、冲突处理和摘要校验；默认不提交。
- 只做规划：可以只运行 `svn mergeinfo`、`svn log`、`svn_merge.py eligible` 或脚本 `--plan-only` 推导候选，不要修改工作副本；如果下一步要真实合并，必须通过同一个脚本 `replay` 执行。

## 定向合并

适用于使用者明确说“合这几条”“合这个单子”“合包含某段日志描述的提交”。不要假设使用者一定会给修订号。

1. 如果使用者给了明确修订号或范围，规范化成修订列表或压缩范围：
   - 单条：`r2685043`
   - 多条：`r2685043,r2685048,r2685050`
   - 连续范围：`r2685043-r2685050`

2. 如果使用者只给了日志描述、工单号或关键词，先查源分支日志并匹配候选修订：

```powershell
svn log --search "<keyword-or-ticket>" "<source-url>"
```

   如果 SVN 客户端不支持 `--search`，改用合适的时间窗口或修订窗口读取日志，再在输出中匹配：

```powershell
svn log -v -r "<start-rev>:HEAD" "<source-url>"
```

   找到候选修订后，必须把匹配到的修订号、作者和日志首行展示给使用者。

3. 用候选修订执行脚本预览。传给 `--revs` 的修订号使用数字形式；展示给使用者时可以保留 `r` 前缀：

```powershell
python "<skill-dir>\scripts\svn_merge.py" replay `
  --source-url "<source-url>" `
  --target-wc "<target-wc>" `
  --revs <rev1> <rev2> <rev3> `
  --plan-only
```

   如果候选是连续范围，先展开成明确修订列表传给 `--revs`，或在修订很多时用 `--min-rev`/`--max-rev` 配合 `--eligible` 过滤。不要改用原生 `svn merge --dry-run`。

```powershell
python "<skill-dir>\scripts\svn_merge.py" replay `
  --source-url "<source-url>" `
  --target-wc "<target-wc>" `
  --eligible `
  --min-rev <start-rev> `
  --max-rev <end-rev> `
  --plan-only
```

4. 预览完成后，向使用者展示最终建议合并的修订列表或范围、日志摘要、目标路径、文件摘要和计划摘要。使用者确认后再执行脚本真实重放。脚本会先执行 dry-run；如果 dry-run 或真实 merge 检测到文本冲突，会尝试自动处理安全的编码冲突。默认结果停在工作副本，提交需要使用者再次明确确认并追加 `--commit`。

```powershell
python "<skill-dir>\scripts\svn_merge.py" replay `
  --source-url "<source-url>" `
  --target-wc "<target-wc>" `
  --revs <rev1> <rev2> <rev3> `
  --message-dir "<doc-root>\messages"
```

连续范围且确认使用 `eligible` 过滤时：

```powershell
python "<skill-dir>\scripts\svn_merge.py" replay `
  --source-url "<source-url>" `
  --target-wc "<target-wc>" `
  --eligible `
  --min-rev <start-rev> `
  --max-rev <end-rev> `
  --message-dir "<doc-root>\messages"
```

脚本成功后执行只读验证：

```powershell
svn status "<target-wc>"
svn diff "<target-wc>"
svn propget svn:mergeinfo -R "<target-wc>"
```

`svn_merge.py replay` 默认只合并到工作副本、不提交。默认模式只支持一个修订组；多个修订组必须拆分后逐组检查，或在使用者明确确认自动逐组提交时传 `--commit`。只有 `--commit` 模式才执行提交和提交日志校验。

## 分支同步

适用于使用者说“把这个分支合过来”、“同步源分支到目标分支”，但没有提供具体修订号。

1. 推导目标尚未合入的候选修订：

```powershell
svn mergeinfo --show-revs eligible "<source-url>" "<target-wc>"
```

2. 读取候选修订日志，帮助使用者判断范围是否正确：

```powershell
svn log -r "<first-eligible-rev>:<last-eligible-rev>" "<source-url>"
```

   如果 eligible 修订不是连续范围，汇报时必须保留真实修订列表或压缩后的多个范围，不要把中间不 eligible 的修订伪装成一个连续范围。

3. 默认候选范围：
   - 如果 eligible 修订连续，建议范围写成 `r<first>-r<last>`。
   - 如果 eligible 修订不连续，建议写成 `r1,r2,r5-r8` 这种压缩列表。
   - 如果使用者提供跳过列表，从候选修订中剔除并在汇报中单独列出。

4. 对最终候选修订执行脚本预览。连续范围使用 `--eligible --min-rev --max-rev`；非连续列表使用精确 `--revs`，必要时分批预览：

```powershell
python "<skill-dir>\scripts\svn_merge.py" replay `
  --source-url "<source-url>" `
  --target-wc "<target-wc>" `
  --revs <rev1> <rev2> <rev5> <rev6> <rev7> <rev8> `
  --plan-only
```

5. 预览后必须向使用者确认：
   - 这是从 `eligible` 推导出的周维护候选，不是使用者手填范围。
   - 实际建议合并的修订列表或范围。
   - 计划文件摘要和可能风险；脚本真实执行时会先做 dry-run，并在发现文本冲突时尝试编码冲突自动解决。
   - 跳过修订和跳过原因。

6. 使用者确认分支同步计划后，再调用 `svn_merge.py replay` 真实重放。真实重放必须使用与预览相同的修订列表、范围和跳过列表，并默认追加 `--commit` 自动逐组提交和校验目标日志。

## 长期分支到新分支

适用于旧分支从主干切出较久，新分支刚从较新的主干切出，现在要把旧分支开发改动搬到新分支。

1. 检查旧分支创建点：

```powershell
svn log --stop-on-copy -q "<old-branch-url>"
```

2. 找出需要迁移的旧分支本地修订：

```powershell
svn mergeinfo --show-revs eligible "<old-branch-url>" "<new-branch-wc>"
```

3. 读取 eligible 修订日志，区分真正的旧分支开发改动、反向同步改动和需要跳过的风险修订。

4. 按周维护/分支同步流程用 `svn_merge.py replay --plan-only` 预览，展示最终建议的修订列表或范围并等待确认。

5. 确认长期分支迁移计划后用 `svn_merge.py replay --commit` 真实重放；脚本会处理 dry-run、真实 merge、冲突停顿、mergeinfo 校验、提交和目标日志校验。

## 逐版本重放脚本

当需要像 git cherry-pick/rebase 一样按 SVN 修订逐个搬迁，并希望自动校验改动集、提交消息和提交后日志时，使用本技能自带脚本：

```powershell
$skillScript = "<skill-dir>\scripts\svn_merge.py"
```

列出 eligible 修订：

```powershell
python $skillScript eligible `
  --source-url "<source-branch-url>" `
  --target-wc "<target-working-copy>"
```

预览重放计划，不修改工作副本：

```powershell
python $skillScript replay `
  --source-url "<source-branch-url>" `
  --target-wc "<target-working-copy>" `
  --eligible `
  --plan-only
```

如果使用者给了下限、上限或跳过列表，再加上：

```powershell
  --min-rev 2685043 `
  --max-rev 2685100 `
  --skip-revs 2685060,2685088
```

展示计划后，必须向使用者确认源路径、最终修订列表或范围和计划摘要。确认定向修订后再执行脚本真实重放；真实重放过程中脚本会先做 dry-run，默认停在工作副本：

```powershell
python $skillScript replay `
  --source-url "<source-branch-url>" `
  --target-wc "<target-working-copy>" `
  --eligible `
  --message-dir "<doc-root>\messages"
```

定向修订只有使用者明确要求提交时，才在同一条命令追加 `--commit`。`--commit` 会在合并校验通过后提交并校验目标日志；分支同步、周维护和长期分支迁移按其工作流默认使用 `--commit`。

只合并到本地工作区、暂不提交时：**不要传 `--commit`**，其余参数照常给：

```powershell
python $skillScript replay `
  --source-url "<source-branch-url>" `
  --target-wc "<target-working-copy>" `
  --revs 2685043 `
  --log-ticket <单号> `
  --log-text "<描述>" `
  --message-dir "<doc-root>\messages"
```

- 脚本会先 dry-run、再真实 merge，然后停在 `MERGE_READY_FOR_REVIEW <修订组> 未提交`，改动留在工作副本里，提交消息写到 `--message-dir` 下，供人工检查或手工提交。
- 只想看计划、不动工作副本时用 `--plan-only`（违规只打印 `TARGET_LOG_POLICY_VIOLATION` 告警）。
- 日志规范校验在“只合并不提交”时同样执行，因为写出的消息文件就是之后提交要用的日志；目标是正式分支且源日志不合规时，仍需 `--log-ticket` 配描述（或源日志里能推导出描述）。
- 不传 `--commit` 时脚本只支持**一个修订组**；多组会被拒绝，需要拆成单组分别执行，或确认后改用 `--commit` 自动逐组提交。

如果确认的是明确修订列表，也可以不用 `--eligible`，改用：

```powershell
python $skillScript replay `
  --source-url "<source-branch-url>" `
  --target-wc "<target-working-copy>" `
  --revs 2685043 2685048 2685050 `
  --message-dir "<doc-root>\messages"
```

脚本会对每个修订组执行以下步骤；这些 `svn merge` 调用只允许发生在脚本内部，不要由主代理手写执行。第 4-8 步仅在显式传入 `--commit` 时执行：

修订组的合并规则：只合并最终待合列表中相邻、作者相同、提交日志首行等价的源修订。首行都包含 `#单号` 时，单号相同即视为同组，即便首行其他文本或正文不同；首行没有单号时，要求首行文本完全一致。

1. 脚本内部 `svn merge --dry-run`
2. 脚本内部真实 `svn merge`
3. 源侧和目标侧 `svn diff --summarize` 对比
4. 生成 UTF-8 提交消息
5. 提交前冲突标记、临时文件、替换字节、BOM 和混合 EOL 检查
6. `svn commit --encoding UTF-8 -F <message-file>`
7. 读取新提交日志并校验提交消息
8. `svn update --ignore-externals`

脚本遇到 dry-run 冲突、真实合并冲突、摘要不一致、提交失败或日志校验失败时会立即停止；但如果 dry-run/真实合并检测到文本冲突，脚本会先尝试识别并自动解决“源/目标文件编码不同导致的可安全文本冲突”。自动解决只在 SVN 留下 `.working`、`.merge-left`、`.merge-right` 三方文件，且三方都能按 UTF-8/GB18030/GBK/CP936 等常见编码解码、源/目标编码不同、行级三方变更不重叠时生效；解决后统一保存为 UTF-8，Python 文件前两行若存在 `coding` 声明（如 `gbk`、`gb18030`、`cp936`）会同步改成 `utf-8`，再执行 `svn resolve --accept working` 并输出 `AUTO_RESOLVE_ENCODING_CONFLICT output_encoding=utf-8`。若存在语义重叠冲突、无法解码或不是编码类文本冲突，仍按真实冲突停止。
对于同作者同工单合并成一组的多修订，脚本内部 `svn merge --dry-run -c rev1,rev2,...` 可能因为未真实落地前置修订而误报后续修订文本冲突；脚本允许多修订组在 dry-run 冲突后继续真实 merge 复核，只有真实 merge 仍冲突时才停止。

## 周维护分支同步

适用于使用者说“做周维护”，指定了一个灰度分支和一个本地文件夹。MUST 使用上述的逐版本重放脚本方案：

1. 预览重放计划，不修改工作副本：

```powershell
python $skillScript replay `
  --source-url "<source-branch-url>" `
  --target-wc "<target-working-copy>" `
  --eligible `
  --weekly-maintenance `
  --risk-report "<doc-root>\weekly-plan.md" `
  --plan-json "<doc-root>\weekly-plan.json" `
  --plan-only
```

2. 周维护计划必须先做候选修订净效果分析。`--weekly-maintenance` 默认启用 `--classify-reverts` 和 `--auto-skip-neutralized-reverts`，脚本必须输出：
   - `INCLUDE`：本轮建议合入的修订。
   - `SKIP`：本轮建议跳过的修订，包括 test 分支内已被回退完全抵消、且目标当前没有该改动的提交对，以及日志明确提示不要回 trunk 的提交。
   - `REVIEW`：需要人工确认的修订，包括疑似回退/回滚但无法证明安全的提交。

   回退关键词只检查提交日志首行，避免 merge commit 正文中携带的历史日志误伤；关键词包括：`回退`、`回滚`、`撤销`、`revert`、`rollback`、`backout`。
   如果日志没有明确写被回退修订号，脚本只能在“同作者、同工单、同文件集合有交集，且本轮更早候选只有一个匹配项”时推断回退目标；否则必须进入 `REVIEW`。
   发布保留关键词包括：`不回全服/trunk`、`不全服/trunk`、`不上全服/trunk`、`不转全服/trunk`、`不合全服/trunk`、`无需merge回全服/trunk`、`连续N周外测`。命中这些关键词时默认 `SKIP`，并在计划中说明是日志明确提醒值周不要 merge 回 trunk。
   纯 `svn:externals` 外链属性修改默认 `SKIP`，周维护不把 test 分支外链合回 trunk/目标分支；目标分支外链配置保持不变。
   提交日志首行如果形如 `Merged revision(s) <rev> from .../wzimage/trunk` 或其他 `.../trunk` 路径，说明该提交是从 trunk 同步到外测分支的 merge commit，周维护回 trunk 时默认 `SKIP`。

3. 对“提交 A 后被 B 回退”的链路按净效果处理：
   - 如果 A 和 B 都只存在于 test，且 B 完全抵消 A，目标当前也没有 A 的内容，默认 `SKIP A,B`。
   - 如果 A 已经在本轮 `INCLUDE` 且不能证明 A/B 在 test 内完全抵消，B 必须进入 `REVIEW`，不能自动遗漏。
   - 如果 A 已经通过 trunk 其他提交实现，B 默认进入 `REVIEW`，避免把 trunk 的正确后续提交回退掉。
   - 如果 B 会改动 trunk 上后续提交过的同文件或同工单，必须进入 `REVIEW`。

4. 展示计划后，向使用者确认源路径、最终修订列表或范围、`INCLUDE/SKIP/REVIEW` 分类和相关svn提交摘要。周维护需要自动逐组推进，只有使用者明确确认提交后才执行：

   周维护机器人提交的 `auto commit:Merged revision <rev>(<author>) from <branch-tag>` 首行是本规范的既有例外；如果目标不是周维护机器人流程（例如人工外放到 release/rel2 等外放分支），必须改用 `--log-ticket` 生成 `finish/refs #单号` 日志，见“目标分支提交日志规范（必须）”。

```powershell
python $skillScript replay `
  --source-url "<source-branch-url>" `
  --target-wc "<target-working-copy>" `
  --eligible `
  --weekly-maintenance `
  --message-dir "<doc-root>\messages" `
  --commit
```

   如需关闭中性回退对自动跳过，显式加 `--no-auto-skip-neutralized-reverts`；这会把可疑回退链放入 `REVIEW` 供人工确认。
   Jenkins 周维护包装脚本支持 `--skip-revs <rev-list>` 手动跳过源修订，支持逗号/空格/分号分隔和小范围；该参数必须同时作用于 plan-only 和真实 replay，最终通知中列出“手动跳过版本”。
   Jenkins 周维护包装脚本也支持自动推导源/目标分支：传 `-branch test -project script|engine -target_wc <wc>` 时，源分支为 `get_cur_release_date()` 对应的 `test`，目标分支自动切到 `trunk`；传 `-branch release2 -project script|engine -target_wc <wc>` 时，源分支为 `get_cur_release_date()` 对应的 `release2`，目标分支自动切到 `get_next_release_date()` 对应的 `test`。`-project script/脚本/wzimage` 映射到 `wzimage`，`-project engine/引擎/engine2.0` 映射到 `engine2.0`。如需特殊分支仍可用 `-source_url`、`-source_branch`、`-target_branch`、`-project_folder` 手工覆盖。

5. 冲突错误处理：
- 如果发生了merge冲突，脚本会报错并停止。请使用如何冲突处理原则解决冲突。
- Jenkins 周维护包装脚本可在 `svn_merge.py` 因真实合并冲突退出后，从外部调用 CodeMaker AI 尝试解决当前工作副本冲突；`svn_merge.py` 本身不依赖 AI。AI 只能修改当前工作副本并执行 `svn resolve --accept working`，不能提交、更新或整体回滚；prompt 必须明确要求 AI 保留目标已有正确逻辑、合入源侧有效语义、不要处理无关文件，无法安全判断时输出 `AI_CONFLICT_RESOLVE_FAILED`，成功时输出 `AI_CONFLICT_SUMMARY_BEGIN/END` 结构化摘要。若源文件编码与目标工作副本文件编码不同，AI 解决冲突后必须统一保存为 UTF-8；Python 文件前两行若存在 `coding` 声明（如 `gbk`、`gb18030`、`cp936`）必须同步改成 `utf-8`。调用 AI 前，包装脚本必须对冲突路径以外的当前工作副本改动做快照；快照校验应忽略冲突文件本身、冲突 sidecar 临时文件（`.working`、`.merge-left.*`、`.merge-right.*`、`.mine`、`.rej`、`.orig`）和版本化目录的 mergeinfo 状态，只把其他业务文件或新增路径变化视为越界修改。AI 返回后如果发现非冲突路径内容、diff 或新增未版本控制路径变化，应视为自动解决失败并中断通知。AI 成功后由包装脚本检查冲突路径、冲突标记和冲突临时文件，并对本次变更的 `.py` 文件执行 AST 语法检查；有 `coding` 声明的 Python 文件必须严格按声明编码完整解码，声明编码不可用或解码失败时不得 fallback，应视为语法/编码检查失败；语法检查失败时不得提交，应中断通知值周和相关作者。通过后记录冲突文件列表、提交前 `svn diff --summarize`、AST 语法检查结果、AI 输出摘要，生成提交消息并提交当前已解决的合并结果，再跳过该源修订继续处理剩余 eligible 修订；最终通知汇总 `AI_CONFLICT_RESOLVE_OK` 报告和目标提交修订。AI 不可用、AI 明确声明无法安全解决，或解决后仍有冲突路径/冲突标记/冲突临时文件时，流程才中断；中断通知前必须打印清理前 `svn status --ignore-externals` 和 `svn diff --summarize`，然后强制执行 `svn revert` 和 `svn cleanup` 清理目标工作副本，再把清理前摘要和清理后状态写入通知。需要关闭 AI 时传 `--no-ai-resolve-conflicts`，但冲突中断前清理仍强制执行。
- 在冲突解决后，继续调用上述脚本，通过指定--min-rev对剩余的未合并内容继续执行merge。
- 如果脚本报“合并后的文件摘要与源修订不一致”，且源侧列出代码文件、目标侧为空或只剩目录级 `svn:mergeinfo` 变更，通常是源修订本身为 merge commit，目标工作副本已经记录了其 merge history 中的原始修订，SVN 只追加了 mergeinfo 而没有落文本改动。此时必须先检查 `svn log -g -v -r <rev> <source-url>`、目标侧 `svn propget svn:mergeinfo -R <target-wc>` 和目标文件内容，确认是“mergeinfo 已合入但内容漂移”还是“目标已包含相同语义”。
- 出现上述摘要不一致后，脚本内部已经执行过真实 `svn merge`，工作副本可能留下目录级 mergeinfo 修改；继续前必须先 `svn revert -R <target-wc>`，再确认 `svn status <target-wc>` 干净。
- 如果确认该修订不应在本轮落地，优先用 `--skip-revs <rev>` 精确绕过

```powershell
python $skillScript replay `
  --source-url "<source-branch-url>" `
  --target-wc "<target-working-copy>" `
  --eligible `
  --min-rev <next-rev> `
  --skip-revs <bad-rev> `
  --weekly-maintenance `
  --message-dir "<doc-root>\messages" `
  --commit
```
 

## 目标分支提交日志规范（必须）

目标分支 URL 里含 `<年份>_ship`（如 `branchs/2026_ship/release_2026_09_22`、`test_2026_09_22`）或目标分支就是 `trunk` 时，该分支属于**正式分支**，提交日志必须满足：

- 首行必须关联 redmine 单号，形如 `finish #321998 描述` 或 `refs #321998 描述`；**单号后面的描述不能省略**，只写单号（`finish #321998`）不算合规。
- 紧急热更来不及建单时，首行可以是 `#热更 描述`，描述同样不能省略。
- `_ship` 下除 `test*` 以外的分支（`release*`、`newbie`、`zlp`、`sjf`、`shiwan` 等，外测分支名除外）统一按**外放正式分支**处理；其维护内容外放日志按制作单规则写：`finish/refs #维护单号 描述 附加内容`；附加内容可以是 `merge from xxx`，也可以是提交平台链接内容。
- 禁止在提交日志里使用 `auto commit:`。该关键词只保留给公共账号自动提交；本技能里唯一例外是**周维护版本合并的机器人调用**：`--weekly-maintenance`，目标可以是 trunk、外测分支或 `_ship` 下的任一外放分支。人工外放、定向合并、长期分支迁移都不允许用 `--weekly-maintenance` 绕过这条规则。

`svn_merge.py replay` 会在合并前（`--plan-only` 预览也会打印 `目标日志首行=`）和提交前各校验一次，并输出 `TARGET_BRANCH_KIND` 与 `TARGET_LOG_*` 标记：

- 首行是 `auto commit:` 且不是周维护机器人调用：直接失败，列出源日志里可用的候选单号，不会改动工作副本。
- 首行有单号但缺 `finish`/`refs` 关键词：自动补关键词（缺省 `refs`），输出 `TARGET_LOG_KEYWORD_ADDED`。
- 首行没有可识别单号：直接失败，提示追加 `--log-ticket` 后重跑。
- 首行只有单号没有描述（含 `--log-ticket` 未配描述的情况）：直接失败，提示追加 `--log-text <描述>`；脚本不会用 `merge from ...` 替代描述（它只作为附加内容）。
- 正文中整行的机器人 `auto commit:` 日志：自动移除，并在缺省情况下补 `merge from <源分支tag> r<修订>` 附加内容，输出 `TARGET_LOG_ROBOT_LINE_REMOVED`。
- 其他位置出现 `auto commit:` 字样：输出 `TARGET_LOG_AUTO_COMMIT_TEXT_WARNING` 告警，不自动改动。

外放/正式分支合并时，如果源日志是机器人的 `auto commit:Merged revision ...`（周维护提交）或缺少维护单号，用下列参数生成合规日志：

```powershell
python "<skill-dir>\scripts\svn_merge.py" replay `
  --source-url "<source-url>" `
  --target-wc "<release-wc>" `
  --revs <rev1> <rev2> `
  --log-ticket <维护单号> `
  --log-keyword finish `
  --log-text "<描述>" `
  --log-extra "merge from trunk r2685000" `
  --message-dir "<doc-root>\messages" `
  --commit
```

- `--log-ticket <单号>`：本次外放关联的（维护）单号，缺省 `finish #单号 描述`；`--log-ticket 热更` 生成 `#热更 描述`。必须同时能给出描述：要么用 `--log-text`，要么源日志里存在带单号、带描述的日志行；只给单号会直接失败。
- `--log-keyword finish|refs`：缺省 `refs`；与 `--log-ticket` 同时使用时缺省 `finish`。
- `--log-text <描述>`：显式描述；缺省从源日志首行推导（保留 `[作者]` 标签），首行推导不到时退回正文里带单号的日志行。
- `--log-extra <附加内容>`：附加内容；缺省在源日志含机器人 `auto commit:` 行时自动补 `merge from <源分支tag> r<修订>`。

## 提交消息规则

普通逐版本重放默认不要使用 `--preserve-log-through`，因为它会完整保留源日志并绕过作者插入。

- 默认只改写提交日志第一行；周维护模式例外，不改写源日志首行，不插入 `[作者]`。
- 把 SVN 作者插入工单前缀后面：
  `#659151 fix crash` -> `#659151 [xuxuming]fix crash`
- 周维护且明确提交时必须同时传 `--weekly-maintenance --commit`，提交日志首行会增加：
  `auto commit:Merged revision <rev>(<author>) from <branch-tag>`，其后的源日志保持原样。
  这个 `auto commit:` 首行只允许周维护版本合并的机器人调用使用；人工外放或定向合并到正式分支时必须改用
  `--log-ticket`/`--log-keyword` 生成 `finish/refs #单号` 日志，详见“目标分支提交日志规范（必须）”。
- 只有明确需要从 `svn log -g` 的 merge history 推断原始作者时，才传
  `--infer-merge-history-author`；默认不启用该推断。
- 作者包含邮箱或域后缀时，默认去掉 `@` 后的部分。
- 已有作者标签只有匹配作者白名单或当前源修订作者时才视为作者标签。
- `[effectpanel]`、`[ZGUI]` 这类模块标签不要当作者。
- 对用户显式指定“保留原日志”的修订，使用 `--preserve-log-revs <rev-list>`。
- `--preserve-log-revs` 保留的日志同样要过“目标分支提交日志规范（必须）”校验：在正式分支上保留机器人的
  `auto commit:` 日志会失败，需要改用 `--log-ticket` 生成 `finish/refs #单号` 日志，或 `--skip-revs` 跳过。

## 冲突处理

不要盲目使用 `--accept theirs-full` 或 `--accept mine-full`。只有使用者明确批准某个文件采用源侧或目标侧整体内容时才允许。

处理冲突时：

1. 阅读 `.working`、`.merge-left`、`.merge-right`，或等价的源侧、基线和目标侧内容。
2. 分清源分支语义、目标分支语义和编码/EOL 噪声。
3. 同时保留有效的源侧和目标侧语义，不能把目标分支已有修复回滚到源基线。
4. 对每个需要人工判断的冲突，在 `<doc-root>\` 写入 `<revision>_<short-log-summary>.md`，记录冲突文件、源意图、目标意图和最终选择。
5. 使用结构化解析或字节安全编辑处理非 UTF-8 文件，避免静默转码。
6. 重新运行：

```powershell
svn status "<target-wc>"
svn diff "<target-wc>"
svn mergeinfo --show-revs merged "<source-url>" "<target-wc>"
svn mergeinfo --show-revs eligible "<source-url>" "<target-wc>"
```

7. 确认没有 `<<<<<<<`、`=======`、`>>>>>>>`，没有 `.working`、`.merge-left`、`.merge-right`、`.mine`、`.rNNN`、`.rej`、`.orig` 等冲突临时文件。
8. 大修订或语义冲突复杂时，启动独立审查子任务，对比源修订和当前工作副本 diff，检查遗漏、误回滚、字符漂移、BOM、CRLF/LF 和中文乱码。

如果使用者明确要求代理“继续处理冲突”，解决冲突后不要再逐个停下等确认；但每次提交前仍必须完成文档、检查、提交消息、日志校验和更新。

## WXSP/Fenghun 特例

如果当前合并项让 `shmm/shmm.fbs` 或 `shmm/shmm_generated.h` 发生冲突或版本化修改：

1. 只按三方语义解决 `shmm/shmm.fbs`。
2. 在提交前运行目标工作副本中的 `shmm\flatc.bat` 重新生成 `shmm/shmm_generated.h`。
3. 不要手工编辑或手工合并生成头文件。
4. 检查生成文件没有冲突标记、编码损坏、BOM 漂移或异常 EOL 漂移。

## svn:externals 特例

处理 `svn:externals` 时要保守。新目标分支可能已经把 release externals 更新到更近路径，而源分支仍指向旧 release。

- 对比源基线、源修改后和当前目标的 `svn:externals`。
- 只应用源修订明确拥有的 external 改动。
- 保留目标分支已经前进的无关 external 行。
- 在冲突文档里记录保留、删除和新增的 external 行。
- 周维护中，纯 `svn:externals` 属性修改应自动进入 `SKIP`，不要 merge 到目标分支。
- 周维护中，如果混合提交只产生 `svn:externals` 属性冲突，脚本可以自动保留目标分支的 `svn:externals` 并 `svn resolve --accept working`；如果同时存在文本冲突、树冲突或非 `svn:externals` 属性冲突，仍必须中止并人工处理。

## 锁和中断恢复

如果 `svn update`、脚本内部 merge/dry-run 超时或中断，或 `svn status` 出现 `L`：

1. 检查是否仍有同一工作副本的 SVN 进程在运行。不要在真实 SVN 操作仍运行时 cleanup。
2. 没有活动 SVN 操作后，在工作副本根目录执行：

```powershell
svn cleanup "<target-wc>"
```

3. 重新运行 `svn status` 确认锁消失。
4. 如果逐版本脚本超时并留下半合并状态，先杀掉残留 `svn.exe`，执行 `svn revert -R <target-wc>`，只删除目标工作副本内的 SVN 冲突临时文件，再确认工作副本干净后从同一个重放项重新开始。

## 编码和 EOL 检查

提交前检查：

- 没有 UTF-8 replacement bytes `EF BF BD` 增量。
- 中文注释和提交消息没有变成 `????` 或乱码。
- 非 UTF-8 文件不要用会自动转成 UTF-8 的工具重写；唯一例外是 `svn_merge.py` 已识别为“源/目标编码不同导致的可安全文本冲突”时，自动解决结果按周维护规则统一保存为 UTF-8，并同步修正 Python `coding` 声明。
- 不要无故统一换行符。只有证据显示源/目标的换行变化是合并噪声时才做机械修正，并记录原因。
- 如果源修订本身引入乱码或混合 EOL，把它记录为源侧风险，不要在合并时擅自修复。

## 必须汇报

执行 SVN 合并任务时，最终必须汇报：

1. HTTPS relocate 的处理结果。
2. 源 URL、目标 URL 和目标工作副本。
3. 合并文档目录。
4. 候选修订来源：明确指定、日志匹配、或 eligible 推导。
5. 脚本计划摘要、脚本 dry-run 结果摘要和使用者确认的最终修订列表或范围。
6. 实际合并或重放的修订列表。
7. 冲突列表和每个冲突的处理选择。
8. `svn:mergeinfo` 检查结果。
9. 执行过的构建或测试。
10. 如已提交，提交后的目标修订号。
11. 目标分支日志规范校验结果：`TARGET_BRANCH_KIND` 推导出的分支类型、实际使用的单号与关键词、是否出现
    `TARGET_LOG_KEYWORD_ADDED`、`TARGET_LOG_TICKET_APPLIED`、`TARGET_LOG_ROBOT_LINE_REMOVED`、
    `TARGET_LOG_POLICY_VIOLATION`、`TARGET_LOG_AUTO_COMMIT_TEXT_WARNING` 等标记。
