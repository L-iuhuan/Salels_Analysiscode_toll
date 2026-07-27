#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试框架入口：三阶段编排器。

依次执行或单独执行各阶段：
  Phase 1: 加载 & Silver 构建
  Phase 2: 测试用例验证（TEST A-H）
  Phase 3: 可视化图表生成（01-05）

使用 --skip-* 跳过特定阶段。
使用 --stage 2 只运行第二阶段。

使用示例：
    python test/run_all_tests.py                          # 全部运行
    python test/run_all_tests.py --skip-load               # 使用已有缓存
    python test/run_all_tests.py --stage 2                 # 仅验证
    python test/run_all_tests.py --stage 3                 # 仅图表
    python test/run_all_tests.py --tests A,B,C             # 仅指定用例
    python test/run_all_tests.py --force                   # 强制重载数据
    python test/run_all_tests.py --file path/to/data.xlsx  # 指定数据文件
"""

import sys, os, time, argparse, importlib.util, subprocess

_TEST_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_TEST_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from test.conftest import header, log

# ============================================================
# 自动依赖安装
# ============================================================

REQUIRED = [
    "pandas", "numpy", "openpyxl", "statsmodels",
    "chinese_calendar", "rapidfuzz", "matplotlib",
    "sklearn",  # scikit-learn's import name is "sklearn"
]
# Note: python-calamine is optional (gives 5-10x speedup), not in required list


def _auto_install_deps():
    """检查必需依赖，缺失时自动从 requirements.txt 安装。"""
    missing = []
    for pkg in REQUIRED:
        if importlib.util.find_spec(pkg) is None:
            missing.append(pkg)

    if missing:
        req_path = os.path.join(_PROJECT_ROOT, "requirements.txt")
        print(f"[自动安装] 检测到缺失依赖: {', '.join(missing)}")
        print(f"[自动安装] 正在安装: pip install -r requirements.txt")
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "-r", req_path]
            )
            print(f"[自动安装] 依赖安装完成")
        except Exception as e:
            print(f"[自动安装] 警告: 依赖安装失败 ({e})，请手动执行: "
                  f"pip install -r requirements.txt")


def main():
    _auto_install_deps()

    parser = argparse.ArgumentParser(
        description="半导体分析测试框架 — 三阶段编排器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
阶段说明：
  Phase 1 (加载)    ：读 Excel → ERP列映射 → 数据清洗 → Silver聚合 → 保存中间件
  Phase 2 (验证)    ：加载中间件 → 执行 TEST A-H → 输出 CSV/JSON/Markdown
  Phase 3 (可视化)  ：加载中间件 → 生成 5 张诊断图表 → 保存至 charts/

使用示例：
  %%(prog)s                          # 全部三阶段
  %%(prog)s --skip-load              # 使用已有缓存，仅验证+图表
  %%(prog)s --stage 2                # 仅运行验证
  %%(prog)s --stage 2 --tests A,B,C  # 仅运行指定用例
  %%(prog)s --force                  # 强制重新加载数据
  %%(prog)s --file data.xlsx         # 指定数据文件
        """,
    )

    # ── 阶段控制 ──
    parser.add_argument("--stage", type=str, default=None,
                        choices=["1", "2", "3"],
                        help="仅运行指定阶段（1/2/3），不指定则运行全部")
    parser.add_argument("--skip-load", action="store_true",
                        help="跳过 Phase 1（加载&Silver），使用已有缓存")
    parser.add_argument("--skip-validate", action="store_true",
                        help="跳过 Phase 2（验证）")
    parser.add_argument("--skip-visualize", action="store_true",
                        help="跳过 Phase 3（可视化）")

    # ── 数据控制 ──
    parser.add_argument("--force", action="store_true",
                        help="强制重新加载数据（忽略中间件缓存）")
    parser.add_argument("--file", type=str, default=None,
                        help="数据文件路径（默认自动检测）")

    # ── 验证控制 ──
    parser.add_argument("--tests", type=str, default=None,
                        help="逗号分隔的测试 ID，如 A,B,C（默认全部 A-H）")
    parser.add_argument("--skip-report", action="store_true",
                        help="跳过 JSON/Markdown 报告生成")

    # ── 可视化控制 ──
    parser.add_argument("--charts", type=str, default=None,
                        help="逗号分隔的图表 ID，如 1,3,5（默认全部 1-5）")
    parser.add_argument("--chart-format", type=str, default="png",
                        choices=["png", "pdf", "svg"],
                        help="图表输出格式（默认 png）")
    parser.add_argument("--chart-dpi", type=int, default=150,
                        help="图表分辨率（默认 150）")

    args = parser.parse_args()

    t_start = time.time()

    # ════════════════════════════════════════════════════════════
    # Phase 1: 加载 & Silver
    # ════════════════════════════════════════════════════════════
    data = None
    run_p1 = (args.stage is None or args.stage == "1") and not args.skip_load

    if run_p1:
        header("Phase 1：加载 & Silver 构建")
        from test.phase1_load import run_phase1
        data = run_phase1(data_file=args.file, force=args.force)
    else:
        if args.stage is None and args.skip_load:
            header("Phase 1：跳过（--skip-load）")
        elif args.stage is not None and args.stage != "1":
            header("Phase 1：跳过（仅运行 Stage {})".format(args.stage))

    # ════════════════════════════════════════════════════════════
    # Phase 2: 验证
    # ════════════════════════════════════════════════════════════
    run_p2 = (args.stage is None or args.stage == "2") and not args.skip_validate
    suite = None

    if run_p2:
        from test.phase2_validate import run_phase2

        # 如果 Phase 1 未执行，需要加载中间件
        if data is None:
            from test.conftest import load_intermediates
            data = load_intermediates()

        # 应用回退策略
        from test.fallback import apply_all_fallbacks
        data = apply_all_fallbacks(data)

        tests = args.tests if args.tests else "A,B,C,D,E,F,G,H"
        suite = run_phase2(tests=tests, skip_report=args.skip_report, data=data)
    else:
        if args.stage is None and args.skip_validate:
            header("Phase 2：跳过（--skip-validate）")
        elif args.stage is not None and args.stage != "2":
            if not run_p1:
                header("Phase 2：跳过（仅运行 Stage {})".format(args.stage))

    # ════════════════════════════════════════════════════════════
    # Phase 3: 可视化
    # ════════════════════════════════════════════════════════════
    run_p3 = (args.stage is None or args.stage == "3") and not args.skip_visualize

    if run_p3:
        from test.phase3_visualize import run_phase3

        if data is None:
            from test.conftest import load_intermediates
            data = load_intermediates()

        # 检查回退是否标记跳过可视化
        if data.get("_skip_phase3"):
            header("Phase 3：跳过（matplotlib 不可用）")
        else:
            charts = args.charts if args.charts else "1,2,3,4,5"
            run_phase3(charts=charts, fmt=args.chart_format, dpi=args.chart_dpi, data=data)
    else:
        if args.stage is None and args.skip_visualize:
            header("Phase 3：跳过（--skip-visualize）")
        elif args.stage is not None and args.stage != "3":
            if not run_p1 and not run_p2:
                header("Phase 3：跳过（仅运行 Stage {})".format(args.stage))

    # ════════════════════════════════════════════════════════════
    # 汇总
    # ════════════════════════════════════════════════════════════
    total_elapsed = time.time() - t_start

    print()
    print("=" * 60)
    if suite:
        s = suite.summary
        print(f"  TEST: {s['pass']}/{s['total']} PASS  |  "
              f"FAIL {s['fail']}  |  SKIP {s['skip']}  |  WARN {s['warn']}")
    print(f"  总耗时: {total_elapsed:.1f}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
