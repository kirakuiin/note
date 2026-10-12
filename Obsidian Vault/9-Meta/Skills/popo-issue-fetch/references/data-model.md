# PopoMgr 数据模型与排错

需要写自定义查询、或 CLI 的输出不够用时再读这份文档。日常拉单只看 `SKILL.md` 就够了。

## 目录

- [数据源](#数据源)
- [工单字段](#工单字段)
- [枚举值](#枚举值)
- [任务（制作内容）字段](#任务制作内容字段)
- [人员映射](#人员映射)
- [自定义查询示例](#自定义查询示例)
- [常见报错](#常见报错)

## 数据源

| 项 | 值 |
|---|---|
| 地址 | `mongo.eros.nie.netease.com:30000`（MongoDB 3.2.22） |
| 库 | `popo_mgr_tool` |
| 工单集合 | `issues_xyq`（梦幻西游；平台上每个项目一个集合，如 `issues_xyq_server`） |
| 任务集合 | `task`（按 `project_id: "xyq"` 区分项目） |
| 人员表 | `ci.user_info_new` |

连接参数都在 `src/config.py`，可以用环境变量 `POPO_MONGO_HOST` / `POPO_MONGO_PORT` /
`POPO_MONGO_USER` / `POPO_MONGO_PASSWORD` 覆盖。

**驱动版本是硬约束**：服务端 3.2 的最高 wire version 是 4，而 `pymongo` 4.x 只支持 wire version 6+
（MongoDB 3.6 起），握手阶段就会被服务端断链。所以 `requirements.txt` 锁 `pymongo>=3.12,<4`，
`PopoClient.__init__` 也会在连接前检查版本并直接给出修复命令，免得白等 8 秒超时再去猜原因。

软删除的工单带 `delete` 字段，所有查询都要叠加 `{"delete": {"$exists": False}}`，
否则会把已删除的单当成有效单。

## 工单字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `readable_id` | int | 平台上显示的单号，如 `291418`，用户口头说的就是这个 |
| `_id` | ObjectId | 内部主键，一般用不到 |
| `subject` | str | 标题/正文，可能多行（`\r\n`），`[图片]` 占位符按序对应 `img` |
| `markdown` | str | 补充说明，约 30% 的单子才有 |
| `way_text` | str | 重现步骤，`[图片]` 占位符按序对应 `way_img` |
| `way_img` | list[str] | 重现步骤截图直链 |
| `img` | list[str] | 标题区截图直链 |
| `client_info` | dict | 客户端附件，如 `{"wslog": "https://mheditor.s3.netease.com/BugData/.../wslog.txt"}` |
| `type` | str | 工单类型，见枚举 |
| `status` | str | 当前状态，见枚举 |
| `priority` | str | `P0`~`P3`，`P0` 最高 |
| `assignee` | str | 当前处理人账号 |
| `author` | str | 提单人账号 |
| `followqa` | str | 跟进 QA 账号 |
| `taskid` | str | 所属任务的 ObjectId 字符串 |
| `ctime` | str | 最近一次状态变更时间（**不是创建时间**），格式 `YYYY-MM-DD HH:MM:SS` |
| `changelst` | list[dict] | 状态流转历史，`{status, person, time}`；第一条的 time 才是提单时间 |
| `assignlst` | list[dict] | 指派历史，`{person, time}` |
| `first_commit_time` | str | 首次提交标记 |
| `reply_time` | str | 回复时间 |
| `redmine_sync_id` | int | 同步到易协作（Redmine）的单号 |
| `redmine` | bool | 是否已同步易协作 |
| `popo_group_num` | int | 提单来源的 popo 群编号 |
| `origin_subject` | str | 原始标题（被编辑过时保留） |
| `tag` / `coder` | str | 偶尔出现的标签、代码负责人 |

截图是内网 S3 直链（`http://gadev2-sunshine.s3dev-ga.nie.netease.com/popomgr/images/...`），
可直接 `GET` 下载，无需鉴权。单张常见 0.5~2 MB。

`ctime` 语义要特别注意：它随状态流转刷新，所以按 `ctime` 倒序拿到的是「最近有动静的单」，
不是「最新提的单」。要真正的提单时间用 `changelst[0]["time"]`。

## 枚举值

状态：`新建`、`已完成`、`描述不清`、`完成转回`、`暂不修复`、`无需修复`、`关闭`

其中还需要开发处理的是 `新建` / `描述不清` / `完成转回`，CLI 的 `--status open` 就是这三个。

类型：`BUG`、`建议`、`备忘`、`阻碍性BUG`、`高优先BUG`、`优先需求`、`经典BUG`、`资源BUG`、`历史BUG`

优先级：`P0`、`P1`、`P2`、`P3`

## 任务（制作内容）字段

| 字段 | 说明 |
|---|---|
| `_id` | 任务 ID（工单的 `taskid` 指向它） |
| `task_name` | 任务名，通常形如 `#816031 全屏战斗界面`，前缀是易协作上策划单的单号 |
| `status` | 字符串 `"true"` 表示进行中，其他表示已关闭 |
| `project_id` | 项目标识，梦幻西游客户端是 `xyq` |
| `ctime` | 创建时间 |

任务名里的 `#643675` 是易协作（Redmine）上**策划单**的单号，和工单自己的 `readable_id`（如 `291418`）
是两套编号，别混用。所以「给一个策划单号，找这个单下我的工单」的路径是：
`search <策划单号>` 拿 `task_id` → `issues --task-id <task_id>`。已收尾的制作内容要在两步都加
`--status all`，否则任务（`status != "true"`）和工单（默认只看待处理状态）都会被默认过滤掉。

平台没有「任务成员」关系表，人和任务的关联只能通过工单的 `assignee` 聚合反推——
这也是 `tasks` 命令的实现方式，所以一个任务里没给你派过单，它就不会出现在你的列表里。

## 人员映射

`ci.user_info_new` 里 `_id` 是账号，`firstname` 是姓名，形如 `L黎靖宇`（姓氏首字母 + 中文名）。
`PopoClient.resolve_person` 依次尝试：账号精确 → 完整姓名精确 → 去前缀的中文名 → 包含匹配。
同名同姓时包含匹配可能命中错人，结果里会带上账号，核对一下再往下走。

「本人」由 `config.detect_person()` 推断：先看环境变量 `POPO_USER`，否则取当前登录用户
（`getpass.getuser()`，Windows 上即 `USERNAME`）。内网机器的登录名通常与平台账号一致，
所以默认的「指派给本人」过滤不需要手输账号；推断结果会打印出来并带上来源，认错人时一眼能看出。

## 自定义查询示例

```python
# 在 skill 目录下执行；从别处调用时先把 skill 目录加进 sys.path
from src.client import PopoClient, NOT_DELETED, render_issue

client = PopoClient()

# 某任务下所有 P1 及以上的未关闭 BUG
cursor = client.issues_col.find(dict(
    NOT_DELETED,
    taskid="6a8cf791049cbe0026bd93e3",
    type="BUG",
    priority={"$in": ["P0", "P1"]},
    status={"$in": ["新建", "描述不清", "完成转回"]},
))
for issue in cursor:
    print(issue["readable_id"], issue["subject"].splitlines()[0])

client.close()
```

写聚合时注意这是 MongoDB 3.2：不支持 `$in` 作为聚合表达式（`$cond` 里要用 `$or` + `$eq`），
也不支持 `$lookup` 的很多新写法。遇到 `invalid operator '$xxx'` 基本都是版本问题。

## 常见报错

| 现象 | 原因与处理 |
|---|---|
| `connection closed` / `ServerSelectionTimeoutError` | 装了 `pymongo` 4.x。`python -m pip install "pymongo>=3.12,<4"`；若别的项目要 4.x，在 skill 目录**之外**建虚拟环境（别在 skill 里装依赖） |
| `invalid operator '$in'` | 聚合里用了 3.4+ 的表达式，改写成 `$or` + `$eq` |
| 控制台中文乱码 | 用 CLI（内部已强制 UTF-8 stdout）；自己写脚本时也要包一层 `io.TextIOWrapper(..., encoding="utf-8")` |
| `找不到人员: xxx` | 换账号或去掉姓名前缀字母重试；确认此人确实在 `ci.user_info_new` 里 |
| 查出来 0 条单 | 默认只看待处理状态，加 `--status all`；也确认 `--task-id` 没写错 |
| 图片下载失败 | 需要内网；`download_issue_images` 会把失败原因写在返回值里而不是整体报错 |
| `pip install` 报 `UnicodeDecodeError` | `requirements.txt` 必须保持纯 ASCII，pip 用系统 GBK 读它 |
| 截图落在 skill 目录 | CLI 会拒绝；`--images`/`--out` 省略路径即用 `%TEMP%\popo_images\<单号>` |
