"""pytest 根配置(合并版):注入 processing/ 入 sys.path,排除非pytest脚本。"""
import sys, os
_PKG = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_PKG, "processing"))
collect_ignore = ["test/batch_a_test.py", "test/fallback.py"]
