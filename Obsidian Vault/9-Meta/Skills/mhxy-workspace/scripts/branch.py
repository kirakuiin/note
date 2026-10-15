#!/usr/bin/env python3
"""创建开发分支，并预览或检出开发分支和周期分支到本地。流程说明见 references/branch.md。"""
import argparse
from collections import Counter
from datetime import date, datetime
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import corp_login  # noqa: E402
import precommit  # noqa: E402
import workspace  # noqa: E402

# 分支位置和接口均集中定义。来源：Cursor 扩展 mhxy2.mhcoder 的“工作区分支管理”面板——
# 创建调用 createbranch（source_name 为空表示不建资源分支，script_base 为空时传 release），
# 创建后每 POLL_INTERVAL 秒查询 getbranch、最多 POLL_ATTEMPTS 次，在最新 20 条记录中
# 找到脚本分支（以及资源 _test／_testhd）即视为成功。资源分支位于 RES_BRANCH_ROOT/<年份>_dev/<分支名>。
SCRIPT_BRANCH_ROOT = "svn://svn-xyq.gz.netease.com/svn/products/xy1/develop/client/wzimage/branchs"
RES_BRANCH_ROOT = "svn://svn-xyq.gz.netease.com/svn/products/xy1/share/patch/branchs"
RES_SUBDIRS = ("_test", "_testhd")
CREATE_BRANCH_API = "https://artrestrans.eros.nie.netease.com/api/createbranch"
GET_BRANCH_API = "https://artrestrans.eros.nie.netease.com/api/getbranch"
POLL_INTERVAL = 2
POLL_ATTEMPTS = 20
HTTP_TIMEOUT = 30
SVN_TIMEOUT = 3600  # checkout、switch、cleanup 和工作副本状态检查：资源工作副本很大，可能很慢。
INFO_TIMEOUT = 120
CONFIG_PATH = Path.home() / ".mhxy-workspace" / "config.json"
# svn info 明确表示目标不存在的错误码：路径不存在、URL 在该版本不存在、部分目标不存在、
# 不是工作副本、本地节点不存在。网络、认证等其他错误不在此列，必须报错而不是当作“不存在”。
MISSING_TARGET_CODES = {"E160013", "W170000", "E200009", "E155007", "E155010"}
PURPOSE_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)?$")
BRANCH_PATTERN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9_.-]*)_(\d{4})_(\d{2})_(\d{2})_([a-z][a-z0-9]*(?:_[a-z0-9]+)?)$")
# 周期分支 <类型>_<yyyy>_<mm>_<dd> 只能检出，不能用本脚本创建。脚本位于 SCRIPT_BRANCH_ROOT/<年份>_ship/<分支名>，
# 不在分支记录中；资源按类型共用 xyq-res 仓库中的固定目录，不随日期变化。只配 _test，_testhd 的对应尚未确认。
# release（全服）对应 branches/xyq_all_res，开发时不需要检出，因此不配资源。类型列表见 workspace.PERIODIC_TYPES。
PERIODIC_RES_ROOT = "svn://svn-xyq.gz.netease.com/xyq-res/xyq"
PERIODIC_RESOURCES = {"test": "xyq_test", "shiwan": "xyq_demo", "release": None, "release2": "xyq_release2",
                      "release3": "xyq_release3", "newbie": "xyq_newbie", "sjf": "xyq_sjf", "zlp": "xyq_zlp"}
PERIODIC_PATTERN = workspace.PERIODIC_NAME  # 分组：类型、年、月、日。
BRANCH_NAME_ERROR = "分支名格式无效，应为 <前缀>_<yyyy>_<mm>_<dd>_<用途>，或周期分支 <类型>_<yyyy>_<mm>_<dd>"

# 标准汉语拼音音节表（不含声调），用于邮箱前缀的确定性切分。
PINYIN_SYLLABLES = frozenset("""
a ai an ang ao e ei en eng er o ou
ba bai ban bang bao bei ben beng bi bian biao bie bin bing bo bu
pa pai pan pang pao pei pen peng pi pian piao pie pin ping po pu
ma mai man mang mao me mei men meng mi mian miao mie min ming miu mo mou mu
fa fan fang fei fen feng fo fou fu
da dai dan dang dao de dei den deng di dia dian diao die ding diu dong dou du duan dui dun duo
ta tai tan tang tao te teng ti tian tiao tie ting tong tou tu tuan tui tun tuo
na nai nan nang nao ne nei nen neng ni nian niang niao nie nin ning niu nong nou nu nuan nuo nv nve
la lai lan lang lao le lei leng li lia lian liang liao lie lin ling liu lo long lou lu luan lun luo lv lve
ga gai gan gang gao ge gei gen geng gong gou gu gua guai guan guang gui gun guo
ka kai kan kang kao ke kei ken keng kong kou ku kua kuai kuan kuang kui kun kuo
ha hai han hang hao he hei hen heng hong hou hu hua huai huan huang hui hun huo
ji jia jian jiang jiao jie jin jing jiong jiu ju juan jue jun
qi qia qian qiang qiao qie qin qing qiong qiu qu quan que qun
xi xia xian xiang xiao xie xin xing xiong xiu xu xuan xue xun
zhi zha zhai zhan zhang zhao zhe zhei zhen zheng zhi zhong zhou zhu zhua zhuai zhuan zhuang zhui zhun zhuo
chi cha chai chan chang chao che chen cheng chi chong chou chu chua chuai chuan chuang chui chun chuo
shi sha shai shan shang shao she shei shen sheng shi shou shu shua shuai shuan shuang shui shun shuo
ri ran rang rao re ren reng ri rong rou ru rua ruan rui run ruo
lue nue
zi za zai zan zang zao ze zei zen zeng zi zong zou zu zuan zui zun zuo
ci ca cai can cang cao ce cen ceng ci cong cou cu cuan cui cun cuo
si sa sai san sang sao se sen seng si song sou su suan sui sun suo
yi ya yan yang yao ye yi yin ying yo yong you yu yuan yue yun
wu wa wai wan wang wei wen weng wo wu
yu yue yuan yun
""".split())


class BranchError(Exception):
    """可直接呈现给用户的分支操作错误。"""


def run_svn(*args, cwd=None, timeout=SVN_TIMEOUT):
    """运行 SVN 命令并返回 CompletedProcess，失败时保留输出供调用方解释（见 precommit.svn_process）。"""
    try:
        return precommit.svn_process(cwd, *args, timeout=timeout)
    except precommit.SvnTimeout as error:
        raise BranchError(f"SVN 命令超时：{error}；命令可能仍未完成，先检查工作副本状态再决定是否重试") from None
    except precommit.PrecheckError as error:
        raise BranchError(f"SVN 命令无法执行：{error}") from None


def svn_error(completed, action):
    """从 SVN 结果中取出适合报告的错误文本。"""
    detail = precommit.decode_output(completed.stderr).strip() or precommit.decode_output(completed.stdout).strip()
    return detail or f"svn {action} 失败，退出码 {completed.returncode}"


def missing_svn_target(completed):
    """判断 svn info 的失败是否明确表示 URL 或工作副本不存在；只认 MISSING_TARGET_CODES 中的错误码。"""
    text = precommit.decode_output(completed.stderr) + "\n" + precommit.decode_output(completed.stdout)
    return bool(set(re.findall(r"\b[EW]\d{6}\b", text)) & MISSING_TARGET_CODES)


def svn_info(target, *, item=None, cwd=None):
    """查询 URL 或工作副本信息；item 为 --show-item 的字段名（如 url、repos-uuid）。不存在时返回 None，其余错误抛出。"""
    args = ["info"]
    if item:
        args += ["--show-item", item]
    args.append(str(target))
    completed = run_svn(*args, cwd=cwd, timeout=INFO_TIMEOUT)
    if completed.returncode:
        if missing_svn_target(completed):
            return None
        raise BranchError(svn_error(completed, "info"))
    return precommit.decode_output(completed.stdout).strip()


def http_get(url, timeout=HTTP_TIMEOUT):
    """以有超时的 GET 请求读取服务端响应。"""
    try:
        with urlopen(Request(url, headers={"User-Agent": "mhxy-workspace/branch"}), timeout=timeout) as response:
            return response.read().decode("utf-8-sig")
    except HTTPError as error:
        raise BranchError(f"HTTP 请求失败：HTTP {error.code} {error.reason}") from None
    except (URLError, OSError, TimeoutError) as error:
        reason = getattr(error, "reason", error)
        raise BranchError(f"网络请求失败：{reason}") from None


def branch_rows():
    """读取最近的分支记录并验证服务端 JSON 结构。"""
    raw = http_get(GET_BRANCH_API + "?need_msg=1")
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        raise BranchError("分支查询结果不是有效 JSON") from None
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise BranchError("分支查询结果缺少 data 列表")
    return [row for row in rows if isinstance(row, dict) and isinstance(row.get("url"), str)]


def load_config(path=CONFIG_PATH):
    """只读加载合并后的配置（用户级加当前目录的工作区级覆盖），校验规则同 workspace.load_config。"""
    try:
        return workspace.load_config(Path.cwd(), path)
    except (workspace.WorkspaceError, OSError) as error:
        raise BranchError(f"读取配置失败：{error}") from None


def email_prefix(config):
    """取 OpenID 邮箱前缀（小写），规则同 corp_login.account_prefix，与其他脚本一致。"""
    try:
        return corp_login.account_prefix(config.get("openid_username"))
    except corp_login.LoginError as error:
        raise BranchError(f"{error}；请先设置用户级 OpenID 邮箱") from None


def split_pinyin(value):
    """按最少音节数切分拼音；并列时优先选择较长的前置音节。"""
    syllables = value.rstrip("0123456789")
    if not syllables:
        return None

    # 动态规划比较完整切分；长度元组的逆序实现“前面音节更长优先”。
    best = {len(syllables): ()}
    for start in range(len(syllables) - 1, -1, -1):
        options = []
        for end in range(start + 1, len(syllables) + 1):
            part = syllables[start:end]
            if part in PINYIN_SYLLABLES and end in best:
                options.append((part,) + best[end])
        if options:
            best[start] = min(options, key=lambda parts: (len(parts), tuple(-len(part) for part in parts)))
    return best.get(0)


def infer_prefix(value):
    """返回邮箱前缀缩写、依据和切分结果。"""
    parts = split_pinyin(value.lower())
    if parts is None:
        return {"prefix": value, "basis": "raw", "syllables": []}
    return {"prefix": "".join(part[0] for part in parts), "basis": "pinyin", "syllables": list(parts)}


def validate_purpose(purpose):
    """验证单词用途格式，不尝试翻译或改写用户输入。"""
    if not isinstance(purpose, str) or not PURPOSE_PATTERN.fullmatch(purpose):
        raise BranchError("用途必须是一个或两个英文小写单词，以字母开头，例如 qixi 或 magic_buff")
    return purpose


def branch_name(prefix, purpose, today=None):
    """按邮箱缩写、日期和用途拼接分支名。"""
    validate_purpose(purpose)
    today = today or date.today()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", prefix):
        raise BranchError("推断出的邮箱前缀不能安全用于分支名")
    return f"{prefix}_{today:%Y_%m_%d}_{purpose}"


def name_result(purpose, config=None, today=None):
    """生成 name/create 共用的命名解释。"""
    validate_purpose(purpose)
    config = load_config() if config is None else config
    original = email_prefix(config)
    inferred = infer_prefix(original)
    return {"email_prefix": original, **inferred, "purpose": purpose,
            "branch": branch_name(inferred["prefix"], purpose, today)}


def branch_urls(name, include_resources=True):
    """返回开发分支脚本 URL 和可选的两个资源 URL；仅用于创建，周期分支不能创建。"""
    match = BRANCH_PATTERN.fullmatch(name)
    if not match:
        raise BranchError("分支名格式无效，应为 <前缀>_<yyyy>_<mm>_<dd>_<用途>")
    year = match[2]
    script = f"{SCRIPT_BRANCH_ROOT}/{year}_dev/{name}"
    resource_root = f"{RES_BRANCH_ROOT}/{year}_dev/{name}"
    return {"script": script,
            "resources": {folder: f"{resource_root}/{folder}" for folder in RES_SUBDIRS} if include_resources else {}}


def create_parameters(name, base, author, include_resources):
    """生成 createbranch 接口参数与分支 URL。"""
    urls = branch_urls(name, include_resources)
    return ({"source_name": name if include_resources else "", "script_name": name,
             "script_base": base or "release", "author": author}, urls)


def create_query_url(parameters):
    """构造 createbranch GET 地址。"""
    return CREATE_BRANCH_API + "?" + urlencode(parameters)


def create_branch_request(parameters):
    """向创建接口发送请求；服务端的响应正文沿用原扩展规则忽略。"""
    http_get(create_query_url(parameters))


def row_name(url):
    """取分支 URL 最后一个路径段，忽略尾部斜线。"""
    return url.rstrip("/").rsplit("/", 1)[-1]


def row_matches_script(row, name):
    """判断服务端记录是否精确指向指定脚本分支。"""
    url = row["url"].rstrip("/")
    return url.startswith(SCRIPT_BRANCH_ROOT + "/") and row_name(url) == name


def row_matches_resource(row, name):
    """判断服务端记录是否指向指定分支的资源子目录。"""
    url = row["url"].rstrip("/")
    return url.startswith(RES_BRANCH_ROOT + "/") and any(
        url.endswith(f"/{name}/{folder}") for folder in RES_SUBDIRS)


def relevant_rows(rows, name, include_resources):
    """最新 20 条记录中与本分支相关的记录，按完整内容计数，用于区分创建前已有的记录。"""
    return Counter(json.dumps(row, sort_keys=True, ensure_ascii=False) for row in rows[:20]
                   if row_matches_script(row, name) or (include_resources and row_matches_resource(row, name)))


def poll_creation(name, include_resources, before=None):
    """按服务端约定轮询最新 20 条记录并给出最终状态。

    before 是发送创建请求前的 relevant_rows 快照；只看之后新出现的记录，以免把以前同名创建失败的旧记录当作本次结果。
    """
    urls = branch_urls(name, include_resources)
    before = before or Counter()
    for attempt in range(POLL_ATTEMPTS):
        relevant = [json.loads(row) for row in (relevant_rows(branch_rows(), name, include_resources) - before).elements()]
        failed = next((row for row in relevant if row.get("msg") != "ok"), None)
        if failed:
            return {"status": "failed", "msg": failed.get("msg"), "urls": urls}
        script_created = any(row_matches_script(row, name) for row in relevant)
        resource_created = any(row_matches_resource(row, name) for row in relevant)
        if script_created and (not include_resources or resource_created):
            return {"status": "created", "urls": urls}
        if attempt + 1 < POLL_ATTEMPTS:
            time.sleep(POLL_INTERVAL)
    return {"status": "timeout", "message": "创建状态暂未出现，稍后执行 checkout 时会再次核实。", "urls": urls}


def create_preview(purpose, base="release", no_res=False, config=None, today=None):
    """准备创建预览并只读检查脚本 URL 是否已存在。"""
    config = load_config() if config is None else config
    named = name_result(purpose, config, today)
    author = email_prefix(config)
    parameters, urls = create_parameters(named["branch"], base or "release", author, not no_res)
    if svn_info(urls["script"]) is not None:
        raise BranchError(f"脚本分支已存在，不允许创建：{urls['script']}")
    return {"action": "create", "preview": True, **named, "base": parameters["script_base"],
            "author": author, "create_resources": not no_res, "parameters": parameters, "urls": urls}


def create(purpose, base="release", no_res=False, apply=False, config=None, today=None, expected=None):
    """预览或执行服务端分支创建并返回创建状态。

    执行时必须用 expected 传入预览确认的分支名：分支名含当天日期，跨日后重新计算的名称会不同，不一致时拒绝创建。
    """
    result = create_preview(purpose, base, no_res, config, today)
    if expected is not None and expected != result["branch"]:
        raise BranchError(f"确认的分支名 {expected} 与当前计算的 {result['branch']} 不一致（日期可能已变化），请重新预览并确认")
    if apply:
        if expected is None:
            raise BranchError("创建时必须用 --branch 传入预览中确认的完整分支名")
        before = relevant_rows(branch_rows(), result["branch"], not no_res)
        # 请求超时等网络错误时服务端可能已经执行了创建，因此仍以轮询结果为准，并附上请求错误。
        try:
            create_branch_request(result["parameters"])
        except BranchError as error:
            result["request_error"] = str(error)
        result.update(poll_creation(result["branch"], not no_res, before))
    result["preview"] = not apply
    result["applied"] = apply
    return result


def settings_suggestion(appdata=None):
    """从 Cursor 或 VS Code 带注释的 settings.json 提取旧总目录配置。"""
    appdata = appdata or os.environ.get("APPDATA")
    if not appdata:
        return None
    appdata = Path(appdata)
    paths = (appdata / "Cursor" / "User" / "settings.json",
             appdata / "Code" / "User" / "settings.json",
             appdata / "Code - Insiders" / "User" / "settings.json")
    pattern = re.compile(r"[\"']MHCoder\.branchesBaseDir[\"']\s*:\s*\"((?:\\.|[^\"\\])*)\"")
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (FileNotFoundError, OSError, UnicodeError):
            continue
        match = pattern.search(text)
        if match:
            try:
                value = json.loads('"' + match[1] + '"')
            except ValueError:
                value = match[1]
            if value:
                return value
    return None


def resolve_root(root_arg=None, config=None):
    """解析绝对分支总目录，缺失时提示配置方法和旧设置建议。"""
    if root_arg:
        value = os.path.abspath(os.path.expanduser(root_arg))
        root = Path(value)
    else:
        config = load_config() if config is None else config
        value = config.get("branches_root")
        if not value:
            command = 'python "<skill>/scripts/workspace.py" config --set-global "branches_root=<路径>" --apply'
            suggestion = settings_suggestion()
            detail = f"；检测到旧设置建议值：{suggestion}" if suggestion else ""
            raise BranchError(f"未配置 branches_root{detail}。请用以下命令设置：{command}")
        if not isinstance(value, str):
            raise BranchError("branches_root 必须是绝对路径或 null")
        root = Path(os.path.expanduser(value))
    if not root.is_absolute():
        raise BranchError("分支总目录必须是绝对路径")
    return root


def has_reparse_attribute(path):
    """路径是否为符号链接或目录联接（见 workspace.is_link）；路径不存在时为 False。"""
    try:
        return workspace.is_link(Path(path))
    except OSError:
        return False


def assert_no_reparse_path(path):
    """拒绝路径本身及已有祖先目录中的链接或目录联接（见 workspace.no_links）。"""
    try:
        workspace.no_links(Path(os.path.abspath(path)))
    except workspace.WorkspaceError as error:
        raise BranchError(str(error)) from None


def validate_root(root):
    """检查总目录已存在且整条路径不经过链接。"""
    assert_no_reparse_path(root)
    if not root.is_dir():
        raise BranchError(f"分支总目录不存在或不是目录：{root}")
    return root.resolve()


def working_copy_url(directory):
    """目录是可复用工作区（普通目录，含普通目录 mhimage 且是 SVN 工作副本）时返回 mhimage 的 URL，否则返回 None。

    reusable 和 --reuse 共用这一标准；svn 的其他错误（网络、超时等）抛出 BranchError。
    """
    image = directory / "mhimage"
    if (not directory.is_dir() or has_reparse_attribute(directory)
            or not image.is_dir() or has_reparse_attribute(image)):
        return None
    try:
        return svn_info(image, item="url") or None
    except BranchError as error:
        if "working copy" in str(error).lower() or "155007" in str(error):
            return None
        raise


def reusable(root):
    """列出总目录下含 mhimage SVN 工作副本的直接子目录，不扫描状态。"""
    root = validate_root(Path(root))
    candidates = []
    warnings = []
    for directory in sorted(root.iterdir(), key=lambda item: item.name.lower()):
        try:
            url = working_copy_url(directory)
        except BranchError as error:
            warnings.append(f"{directory.name}：{error}")
            continue
        if not url:
            continue
        image = directory / "mhimage"
        modified = datetime.fromtimestamp(image.stat().st_mtime).astimezone().isoformat(timespec="seconds")
        candidates.append({"directory": directory.name, "mhimage_url": url, "last_modified": modified})
    return {"action": "reusable", "root": str(root), "candidates": candidates, "warnings": warnings}


def validate_branch_name(name):
    """限制分支名为开发分支或周期分支的单一路径片段，并返回其中年份。"""
    match = BRANCH_PATTERN.fullmatch(name or "") or PERIODIC_PATTERN.fullmatch(name or "")
    if not match:
        raise BranchError(BRANCH_NAME_ERROR)
    return match[2]


def periodic_type(name):
    """周期分支返回类型（如 zlp），其他名称返回 None。"""
    match = PERIODIC_PATTERN.fullmatch(name or "")
    return match[1] if match else None


def periodic_urls(name):
    """按周期分支类型构造脚本 URL 和固定资源 URL；不配资源的类型返回空资源。"""
    match = PERIODIC_PATTERN.fullmatch(name)
    folder = PERIODIC_RESOURCES[match[1]]
    return {"script": f"{SCRIPT_BRANCH_ROOT}/{match[2]}_ship/{name}",
            "resources": {"_test": f"{PERIODIC_RES_ROOT}/{folder}"} if folder else {}}


def urls_from_rows(name, rows):
    """优先使用分支记录中的精确 URL，缺失时按分支年份构造 URL；周期分支不在记录中，直接构造。"""
    year = validate_branch_name(name)
    if periodic_type(name):
        return periodic_urls(name)
    script_row = next((row for row in rows if row_matches_script(row, name)), None)
    if script_row and script_row.get("msg") != "ok":
        raise BranchError(f"脚本分支记录失败：{script_row.get('msg')}")
    script_url = script_row["url"].rstrip("/") if script_row else f"{SCRIPT_BRANCH_ROOT}/{year}_dev/{name}"
    resource_root = f"{RES_BRANCH_ROOT}/{year}_dev/{name}"
    for row in rows:
        if not row_matches_resource(row, name):
            continue
        if row.get("msg") != "ok":
            raise BranchError(f"资源分支记录失败：{row.get('msg')}")
        resource_root = row["url"].rstrip("/").rsplit("/", 1)[0]
        break
    return {"script": script_url, "resources": {folder: f"{resource_root}/{folder}" for folder in RES_SUBDIRS}}


def resolve_branch_urls(name, rows=None):
    """查找分支记录或按年份构造 URL，再用 svn info 核实存在性；周期分支不在记录中，不请求记录接口。"""
    validate_branch_name(name)
    if periodic_type(name):
        rows = []
    rows = branch_rows() if rows is None else rows
    urls = urls_from_rows(name, rows)
    if svn_info(urls["script"]) is None:
        raise BranchError(f"脚本分支不存在：{urls['script']}")
    resources, warnings = {}, []
    for folder, url in urls["resources"].items():
        if svn_info(url) is None:
            warnings.append(f"资源子分支不存在，已跳过：{url}")
        else:
            resources[folder] = url
    kind = periodic_type(name)
    if kind and PERIODIC_RESOURCES[kind] is None:
        warnings.append(f"{kind} 周期分支不检出资源目录，只检出 mhimage")
    return {"script": urls["script"], "resources": resources}, warnings


def resolve_reuse(root, reuse_arg):
    """校验复用目录：必须是总目录的直接子目录并含 mhimage 工作副本（同 reusable），且不是当前会话目录或其祖先。"""
    candidate = Path(reuse_arg).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    candidate = Path(os.path.abspath(candidate))
    assert_no_reparse_path(candidate)
    if not candidate.exists() or not candidate.is_dir():
        raise BranchError(f"复用目录不存在或不是普通目录：{candidate}")
    selected = candidate.resolve()
    session = Path.cwd().resolve()
    if selected == session or selected in session.parents:
        raise BranchError(f"拒绝复用当前会话目录或其祖先目录：{selected}")
    if selected.parent != root:
        raise BranchError(f"复用目录必须是分支总目录 {root} 的直接子目录：{selected}")
    if not working_copy_url(selected):
        raise BranchError(f"复用目录中没有 mhimage SVN 工作副本，不是可复用的工作区：{selected}")
    return selected


def command_preview(step):
    """将计划步骤转换为便于阅读的命令描述。"""
    if step["type"] == "mkdir":
        return f"mkdir {step['path']}"
    if step["type"] == "rename":
        return f"rename {step['source']} -> {step['target']}"
    if step["type"] == "same_directory":
        return f"reuse {step['path']} (already at target)"
    if step["type"] == "set_aside":
        return f"rename {step['source']} -> {step['target']} (different repository, checkout again)"
    if step["type"] == "remove":
        return f"remove {step['path']} (set-aside old working copy, kept if status unavailable, not clean or removal fails)"
    return "svn " + " ".join(step["args"] + ["--non-interactive"])


def make_svn_step(args, cwd, label):
    """创建带工作目录和用途说明的 SVN 计划步骤。"""
    return {"type": "svn", "args": list(map(str, args)), "cwd": str(cwd), "label": label}


def checkout_plan(name, root, urls, reuse=None, replace=()):
    """构造新建或复用目录的操作计划，不产生文件系统副作用。

    replace 中的复用子目录与目标不在同一仓库，无法 switch（见 cross_repository_folders）：先改名挪开再检出，
    全部步骤成功后最后删除挪开的旧目录。改名在文件被占用时会直接失败，不会留下删了一半的工作副本。
    """
    target = root / name
    steps = []
    removals = []
    stamp = time.strftime("%Y%m%d%H%M%S")
    if reuse is None:
        validate_checkout_target(target)
        steps.append({"type": "mkdir", "path": str(target)})
        for folder, url in [("mhimage", urls["script"]), *urls["resources"].items()]:
            steps.append(make_svn_step(["checkout", "-q", url, folder], target, f"checkout {folder}"))
    else:
        same_directory = validate_checkout_target(target, reuse)
        if same_directory:
            steps.append({"type": "same_directory", "path": str(target)})
        else:
            steps.append({"type": "rename", "source": str(reuse), "target": str(target)})
        for folder, url in [("mhimage", urls["script"]), *urls["resources"].items()]:
            local = reuse / folder
            if folder in replace:
                aside = target / f"{folder}.old-{stamp}"
                if (reuse / aside.name).exists():
                    raise BranchError(f"挪开旧目录用的名称已存在：{reuse / aside.name}")
                steps.append({"type": "set_aside", "source": str(target / folder), "target": str(aside)})
                steps.append(make_svn_step(["checkout", "-q", url, folder], target, f"checkout {folder}"))
                removals.append({"type": "remove", "path": str(aside)})
            elif local.is_dir():
                steps.append(make_svn_step(["cleanup", folder], target, f"cleanup {folder}"))
                steps.append(make_svn_step(["switch", "-q", url, folder, "--force", "--ignore-ancestry"],
                                           target, f"switch {folder}"))
            else:
                steps.append(make_svn_step(["checkout", "-q", url, folder], target, f"checkout {folder}"))
    return steps + removals


def validate_checkout_target(target, reuse=None):
    """拒绝目标链接；复用时仅允许普通目标目录与来源目录相同。"""
    target = Path(target)
    if has_reparse_attribute(target):
        raise BranchError(f"目标目录不能是符号链接或目录联接：{target}")
    if not (target.exists() or target.is_symlink()):
        return False
    if reuse is not None and target.resolve() == reuse:
        return True
    raise BranchError(f"目标目录已存在：{target}")


def local_only(path):
    """mhimage 下的入口文件和本地辅助目录（sync 写入，不会被提交）不算阻止复用的改动。"""
    parts = path.strip().replace("\\", "/").split("/")
    return len(parts) > 1 and parts[1] in precommit.LOCAL_ONLY


def inspect_reuse(reuse):
    """检查每个现有工作副本，有本地修改、未纳管文件（?）或其他输出就拒绝复用。

    不用 -q：switch --force 会把未纳管文件原样带进新分支。被忽略的文件（I，如构建产物）不显示，不阻止复用；
    mhimage 顶层的 AGENTS.md、CLAUDE.md、.claude、.mhxy-workspace 由 sync 维护，随工作副本保留，不阻止复用。
    """
    changed = []
    unversioned = []
    checked = []
    for folder in ("mhimage", *RES_SUBDIRS):
        local = reuse / folder
        if local.exists() or local.is_symlink():
            if has_reparse_attribute(local):
                raise BranchError(f"复用子目录不能是符号链接或目录联接：{local}")
            if not local.is_dir():
                raise BranchError(f"复用子路径必须是普通目录：{local}")
        if not local.is_dir():
            continue
        completed = run_svn("status", "--ignore-externals", folder, cwd=reuse, timeout=SVN_TIMEOUT)
        if completed.returncode:
            raise BranchError(svn_error(completed, "status"))
        # 不加 -q 时外链定义总会显示为 X 行（即使 --ignore-externals），不算本地改动。
        lines = [line for line in (precommit.decode_output(completed.stdout)
                                   + "\n" + precommit.decode_output(completed.stderr)).splitlines()
                 if line.strip() and not line.startswith("X ") and not line.startswith("--- Changelist")
                 and not (folder == "mhimage" and local_only(line[8:]))]
        checked.append(folder)
        unversioned += [line[8:].strip() for line in lines if line.startswith("?")]
        if any(not line.startswith("?") for line in lines):
            changed.append(folder)
    if changed:
        raise BranchError("复用目录状态检查有输出，拒绝切换：" + ", ".join(changed))
    if unversioned:
        listed = unversioned[:20] + ([f"……另有 {len(unversioned) - 20} 项"] if len(unversioned) > 20 else [])
        raise BranchError("复用目录中有未纳入版本控制的文件，switch 会把它们带进新分支，拒绝切换；"
                          "请先由用户处理：" + ", ".join(listed))
    return checked


def full_status(path, cwd):
    """返回工作副本完整状态（含未纳管、被忽略的文件和外链）的输出；空字符串表示干净，可以安全删除。"""
    completed = run_svn("status", "--no-ignore", str(path), cwd=cwd, timeout=SVN_TIMEOUT)
    if completed.returncode:
        raise BranchError(svn_error(completed, "status"))
    return (precommit.decode_output(completed.stdout) + precommit.decode_output(completed.stderr)).strip()


def cross_repository_folders(reuse, urls):
    """返回复用目录中与目标资源不在同一仓库、无法 switch 的资源子目录。

    开发分支资源在 svn 仓库，周期分支资源在 xyq-res 仓库，两个方向的复用都可能跨仓库，因此检查每个已存在的
    资源子目录。按仓库 UUID 判断，不比较 URL，以免协议不同（svn:// 与 https://）被误判；任一侧查不到 UUID 时
    无法判断，直接报错。跨仓库的子目录会被挪开后删除，因此要求它的完整状态为空：inspect_reuse 的 status
    不显示被忽略的文件。
    """
    folders = []
    for folder, url in urls["resources"].items():
        if not (reuse / folder).is_dir():
            continue
        local_uuid = svn_info(folder, item="repos-uuid", cwd=reuse)
        target_uuid = svn_info(url, item="repos-uuid")
        if not local_uuid or not target_uuid:
            raise BranchError(f"无法确定 {folder} 与目标资源是否在同一仓库：{reuse / folder} -> {url}")
        if local_uuid == target_uuid:
            continue
        if full_status(folder, reuse):
            raise BranchError(f"{folder} 与目标资源不在同一仓库，需要删除后重新检出，"
                              f"但其中有未纳管、被忽略或修改的文件：{reuse / folder}")
        folders.append(folder)
    return folders


def remove_set_aside(path):
    """删除挪开的旧工作副本，返回结果说明；状态无法检查、不干净或删除失败时保留目录，不让已完成的检出失败。"""
    path = Path(path)
    try:
        output = full_status(path.name, path.parent)
    except BranchError as error:
        return f"kept: 无法检查 {path} 的状态（{error}），请手动处理"
    if output:
        return f"kept: {path} 有未纳管、被忽略或修改的文件，请手动处理"

    def retry(function, target, *_):
        # SVN 工作副本中的只读文件先去掉只读属性再删除。
        os.chmod(target, stat.S_IWRITE)
        function(target)

    try:
        if sys.version_info >= (3, 12):
            shutil.rmtree(path, onexc=retry)
        else:
            shutil.rmtree(path, onerror=retry)
    except OSError as error:
        return f"kept: 删除 {path} 失败（{error}），请手动删除"
    return "removed"


def stale_resource_warnings(reuse, urls):
    """复用目录中有本次不检出的资源子目录时提示：它们保持原样，仍指向原来的分支。"""
    warnings = []
    for folder in RES_SUBDIRS:
        if folder not in urls["resources"] and (reuse / folder).is_dir():
            current = svn_info(folder, item="url", cwd=reuse)
            where = f"仍指向：{current}" if current else "未能读取其 SVN URL（可能不是工作副本）"
            warnings.append(f"复用目录中的 {folder} 不在本次检出范围，保持原样，{where}")
    return warnings


def build_checkout(name, root_arg=None, reuse_arg=None, config=None, rows=None):
    """检查分支、目录和本地改动，生成无副作用的检出预览。"""
    validate_branch_name(name)
    root = validate_root(resolve_root(root_arg, config))
    target = root / name
    reuse = resolve_reuse(root, reuse_arg) if reuse_arg else None
    validate_checkout_target(target, reuse)
    urls, warnings = resolve_branch_urls(name, rows)
    checks = {"root_exists": True, "script_url_exists": True,
              "resource_urls_exist": sorted(urls["resources"])}
    replace = []
    if reuse is not None:
        checks["reuse_directory"] = str(reuse)
        checks["clean_working_copies"] = inspect_reuse(reuse)
        replace = cross_repository_folders(reuse, urls)
        if replace:
            checks["replaced_working_copies"] = replace
        warnings = warnings + stale_resource_warnings(reuse, urls)
    steps = checkout_plan(name, root, urls, reuse, replace)
    return {"action": "checkout", "preview": True, "applied": False, "branch": name,
            "root": str(root), "target": str(target), "reuse": str(reuse) if reuse else None,
            "urls": urls, "warnings": warnings, "checks": checks,
            "initialize_root": str(target / "mhimage"),
            "steps": [{**step, "command": command_preview(step)} for step in steps]}


def execute_steps(result):
    """依次执行已检查的计划，失败时保留完成和剩余步骤，不自动回滚。"""
    steps = result["steps"]
    target = Path(result["target"])
    completed = []
    for index, step in enumerate(steps):
        print(f"[{index + 1}/{len(steps)}] {step['command']}", file=sys.stderr)
        try:
            if step["type"] == "mkdir":
                Path(step["path"]).mkdir()
                outcome = "created"
            elif step["type"] == "rename":
                os.rename(step["source"], step["target"])
                outcome = "renamed"
            elif step["type"] == "same_directory":
                outcome = "already_at_target"
            elif step["type"] == "set_aside":
                os.rename(step["source"], step["target"])
                outcome = "set_aside"
            elif step["type"] == "remove":
                outcome = remove_set_aside(step["path"])
            else:
                completed_process = run_svn(*step["args"], cwd=step["cwd"], timeout=SVN_TIMEOUT)
                if completed_process.returncode:
                    raise BranchError(svn_error(completed_process, step["args"][0]))
                outcome = "ok"
            completed.append({"command": step["command"], "status": outcome})
        except (OSError, BranchError) as error:
            return {"status": "failed", "completed_steps": completed,
                    "failed_step": {"command": step["command"], "error": str(error)},
                    "remaining_steps": [item["command"] for item in steps[index + 1:]],
                    "initialize_root": str(target / "mhimage")}
    return {"status": "completed", "completed_steps": completed, "failed_step": None,
            "remaining_steps": [], "initialize_root": str(target / "mhimage")}


def checkout(name, root_arg=None, reuse_arg=None, apply=False, config=None, rows=None):
    """预览或执行检出；预览只读取 API、SVN 状态和路径元数据。"""
    result = build_checkout(name, root_arg, reuse_arg, config, rows)
    if apply:
        outcome = execute_steps(result)
        result.update(outcome)
    result["preview"] = not apply
    result["applied"] = apply
    return result


def main(argv=None):
    """解析命令行并以 JSON 输出结果。"""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", type=Path, default=CONFIG_PATH, help="用户级配置文件")

    name_parser = commands.add_parser("name", parents=[common], help="只读预览分支名")
    name_parser.add_argument("--purpose", required=True)

    create_parser = commands.add_parser("create", parents=[common], help="预览或创建服务端分支")
    create_parser.add_argument("--purpose", required=True)
    create_parser.add_argument("--base", default="release")
    create_parser.add_argument("--no-res", action="store_true")
    create_parser.add_argument("--branch", help="预览中确认的完整分支名；--apply 时必填，与当前计算结果不一致则拒绝")
    create_parser.add_argument("--apply", action="store_true")

    reusable_parser = commands.add_parser("reusable", parents=[common], help="列出可复用的本地工作区")
    reusable_parser.add_argument("--root")

    checkout_parser = commands.add_parser("checkout", parents=[common], help="预览或检出开发分支或周期分支")
    checkout_parser.add_argument("--branch", required=True)
    checkout_parser.add_argument("--root")
    checkout_parser.add_argument("--reuse")
    checkout_parser.add_argument("--apply", action="store_true")

    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        if args.action == "name":
            result = {"action": "name", **name_result(args.purpose, config)}
        elif args.action == "create":
            result = create(args.purpose, args.base, args.no_res, args.apply, config, expected=args.branch)
        elif args.action == "reusable":
            result = reusable(resolve_root(args.root, config))
        else:
            result = checkout(args.branch, args.root, args.reuse, args.apply, config)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result.get("status") == "failed" else 0
    except (BranchError, OSError, ValueError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
