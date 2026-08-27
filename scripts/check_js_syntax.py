# -*- coding: utf-8 -*-
r"""
JS 语法门禁 · 校验看板 HTML 中所有 <script> 块的语法
=====================================================================

从 sales_analytics_platform/dashboard/dashboard_a.html 提取全部 <script> 块，
逐块调用 node --check 做语法校验（临时文件写入 %TEMP%）：

  python scripts/check_js_syntax.py

结果：
  全部通过  → 打印 "JS: ALL OK (N blocks)"，exit 0
  任一失败  → 打印块号 + node 错误首行，exit 1
  HTML 缺失 → 提示「先跑生成」，exit 2
"""

import io
import os
import re
import subprocess
import sys
import tempfile

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
HTML_PATH = os.path.join(REPO_ROOT, "sales_analytics_platform", "dashboard", "dashboard_a.html")

# 提取 <script> 块（含 type=module / src 等属性的块；空块跳过）
SCRIPT_RE = re.compile(r"<script[^>]*>(.*?)</script>", re.S)


def main():
    if not os.path.exists(HTML_PATH):
        print(f"[错误] 未找到 {HTML_PATH}")
        print("先跑生成：python sales_analytics_platform/run_chain.py（或 dashboard/generate_dashboard.py）后重试。")
        sys.exit(2)

    with open(HTML_PATH, "r", encoding="utf-8") as f:
        html = f.read()

    # 取所有 <script> 块，跳过空白块
    blocks = SCRIPT_RE.findall(html)
    non_empty = [(idx, body) for idx, body in enumerate(blocks) if body.strip()]
    n = len(non_empty)

    if n == 0:
        print("JS: ALL OK (0 blocks)")
        sys.exit(0)

    tmp_dir = tempfile.gettempdir()  # %TEMP%
    failed_block = None
    for idx, body in non_empty:
        block_no = idx + 1  # 块号（从 1 开始，对应 HTML 中出现顺序）
        tmp_path = os.path.join(tmp_dir, f"js_check_block_{block_no}.js")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(body)
            proc = subprocess.run(
                ["node", "--check", tmp_path],
                capture_output=True, text=True,
                encoding="utf-8", errors="replace",
            )
            if proc.returncode != 0:
                err = (proc.stderr or proc.stdout or "").strip()
                first_line = err.splitlines()[0] if err.splitlines() else "(无错误输出)"
                print(f"[FAIL] script 块 #{block_no}: node --check 失败")
                print(f"       错误首行: {first_line}")
                failed_block = block_no
                break
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    if failed_block is not None:
        print(f"[结果] JS 语法门禁未通过（块 #{failed_block} 报错）")
        sys.exit(1)

    print(f"JS: ALL OK ({n} blocks)")
    sys.exit(0)


if __name__ == "__main__":
    main()
