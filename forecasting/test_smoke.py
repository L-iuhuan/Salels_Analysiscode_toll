# -*- coding: utf-8 -*-
"""冒烟测试 — forecasting 项目
用法: python test_smoke.py
当前状态: quarterly 可用(需数据); unified 待 M3 定版后启用。
"""
import csv, glob, os, subprocess, sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BRANCH = os.path.dirname(os.path.abspath(__file__))

def find_xlsx():
    for pat in ["*.xlsx", "data/*.xlsx", "../sales_analytics_platform/data/*.xlsx"]:
        hits = glob.glob(os.path.join(BRANCH, pat))
        if hits:
            return hits[0]
    return None

def check_csv(rel, min_rows=1):
    p = os.path.join(BRANCH, rel)
    if not os.path.exists(p):
        print(f"[FAIL] 输出缺失: {rel}"); return False
    with open(p, encoding="utf-8-sig", newline="") as f:
        rd = csv.reader(f)
        header = next(rd, None)
        n = sum(1 for _ in rd)
    if n < min_rows:
        print(f"[FAIL] {rel} 行数 {n} < {min_rows}"); return False
    print(f"[OK] {rel}: {n} 行"); return True

def main():
    print("=== 冒烟测试: forecasting(quarterly 产品线维度) ===")
    xlsx = find_xlsx()
    if not xlsx:
        print("[SKIP] 未找到数据 xlsx。请将原始出货明细 Excel 放入本目录或 data/,")
        print("       或确认 ../sales_analytics_platform/data/ 下存在数据文件后重跑。")
        print("补齐后将检查: quarterly/output/quarterly_forecast/*.csv 生成且行数>0")
        return 0
    qdir = os.path.join(BRANCH, "quarterly")
    cmd = [sys.executable, "run_quarterly_forecast.py", "--data", xlsx]
    print(f"[RUN] (quarterly) {' '.join(cmd)}")
    r = subprocess.run(cmd, cwd=qdir, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=1800)
    print((r.stdout or "")[-1200:])
    if r.returncode != 0:
        print(f"[FAIL] 退出码 {r.returncode}\nSTDERR尾部:\n{(r.stderr or '')[-1200:]}")
        return 1
    ok = True
    for rel in ["quarterly/output/quarterly_forecast/产品线季度历史与预测.csv",
                "quarterly/output/quarterly_forecast/预测方法排行榜.csv"]:
        ok &= check_csv(rel, min_rows=1)
    print("=== 结果:", "全部通过" if ok else "存在失败项", "===")
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
