# -*- coding: utf-8 -*-
r"""
批次⓪ 基线工具链 · 漂移对比
=====================================================================

两种用法：

 1. rescan 模式（默认）：对比基线快照与当前产物
      python scripts/golden_diff.py --baseline baseline\20260818\summary.json
      用 _baseline_common 现采当前 output/ 与 dashboard_a.html，与基线逐表对比。

 2. HTML 对比模式：直接对比两份看板 HTML 的内嵌 JSON
      python scripts/golden_diff.py --html-old a.html --html-new b.html

容差：
  - row_count / columns / schema_hash : 严格相等
  - 数值列合计 / KPI 标量数值          : 相对容差 1e-6（近零值用绝对容差 1e-6）
  - 字符串 / 日期                      : 严格相等

退出码：0 无漂移，1 存在漂移，2 用法错误。
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _baseline_common as common  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PLATFORM = os.path.join(REPO_ROOT, "sales_analytics_platform")

REL_TOL = 1e-6
ABS_TOL = 1e-6
NEAR_ZERO = 1e-9


# ============================================================
# 数值比较
# ============================================================

def _norm_scalar(v):
    if isinstance(v, float) and v != v:
        return None
    return v


def _num_close(a, b):
    a = float(a)
    b = float(b)
    if a != a and b != b:
        return True  # 两边都是 NaN
    if a != a or b != b:
        return False  # 仅一边 NaN
    diff = abs(a - b)
    if abs(a) < NEAR_ZERO or abs(b) < NEAR_ZERO:
        return diff <= ABS_TOL
    return diff <= REL_TOL * max(abs(a), abs(b))


def kpi_equal(a, b):
    """比较两个 KPI 值（可能是嵌套 dict/list/标量）。"""
    if isinstance(a, dict) and isinstance(b, dict):
        return a == b  # {"__array_len__": N} 等结构严格相等
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(
            kpi_equal(x, y) for x, y in zip(a, b)
        )
    a = _norm_scalar(a)
    b = _norm_scalar(b)
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return _num_close(a, b)
    return a == b


# ============================================================
# 对比逻辑
# ============================================================

def compare_csv_records(layer, name, base, cur, report):
    """对比两个 CSV 画像记录，把漂移写进 report。返回是否漂移。"""
    drift = False
    tag = f"{layer}/{name}"
    if base.get("status") != "ok" or cur.get("status") != "ok":
        report.append(f"  [状态] {tag}: baseline={base.get('status')} "
                      f"current={cur.get('status')} "
                      f"{cur.get('error', '') or base.get('error', '')}".rstrip())
        return True

    rb, rc = int(base["row_count"]), int(cur["row_count"])
    if rb != rc:
        drift = True
        report.append(f"  [行数] {tag}: {rb:,} -> {rc:,}")

    cb, cc = base["columns"], cur["columns"]
    if cb != cc:
        drift = True
        report.append(f"  [列]   {tag}: baseline={len(cb)}列 -> current={len(cc)}列")
        if len(cb) == len(cc):
            for i, (x, y) in enumerate(zip(cb, cc)):
                if x != y:
                    report.append(f"         列#{i}: {x!r} -> {y!r}")
        only_b = [c for c in cb if c not in cc]
        only_c = [c for c in cc if c not in cb]
        if only_b:
            report.append(f"         仅 baseline: {only_b}")
        if only_c:
            report.append(f"         仅 current : {only_c}")

    if base.get("schema_hash") != cur.get("schema_hash"):
        drift = True
        report.append(f"  [schema] {tag}: 哈希不一致 "
                      f"({base.get('schema_hash', '')[:8]} vs "
                      f"{cur.get('schema_hash', '')[:8]})")

    sums_b, sums_c = base.get("numeric_sums", {}), cur.get("numeric_sums", {})
    for col in sorted(set(sums_b) | set(sums_c)):
        if col in sums_b and col in sums_c:
            vb, vc = sums_b[col], sums_c[col]
            if not _num_close(vb, vc):
                drift = True
                rel = "" if (abs(vb) < NEAR_ZERO or abs(vc) < NEAR_ZERO) \
                    else f" (rel {abs(vc - vb) / max(abs(vb), abs(vc)) * 100:.6f}%)"
                report.append(f"  [数值合计] {tag} · {col}: {vb} -> {vc}{rel}")
        elif col in sums_b:
            drift = True
            report.append(f"  [数值合计] {tag} · {col}: 已消失 (baseline={sums_b[col]})")
        else:
            drift = True
            report.append(f"  [数值合计] {tag} · {col}: 新增 (current={sums_c[col]})")
    return drift


def compare_dashboard(base, cur, report):
    """对比两份看板 JSON 画像，返回是否漂移。"""
    drift = False
    sb, sc = base.get("status"), cur.get("status")
    if sb != "ok" or sc != "ok":
        report.append(f"  [看板] 状态: baseline={sb} current={sc} "
                      f"{cur.get('error', '') or base.get('error', '')}".rstrip())
        return True

    vars_b = {v["name"]: v for v in base.get("vars", [])}
    vars_c = {v["name"]: v for v in cur.get("vars", [])}
    for name in sorted(set(vars_b) | set(vars_c)):
        if name in vars_b and name in vars_c:
            vb, vc = vars_b[name], vars_c[name]
            if vb["type"] != vc["type"] or vb["len"] != vc["len"]:
                drift = True
                report.append(f"  [变量] {name}: {vb['type']}/{vb['len']} "
                              f"-> {vc['type']}/{vc['len']}")
        elif name in vars_b:
            drift = True
            report.append(f"  [变量] {name}: 已消失")
        else:
            drift = True
            report.append(f"  [变量] {name}: 新增")

    kpis_b = base.get("kpis", {})
    kpis_c = cur.get("kpis", {})
    for path in sorted(set(kpis_b) | set(kpis_c)):
        if path in kpis_b and path in kpis_c:
            if not kpi_equal(kpis_b[path], kpis_c[path]):
                drift = True
                report.append(f"  [KPI] {path}: {kpis_b[path]!r} -> {kpis_c[path]!r}")
        elif path in kpis_b:
            drift = True
            report.append(f"  [KPI] {path}: 已消失 (baseline={kpis_b[path]!r})")
        else:
            drift = True
            report.append(f"  [KPI] {path}: 新增 (current={kpis_c[path]!r})")
    return drift


# ============================================================
# rescan 模式
# ============================================================

def run_rescan(baseline_path, platform_dir):
    with open(baseline_path, "r", encoding="utf-8") as f:
        baseline = json.load(f)

    print(f"[rescan] 现采当前产物: {os.path.abspath(platform_dir)}")
    current = common.collect_summary(platform_dir)

    report = []
    drift = False

    # ── 按表对比 CSV ──
    for layer in ("silver", "gold"):
        base_tables = baseline.get("csvs", {}).get(layer, {})
        cur_tables = current.get("csvs", {}).get(layer, {})
        for name in sorted(set(base_tables) | set(cur_tables)):
            if name in base_tables and name in cur_tables:
                drift |= compare_csv_records(layer, name, base_tables[name],
                                             cur_tables[name], report)
            elif name in base_tables:
                drift = True
                report.append(f"  [表] {layer}/{name}: 已消失 (baseline 有, current 无)")
            else:
                drift = True
                report.append(f"  [表] {layer}/{name}: 新增 (current 有, baseline 无)")

    # ── 看板 JSON ──
    drift |= compare_dashboard(baseline.get("dashboard", {}),
                               current.get("dashboard", {}), report)

    return drift, report


# ============================================================
# HTML 对比模式
# ============================================================

def run_html_diff(html_old, html_new):
    base = common.parse_dashboard(html_old)
    cur = common.parse_dashboard(html_new)
    report = []
    drift = compare_dashboard({"status": "ok", **base},
                              {"status": "ok", **cur}, report)
    return drift, report


# ============================================================
# 主入口
# ============================================================

def main():
    ap = argparse.ArgumentParser(description="批次0 基线漂移对比")
    ap.add_argument("--baseline", default=None, help="基线 summary.json 路径（rescan 模式）")
    ap.add_argument("--platform-dir", default=DEFAULT_PLATFORM,
                    help="销售分析平台目录（rescan 模式现采，默认 %(default)s）")
    ap.add_argument("--html-old", default=None, help="旧看板 HTML（HTML 对比模式）")
    ap.add_argument("--html-new", default=None, help="新看板 HTML（HTML 对比模式）")
    args = ap.parse_args()

    html_mode = bool(args.html_old or args.html_new)
    if html_mode and not (args.html_old and args.html_new):
        print("[用法错误] --html-old 与 --html-new 必须同时提供。", file=sys.stderr)
        sys.exit(2)
    if not html_mode and not args.baseline:
        print("[用法错误] 需要 --baseline（rescan 模式）或 --html-old/--html-new（HTML 对比模式）。",
              file=sys.stderr)
        sys.exit(2)

    print("=" * 64)
    if html_mode:
        print("模式: HTML 对比")
        print(f"  old: {args.html_old}")
        print(f"  new: {args.html_new}")
    else:
        print("模式: rescan")
        print(f"  baseline: {args.baseline}")
        print(f"  platform: {args.platform_dir}")
    print("=" * 64)

    try:
        if html_mode:
            drift, report = run_html_diff(args.html_old, args.html_new)
        else:
            drift, report = run_rescan(args.baseline, args.platform_dir)
    except Exception as e:  # noqa: BLE001
        print(f"[错误] 对比失败: {type(e).__name__}: {e}", file=sys.stderr)
        print("      若为并发跑批导致文件半写/读取失败，请等待 60 秒后重试。",
              file=sys.stderr)
        sys.exit(1)

    print("\n== 漂移报告 ==")
    if report:
        for line in report:
            print(line)
        print(f"\n[结果] 存在 {len(report)} 处漂移。")
        sys.exit(1)
    print("[结果] 无漂移。")
    sys.exit(0)


if __name__ == "__main__":
    main()
