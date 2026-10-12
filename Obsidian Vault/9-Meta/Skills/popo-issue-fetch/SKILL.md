---
name: popo-issue-fetch
description: 从 popo 提单平台（PopoMgr）拉取指派给本人的工单，读正文、重现步骤和截图，再动手修 bug。用户提到提单平台、popo 工单、我的单子、任务/制作内容下的工单、6 位数字单号、重现步骤或工单截图时都用它，不要凭记忆猜工单内容。
metadata:
  version: 1.0.0
---

# Popo 工单拉取与修复

梦幻西游的策划/QA 在 popo 提单平台（PopoMgr）上提单，单子挂在「制作内容（任务）」下，指派给具体开发。
最关键的信息在**内容字段**里：`subject`（问题描述正文）和 `markdown`（补充说明），这是判断要改什么的主要依据。
列表里看到的标题只是正文的第一行，很多单子的关键条件、期望效果都在后面几行或补充说明里。
另外正文里的 `[图片]` 只是占位符，图片 URL 单独存放，所以有图的单子必须把图取下来才算读完整；
也有不少单子本来就没有截图，纯文字描述清楚就够用，这是正常情形，不用去找图。
总之顺序是**先完整读正文和补充说明，有图再补上图，然后才改代码**，凭标题一行就动手是最常见的返工原因。

平台没有对外 HTTP API，工单存在 MongoDB 里。本 skill 封装了只读访问：查任务、列工单、读正文、下载截图。
**只读，不写**——不改状态、不回复、不重新指派，流转仍由本人在 popo 上操作，避免 agent 误动线上数据。

## 依赖（每台机器一次，用系统 Python 3.11+ 即可）

先 `cd` 到本 skill 目录（`SKILL.md` 所在目录），后面所有命令都在这里执行：

```powershell
python -m pip install -r requirements.txt
python cli\popo.py --help
```

`requirements.txt` 把 `pymongo` 锁在 `3.x`，这不是随手写的下限：平台的 MongoDB 还是 3.2，
`pymongo` 4.x 只支持 3.6+，握手会被服务端直接断开，报出来的是很难联想到版本问题的
`connection closed` / `ServerSelectionTimeoutError`。所以看到这个报错先查 `pymongo` 版本。

**不要在 skill 目录里装依赖或建虚拟环境**（`.deps\`、`.venv\` 这类都不行）：这里是 SVN 工作副本，
几千个文件会污染 `svn status`、还可能被误提交。如果这台机器上有别的项目依赖 `pymongo 4`、不方便全局降级，
就把虚拟环境建在 skill 目录**之外**，再用它的解释器跑本 skill：

```powershell
python -m venv $env:TEMP\popo-skill-env
$env:TEMP\popo-skill-env\Scripts\python.exe -m pip install -r requirements.txt
$env:TEMP\popo-skill-env\Scripts\python.exe cli\popo.py --help
```

### 「本人」是怎么定的

默认筛选规则是**工单的 `指派` 字段等于本人**，`--person` 可以不填：内网机器的 Windows 登录名一般就是平台账号，
CLI 会按「环境变量 `POPO_USER` > 当前登录用户」推断，并在输出第一行打印用了哪个账号、来自哪里，方便发现认错人。

推断不出来或登录名与平台账号不一致时（比如共用机器、账号改过），显式指定或写进环境变量：

```powershell
python cli\popo.py issues --person <账号或中文名>
$env:POPO_USER = "<账号或中文名>"
```

要查别人或整个任务的单，用 `--person <别人>` 或 `--all-assignees` 显式取消这个默认过滤。

## 主线工作流

### 1. 找到自己的制作内容（任务）

```powershell
python cli\popo.py tasks
```

输出里 `待处理` 列是这个任务下还挂在本人名下的单数。要查别人时 `--person` 支持账号（`wangzhuowei`）、
完整姓名（`W王卓为`）、纯中文名（`王卓为`）三种写法——平台存的是带前缀的姓名，只认一种会误判成「没有单」。

只知道项目名不知道任务 ID 时用 `search`：

```powershell
python cli\popo.py search 全屏战斗
```

#### 从策划单号反查

任务名前缀形如 `#643675 登录相关dprf log接入`，这个 `#643675` 是**易协作上策划单的单号**
（策划提的那张制作需求单），不要和 popo 工单号混淆——后者是 6 位纯数字的 `readable_id`（如 `291418`），
是 `show` 命令的参数。拿着策划单号直接搜任务即可：

```powershell
python cli\popo.py search 643675 --status all   # 643675 = 策划单号
# | 任务ID                   | 任务名                   | 状态   |
# | 6912a116c0dad200679040ab | #643675 登录相关dprf log接入 | 已关闭 |

python cli\popo.py issues --task-id 6912a116c0dad200679040ab --status all
```

两个 `--status all` 都不是可有可无的：`search` 默认只看进行中的任务，`issues` 默认只看待处理的单。
**回顾一个已收尾的策划单时，两处都得放开，否则会得到「搜不到任务」或「0 条工单」的假象。**
搜不到时也试试换关键词——带不带 `#` 都能匹配，但任务名里的文字可能和策划单标题不完全一致。

### 2. 列出待处理工单

```powershell
python cli\popo.py issues                                   # 本人所有待处理单
python cli\popo.py issues --task-id 6a8cf791049cbe0026bd93e3 # 限定某个制作内容
```

默认两条过滤：`指派 = 本人`，以及 `--status open`（**新建 / 描述不清 / 完成转回**这三种还需要处理的状态）。
`--status all` 看全部，也可以直接写具体状态名。其他常用开关：
`--type BUG`、`--priority P1`、`--limit 100`、`--person <别人>`、`--all-assignees`（配合 `--task-id` 看整个任务的单）。

列表里的标题是截断过的，`[图片]` 占位符也说明还有图没看——挑中要处理的单，都走第 3 步读全文。

### 3. 读透单个工单

```powershell
python cli\popo.py show 291418 --images --history
```

输出是一段 Markdown：元信息、问题描述、补充说明、重现步骤、附件。**先把问题描述和补充说明读完**，
这两段决定了要改什么；`补充说明` 常常是开发/QA 后来追加的结论或约束，别跳过。

`--images` 不带路径时，截图会存到**系统临时目录** `%TEMP%\popo_images\<单号>\`，并把正文里的
`[图片]` 占位符替换成本地路径；**这时用看图能力把每张图打开看一遍**，报错弹窗、UI 错位对比、
日志片段这类信息只能从图里拿到。没有截图时命令会提示「这个工单没有截图」，照着文字描述往下走即可。

**不要把截图下载到 skill 目录下的 `popo_images\`，也不要放进 mhimage/engine 的 SVN 工作副本。**
这些是一次性排查材料，混进代码库会被误提交，看完就该删，需要时随时能重新拉。
CLI 已经做了硬拦截：`--images`/`--out` 指向 skill 目录内会直接报错退出；
要自定义位置就显式给一个临时路径，例如 `--images $env:TEMP\popo_291418`。

`附件` 段落里如果有 `wslog` 之类的链接，那是提单人客户端的运行日志，排查崩溃/报错时值得下载。
需要结构化数据（喂给脚本或做批量分析）时加 `--json`。

### 4. 定位并修复

读懂单子后按正常开发流程走，仓库约定见工作区根目录的 `AGENTS.md`：
脚本改动在 `mhimage_*` 分支目录，引擎改动在 `engine2.0_*`，分支含义和 SVN 地址都在那份文档里。
先确认单子该落在哪个分支（主干还是外测/灰度），再动手。

修完回报时把这些说清楚，方便本人去 popo 上流转：

- 单号与结论（是 bug / 是预期行为 / 需要策划补充说明）
- 根因，以及是哪张截图或哪段日志支撑这个判断
- 改了哪些文件、改在哪个分支
- 怎么自测的、还有什么风险没覆盖

如果读完发现描述不足以定位（截图缺失、步骤含糊、复现条件不明），不要硬猜：把缺什么列出来，
建议本人在平台上流转成「描述不清」并 @ 提单人。

## 命令速查

| 目的 | 命令 |
|---|---|
| 我参与的制作内容 | `python cli\popo.py tasks` |
| 按名字搜任务 | `python cli\popo.py search 全屏战斗` |
| 按策划单号找任务 | `python cli\popo.py search 643675 --status all` |
| 我的待处理单 | `python cli\popo.py issues` |
| 某任务下我的单 | `python cli\popo.py issues --task-id <任务ID>` |
| 某任务下我的全部单（含已关闭） | `python cli\popo.py issues --task-id <任务ID> --status all` |
| 别人的单 | `python cli\popo.py issues --person <账号或中文名>` |
| 某任务全员的单 | `python cli\popo.py issues --all-assignees --task-id <任务ID> --status all` |
| 读单 + 存图 | `python cli\popo.py show 291418 --images`（默认存 `%TEMP%\popo_images\291418`） |
| 单里的截图 | `python cli\popo.py images 291418` |
| 结构化输出 | 任意命令加 `--json` |

批量场景（例如「把这个任务下我的 10 个单都过一遍」）：先 `issues` 拿单号列表，
再对每个单号 `show --images`，默认就会按单号分目录，避免图片互相覆盖、看错图。
全部看完后清掉 `%TEMP%\popo_images`。

## 读工单时容易踩的点

- `subject` 里的 `[图片]` 对应 `img`，`way_text` 里的 `[图片]` 对应 `way_img`，按出现顺序一一对应。
  `show` 已经替你对齐了；直接读 `--json` 时别把两组图混起来，否则会把「现状截图」当成「期望效果」。
- `markdown` 是补充说明，只有部分单子有；里面常是开发/QA 后续追加的结论，值得优先读。
- `type` 里的「备忘」不等于「可以不做」，策划经常用备忘提改动需求；判断轻重看 `priority`。
- 时间字段是字符串（`2026-09-29 15:07:28`），不是日期类型，做区间筛选时按字符串比较。
- `redmine_sync_id` 是同步到易协作的单号，跨系统对工时/进度时用它对齐。
- 字段完整语义、状态/类型枚举、排错方法见 `references/data-model.md`。

## 边界

- 只读线上数据库，不要在本 skill 里加写操作；状态流转、回复、指派都由本人在 popo 上做。
- 工单内容属于项目内部资料（含玩家 ID、日志、未发布功能），只在本地使用，不要外发或贴到外部服务。
- 截图单张可能有 1~2 MB，只放系统临时目录（默认行为），任务结束后清掉 `%TEMP%\popo_images`。
- **skill 目录只放源码，不产生任何文件**：依赖、虚拟环境、截图、导出结果一律放 `%TEMP%` 或其他目录。
  这里是 SVN 工作副本，生成物会污染 `svn status` 并可能被误提交。

## 参考

- `references/data-model.md`：字段语义、枚举、Mongo 连接细节与常见报错处理。
