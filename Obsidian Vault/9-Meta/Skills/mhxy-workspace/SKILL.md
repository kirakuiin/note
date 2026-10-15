---
name: mhxy-workspace
description: 仅在用户明确要求使用本技能初始化、更新梦幻西游工作区配置或清理个人辅助目录时执行；维护本机路径、AGENTS.md 与 CLAUDE.md 的受管区段及需求索引。不因普通开发、讨论初始化方案或更新业务代码而自动执行。
disable-model-invocation: true
---

# 梦幻西游工作区

为梦幻西游项目工作区安装本地工作约定，同时支持 Codex 和 Claude Code。只在用户明确要求**初始化、更新配置或清理**时执行。日常开发依靠入口文件里的规则，不需要调用本 skill。

当前目录就是项目根目录，不要向上寻找仓库；用户明确指定其他目录时（例如刚检出的分支）以该目录为准，所有命令的 `--root` 都传该目录。工作区脚本只需要 Python 3.10+ 标准库；Codex 委派脚本 `codex_cli.py` 需要 Python 3.11+。下文 `<skill>` 指本 skill 的安装目录。

## 初始化或更新配置

1. **预览**：`python "<skill>/scripts/workspace.py" sync --root "."`，只检查，不写入。
2. **补齐配置**（字段和规则见 [workspace-management.md](references/workspace-management.md)「配置」）：
   - 没有用户级配置时，询问五个路径：PC 客户端、互通客户端、引擎、全局资源、策划配置。不用的项让用户明确选择 null。脚本发现的路径只作建议，由用户确认。
   - 同时提醒可以配置 OpenID 邮箱和密码（覆盖率、工单查询会用到），这些都可以跳过。调试设备默认按 IP 自动查找，不需要询问。
   - `branches_root` 是开发分支总目录的可选配置，初始化时不询问；创建或检出分支时再按需配置。
   - 已有用户级配置但缺少字段时（预览输出的 `missing_fields` 不为空），只询问其中列出的项；已有的配置（包括 null）直接复用，不重复询问。
3. **应用**：在预览命令后加上收集到的 `--set-global "键=值"`，再加 `--apply`。用户已经要求初始化或更新时，不需要再单独请求批准。
4. **交付**：说明改了哪些文件和检查结果。预览报告目录不可用时请用户核实，不要自动替换已保存的值。在 Claude Code 中，告诉用户新写入或变化的 hooks 和 CLAUDE.md 要在新会话中才生效：当前会话不会收到 SessionStart 注入的 context，写入 spec 也不会经 PostToolUse 收录。
5. **入口规则有变化时**：输出中 `entry_rules_changed` 为 true（`notice` 会提示）时，重新读取 AGENTS.md 的受管区段，按实际内容向用户说明新增或变化了哪些规则。当前会话已加载的是旧版本，不要凭印象判断“没有变化”。

sync 会写入用户级配置、AGENTS.md 和 CLAUDE.md 的受管区段、Claude Code 的 hooks，并建立需求索引的收录起点；细节见 workspace-management.md「sync 做什么」。脚本会拒绝不完整的配置、异常标记和版本降级；按报错处理原因，不要手工绕过。

## 清理

用户明确要求清理 `.mhxy-workspace/` 时，按 [workspace-management.md](references/workspace-management.md)「清理个人目录」执行。

## 平台差异

| | Codex | Claude Code |
| --- | --- | --- |
| 读取的入口文件 | AGENTS.md（完整规则） | CLAUDE.md（通过 `@AGENTS.md` 导入同一份规则） |
| 会话开始加载 context | 按入口规则运行命令 | SessionStart hook 自动注入 |
| 禁止自动调用本 skill | `agents/openai.yaml` | 头部 `disable-model-invocation`，需用 `/mhxy-workspace` 手动调用 |
| MCP 工具 | 直接可见 | 可能需要先用 ToolSearch 加载，见 game-debugging.md |
| 委派（调查、review、真机自检） | 原生子代理 investigator／reviewer／verifier，见 cli.md「Codex 主会话」 | `scripts/codex_cli.py`，见 cli.md「Claude 主会话」 |
| 隐藏输入密码 | 取决于终端 | 命令工具没有交互终端，见 workspace-management.md「密码」 |

## 维护本 skill

- **每条规则只在一个文件里完整描述**，其他地方只放链接。归属：配置、密码、入口文件、索引、hook、清理 → `workspace-management.md`；其余按能力写在各自的 reference 里。入口模板 `assets/managed-block.md` 只放每次会话都要遵守的内容：会话开始、项目约定、需求索引和追踪工单的用法、「按需读取」表和边界；配置字段等细节只放链接，完整说明留在对应的 reference。
- 版本的唯一来源是 `config/version.json`。修改模板或行为时递增发布版本；结构不兼容时再递增结构版本（当前只支持 2）。
- 升级 skill 不会修改已有工作区；入口规则变化后，由用户在各工作区重新执行更新。references 直接从安装目录引用，改了立即生效。
- 新能力放进 `references/` 和 `scripts/`，并在入口模板的「按需读取」表里加一行。保持只依赖标准库；`cryptography` 只是 OpenID 登录的可选依赖。
- 测试：`python -B -m pytest -q -p no:cacheprovider tests`。
