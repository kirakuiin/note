"""pytest 选项：--skip-svn 跳过真实调用 svn 的测试（改动不涉及 SVN 时快速回归）。"""
import os


def pytest_addoption(parser):
    parser.addoption("--skip-svn", action="store_true", help="跳过真实调用 svn 的测试（设置 MHXY_TEST_SKIP_SVN=1）")


def pytest_configure(config):
    # 在收集测试（导入 svn_fixture）之前设置；pytest-xdist 的各 worker 也会各自执行这里。
    if config.getoption("--skip-svn"):
        os.environ["MHXY_TEST_SKIP_SVN"] = "1"
