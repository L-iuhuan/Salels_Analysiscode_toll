# -*- coding: utf-8 -*-
"""阶段六:为每个分支生成 test_smoke.py,并把可执行分支的样例数据补齐。
只复制小文件;执行仅 recession_risk_opt(其余脚本生成后由用户补数据再跑)。
"""
import os, shutil, json

ROOT = r"E:\3-其他资料\数据分析"
BRANCHES = os.path.join(ROOT, "project_branches")
SRC_DOC = os.path.join(ROOT, "semiconductor_analysis")

TEMPLATE = '''# -*- coding: utf-8 -*-
"""冒烟测试 — {title}
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
TITLE = {title!r}
SKIP_REASON = {skip_reason!r}
SAMPLE_GLOBS = {sample_globs!r}      # 样例数据(相对分支根),全部存在才可执行
RUN_CMDS = {run_cmds!r}              # 相对分支根的工作目录 + 命令
EXPECTED = {expected!r}              # 相对路径 -> {{"min_rows": n, "key_cols": [...]}}
EXPECTED_GLOBS = {expected_globs!r}  # 只需存在且非空的文件模式

def check_samples():
    missing = [g for g in SAMPLE_GLOBS
               if not glob.glob(os.path.join(BRANCH, g.replace("/", os.sep)))]
    return missing

def run_cmds():
    for cwd, cmd in RUN_CMDS:
        full = [sys.executable] + cmd
        print(f"[RUN] ({{cwd}}) {{' '.join(full)}}")
        r = subprocess.run(full, cwd=os.path.join(BRANCH, cwd),
                           capture_output=True, text=True, timeout=1800,
                           encoding="utf-8", errors="replace")
        tail = (r.stdout or "")[-1500:]
        print(tail)
        if r.returncode != 0:
            print(f"[FAIL] 命令退出码 {{r.returncode}}\\nSTDERR尾部:\\n{{(r.stderr or '')[-1500:]}}")
            return False
    return True

def check_csv(rel, spec):
    p = os.path.join(BRANCH, rel.replace("/", os.sep))
    if not os.path.exists(p):
        print(f"[FAIL] 输出缺失: {{rel}}"); return False
    with open(p, "r", encoding="utf-8-sig", newline="") as f:
        rd = csv.reader(f)
        try:
            header = next(rd)
        except StopIteration:
            print(f"[FAIL] 空文件: {{rel}}"); return False
        n = sum(1 for _ in rd)
    if n < spec.get("min_rows", 1):
        print(f"[FAIL] {{rel}} 行数 {{n}} < {{spec.get('min_rows',1)}}"); return False
    missing_cols = [c for c in spec.get("key_cols", []) if c not in header]
    if missing_cols:
        print(f"[FAIL] {{rel}} 缺关键列 {{missing_cols}}(实际列: {{header[:12]}}...)"); return False
    print(f"[OK] {{rel}}: {{n}} 行, 列检查通过")
    return True

def check_globs():
    ok = True
    for g in EXPECTED_GLOBS:
        hits = [h for h in glob.glob(os.path.join(BRANCH, g.replace("/", os.sep)))
                if os.path.getsize(h) > 0]
        if not hits:
            print(f"[FAIL] 无匹配输出: {{g}}"); ok = False
        else:
            print(f"[OK] {{g}}: {{len(hits)}} 个文件")
    return ok

def main():
    print(f"=== 冒烟测试: {{TITLE}} ===")
    miss = check_samples()
    if miss:
        print("[SKIP] 样例数据未就绪,缺失:")
        for m in miss:
            print(f"  - {{m}}")
        print(f"原因/补齐方法: {{SKIP_REASON}}")
        print("补齐后重新运行 python test_smoke.py 将执行完整检查:")
        for rel, spec in EXPECTED.items():
            print(f"  将检查 {{rel}} (min_rows={{spec.get('min_rows',1)}}, key_cols={{spec.get('key_cols',[])}})")
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
                print(f"[FAIL] 输出缺失或为空: {{rel}}"); ok = False
            else:
                print(f"[OK] {{rel}} ({{os.path.getsize(p)}} bytes)")
    ok &= check_globs()
    print("=== 结果:", "全部通过" if ok else "存在失败项", "===")
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
'''

def write_test(branch, **kw):
    p = os.path.join(BRANCHES, branch, "test_smoke.py")
    with open(p, "w", encoding="utf-8") as f:
        f.write(TEMPLATE.format(title=kw["title"],
                                skip_reason=kw["skip_reason"],
                                sample_globs=kw.get("sample_globs", []),
                                run_cmds=kw.get("run_cmds", []),
                                expected=kw.get("expected", {}),
                                expected_globs=kw.get("expected_globs", [])))
    print("written:", branch)

# ---- recession_risk_opt: 补样例数据(小文件) ----
rec = os.path.join(BRANCHES, "recession_risk_opt")
os.makedirs(os.path.join(rec, "output", "silver"), exist_ok=True)
os.makedirs(os.path.join(rec, "output", "gold"), exist_ok=True)
for f in ["silver_product_monthly.csv", "silver_customer_x_product.csv"]:
    shutil.copy2(os.path.join(SRC_DOC, "output", "silver", f),
                 os.path.join(rec, "output", "silver", f))
shutil.copy2(os.path.join(SRC_DOC, "output", "gold", "gold_product_portrait.csv"),
             os.path.join(rec, "output", "gold", "gold_product_portrait.csv"))

write_test("recession_risk_opt",
    title="衰退风险优化(phaseB1a 严重度回归)",
    skip_reason="样例数据已随包(output/silver 2张 + gold 1张),此分支不应SKIP",
    sample_globs=["output/silver/silver_product_monthly.csv",
                  "output/silver/silver_customer_x_product.csv",
                  "recession_risk_opt/data/samples.pkl"],
    run_cmds=[(".", [os.path.join("recession_risk_opt", "phaseB1a_severity_regression.py")])],
    expected={"recession_risk_opt/output/phaseB1a_results.pkl": {}},
    expected_globs=["recession_risk_opt/output/phaseB1a_*.png", "recession_risk_opt/output/phaseB1a_*.md"])

write_test("main_pipeline",
    title="主流水线(silver 阶段)",
    skip_reason="财务分析 xlsx 未随包(>50MB)。请将任一 财务分析-N月.xlsx 放入 data/ "
                "(原位置: E:\\3-其他资料\\数据分析\\工作文件\\semiconductor_analysis\\data\\财务分析-6月（7.6）.xlsx)",
    sample_globs=["data/*.xlsx"],
    run_cmds=[(".", ["run_all.py", "--stage", "silver"])],
    expected={"output/silver/silver_cleaned_rows.csv": {"min_rows": 1000, "key_cols": ["客户编号"]},
              "output/silver/silver_customer_monthly.csv": {"min_rows": 10, "key_cols": ["客户编号"]},
              "output/silver/silver_product_monthly.csv": {"min_rows": 10, "key_cols": []},
              "output/silver/silver_customer_x_product.csv": {"min_rows": 10, "key_cols": []}},
    expected_globs=[])

write_test("dashboard_chain",
    title="看板流水线(全链)",
    skip_reason="data/ 下无 xlsx。请放入任一 财务分析-N月.xlsx 后运行(或用 run_chain.py --data 指定)",
    sample_globs=["data/*.xlsx"],
    run_cmds=[(".", ["run_chain.py"])],
    expected={"dashboard/dashboard_a.html": {}},
    expected_globs=["output/gold/*.csv"])

write_test("deep_dive_h1_report",
    title="2026H1 深度分析报告群",
    skip_reason="脚本硬编码 C:/Users/45091/Desktop 路径,需先批量替换为本机路径;且依赖主流水线 silver 产物",
    sample_globs=["output/silver/silver_customer_x_product.csv"],
    run_cmds=[(".", ["deep_all.py"])],
    expected={},
    expected_globs=["deep_*.md"])

write_test("eda_forecast",
    title="EDA 与出货预测实验",
    skip_reason="财务分析-5月(6.3)(1).xlsx 未随包(216MB),且脚本头部数据路径变量需先修改",
    sample_globs=["财务分析-5月(6.3)(1).xlsx"],
    run_cmds=[(".", ["eda_analysis_v3.py"])],
    expected={},
    expected_globs=["eda_results.txt"])

write_test("quarterly_forecast",
    title="季度预测包",
    skip_reason="需原始出货明细 Excel(未随包)。放入后先核对 run_quarterly_forecast.py 内的数据路径配置",
    sample_globs=["data/*.xlsx"],
    run_cmds=[(".", ["run_quarterly_forecast.py"])],
    expected={},
    expected_globs=["output/quarterly_forecast/*.csv"])

write_test("unified_forecast",
    title="统一预测系统",
    skip_reason="需先运行 quarterly_forecast 分支产出 预测方案总行版.csv",
    sample_globs=["output/quarterly_forecast_customer/预测方案总行版.csv"],
    run_cmds=[(".", ["unified_forecast_v3.py"])],
    expected={},
    expected_globs=["*.csv"])

write_test("product_lifecycle_legacy_v28",
    title="产品生命周期评估 v2.8(存档)",
    skip_reason="需 所有的出货明细5.9.xlsx(137MB,未随包;"
                "原位置 E:\\3-其他资料\\数据分析\\产品生命周期评估\\),放入本分支根目录后运行",
    sample_globs=["所有的出货明细5.9.xlsx"],
    run_cmds=[(".", ["run_v2.8.py"])],
    expected={},
    expected_globs=["output_v2.8_*.xlsx"])

print("all smoke tests written")
