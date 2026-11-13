---
name: mhxy-cov-testreport
description: 梦幻西游客户端覆盖率跑测、覆盖率网站查询与提测单（newtestreport）准备和保存。当用户要求创建/设置/跑测/补测/查询客户端代码覆盖率（scover、mh-mos2-coverage），或要求准备/填写/更新/保存客户端提测报告（提测单、newtestreport）时使用。
---

# 梦幻西游客户端覆盖率与提测

本技能提供独立的**客户端代码覆盖率（跑测 + 网站查询）**与**提测单（准备 + 预览 + 保存）**流程，不依赖 `mhxy-workspace` 本体，可直接分享给其他开发者使用。

下文 `<skill>` 指本技能目录，`<工作区>` 指客户端脚本工作副本目录（如 `.../mhimage`）。

## 环境要求

- **Python 3.10+**，登录 CORP OpenID 需要安装支持 SM4 的 `cryptography`：
  ```bash
  python -m pip install cryptography
  ```
- **覆盖率客户端跑测**：需要已接入 `mh-game-mcp`（入口 `https://mh-game-mcp.eros.nie.netease.com/mcp` 或 `/xyq-dev/mcp`），且本机客户端已开启 `inner_test` 并登录进游戏。仅查询覆盖率网站或操作提测单时不需要打开游戏客户端。

## 账号与密码配置

覆盖率网站查询与提测系统共用用户级配置文件 `~/.mhxy-workspace/config.json` 中的 CORP 账号（与 `mhxy-workspace` 完全兼容，互不覆盖其他字段）：

- `openid_username`：CORP 邮箱（如 `zhangsan@corp.netease.com`）或前缀
- `openid_password`：CORP 密码（**禁止写在命令行参数里**，只能在交互终端隐藏输入）
- `coder_name`：覆盖率开发者名（可选，缺省自动取 `openid_username` 的邮箱前缀）

**首次配置或更新密码**（必须在用户自己的交互终端执行，输入密码时不回显）：

```bash
python -X utf8 "<skill>/scripts/corp_login.py" config --username <CORP邮箱> --prompt-password --apply
```

- 查看当前脱敏配置：`python -X utf8 "<skill>/scripts/corp_login.py" show`
- 清空已存密码：`python -X utf8 "<skill>/scripts/corp_login.py" config --clear-password --apply`
- Agent 的命令工具通常没有交互终端（stdin/stderr 不是终端），缺少已存密码时脚本会直接报错而不会卡死等待输入；此时把上述命令交给用户在自己的终端运行一次即可。

## 功能导航

| 任务 | 读取文档 | 核心脚本 |
| --- | --- | --- |
| 客户端覆盖率（创建、采集、MCP 跑测与上传、网站查询、补测） | [references/coverage.md](references/coverage.md) | `scripts/coverage_query.py`、`scripts/error_watch.py` |
| 提测报告（刷新单号、查已有提测单、生成测试重点 HTML、预览与保存） | [references/test-request.md](references/test-request.md) | `scripts/testreport.py` |

## 维护与自检

修改本技能脚本后，在技能根目录运行单元测试：

```bash
python -B -m pytest -q -p no:cacheprovider tests
```
