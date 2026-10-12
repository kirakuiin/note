# -*- coding: utf-8 -*-
"""PopoMgr 工单只读客户端

只做读取：查任务、查工单、读内容、下载截图。
不提供任何写入/流转接口，避免 agent 误改线上工单状态。
"""
import os
import re
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlparse

import pymongo
from bson.objectid import ObjectId

from .config import (
    ISSUES_COLLECTION,
    MONGO_CONFIG,
    OPEN_STATUSES,
    PROJECT_ID,
    TASK_COLLECTION,
    USER_COLLECTION,
    USER_DB,
)

# 软删除的工单不返回
NOT_DELETED = {"delete": {"$exists": False}}

# 列表查询字段：够用来挑单，不拖慢查询
LIST_FIELDS = ["readable_id", "subject", "type", "status", "priority", "taskid", "ctime", "author", "assignee"]

# 内容详情字段：描述正文、重现步骤、截图、客户端附件
DETAIL_FIELDS = ["markdown", "way_text", "way_img", "img", "client_info", "changelst", "assignlst", "followqa",
                 "redmine_sync_id"]

# 工单文本里的图片占位符，按出现顺序对应图片数组
IMAGE_PLACEHOLDER = "[图片]"


class PopoClient(object):
    """PopoMgr MongoDB 只读客户端"""

    def __init__(self):
        # 平台的 MongoDB 还是 3.2，pymongo 4.x 的握手会被直接断开，
        # 报错信息是难以理解的 "connection closed"，所以提前拦一道。
        if int(pymongo.version.split(".")[0]) >= 4:
            raise RuntimeError(
                "当前 pymongo 版本为 %s，无法连接 PopoMgr 的 MongoDB 3.2。\n"
                "请降到 3.x：python -m pip install \"pymongo>=3.12,<4\"\n"
                "如果别的项目需要 pymongo 4，请在 skill 目录之外建虚拟环境再跑本 skill，\n"
                "不要在 skill 目录里安装依赖（这里是 SVN 工作副本）。" % pymongo.version
            )
        uri = "mongodb://%s:%s@%s:%s" % (
            quote(MONGO_CONFIG["username"]),
            quote(MONGO_CONFIG["password"]),
            MONGO_CONFIG["host"],
            MONGO_CONFIG["port"],
        )
        self.conn = pymongo.MongoClient(uri, serverSelectionTimeoutMS=MONGO_CONFIG["timeout_ms"])
        self.db = self.conn[MONGO_CONFIG["database"]]
        self.issues_col = self.db[ISSUES_COLLECTION]
        self.task_col = self.db[TASK_COLLECTION]
        self.user_col = self.conn[USER_DB][USER_COLLECTION]
        self._user_map: Optional[Dict[str, str]] = None
        self._task_name_cache: Dict[str, str] = {}

    # ---------- 人员 ----------

    def user_map(self) -> Dict[str, str]:
        """账号 -> 真实姓名（姓名带姓氏首字母前缀，如 L黎靖宇）"""
        if self._user_map is None:
            self._user_map = {}
            for user in self.user_col.find({"firstname": {"$ne": ""}}, {"firstname": 1}):
                self._user_map[user["_id"]] = user.get("firstname", user["_id"])
        return self._user_map

    def display_name(self, username: str) -> str:
        if not username:
            return "未指派"
        return self.user_map().get(username, username)

    def resolve_person(self, person: str) -> Optional[str]:
        """把账号 / 完整姓名 / 纯中文名解析成账号

        平台里姓名存的是 L黎靖宇 这种带前缀的形式，开发同学口头只说「黎靖宇」，
        所以这里要容忍三种写法，否则查不到人会被误读成「没有工单」。
        """
        if not person:
            return None
        users = self.user_map()
        if person in users:
            return person
        name_to_user = {name: account for account, name in users.items()}
        if person in name_to_user:
            return name_to_user[person]
        for name, account in name_to_user.items():
            if not name:
                continue
            if name.endswith(person) and len(name) == len(person) + 1:
                return account
        for name, account in name_to_user.items():
            if name and person in name:
                return account
        return None

    # ---------- 任务（制作内容） ----------

    def task_name(self, task_id: Optional[str]) -> str:
        if not task_id:
            return ""
        if task_id not in self._task_name_cache:
            task = self._find_task(task_id)
            self._task_name_cache[task_id] = task.get("task_name", "") if task else ""
        return self._task_name_cache[task_id]

    def _find_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        try:
            return self.task_col.find_one({"_id": ObjectId(task_id)})
        except Exception:
            return None

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        task = self._find_task(task_id)
        if not task:
            return None
        return {
            "task_id": str(task["_id"]),
            "task_name": task.get("task_name", ""),
            "task_status": "进行中" if task.get("status") == "true" else "已关闭",
            "ctime": task.get("ctime", ""),
        }

    def list_person_tasks(self, person: str, status: str = "open") -> List[Dict[str, Any]]:
        """列出某人有工单的制作内容（任务），按工单数倒序

        平台没有「任务成员」表，人和任务的关系是通过工单的 assignee 体现的，
        所以这里用工单聚合反推任务归属。
        """
        account = self.resolve_person(person)
        if not account:
            raise LookupError("找不到人员: %s（试试账号，或中文名如 黎靖宇）" % person)

        # MongoDB 3.2 的聚合不支持 $in 表达式，只能用 $or + $eq 判断「待处理」
        is_open = {"$or": [{"$eq": ["$status", status]} for status in OPEN_STATUSES]}
        pipeline = [
            {"$match": dict(NOT_DELETED, assignee=account)},
            {"$group": {"_id": "$taskid", "issue_count": {"$sum": 1},
                        "open_count": {"$sum": {"$cond": [is_open, 1, 0]}},
                        "last_ctime": {"$max": "$ctime"}}},
            {"$sort": {"last_ctime": -1}},
        ]
        tasks = []
        for row in self.issues_col.aggregate(pipeline):
            task_id = row["_id"]
            if not task_id:
                continue
            task = self.get_task(task_id)
            if not task:
                continue
            if status == "open" and task["task_status"] != "进行中":
                continue
            if status == "closed" and task["task_status"] == "进行中":
                continue
            task["issue_count"] = row["issue_count"]
            task["open_count"] = row["open_count"]
            task["last_ctime"] = row.get("last_ctime", "")
            tasks.append(task)
        return tasks

    def search_tasks(self, keyword: str, status: str = "open", limit: int = 20) -> List[Dict[str, Any]]:
        query: Dict[str, Any] = {
            "project_id": PROJECT_ID,
            "task_name": {"$regex": re.escape(keyword)},
        }
        if status == "open":
            query["status"] = "true"
        elif status == "closed":
            query["status"] = {"$ne": "true"}
        cursor = self.task_col.find(query).sort("ctime", -1).limit(limit)
        return [{
            "task_id": str(task["_id"]),
            "task_name": task.get("task_name", ""),
            "task_status": "进行中" if task.get("status") == "true" else "已关闭",
            "ctime": task.get("ctime", ""),
        } for task in cursor]

    # ---------- 工单 ----------

    def list_issues(
        self,
        person: Optional[str] = None,
        task_id: Optional[str] = None,
        status: Optional[str] = "open",
        issue_type: Optional[str] = None,
        priority: Optional[str] = None,
        limit: int = 50,
        detail: bool = False,
    ) -> Dict[str, Any]:
        """按人 / 任务 / 状态查工单列表

        status 取 "open" 表示还需要处理的状态（新建/描述不清/完成转回），
        "all" 表示不过滤，其他值按平台状态精确匹配。
        """
        match: Dict[str, Any] = dict(NOT_DELETED)
        account = None
        if person:
            account = self.resolve_person(person)
            if not account:
                raise LookupError("找不到人员: %s（试试账号，或中文名如 黎靖宇）" % person)
            match["assignee"] = account
        if task_id:
            match["taskid"] = task_id
        if status == "open":
            match["status"] = {"$in": OPEN_STATUSES}
        elif status and status != "all":
            match["status"] = status
        if issue_type:
            match["type"] = issue_type
        if priority:
            match["priority"] = priority

        projection = {field: 1 for field in LIST_FIELDS}
        if detail:
            for field in DETAIL_FIELDS:
                projection[field] = 1

        cursor = self.issues_col.find(match, projection).sort("ctime", -1)
        if limit:
            cursor = cursor.limit(limit)

        issues = []
        for issue in cursor:
            issues.append(self._decorate(issue, detail=detail))

        return {
            "person": self.display_name(account) if account else None,
            "username": account,
            "task_id": task_id,
            "task_name": self.task_name(task_id) if task_id else None,
            "status": status,
            "total": len(issues),
            "issues": issues,
        }

    def get_issue(self, issue_id: int) -> Optional[Dict[str, Any]]:
        """按工单号（readable_id，即 popo 上显示的单号）取完整工单"""
        issue = self.issues_col.find_one(dict(NOT_DELETED, readable_id=int(issue_id)))
        if not issue:
            return None
        return self._decorate(issue, detail=True)

    def _decorate(self, issue: Dict[str, Any], detail: bool = False) -> Dict[str, Any]:
        issue["_id"] = str(issue["_id"])
        issue["assignee_name"] = self.display_name(issue.get("assignee", ""))
        issue["author_name"] = self.display_name(issue.get("author", ""))
        issue["task_name"] = self.task_name(issue.get("taskid"))
        if detail:
            issue["images"] = list(issue.get("img") or []) + list(issue.get("way_img") or [])
        return issue

    def close(self):
        self.conn.close()


# ---------- 内容渲染 ----------


def _fill_placeholders(text: Optional[str], images: Optional[List[str]],
                       image_map: Optional[Dict[str, str]] = None) -> str:
    """把文本里的 [图片] 占位符按顺序换成 Markdown 图片

    平台把图片和正文分开存，正文只留占位符；不做这一步就会丢掉
    「第几步对应哪张图」的信息，排查时很容易看错。
    """
    text = text or ""
    urls = [(image_map or {}).get(url, url) for url in (images or [])]
    segments = text.split(IMAGE_PLACEHOLDER)

    pieces = [segments[0]]
    for index, segment in enumerate(segments[1:]):
        if index < len(urls):
            pieces.append("\n![图片](%s)\n" % urls[index])
        else:
            pieces.append(IMAGE_PLACEHOLDER)
        pieces.append(segment)
    rendered = "".join(pieces)

    leftover = urls[len(segments) - 1:]
    if leftover:
        extra = "\n".join("![图片](%s)" % url for url in leftover)
        rendered = (rendered.rstrip() + "\n" + extra) if rendered.strip() else extra
    return rendered


def render_issue(issue: Dict[str, Any], with_meta: bool = True, with_history: bool = False,
                 image_map: Optional[Dict[str, str]] = None) -> str:
    """把工单渲染成一段 Markdown：元信息 + 标题 + 描述 + 重现步骤 + 附件"""
    blocks: List[str] = []

    if with_meta:
        meta = [
            "# #%s %s" % (issue.get("readable_id", "?"), (issue.get("subject") or "").splitlines()[0]
                          if issue.get("subject") else ""),
            "- 类型/状态/优先级: %s / %s / %s" % (issue.get("type", ""), issue.get("status", ""),
                                             issue.get("priority", "")),
            "- 指派: %s（%s）" % (issue.get("assignee_name", ""), issue.get("assignee", "")),
            "- 提单: %s（%s） %s" % (issue.get("author_name", ""), issue.get("author", ""),
                                  issue.get("ctime", "")),
            "- 所属任务: %s" % (issue.get("task_name") or "无"),
        ]
        if issue.get("redmine_sync_id"):
            meta.append("- 易协作同步单号: %s" % issue["redmine_sync_id"])
        blocks.append("\n".join(meta))

    subject = _fill_placeholders(issue.get("subject"), issue.get("img"), image_map).strip()
    if subject:
        blocks.append("## 问题描述\n" + subject)

    markdown = (issue.get("markdown") or "").strip()
    if markdown:
        blocks.append("## 补充说明\n" + markdown)

    way = _fill_placeholders(issue.get("way_text"), issue.get("way_img"), image_map).strip()
    if way:
        blocks.append("## 重现步骤\n" + way)

    client_info = issue.get("client_info")
    if isinstance(client_info, dict) and client_info:
        blocks.append("## 附件\n" + "\n".join("- %s: %s" % (key, value) for key, value in client_info.items()))

    if with_history:
        changes = issue.get("changelst") or []
        if changes:
            blocks.append("## 状态流转\n" + "\n".join(
                "- %s %s %s" % (item.get("time", ""), item.get("person", ""), item.get("status", ""))
                for item in changes))

    return "\n\n".join(blocks)


def download_issue_images(issue: Dict[str, Any], out_dir: str, timeout: int = 30) -> Dict[str, str]:
    """把工单截图下载到本地，返回 {原始 URL: 本地路径}

    下载到本地是为了能用看图工具直接读图——截图里往往是真正的报错信息，
    只看文字描述容易漏掉关键线索。
    """
    import requests

    urls: List[str] = list(issue.get("img") or []) + list(issue.get("way_img") or [])
    if not urls:
        return {}

    os.makedirs(out_dir, exist_ok=True)
    mapping: Dict[str, str] = {}
    for index, url in enumerate(urls):
        base = os.path.basename(urlparse(url).path) or ("image_%d.png" % index)
        local = os.path.join(out_dir, "%02d_%s" % (index, base))
        try:
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()
            with open(local, "wb") as fp:
                fp.write(response.content)
            mapping[url] = os.path.abspath(local)
        except Exception as exc:  # 图片挂了不该让整条流程失败
            mapping[url] = "下载失败(%s): %s" % (exc, url)
    return mapping
