# -*- coding: utf-8 -*-
"""阶段五b:修正清单路径错误(第二轮)。
- eda_forecast: longtail_forecast/ 子目录才是真实位置
- deep_dive: audit_html.py 在 dashboard/
- _orphans temp: check_*/find_*/verify_* 实际在 ②/dashboard/
"""
import json, os, shutil

ROOT = r"E:\3-其他资料\数据分析"
SRC_MAIN = os.path.join(ROOT, "工作文件", "semiconductor_analysis")
SRC_WORK = os.path.join(ROOT, "工作文件")
BRANCHES = os.path.join(ROOT, "project_branches")
ANALYSIS_DIR = os.path.join(ROOT, "project_analysis")

rep = json.load(open(os.path.join(ANALYSIS_DIR, "05_branches_report.json"), encoding="utf-8"))

def copy_file(src, dst):
    if not os.path.exists(src):
        print("STILL MISSING:", src); return 0
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)
    return 1

# 1. eda_forecast
n = 0
n += copy_file(os.path.join(SRC_WORK, "longtail_forecast", "run_longtail_forecast.py"),
               os.path.join(BRANCHES, "eda_forecast", "run_longtail_forecast.py"))
n += copy_file(os.path.join(SRC_WORK, "longtail_forecast", "v3", "run_full_forecast_v3.py"),
               os.path.join(BRANCHES, "eda_forecast", "run_full_forecast_v3.py"))
for f, a in [("eda_analysis.py", "eda_analysis_v1.py"), ("eda_analysis_v2.py", "eda_analysis_v2.py")]:
    n += copy_file(os.path.join(SRC_WORK, f), os.path.join(BRANCHES, "eda_forecast", "_archive", a))
n += copy_file(os.path.join(SRC_WORK, "longtail_forecast", "v2", "run_full_forecast_v2.py"),
               os.path.join(BRANCHES, "eda_forecast", "_archive", "run_full_forecast_v2.py"))
rep["branches"]["eda_forecast"]["files_copied"] += n

# 2. deep_dive: audit_html.py 在 dashboard/
n = copy_file(os.path.join(SRC_MAIN, "dashboard", "audit_html.py"),
              os.path.join(BRANCHES, "deep_dive_h1_report", "audit_html.py"))
rep["branches"]["deep_dive_h1_report"]["files_copied"] += n

# 3. _orphans temp: dashboard/ 下的剩余检查脚本
n = 0
for f in ["check_col.py", "check_kpi2.py", "data_inventory.py", "final_audit.py",
          "find_col.py", "find_col3.py", "find_col4.py", "verify_raw.py", "verify_syntax.py"]:
    n += copy_file(os.path.join(SRC_MAIN, "dashboard", f),
                   os.path.join(BRANCHES, "_orphans", "temp_临时检查", "dashboard_" + f))
rep["branches"]["_orphans"]["files_copied"] += n

# 修正 missing 列表(重新核对)
still_missing = []
for m in rep["missing"]:
    if not any(k in m for k in ["audit_html", "longtail", "full_forecast", "check_", "find_col",
                                 "data_inventory", "final_audit", "final_check", "verify_raw",
                                 "verify_syntax"]):
        still_missing.append(m)
rep["missing_round2_resolved"] = len(rep["missing"]) - len(still_missing)
rep["missing"] = still_missing
with open(os.path.join(ANALYSIS_DIR, "05_branches_report.json"), "w", encoding="utf-8") as f:
    json.dump(rep, f, ensure_ascii=False, indent=2)
print(json.dumps({"fixed": {b: v["files_copied"] for b, v in rep["branches"].items()},
                  "still_missing": still_missing}, ensure_ascii=False))
