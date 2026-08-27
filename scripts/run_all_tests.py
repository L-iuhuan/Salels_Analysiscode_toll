# -*- coding: utf-8 -*-
r"""
统一测试收集入口 · 全量跑 pytest
=====================================================================

在 sales_analytics_platform 目录下执行 `python -m pytest test -q`，
透传输出与退出码，末尾打印明确摘要：

  python scripts/run_all_tests.py

目的：根除「只跑子集当全量」—— 以后验收固定用本入口跑全量测试。
"""

import io
import os
import re
import subprocess
import sys

# GBK/UTF-8 控制台兼容：防止非 GBK 字符在 print 时抛 UnicodeEncodeError 中断门禁
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer,
                                  encoding=sys.stdout.encoding or "utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer,
                                  encoding=sys.stderr.encoding or "utf-8", errors="replace")
except (AttributeError, OSError, ValueError):
    pass

# 仓库根目录 = 本脚本所在目录的上一级
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLATFORM_DIR = os.path.join(REPO_ROOT, "sales_analytics_platform")
TEST_DIR = os.path.join(PLATFORM_DIR, "test")

# pytest -q 摘要形如："93 passed in 51.81s" / "2 failed, 93 passed in 60s" / "1 error in 2s"
SUMMARY_RE = re.compile(r"(\d+)\s+passed|\b(\d+)\s+failed|\b(\d+)\s+error", re.I)


def main():
    if not os.path.isdir(TEST_DIR):
        print(f"[错误] 未找到测试目录 {TEST_DIR}")
        sys.exit(2)

    cmd = [sys.executable, "-m", "pytest", "test", "-q"]
    print(f"▶ 全量测试: {' '.join(cmd)}  (cwd={PLATFORM_DIR})", flush=True)

    # 强制子进程以 UTF-8 输出，避免 Windows 下 GBK 管道解码错乱
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    rc = -1
    summary_line = ""
    n_pass = n_fail = 0
    try:
        # 流式透传输出 + 逐行捕获摘要（stderr 合并进 stdout，保证顺序一致）
        proc = subprocess.Popen(
            cmd, cwd=PLATFORM_DIR,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
            env=env,
        )
        if proc.stdout is None:  # stdout=PIPE 下实际不会为 None，仅满足类型检查
            print("[错误] 无法获取 pytest 输出管道")
            sys.exit(2)
        for line in proc.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            if SUMMARY_RE.search(line):
                summary_line = line.strip()
        proc.stdout.close()
        rc = proc.wait()
    except FileNotFoundError:
        print("[错误] 找不到 python 可执行文件")
        sys.exit(2)

    # 解析摘要
    m_pass = re.search(r"(\d+)\s+passed", summary_line)
    m_fail = re.search(r"(\d+)\s+failed", summary_line)
    if m_pass:
        n_pass = int(m_pass.group(1))
    if m_fail:
        n_fail = int(m_fail.group(1))

    print("-" * 64)
    if summary_line:
        print(f"全量测试 {n_pass} passed / {n_fail} failed")
    else:
        print(f"全量测试 未完成（未能解析 pytest 摘要，exit={rc}）")
    print(f"pytest exit code: {rc}")
    sys.exit(rc)


if __name__ == "__main__":
    main()
