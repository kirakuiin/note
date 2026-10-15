# 工作区管理

本文件是以下内容的唯一说明：配置、密码、入口文件、需求索引、Claude Code hook 和个人目录清理。其他文档只引用这里。下文 `<skill>` 指本 skill 的安装目录，`<项目>` 指项目根目录。

## 配置

**位置**
- 用户级：`~/.mhxy-workspace/config.json`，所有工作区共用。
- 工作区级：`<项目>/.mhxy-workspace/config.json`，可选。按键覆盖用户级（包括显式 null），未提供的键继承用户级。账号和密码不能放在这里。

**字段**

| 键 | 含义 | 是否必须确认 | 取值 |
| --- | --- | --- | --- |
| `pc_client_dir`／`ht_client_dir` | PC／互通客户端运行根目录（启动程序和 `Log/`） | 是 | 绝对路径或 null |
| `engine_dir` | 引擎源码目录，用于查 API 和底层实现，不是运行目录 | 是 | 绝对路径或 null |
| `global_resources_dir` | 全局共享资源（UI、造型等） | 是 | 绝对路径或 null |
| `design_config_dir` | 策划配置源目录（导表输入） | 是 | 绝对路径或 null |
| `openid_username` | OpenID 账号，工单查询、覆盖率、提测、提 CR 登录用 | 否 | CORP 邮箱（`@corp.netease.com`）或 null |
| `openid_password` | OpenID 密码，只存在用户级配置中 | 否 | 只能隐藏输入（见「密码」）；任何输出里都显示为 `***` |
| `coder_name` | 覆盖率开发者名，用于 diff 过滤 | 否 | 邮箱前缀；为 null 时自动取 `openid_username` 的前缀 |
| `default_devid` | 按 IP 查找不到调试设备时的兜底设备 ID，见 game-debugging.md「选择设备」 | 否 | 设备 ID 或 null |
| `branches_root` | 开发分支总目录，创建或检出分支时使用，见 branch.md | 否 | 绝对路径或 null |
| `login_accounts` | 自动启动客户端用的游戏账号池，按优先顺序排列，只存在用户级配置中，见「账号池」 | 否 | 只能用 `login-account` 维护；输出中只显示账号 |
| `login_server` | 自动启动客户端登录的服务器名（如 `王卓为-trunk`、`模拟14`），每个分支通常固定，一般放工作区级 | 否 | 单行服务器名或 null |

null 表示明确不配置；用到该项时再请用户补齐。只有五个路径是初始化的必填项。

**命令**（`sync` 和 `config` 默认只预览，加 `--apply` 才写入）

```text
python "<skill>/scripts/workspace.py" sync    --root "<项目>" [--set-global "键=值"]... [--set-local "键=值"]... [--apply]
python "<skill>/scripts/workspace.py" config  --set-global "键=值"... [--prompt-password] [--apply]
python "<skill>/scripts/workspace.py" context --root "<项目>"
```

- `sync`：初始化或更新工作区，可同时设置配置。
- `config`：用 `--set-global` 只改用户级配置；用 `--root` 加 `--set-local` 只改工作区级配置。都不碰入口文件。
- `context`：查看合并后的配置（已脱敏），以及追踪工单和索引状态；同时修复 skill 链接，见下节。
- 值写 `键=null` 表示不配置。

## skill 链接自检

本 skill 和同级的其他 skill 放在一个共享目录（如笔记库 `9-Meta/Skills/`），用目录联接（junction）链接进 `~/.claude/skills` 和 `~/.codex/skills`。这些链接曾被外部工具重置，所以每次 `context`（包括 SessionStart hook）都运行 `scripts/skill_links.py` 的检查：

- 共享目录下每个含 `SKILL.md` 的子目录，在已安装工具（`~/.claude`、`~/.codex` 存在）的 skill 目录里都应有指向它的链接。缺失就新建，指向别处或已失效就替换；只删除链接本身，不碰任何目标目录。
- 同名的普通目录或文件不替换，记入 `problems`，由用户处理。
- 补建过的链接列在 context 的 `skill_links_repaired` 里。Claude Code 会在会话中途发现新链接的 skill，Codex 要到新会话才加载；告诉用户哪些链接补建了。
- skill 直接装在工具的 skill 目录里（没有共享目录）时不做任何事。也可以单独运行 `python "<skill>/scripts/skill_links.py"` 检查和修复。

**规则**
- 配置文件只由脚本写入。不要手写 JSON，也不要直接输出配置原文。
- 发现的路径只作建议，由用户确认。脚本报告目录不可用时请用户核实，不要自动替换。
- 修改 `openid_username` 会清掉旧密码。

## 密码

密码不能出现在命令行参数里，只能在交互终端隐藏输入：

```text
python "<skill>/scripts/workspace.py" config --set-global "openid_username=<CORP邮箱>" --prompt-password --apply
```

`--prompt-password` 必须和 `--apply` 一起使用，否则在询问之前就报错。脚本要求 stdin 和 stderr 都是终端，否则直接报“需要交互终端”而不是等待输入。agent 的命令工具通常没有交互终端（Claude Code 的 Bash／PowerShell 工具都没有），此时：
- **Claude Code 桌面版**：用 Terminal 面板工具（`run_in_terminal`）启动上面的命令，请用户在面板里输入密码。
- **其他情况**：把完整命令交给用户在自己的终端运行，完成后再继续。

不要用其他方式绕过。清空密码用 `config --set-global "openid_password=null" --apply`。工单查询和覆盖率脚本在没有已存密码时也只在交互终端询问，处理方式相同。

## 账号池

自动启动客户端（game-debugging.md「自动启动客户端」）按顺序选第一个没被本机在线客户端占用的账号，登录第一个角色。账号和密码只存在用户级配置中，密码只能隐藏输入（输两遍核对，不一致不保存），交互终端的要求和处理方式同「密码」：

```text
python "<skill>/scripts/workspace.py" login-account --account <游戏账号> --apply                    # 新增（排在最后）或更新密码
python "<skill>/scripts/workspace.py" login-account --account <游戏账号> --remove-account --apply   # 移除
```

服务器名由用户说出即可，保存到当前工作区：`config --root "<项目>" --set-local "login_server=<服务器名>" --apply`（只写工作区级配置，不动入口文件）。

## sync 做什么

- **配置**：写入通过 `--set-global`／`--set-local` 传入的值；第一次运行时，工作区级配置创建为空对象。
- **AGENTS.md**（Codex 读取）：写入完整规则区段，模板是 `assets/managed-block.md`，脚本只替换管理元数据（含版本）、`workspace.py` 脚本路径和 references 目录路径。
- **CLAUDE.md**（Claude Code 读取）：只写元数据和一行 `@AGENTS.md`，模板是 `assets/claude-block.md`。文件不存在时创建；旧版写入的完整区段会替换为导入行。
- **Claude Code hooks**：在 `<项目>/.claude/settings.local.json` 中登记两项。只增改命令带 `--from-hook` 的本 skill 条目，保留其他设置。
  - SessionStart：运行 `context --from-hook`，使会话开始、恢复、清空和上下文压缩后都自动加载 context。
  - PostToolUse：运行 `index --from-hook`，写入 spec 后立即收录。
- **需求索引**：没有收录名单时新建（起点为当前时间、名单为空），然后刷新，见下节。
- **保留的内容**：区段外的内容、原有编码（UTF-8、UTF-16 BOM、GB18030）和换行格式，以及工作区级配置。Codex 和 Claude Code 按 UTF-8 读取入口文件，所以 AGENTS.md／CLAUDE.md 不是 UTF-8 时 `warnings` 会提示，由用户决定是否转换；脚本不自动转换。
- **初始化只由 sync 完成**：`context`、`index`（包括 hook）、`track`／`untrack`、`coverage-task` 和 `precommit.py --mark-reviewed` 要求 `--root` 的 AGENTS.md 已有受管区段，否则报错且不写入，避免从子目录运行时另建一个 `.mhxy-workspace/`。hook 遇到这种情况时不阻断会话或工具：SessionStart 把错误放进注入的 `problems`，PostToolUse 静默跳过。
- **入口规则是否变化**：输出中的 `entry_rules_changed` 只比较 AGENTS.md 受管区段去掉管理元数据后的内容；单纯升级版本号不算变化。
- **安全检查**：先检查全部目标，再逐个文件原子替换；写入失败可捕获时回滚本轮变更。目标文件只读（例如 `svn:needs-lock` 未加锁）时，写入任何文件之前就报错，不自动去掉只读属性。遇到异常标记、未知结构版本或版本降级（AGENTS.md 或 CLAUDE.md 任一版本更新）时停止。内容无变化时不写入。进程被杀、断电或有其他程序同时写入时，不保证跨文件的原子性，重跑时先处理报出的不一致。不要删除标记来绕过报错。
- **防止误提交**：受版本控制的 `AGENTS.md`、`CLAUDE.md`（`AGENTS.md` 是团队规范文件）写入受管区段后，会显示为已修改。写入完成后，自动用 `svn changelist ignore-on-commit` 把它们放进 TortoiseSVN 提交对话框默认不勾选的变更列表。这只改本地工作副本的元数据，不影响服务器；真要提交团队规范的修改时，在对话框里手动勾选即可。
  - 预览时 `ignore_on_commit` 列出将要加入的文件。
  - 已在该列表中的跳过；在你自己建的其他变更列表中的不移动，只给出警告。
  - 未纳入版本控制或目录不是工作副本时跳过；svn 不可用或执行失败时只给出警告，不影响其余写入。
- **不修改**：业务代码、spec；除上一条外不执行任何 SVN 操作。升级 skill 不会自动同步工作区；安装路径变化后重新 sync 即可修复引用。

## 需求索引

`spec/` 是团队共用的，索引只收录**你在这个工作区里新建或修改的 spec**，不收录他人的或历史的 spec。

**起点**：`.mhxy-workspace/index-state.json` 记录起点时间、收录名单和排除名单。文件不存在时（首次初始化或清理之后），以当前时间为起点、名单为空，旧 spec 一律不收录。

**自动收录**（满足任一条件）：
- **Claude Code**：PostToolUse hook 监听 Write／Edit／MultiEdit，写入 `spec/` 下的 `.md` 后立即收录。
- **两边通用**：每次 `sync`、`context`、`index` 运行 `svn status spec`（只读），把起点之后修改过、且本地有改动（修改、新增、未纳入版本控制、替换、冲突）的 spec 加入名单。svn update 拉下的他人 spec 在本地没有改动，因此不会被收录。找不到 svn 或不是工作副本时跳过这一来源，不报错（输出中 `svn` 为 `unavailable`）。
- **合并未提交时**：svn merge 合并进来的他人 spec 在提交前也显示为本地改动，无法和自己的改动区分。因此项目根目录或 `spec/` 下有未提交的 `svn:mergeinfo` 变更时，跳过 svn 这一来源（输出中 `svn` 为 `merge_pending`）。这段时间自己改的 spec 只能通过 Claude Code 的 hook 或 `index --add` 收录；合并提交后恢复正常。

**名单维护**：
- 名单只增不减：提交后本地不再有改动，也仍保留。文件被删除或改名后，旧路径自动移出；改名后的新文件按上述规则重新收录。
- 手动调整：`index --add spec/...md` 收录（不受起点限制），`index --remove spec/...md` 移出，都可以重复。移出的路径记入 `index-state.json` 的排除名单，之后 svn 扫描和 hook 都不再自动收录它；再次 `--add` 时从排除名单中去掉。文件被删除后，排除记录也一并清除。
- 从 0.2.x 升级时，旧版手写索引里登记过的 spec 路径会迁入名单。

**index.md 的内容**：按 `spec/` 一级子目录分组，每篇取第一个标题和第一行正文（截断到 60 字），支持 UTF-8、UTF-16 和 GB18030。每次刷新都重新渲染，内容无变化时不写入；手工修改会被覆盖。想让索引更准确，就改进 spec 自己的标题和开头一句。

**查询**：`python "<skill>/scripts/workspace.py" index --root "<项目>" [--query 关键词]... [--add 路径]... [--remove 路径]...`。所有关键词都要命中，不区分大小写，最多返回 50 条。

## 清理个人目录

只在用户明确要求清理 `.mhxy-workspace/` 的全部内容时执行；“清理业务工作副本”不是这个动作。先预览，确认范围符合用户的要求后再应用；授权已经明确时不重复询问。

```text
python "<skill>/scripts/workspace.py" clean --root "<项目>"
python "<skill>/scripts/workspace.py" clean --root "<项目>" --apply
```

- **会删除**：`.mhxy-workspace/` 内的全部内容，包括工作区级配置、索引和收录名单、工单正文和图片、`tracking.json`、覆盖率登记和 Mock、改动执行检查的用例脚本、CR diff 及其清单和上传记录 `applied.json`（清理后脚本不再能拦截同一工单的重复上传）、`codex_cli.py` 的任务目录 `codex-cli/`、review 指纹 `review-mark.json`、会话交接文件 `handoff/`。目录本身保留为空；目录不存在时不创建。
- **拒绝清理**：`codex-cli/` 中有任务的 `state.json` 状态为 starting／running，或 test 任务（含 `lock` 建立的 native 任务）的 `released` 不是 true，或任务目录没有、无法读取 state.json（状态未知）时，预览和应用都报错并列出这些任务，不删除任何内容。请用户先等任务结束、取消或 release，再重新预览；没有 state.json 的目录按报错中的方法核实后由用户手动删除。
- **不会修改**：spec、业务代码、AGENTS.md、CLAUDE.md、用户级配置、用户级经验库 `~/.mhxy-workspace/lessons/` 和远端任务。
- **安全检查**：脚本先扫描全部待删项，遇到符号链接、目录联接或其他 reparse point 就整体停止。请用户先核实并处理该链接，再重新预览；不要用递归删除绕过。清理无法撤销；中途遇到文件占用等错误时，会报告可能已部分清理。不要在其他程序正在修改这个目录时清理。
- **清理之后**：下次 context 以当时为新起点建立空索引，之后只收录新建或修改的 spec。配置覆盖、追踪和覆盖率登记要等用户再做对应操作时才会重新创建，不需要重新初始化。
