"""
pytest 根配置。
"""
import sys
import os

# 将项目根目录加入 sys.path
sys.path.insert(0, os.path.dirname(__file__))

# 忽略独立脚本（非 pytest 测试）
collect_ignore = [
    "test/batch_a_test.py",
]
