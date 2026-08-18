# -*- coding: utf-8 -*-
r"""
批次⓪ 基线工具链 · 冻结基线
=====================================================================

采集销售分析平台的当前产物状态并冻结为基线快照：

  python scripts/freeze_baseline.py
  python scripts/freeze_baseline.py --out-dir baseline\20260818 --label "2026-07 基线"
  python scripts/freeze_baseline.py --platform-dir path/to/platform

产出：
  输出目录/summary.json —— 全部采集结果（UTF-8、ensure_ascii=False、indent=2）。
"""

import argparse
import datetime
import json
import os
import sys

# 保证可被当作模块直接运行（scripts/ 同目录的 _baseline_common）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _baseline_common as common  # noqa: E402

# 仓库根目录 = 本脚本所在目录的上一级
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PLATFORM = os.path.join(REPO_ROOT, "sales_analytics_platform")


def main():
    ap = argparse.ArgumentParser(description="冻结销售分析平台基线快照")
    ap.add_argument("--platform-dir", default=DEFAULT_PLATFORM,
                    help="销售分析平台目录（默认 %(default)s）")
    ap.add_argument("--out-dir", default=None,
                    help="基线输出目录（默认 baseline\\YYYYMMDD，相对仓库根）")
    ap.add_argument("--label", default=None, help="可选的基线标签（写入 summary.json）")
    args = ap.parse_args()

    # ── 计算输出目录 ──
    if args.out_dir:
        out_dir = args.out_dir if os.path.isabs(args.out_dir) \
            else os.path.join(REPO_ROOT, args.out_dir)
    else:
        stamp = datetime.datetime.now().strftime("%Y%m%d")
        out_dir = os.path.join(REPO_ROOT, "baseline", stamp)
    os.makedirs(out_dir, exist_ok=True)

    # ── 采集 ──
    print(f"[采集] 平台目录: {os.path.abspath(args.platform_dir)}")
    try:
        summary = common.collect_summary(args.platform_dir)
    except Exception as e:  # noqa: BLE001
        print(f"[错误] 采集失败: {type(e).__name__}: {e}", file=sys.stderr)
        print("      若为并发跑批导致文件半写，请等待 60 秒后重试。", file=sys.stderr)
        sys.exit(1)

    if args.label:
        summary["label"] = args.label

    # ── 写文件 ──
    out_path = os.path.join(out_dir, "summary.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"[写入] {out_path}")

    # ── 打印采集摘要 ──
    counts, rows, n_vars, n_kpis = common.csvs_summary(summary)
    print("=" * 60)
    print("采集摘要")
    print(f"  silver 文件: {counts.get('silver', 0)}    gold 文件: {counts.get('gold', 0)}")
    print(f"  总行数:      {rows:,}")
    print(f"  看板顶层变量: {n_vars}    标量 KPI 点: {n_kpis}")
    md = summary.get("metadata", {})
    print(f"  git HEAD:    {md.get('git_head') or 'N/A'}  ({md.get('git_branch') or ''})")
    print(f"  数据目录文件: {len(md.get('data_dir_files', []))} 个")
    dash = summary.get("dashboard", {})
    if dash.get("status") != "ok":
        print(f"  [警告] 看板解析状态: {dash.get('status')} {dash.get('error', '')}")
    # 检查是否有采集失败的 CSV
    bad = []
    for layer in ("silver", "gold"):
        for name, rec in summary.get("csvs", {}).get(layer, {}).items():
            if rec.get("status") != "ok":
                bad.append(f"{layer}/{name}: {rec.get('error', rec.get('status'))}")
    if bad:
        print(f"  [警告] 以下 CSV 采集异常（基线不完整，建议重试）:")
        for b in bad:
            print(f"         - {b}")
    print("=" * 60)


if __name__ == "__main__":
    main()
