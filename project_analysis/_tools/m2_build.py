# -*- coding: utf-8 -*-
"""M2: 构建 forecasting 项目。
quarterly=①版(6/12权威); unified=①两候选(定版在M3跑对比); utils=①scripts;
_archive=eda/longtail/quantile实验+optimizer。只复制,不动原件。
"""
import json, os, shutil

ROOT = r"E:\3-其他资料\数据分析"
SRC1 = os.path.join(ROOT, "semiconductor_analysis")
SRC2 = os.path.join(ROOT, "工作文件", "semiconductor_analysis")
SRCW = os.path.join(ROOT, "工作文件")
DST = os.path.join(ROOT, "forecasting")
LOG = []

def cp_file(src, dst):
    if not os.path.exists(src):
        LOG.append(f"MISSING {src}"); return 0
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)
    return 1

def cp_dir(src, dst, exclude=()):
    n = 0
    if not os.path.isdir(src):
        LOG.append(f"MISSING DIR {src}"); return 0
    for dp, dn, fn in os.walk(src):
        dn[:] = [d for d in dn if d != "__pycache__" and d not in exclude]
        for f in fn:
            if f.endswith(".pyc") or f in exclude:
                continue
            n += cp_file(os.path.join(dp, f),
                         os.path.join(dst, os.path.relpath(os.path.join(dp, f), src)))
    return n

n = 0
# 1. quarterly(①权威版,排除output与__pycache__)
n += cp_dir(os.path.join(SRC1, "quarterly_forecast_package"),
            os.path.join(DST, "quarterly"), exclude=("output",))
LOG.append(f"quarterly: ①版已拷(排除output/)")

# 2. unified(两候选 + 3个backup入_archive)
for f in ["unified_forecast_v3.py", "unified_forecast_system.py"]:
    n += cp_file(os.path.join(SRC1, f), os.path.join(DST, "unified", f))
for v in ["v1", "v2", "v3"]:
    n += cp_file(os.path.join(SRC1, f"unified_forecast_system_backup_{v}.py"),
                 os.path.join(DST, "unified", "_archive", f"unified_forecast_system_backup_{v}.py"))
LOG.append("unified: v3+system两候选待M3跑对比定版;backup_v1-3入_archive")

# 3. utils(①scripts 预测工具)
for f in ["chart_data.py", "final_forecast.py", "generate_chart_html.py"]:
    n += cp_file(os.path.join(SRC1, "scripts", f), os.path.join(DST, "utils", f))
LOG.append("utils: chart_data/final_forecast/generate_chart_html")

# 4. _archive(实验草稿 + optimizer孤岛)
for f in ["eda_analysis.py", "eda_analysis_v2.py", "eda_analysis_v3.py"]:
    n += cp_file(os.path.join(SRCW, f), os.path.join(DST, "_archive", "eda_experiments", f))
n += cp_dir(os.path.join(SRCW, "longtail_forecast"), os.path.join(DST, "_archive", "longtail_forecast"))
n += cp_dir(os.path.join(SRC1, "experiment_log", "experiment_log_extra_quantile_prediction"),
            os.path.join(DST, "_archive", "quantile_prediction_experiment"))
n += cp_dir(os.path.join(SRC2, "optimizer"), os.path.join(DST, "_archive", "optimizer"))
LOG.append("_archive: eda×3 / longtail全族 / quantile实验 / optimizer")

with open(os.path.join(ROOT, "project_analysis", "m2_build_log.json"), "w", encoding="utf-8") as f:
    json.dump(LOG, f, ensure_ascii=False, indent=2)
print(json.dumps({"copied": n, "log": LOG}, ensure_ascii=False, indent=1))
