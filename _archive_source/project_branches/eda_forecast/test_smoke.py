# -*- coding: utf-8 -*-
"""冒烟测试 — EDA 与出货预测实验
自动生成(2026-07-27)。用法: python test_smoke.py
逻辑: 若样例数据缺失 -> 打印 SKIP 原因与补齐方法,退出码 0;
      否则运行流水线命令并检查输出(存在性/关键列/行数>0),任何失败退出码 1。
"""
import csv, glob, os, subprocess, sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BRANCH = os.path.dirname(os.path.abspath(__file__))
TITLE = 'EDA 与出货预测实验'
SKIP_REASON = '财务分析-5月(6.3)(1).xlsx 未随包(216MB),且脚本头部数据路径变量需先修改'
SAMPLE_GLOBS = ['财务分析-5月(6.3)(1).xlsx']      # 样例数据(相对分支根),全部存在才可执行
RUN_CMDS = [('.', ['eda_analysis_v3.py'])]              # 相对分支根的工作目录 + 命令
EXPECTED = {}              # 相对路径 -> {"min_rows": n, "key_cols": [...]}
EXPECTED_GLOBS = ['eda_results.txt']  # 只需存在且非空的文件模式

def check_samples():
    missing = [g for g in SAMPLE_GLOBS
               if not glob.glob(os.path.join(BRANCH, g.replace("/", os.sep)))]
    return missing

def run_cmds():
    for cwd, cmd in RUN_CMDS:
        full = [sys.executable] + cmd
        print(f"[RUN] ({cwd}) {' '.join(full)}")
        r = subprocess.run(full, cwd=os.path.join(BRANCH, cwd),
                           capture_output=True, text=True, timeout=1800,
                           encoding="utf-8", errors="replace")
        tail = (r.stdout or "")[-1500:]
        print(tail)
        if r.returncode != 0:
            print(f"[FAIL] 命令退出码 {r.returncode}\nSTDERR尾部:\n{(r.stderr or '')[-1500:]}")
            return False
    return True

def check_csv(rel, spec):
    p = os.path.join(BRANCH, rel.replace("/", os.sep))
    if not os.path.exists(p):
        print(f"[FAIL] 输出缺失: {rel}"); return False
    with open(p, "r", encoding="utf-8-sig", newline="") as f:
        rd = csv.reader(f)
        try:
            header = next(rd)
        except StopIteration:
            print(f"[FAIL] 空文件: {rel}"); return False
        n = sum(1 for _ in rd)
    if n < spec.get("min_rows", 1):
        print(f"[FAIL] {rel} 行数 {n} < {spec.get('min_rows',1)}"); return False
    missing_cols = [c for c in spec.get("key_cols", []) if c not in header]
    if missing_cols:
        print(f"[FAIL] {rel} 缺关键列 {missing_cols}(实际列: {header[:12]}...)"); return False
    print(f"[OK] {rel}: {n} 行, 列检查通过")
    return True

def check_globs():
    ok = True
    for g in EXPECTED_GLOBS:
        hits = [h for h in glob.glob(os.path.join(BRANCH, g.replace("/", os.sep)))
                if os.path.getsize(h) > 0]
        if not hits:
            print(f"[FAIL] 无匹配输出: {g}"); ok = False
        else:
            print(f"[OK] {g}: {len(hits)} 个文件")
    return ok

def main():
    print(f"=== 冒烟测试: {TITLE} ===")
    miss = check_samples()
    if miss:
        print("[SKIP] 样例数据未就绪,缺失:")
        for m in miss:
            print(f"  - {m}")
        print(f"原因/补齐方法: {SKIP_REASON}")
        print("补齐后重新运行 python test_smoke.py 将执行完整检查:")
        for rel, spec in EXPECTED.items():
            print(f"  将检查 {rel} (min_rows={spec.get('min_rows',1)}, key_cols={spec.get('key_cols',[])})")
        return 0
    if not run_cmds():
        return 1
    ok = True
    for rel, spec in EXPECTED.items():
        if rel.endswith(".csv"):
            ok &= check_csv(rel, spec)
        else:
            p = os.path.join(BRANCH, rel.replace("/", os.sep))
            if not os.path.exists(p) or os.path.getsize(p) == 0:
                print(f"[FAIL] 输出缺失或为空: {rel}"); ok = False
            else:
                print(f"[OK] {rel} ({os.path.getsize(p)} bytes)")
    ok &= check_globs()
    print("=== 结果:", "全部通过" if ok else "存在失败项", "===")
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
