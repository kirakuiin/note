---
area: knowledge
visibility: public
tags:
  - AI与Agent
---

# FastCtx部署与用途

FastCtx 用于改善 Codex 读取文件、搜索代码和执行终端命令的体验，尤其针对 Windows 下的 PowerShell 命令与文本编码问题。

## 想解决的问题

通过 MCP 提供文件读取、文件查找、内容搜索、批量替换及前后台 Bash 工具，减少模型自行拼接命令、处理编码与分页的负担，让它更专注于任务。

## 部署方式

1. 安装 Node.js；Windows 用户还需安装 Git。
2. 全局安装：

```bash
npm install --global fastctx
```

若遇到 404、找不到包或无法更新，改用官方源：

```bash
npm install --global fastctx --registry=https://registry.npmjs.org/
```

3. 运行配置界面，按提示完成 MCP 安装与配置：

```bash
fastctx
```

作者建议 Windows 用户开启 Bash 终端，不熟悉输出长度设置时保持默认。配置完成后无需一直开着配置界面，MCP 随 Codex 启停。

## 来源

仅整理 MotorwaySouth 的首帖内容。

- [原文：让 Codex 又快又准的原生模型工具](https://linux.do/t/topic/2612425/1)
- [FastCtx 仓库](https://github.com/yc-duan/fastctx)
