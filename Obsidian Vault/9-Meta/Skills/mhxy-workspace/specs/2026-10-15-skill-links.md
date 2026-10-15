# skill 链接自检

日期：2026-10-15　版本：0.3.25

| 代码 | 说明 |
| --- | --- |
| `scripts/skill_links.py` | 检查并修复链接 |
| `scripts/workspace.py` | `context` 调用 |

## 目标

skill 的真实文件放在共享目录（笔记库 `9-Meta/Skills/`），用 junction 链接进 `~/.claude/skills` 和 `~/.codex/skills`。这些链接曾被外部工具重置，导致 `grilling` 等 skill 消失。会话开始时自动发现并修复，不需要用户处理。

## 方案

- **时机**：每次 `context`（Claude Code 由 SessionStart hook 运行，Codex 按入口规则运行）。只在 mhxy 工作区的会话里触发；其他目录的会话不检查，可手动运行 `skill_links.py`。
- **范围**：本 skill 上级目录中每个含 `SKILL.md` 的子目录；工具目录（`~/.claude`、`~/.codex`）存在才处理对应的 skill 目录。上级目录本身就是工具的 skill 目录时（直接安装）不处理。
- **修复**：缺失就新建 junction（`_winapi.CreateJunction`，不需要管理员权限）；是链接但指向别处或失效就移除链接后重建。同名普通目录或文件不动，记为问题。只删除链接，不删除目标。
- **输出**：补建的链接列在 context 的 `skill_links_repaired`，失败和冲突进 `problems`。

## 验收

- 单元测试：新建、幂等、替换错误或失效的链接且不碰目标、不替换普通目录、直接安装时跳过。
- 真实环境：恢复了两边各 16 个缺失的链接。
