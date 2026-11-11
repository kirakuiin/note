"""svn_merge.py：在临时仓库里走完整流程，不接触任何真实仓库。

仓库布局仿照正式环境，让分支类型判定生效：
  wzimage/trunk
  wzimage/branchs/2026_dev/feat            研发分支
  wzimage/branchs/2026_ship/release2_2026_11_17   周期分支（外放）
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from svn_fixture import FLAGS, Repository, requires_svn, svn

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "svn_merge.py"
DEV = "wzimage/branchs/2026_dev/feat"
SHIP = "wzimage/branchs/2026_ship/release2_2026_11_17"
AGENTS = "# agents\nl1\nl2\nl3\nl4\nl5\nl6\n"
BLOCK = "<!-- mhxy-workspace:begin -->\nrules\n<!-- mhxy-workspace:end -->\n"


def run(*args, no_commit=False):
    env = {key: value for key, value in os.environ.items() if key != "MHXY_NO_COMMIT"}
    if no_commit:
        env["MHXY_NO_COMMIT"] = "1"
    completed = subprocess.run([sys.executable, "-X", "utf8", str(SCRIPT), *map(str, args)], capture_output=True,
                               creationflags=FLAGS, env=env)
    text = completed.stdout.decode("utf-8", "replace")
    try:
        return completed.returncode, json.loads(text)
    except json.JSONDecodeError:
        raise AssertionError(f"输出不是 JSON：{text}\n{completed.stderr.decode('utf-8', 'replace')}") from None


@requires_svn
class MergeTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.repo = Repository(self.base)
        self.repo.import_tree({"AGENTS.md": AGENTS, "a.py": "a = 1\n", "b.py": "b = 1\n"}, "wzimage/trunk")
        self.repo.copy("wzimage/trunk", DEV)
        self.repo.copy("wzimage/trunk", SHIP)
        self.wc = self.repo.checkout(SHIP, self.base / "ship")
        self.message = self.base / "message.txt"

    def tearDown(self):
        self.temporary.cleanup()

    # ---- 小工具 ----
    def head(self, branch):
        out = svn("info", "--show-item", "last-changed-revision", f"{self.repo.url}/{branch}").stdout
        return int(out.decode().strip())

    def change(self, branch, changes, deletes=()):
        self.repo.commit_through(branch, changes, deletes)
        return self.head(branch)

    def say(self, text):
        self.message.write_text(text, encoding="utf-8")
        return self.message

    def local_rules(self, wc=None):
        """模拟初始化工作区：入口文件加受管区段并放进 ignore-on-commit。"""
        path = (wc or self.wc) / "AGENTS.md"
        path.write_bytes(path.read_bytes() + BLOCK.encode())
        svn("changelist", "ignore-on-commit", path)

    def log(self, branch=SHIP):
        """最近一次提交的说明和改动路径；用 --xml 取，避免控制台代码页把中文转坏。"""
        return svn("log", "--xml", "-v", "-l", "1", f"{self.repo.url}/{branch}").stdout.decode("utf-8")

    def merged(self, source, target=SHIP):
        out = svn("mergeinfo", "--show-revs", "merged", f"{self.repo.url}/{source}", f"{self.repo.url}/{target}").stdout
        return {int(line.strip().lstrip("r").rstrip("*")) for line in out.decode().split() if line.strip()}

    def text(self, relative):
        return (self.wc / relative).read_text(encoding="utf-8")

    # ---- 计划 ----
    def test_plan_is_read_only_and_describes_the_merge(self):
        rev = self.change(DEV, {"a.py": "a = 2\n"})
        self.local_rules()
        code, plan = run("plan", "--root", self.wc, "--source", f"{self.repo.url}/{DEV}", "--revs", rev)
        self.assertEqual((code, plan["status"]), (0, "planned"))
        self.assertEqual(plan["target"]["kind"], "周期分支")
        self.assertEqual(plan["message"]["format"], "finish #工单号 工单名：改动描述")
        self.assertNotIn("suffix", plan["message"])                        # 来源不进说明，由合并信息记录
        self.assertEqual(plan["revisions"][0]["paths"], ["a.py"])
        self.assertEqual(plan["local_changes"], ["AGENTS.md"])           # 会被暂存，不挡路
        self.assertEqual(self.text("a.py"), "a = 1\n")                   # 没有动工作副本
        self.assertFalse((self.wc / ".mhxy-workspace").exists())

    def test_plan_reports_blockers_and_already_merged(self):
        rev = self.change(DEV, {"a.py": "a = 2\n"})
        (self.wc / "new.py").write_text("x\n", encoding="utf-8")
        svn("add", self.wc / "new.py")
        code, plan = run("plan", "--root", self.wc, "--source", DEV, "--revs", rev)
        self.assertEqual((code, plan["status"]), (2, "blocked"))
        self.assertIn("new.py", plan["blockers"][0])
        svn("revert", self.wc / "new.py")
        (self.wc / "new.py").unlink()
        code, _ = run("run", "--root", self.wc, "--source", DEV, "--revs", rev, "--commit",
                      "--message-file", self.say(f"finish #100 测试单：合并"))
        self.assertEqual(code, 0)
        code, plan = run("plan", "--root", self.wc, "--source", DEV, "--revs", rev)
        self.assertEqual((plan["status"], plan["already_merged"]), ("nothing_to_merge", [rev]))

    # ---- 外放分支：直接提交 ----
    def test_merge_and_commit_records_mergeinfo_and_keeps_local_rules(self):
        first = self.change(DEV, {"a.py": "a = 2\n"})
        second = self.change(DEV, {"b.py": "b = 2\n"})
        self.local_rules()
        message = f"finish #864519 金刚护法：测效率开关"
        code, result = run("run", "--root", self.wc, "--source", f"{self.repo.url}/{DEV}", "--revs", first, second,
                           "--commit", "--message-file", self.say(message))
        self.assertEqual((code, result["status"], result["verified"]), (0, "committed", True), result)
        self.assertEqual(self.merged(DEV), {first, second})               # 合并信息记录在提交后的分支上
        log = self.log()
        self.assertIn(message, log)
        self.assertNotIn("AGENTS.md", log)                                # 入口文件没有跟着提交
        self.assertIn("rules", self.text("AGENTS.md"))                    # 受管区段还在
        self.assertIn("ignore-on-commit", svn("status", self.wc).stdout.decode())
        self.assertEqual(run("status", "--root", self.wc)[1]["status"], "idle")

    def test_source_given_as_working_copy_or_relative_path(self):
        rev = self.change(DEV, {"a.py": "a = 2\n"})
        dev_wc = self.repo.checkout(DEV, self.base / "dev")
        for source in (dev_wc, DEV):
            code, plan = run("plan", "--root", self.wc, "--source", source, "--revs", rev)
            self.assertEqual((code, plan["source"]), (0, f"{self.repo.url}/{DEV}"), plan)

    def test_source_from_another_repository_is_refused(self):
        other = Repository(self.base, "other")
        other.import_tree({"a.py": "a = 9\n"}, "wzimage/trunk")
        code, result = run("plan", "--root", self.wc, "--source", f"{other.url}/wzimage/trunk", "--revs", 1)
        self.assertEqual(code, 1)
        self.assertIn("不在同一个 SVN 仓库", result["error"])

    # ---- 提交说明的格式和直接提交一样 ----
    def test_message_rules_follow_branch_kind(self):
        rev = self.change(DEV, {"a.py": "a = 2\n"})
        for text, expected in (("#100 测试单：合并", "必须以 `finish #工单号` 开头"),
                               ("finish #100 测试单：auto commit: 合并", "auto commit:"),
                               ("合并一下", "说明首行必须是")):
            code, result = run("run", "--root", self.wc, "--source", DEV, "--revs", rev, "--message-file", self.say(text))
            self.assertEqual(code, 1)
            self.assertIn(expected, result["error"])
            self.assertEqual(run("status", "--root", self.wc)[1]["status"], "idle")   # 没开始，没留状态
        trunk_rev = self.change("wzimage/trunk", {"b.py": "b = 5\n"})
        dev_wc = self.repo.checkout(DEV, self.base / "dev")
        code, result = run("run", "--root", dev_wc, "--source", "wzimage/trunk", "--revs", trunk_rev, "--commit",
                           "--message-file", self.say(f"finish #100 测试单：同步"))
        self.assertIn("研发分支的说明不加 finish", result["error"])
        code, result = run("run", "--root", dev_wc, "--source", "wzimage/trunk", "--revs", trunk_rev, "--commit",
                           "--message-file", self.say(f"#100 测试单：同步主干"))
        self.assertEqual((code, result["status"]), (0, "committed"), result)      # 研发分支走同一套流程
        self.assertEqual(self.merged("wzimage/trunk", DEV), {trunk_rev})

    # ---- 先合、看过、再提交 ----
    def test_merge_then_review_then_commit(self):
        rev = self.change(DEV, {"a.py": "a = 2\n"})
        self.local_rules()
        code, result = run("run", "--root", self.wc, "--source", DEV, "--revs", rev,
                           "--message-file", self.say(f"finish #100 测试单：合并"))
        self.assertEqual((code, result["status"], result["committed"]), (0, "merged", False), result)
        self.assertEqual(self.text("a.py"), "a = 2\n")
        self.assertIn("rules", self.text("AGENTS.md"))                    # 不相干的本地修改马上放回，工作区规则不缺
        self.assertEqual(self.merged(DEV), set())                         # 还没提交
        (self.wc / "b.py").write_text("b = 99\n", encoding="utf-8")       # 合并之后才改的别的文件，不跟着提交
        code, result = run("commit", "--root", self.wc)
        self.assertEqual((code, result["status"], result["verified"]), (0, "committed", True), result)
        log = self.log()
        self.assertIn("a.py", log)
        self.assertNotIn("AGENTS.md", log)
        self.assertNotIn("b.py", log)
        self.assertEqual(self.text("b.py"), "b = 99\n")                   # 那处修改还在本地
        self.assertEqual(self.merged(DEV), {rev})

    def test_abort_restores_everything(self):
        rev = self.change(DEV, {"a.py": "a = 2\n", "added.py": "new\n"})
        self.local_rules()
        run("run", "--root", self.wc, "--source", DEV, "--revs", rev,
            "--message-file", self.say(f"finish #100 测试单：合并"))
        self.assertTrue((self.wc / "added.py").exists())
        code, result = run("abort", "--root", self.wc)
        self.assertEqual((code, result["status"]), (0, "aborted"))
        self.assertEqual(self.text("a.py"), "a = 1\n")
        self.assertFalse((self.wc / "added.py").exists())
        self.assertIn("rules", self.text("AGENTS.md"))
        changed = [line for line in svn("status", "-q", self.wc).stdout.decode().splitlines()
                   if line[:8].strip() and not line.startswith("---")]
        self.assertEqual(len(changed), 1, changed)                        # 只剩入口文件的本地修改
        self.assertIn("AGENTS.md", changed[0])

    # ---- 冲突 ----
    def test_real_conflict_stops_then_continue_commits(self):
        self.change(SHIP, {"a.py": "a = 100\n"})
        svn("update", "-q", self.wc)
        rev = self.change(DEV, {"a.py": "a = 2\n", "b.py": "b = 2\n"})
        self.local_rules()
        code, result = run("run", "--root", self.wc, "--source", DEV, "--revs", rev, "--commit",
                           "--message-file", self.say(f"finish #100 测试单：合并"))
        self.assertEqual((code, result["status"]), (2, "conflict"), result)
        conflict = result["conflicts"][0]
        self.assertEqual((conflict["path"], conflict["kind"]), ("a.py", "文本冲突"))
        self.assertEqual(set(conflict["files"]), {"目标分支原内容", "共同基准", "源分支内容"})
        self.assertNotIn("rules", self.text("AGENTS.md"))                 # 冲突期间本地修改不放回，免得被一起提交
        code, result = run("continue", "--root", self.wc)                 # 没处理就继续：仍然停着
        self.assertEqual((code, result["status"]), (2, "conflict"))
        (self.wc / "a.py").write_text("a = 102\n", encoding="utf-8")      # agent 处理冲突
        svn("resolve", "--accept", "working", self.wc / "a.py")
        code, result = run("continue", "--root", self.wc)
        self.assertEqual((code, result["status"], result["verified"]), (0, "committed", True), result)
        self.assertEqual(self.merged(DEV), {rev})
        self.assertNotIn("AGENTS.md", self.log())
        self.assertIn("rules", self.text("AGENTS.md"))

    def test_conflict_markers_left_in_file_block_commit(self):
        self.change(SHIP, {"a.py": "a = 100\n"})
        svn("update", "-q", self.wc)
        rev = self.change(DEV, {"a.py": "a = 2\n"})
        run("run", "--root", self.wc, "--source", DEV, "--revs", rev, "--commit",
            "--message-file", self.say(f"finish #100 测试单：合并"))
        svn("resolve", "--accept", "working", self.wc / "a.py")           # 标记还在文件里就声明解决了
        code, result = run("continue", "--root", self.wc)
        self.assertEqual((code, result["status"]), (2, "blocked"), result)
        self.assertTrue(any("冲突标记" in p or "语法" in p for p in result["problems"]))
        self.assertEqual(self.merged(DEV), set())
        (self.wc / "a.py").write_text("a = 102\n", encoding="utf-8")
        code, result = run("continue", "--root", self.wc)
        self.assertEqual((code, result["status"]), (0, "committed"), result)

    def test_encoding_conflict_is_resolved_automatically(self):
        """目标文件是 GBK，源把文件转成了 UTF-8。目标改了一行中文，源改了别的行：
        按字节看两边都动了那行中文所以冲突，按文字看并不重叠，脚本自动合好并统一成 UTF-8。"""
        lines = ["# -*- coding: gbk -*-\n", "name = '梦幻'\n", "x = 1\n", "y = 1\n", "z = 1\n"]
        self.change("wzimage/trunk", {"c.py": "".join(lines).encode("gbk")})
        for branch, directory in ((SHIP, self.wc), (DEV, self.repo.checkout(DEV, self.base / "dev"))):
            svn("update", "-q", directory)
            svn("merge", "-q", f"{self.repo.url}/wzimage/trunk", directory)
            svn("commit", "-q", "-m", "sync", directory)
        target = list(lines)
        target[1] = "name = '梦幻西游'\n"
        self.change(SHIP, {"c.py": "".join(target).encode("gbk")})
        svn("update", "-q", self.wc)
        source = list(lines)
        source[0], source[2] = "# -*- coding: utf-8 -*-\n", "x = 2\n"
        rev = self.change(DEV, {"c.py": "".join(source).encode("utf-8")})
        code, result = run("run", "--root", self.wc, "--source", DEV, "--revs", rev, "--commit",
                           "--message-file", self.say(f"finish #100 测试单：合并"))
        self.assertEqual((code, result["status"]), (0, "committed"), result)
        self.assertEqual([item["path"] for item in result["auto_resolved"]], ["c.py"])
        merged = (self.wc / "c.py").read_bytes().decode("utf-8")
        self.assertEqual(merged, "# -*- coding: utf-8 -*-\nname = '梦幻西游'\nx = 2\ny = 1\nz = 1\n")

    # ---- 入口文件也被合并改到 ----
    def test_local_rules_remerged_when_merge_touches_same_file(self):
        rev = self.change(DEV, {"AGENTS.md": AGENTS.replace("# agents", "# agents upstream")})
        self.local_rules()
        code, result = run("run", "--root", self.wc, "--source", DEV, "--revs", rev, "--commit",
                           "--message-file", self.say(f"finish #100 测试单：合并"))
        self.assertEqual((code, result["status"]), (0, "committed"), result)
        self.assertEqual(result["local_changes"]["remerged"], ["AGENTS.md"])
        text = self.text("AGENTS.md")
        self.assertIn("agents upstream", text)
        self.assertIn("rules", text)
        committed = svn("cat", f"{self.repo.url}/{SHIP}/AGENTS.md").stdout.decode()
        self.assertNotIn("rules", committed)                              # 提交上去的只有上游的改动

    # ---- 按“还没合过的”合并 ----
    def test_eligible_merges_everything_not_yet_merged(self):
        first = self.change(DEV, {"a.py": "a = 2\n"})
        second = self.change(DEV, {"b.py": "b = 2\n"})
        third = self.change(DEV, {"a.py": "a = 3\n"})
        code, plan = run("plan", "--root", self.wc, "--source", DEV, "--eligible", "--skip-revs", second)
        self.assertEqual([item["revision"] for item in plan["revisions"]], [first, third])
        code, result = run("run", "--root", self.wc, "--source", DEV, "--eligible", "--commit", "--message-file",
                           self.say(f"finish #100 测试单：合并"))
        self.assertEqual((code, result["status"]), (0, "committed"), result)
        self.assertEqual(self.merged(DEV), {first, second, third})
        self.assertEqual(run("plan", "--root", self.wc, "--source", DEV, "--eligible")[1]["status"], "nothing_to_merge")

    def test_commit_refused_when_mergeinfo_is_missing(self):
        """合并信息没有记录时（这里人为删掉属性来模拟）不能提交，只能撤销。"""
        rev = self.change(DEV, {"a.py": "a = 2\n"})
        run("run", "--root", self.wc, "--source", DEV, "--revs", rev,
            "--message-file", self.say(f"finish #100 测试单：合并"))
        svn("revert", "--depth", "empty", self.wc)                         # 内容还在，根目录上的 svn:mergeinfo 没了
        code, result = run("commit", "--root", self.wc)
        self.assertEqual((code, result["status"], result["committed"]), (2, "blocked", False), result)
        self.assertTrue(any("svn:mergeinfo 没有记录" in problem for problem in result["problems"]))
        self.assertEqual(self.merged(DEV), set())
        self.assertNotIn("a.py", self.log())                               # 什么都没提交上去
        self.assertEqual(run("abort", "--root", self.wc)[1]["status"], "aborted")
        self.assertEqual(self.text("a.py"), "a = 1\n")

    def test_session_without_commit_approval_cannot_commit(self):
        """调用方用 MHXY_NO_COMMIT=1 声明没有提交的批准：带 --commit、单独 commit 都只停在已合并。"""
        rev = self.change(DEV, {"a.py": "a = 2\n"})
        self.local_rules()
        code, result = run("run", "--root", self.wc, "--source", DEV, "--revs", rev, "--commit", "--message-file",
                           self.say(f"finish #100 测试单：合并"), no_commit=True)
        self.assertEqual((code, result["status"], result["committed"]), (0, "merged", False), result)
        self.assertIn("MHXY_NO_COMMIT", result["reason"])
        code, result = run("commit", "--root", self.wc, no_commit=True)
        self.assertEqual((result["status"], result["committed"]), ("merged", False), result)
        self.assertEqual(self.merged(DEV), set())
        self.assertIn("rules", self.text("AGENTS.md"))
        code, result = run("commit", "--root", self.wc)                    # 有批准的调用方（用户点了提交）才提交
        self.assertEqual((code, result["status"]), (0, "committed"), result)
        self.assertEqual(self.merged(DEV), {rev})

    def test_second_run_refused_while_one_is_pending(self):
        rev = self.change(DEV, {"a.py": "a = 2\n"})
        message = self.say(f"finish #100 测试单：合并")
        run("run", "--root", self.wc, "--source", DEV, "--revs", rev, "--message-file", message)
        code, result = run("run", "--root", self.wc, "--source", DEV, "--revs", rev, "--message-file", message)
        self.assertEqual(code, 1)
        self.assertIn("上一次合并还没结束", result["error"])


if __name__ == "__main__":
    unittest.main()
