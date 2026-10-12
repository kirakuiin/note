# -*- coding: utf-8 -*-
"""PopoMgr 数据源配置

PopoMgr（提单平台）的工单直接存放在 MongoDB 里，没有对外 HTTP API，
所以这里配置的是只读访问用的连接信息。需要换环境时改这一个文件即可。
"""
import getpass
import os

# MongoDB 连接配置（只读使用）
MONGO_CONFIG = {
    "host": os.environ.get("POPO_MONGO_HOST", "mongo.eros.nie.netease.com"),
    "port": int(os.environ.get("POPO_MONGO_PORT", "30000")),
    "username": os.environ.get("POPO_MONGO_USER", "root"),
    "password": os.environ.get("POPO_MONGO_PASSWORD", "root123"),
    "database": "popo_mgr_tool",
    "timeout_ms": 8000,
}

# 项目标识与集合名：梦幻西游客户端用 xyq
PROJECT_ID = "xyq"
ISSUES_COLLECTION = "issues_xyq"
TASK_COLLECTION = "task"

# 账号 -> 真实姓名映射所在的库表
USER_DB = "ci"
USER_COLLECTION = "user_info_new"


def detect_person():
    """推断「本人」是谁，返回 (人员标识, 来源说明)

    工单的默认筛选条件是「指派给本人」，而内网机器的 Windows 登录名通常就是平台账号，
    所以不必每次都手输 --person；识别错了也看得见来源，好排查。
    优先级：显式环境变量 POPO_USER > 当前登录用户。
    """
    configured = os.environ.get("POPO_USER", "").strip()
    if configured:
        return configured, "环境变量 POPO_USER"
    try:
        user = getpass.getuser()
    except Exception:
        user = os.environ.get("USERNAME", "") or os.environ.get("USER", "")
    return (user or ""), "当前登录用户"

# 工单状态 / 类型 / 优先级枚举，供参数校验与提示使用
ISSUE_STATUSES = [
    "新建",
    "已完成",
    "描述不清",
    "完成转回",
    "暂不修复",
    "无需修复",
    "关闭",
]

ISSUE_TYPES = [
    "BUG",
    "建议",
    "备忘",
    "阻碍性BUG",
    "高优先BUG",
    "优先需求",
    "经典BUG",
    "资源BUG",
    "历史BUG",
]

ISSUE_PRIORITIES = ["P0", "P1", "P2", "P3"]

# 未关闭（还需要处理）的状态集合
OPEN_STATUSES = ["新建", "描述不清", "完成转回"]
