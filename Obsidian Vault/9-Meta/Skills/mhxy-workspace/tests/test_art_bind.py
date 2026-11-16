"""资源提交网站绑定脚本与通用 CORP 登录的隔离测试；不访问网络。"""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import art_bind as a  # noqa: E402
import corp_login  # noqa: E402

TAG = "art_836252_2027寒促斩杀特效-XYQ-2026长期运营（26-30年）-角色其他-B1"
SVN = "https://svn-xyq.gz.netease.com/svn/products/xy1/share/patch/2026_dev/wzw_demo/_test"
NOTICE = f"""[转自 某人 11/14 19:13]
【时间服】
某人已于

{TAG}

成功上传1份新资源:
temp/res_copy/{TAG}/1794654796_origin/2026年_斩杀特效/tcp/1.25/斩杀特效.tcp

请策划告知程序为该标签或对应总单绑定svn
"""


class Site:
    """假的网站接口：记下收到的请求，绑定是整份覆盖。"""

    def __init__(self, bound, tags=(TAG,), reject=None, drop=False, rewrite=False):
        self.items, self.tags, self.reject, self.drop, self.calls = list(bound), tags, reject, drop, []
        self.rewrite = rewrite      # 像真实平台那样改写：svn:// 存成 https://，补上 _testhd，地址排到群号前面

    def post(self, path, payload):
        self.calls.append((path, payload))
        if path.endswith("get_redmine_svn_info"):
            return 200, {"infos": [{"tag": t, "art_svn": "https://art", "sub_account": "美术", "mod_time": "now"}
                                   for t in payload["tags"] if t in self.tags], "msg": "succeed"}
        if path.endswith("get_redmine_svn_by_tag"):
            return 200, {"bindSVN": list(self.items), "code_svn_binder": "x@corp.netease.com", "needBindSvn": True}
        if self.reject:
            return 201, {"msg": self.reject}
        if self.rewrite:
            svns = [i.replace("svn://", "https://") for i in payload["bindSVN"] if not i.isdigit()]
            svns += [i[:-len("_test")] + "_testhd" for i in svns if i.endswith("/_test")]
            self.items = svns + [i for i in payload["bindSVN"] if i.isdigit()]
        elif not self.drop:
            self.items = list(payload["bindSVN"])
        return 200, {"msg": "绑定成功", "infos": []}

    info, bound, bind = a.Client.info, a.Client.bound, a.Client.bind


def run(argv, site):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = a.main(argv, client=site)
    return code, json.loads(out.getvalue())


class ArtBindTests(unittest.TestCase):
    def test_tag_from_notice(self):
        self.assertEqual(a.tag_from_text(NOTICE), TAG)
        self.assertEqual(a.tag_from_text(NOTICE.replace("\n", " ")), TAG)                 # 引用时换行被压成空格
        self.assertEqual(a.tag_from_text(f"temp/res_copy/{TAG}/a/b.tcp"), TAG)             # 只剩路径那一行
        self.assertEqual(a.tag_from_text("今天几点开会"), "")

    def test_address_must_be_resource_repo(self):
        self.assertEqual(a.check_svn(SVN + "/"), SVN)
        self.assertEqual(a.check_svn("svn://svn-xyq.gz.netease.com/svn/xyqs/share/x"), "svn://svn-xyq.gz.netease.com/svn/xyqs/share/x")
        for url in ("", "https://svn-xyq.gz.netease.com/svn/products/xy1/wzimage/branchs/2026_dev/x",
                    "https://svn-xyq.gz.netease.com/svn/products/xy1/share/", "https://other.invalid/svn/xyqs/share/x"):
            with self.assertRaises(a.ArtBindError):
                a.check_svn(url)

    def test_bind_appends_and_keeps_existing_items(self):
        site = Site(["8205741"])
        code, result = run(["bind", "--tag", TAG, "--svn", SVN], site)                      # 预览：不提交
        self.assertEqual((code, result["applied"], result["will_bind"]), (0, False, ["8205741", SVN]))
        self.assertFalse([c for c in site.calls if "bind_redmine" in c[0]])
        code, result = run(["bind", "--tag", TAG, "--svn", SVN, "--apply"], site)
        self.assertEqual((code, result["applied"], result["changed"]), (0, True, True))
        self.assertEqual(site.calls[-2], ("/api/tag/bind_redmine_svn_by_tag", {"searchTag": TAG, "bindSVN": ["8205741", SVN]}))
        self.assertEqual((result["groups"], result["svns"]), (["8205741"], [SVN]))
        code, result = run(["bind", "--tag", TAG, "--svn", SVN + "/", "--apply"], site)     # 再绑一次：不动
        self.assertEqual((code, result["applied"], result["changed"]), (0, False, False))
        self.assertEqual(sum("bind_redmine" in c[0] for c in site.calls), 1)

    def test_platform_rewrites_address(self):
        """真实平台把 svn:// 存成 https://、自动补 _testhd：读回核对要认得出来，再绑一次也认得出已经绑过。"""
        svn = SVN.replace("https://", "svn://")
        site = Site(["8205741"], rewrite=True)
        code, result = run(["bind", "--tag", TAG, "--svn", svn, "--apply"], site)
        self.assertEqual((code, result["changed"], result["errors"]), (0, True, []))
        self.assertEqual(result["bound"], [SVN, SVN + "hd", "8205741"])
        code, result = run(["bind", "--tag", TAG, "--svn", svn, "--apply"], site)
        self.assertEqual((code, result["applied"], result["will_bind"]), (0, False, None))
        self.assertEqual(sum("bind_redmine" in c[0] for c in site.calls), 1)

    def test_show_and_tag_from_text_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            notice = Path(tmp) / "notice.txt"
            notice.write_text(NOTICE, encoding="utf-8")
            code, result = run(["show", "--text-file", str(notice)], Site(["8205741"]))
            self.assertEqual((code, result["tag"], result["bound"], result["need_bind"]), (0, TAG, ["8205741"], True))
            notice.write_text("没有标签", encoding="utf-8")
            code, result = run(["show", "--text-file", str(notice)], Site([]))
            self.assertEqual(code, 1)
            self.assertIn("没有从通知原文里找到标签", result["errors"][0])

    def test_failures(self):
        code, result = run(["bind", "--tag", "art_不存在", "--svn", SVN, "--apply"], Site([]))
        self.assertEqual(code, 1)
        self.assertIn("没有这个标签", result["errors"][0])
        code, result = run(["bind", "--tag", TAG, "--svn", SVN, "--apply"], Site([], reject="非法格式"))
        self.assertEqual((code, result["applied"]), (1, False))
        self.assertIn("非法格式", result["errors"][0])
        code, result = run(["bind", "--tag", TAG, "--svn", SVN, "--apply"], Site([], drop=True))   # 提交了但读回没有
        self.assertEqual((code, result["applied"], result["changed"]), (2, True, False))
        code, result = run(["bind", "--tag", TAG], Site([]))
        self.assertEqual(code, 1)
        code, result = run(["bind", "--tag", TAG, "--svn", "https://other.invalid/x"], Site([]))
        self.assertEqual(code, 1)

    def test_resource_address_from_workspace(self):
        with patch.object(a.branch, "svn_info", return_value=SVN.replace("wzw_demo", "wzw%20demo") + "/") as info:
            self.assertEqual(a.resource_svn("D:/work/proj/mhimage"), SVN.replace("wzw_demo", "wzw demo"))
            self.assertEqual(info.call_args.args[0], Path("D:/work/proj/mhimage").resolve().parent / "_test")
        with patch.object(a.branch, "svn_info", return_value=""), self.assertRaisesRegex(a.ArtBindError, "没有找到资源工作副本"):
            a.resource_svn("D:/work/proj/mhimage")


class CorpLoginTests(unittest.TestCase):
    def test_redirect_whitelist_and_headers(self):
        handler = corp_login.redirects(a.SITE, http_hosts=(a.HOST,))()
        request = corp_login.Request(corp_login.LOGIN + "/accounts/login/", headers={"Origin": corp_login.LOGIN, "Referer": "x"})
        moved = handler.redirect_request(request, None, 302, "", {}, "http://" + a.HOST + "/login?openid.mode=id_res")
        self.assertEqual(moved.full_url, "http://" + a.HOST + "/login?openid.mode=id_res")
        self.assertFalse({k.lower() for k in moved.headers} & {"origin", "referer"})     # 不把登录页的来源带给站点
        for url in ("http://login.netease.com/x", "https://other.invalid/", "https://u:p@" + a.HOST + "/",
                    "http://auth.eros.nie.netease.com/x"):
            with self.assertRaises(corp_login.LoginError):
                handler.redirect_request(request, None, 302, "", {}, url)
        with self.assertRaises(corp_login.LoginError):       # 没声明时站点的 http 也不放行
            corp_login.redirects(a.SITE)().redirect_request(request, None, 302, "", {}, "http://" + a.HOST + "/login")

    def test_login_flow(self):
        html = '<form><input name="authm" value="corp"><input name="corpid"><input name="corppw" type="password"></form>'

        def response(url, body=""):
            r = MagicMock()
            r.__enter__.return_value = r
            r.url, r.read.return_value = url, body.encode()
            return r

        with patch.object(corp_login, "build_opener") as build, \
                patch.object(corp_login, "encode_password", return_value="synthetic-encoded-value"):
            build.return_value.open.side_effect = [response(corp_login.LOGIN + "/accounts/login/?uid=1", html),
                                                   response("http://" + a.HOST + "/")]
            opener = corp_login.login(a.SITE, "test@corp.netease.com", "synthetic-test-input", http_hosts=(a.HOST,))
            self.assertIs(opener, build.return_value)
            first, second = (c.args[0] for c in build.return_value.open.call_args_list)
            self.assertEqual(first.full_url, a.SITE + "/login?next=/")
            self.assertIn(b"corppw=synthetic-encoded-value", second.data)
            self.assertNotIn(b"synthetic-test-input", second.data)
            build.return_value.open.side_effect = [response(corp_login.LOGIN + "/accounts/login/", html),
                                                   response(corp_login.LOGIN + "/accounts/login/", html)]
            with self.assertRaisesRegex(corp_login.LoginError, "登录未完成"):
                corp_login.login(a.SITE, "test", "synthetic-test-input")
            build.return_value.open.side_effect = [response(a.SITE + "/")]
            with self.assertRaisesRegex(corp_login.LoginError, "未到达 CORP 登录页"):
                corp_login.login(a.SITE, "test", "synthetic-test-input")
        with self.assertRaisesRegex(corp_login.LoginError, "https"):
            corp_login.login("http://" + a.HOST, "test", "x")


if __name__ == "__main__":
    unittest.main()
