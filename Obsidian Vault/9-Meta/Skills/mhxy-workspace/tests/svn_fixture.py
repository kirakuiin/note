"""测试用的临时 SVN 仓库：只在临时目录里建库、检出、提交，不接触任何真实仓库。"""
import os
from pathlib import Path
import shutil
import subprocess
import unittest

AVAILABLE = bool(shutil.which("svn") and shutil.which("svnadmin"))
FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def svn(*args, cwd=None, check=True):
    """运行 svn 并返回 CompletedProcess；check 为真时失败抛 AssertionError。"""
    completed = subprocess.run(["svn", *map(str, args), "--non-interactive"], cwd=cwd, capture_output=True,
                               creationflags=FLAGS)
    if check and completed.returncode:
        raise AssertionError(f"svn {' '.join(map(str, args))} 失败：{completed.stderr.decode('utf-8', 'replace')}")
    return completed


class Repository:
    """base 下的一个 file:// 仓库。路径只用 ASCII，避免 svn 在不同代码页下的参数转码问题。"""

    def __init__(self, base, name="repo"):
        self.path = Path(base) / name
        subprocess.run(["svnadmin", "create", str(self.path)], check=True, capture_output=True, creationflags=FLAGS)
        self.url = self.path.as_uri()

    def import_tree(self, files, target):
        """把 {相对路径: 文本或字节} 导入到仓库的 target 路径下（一次提交）。"""
        staging = self.path.parent / f"staging-{os.urandom(4).hex()}"
        for relative, content in files.items():
            path = staging / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
        staging.mkdir(parents=True, exist_ok=True)
        svn("import", "-q", staging, f"{self.url}/{target}", "-m", "import")
        shutil.rmtree(staging)

    def copy(self, source, target):
        svn("copy", "-q", "--parents", f"{self.url}/{source}", f"{self.url}/{target}", "-m", "copy")

    def checkout(self, source, directory):
        svn("checkout", "-q", f"{self.url}/{source}", directory)
        return Path(directory)

    def commit_through(self, source, changes, deletes=()):
        """通过一个临时工作副本向仓库的 source 提交改动：changes 为 {相对路径: 内容}，deletes 为要删除的路径。"""
        scratch = self.path.parent / f"scratch-{os.urandom(4).hex()}"
        self.checkout(source, scratch)
        for relative, content in changes.items():
            path = scratch / relative
            existed = path.exists()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
            if not existed:
                svn("add", "-q", "--parents", relative, cwd=scratch)
        for relative in deletes:
            svn("delete", "-q", relative, cwd=scratch)
        svn("commit", "-q", "-m", "change", cwd=scratch)
        shutil.rmtree(scratch, onerror=_writable)


def _writable(function, path, _):
    os.chmod(path, 0o700)
    function(path)


requires_svn = unittest.skipUnless(AVAILABLE, "需要本机的 svn 和 svnadmin")
