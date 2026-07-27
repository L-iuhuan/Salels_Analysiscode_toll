# -*- coding: utf-8 -*-
"""unified 两候选对比定版: v3 vs system
指标: 列完整性 / 覆盖率(行数·客户数·品类数) / WAPE分布 / 预测horizon / 总额对账
"""
import json, os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import pandas as pd
import numpy as np

CMP = r"E:\3-其他资料\数据分析\project_analysis\unified_compare"
OUT = os.path.join(CMP, "unified_compare_report.json")

def load(cand, name):
    return pd.read_csv(os.path.join(CMP, cand, name), dtype=str, encoding="utf-8-sig")

rep = {}
for kind in ("product", "customer"):
    fn = f"{kind}_path_forecast.csv"
    a, b = load("v3", fn), load("system", fn)
    r = {"v3_rows": len(a), "system_rows": len(b)}
    ca, cb = list(a.columns), list(b.columns)
    r["cols_v3"] = ca; r["cols_system"] = cb
    r["cols_only_v3"] = [c for c in ca if c not in cb]
    r["cols_only_system"] = [c for c in cb if c not in ca]
    r["cols_common_n"] = len(set(ca) & set(cb))

    # 时间列探测: 月份/月 或 桶结构
    mcol = next((c for c in ca if "月份" in c or c in ("月", "桶开始日", "桶编号")), None)
    fa = a[a["数据类型"] == "预测"]; fb = b[b["数据类型"] == "预测"]
    # 历史/预测 行数
    r["hist_rows"] = [int((a["数据类型"] == "历史").sum()), int((b["数据类型"] == "历史").sum())]
    r["fcst_rows"] = [len(fa), len(fb)]
    # 预测总额
    sa = pd.to_numeric(fa["销售额"], errors="coerce").sum()
    sb = pd.to_numeric(fb["销售额"], errors="coerce").sum()
    r["fcst_sales_total"] = [round(float(sa), 1), round(float(sb), 1)]
    # WAPE 分布(预测行, 方法WAPE>0)
    for tag, f in (("v3", fa), ("system", fb)):
        w = pd.to_numeric(f["方法WAPE"], errors="coerce").dropna()
        w = w[w > 0]
        r[f"wape_{tag}"] = {
            "n": int(len(w)),
            "mean": round(float(w.mean()), 4) if len(w) else None,
            "median": round(float(w.median()), 4) if len(w) else None,
            "p25": round(float(w.quantile(.25)), 4) if len(w) else None,
            "p75": round(float(w.quantile(.75)), 4) if len(w) else None,
            "le_0.2_pct": round(float((w <= 0.2).mean() * 100), 1) if len(w) else None,
        }
    # 置信度分布
    r["confidence_v3"] = fa["置信度"].value_counts().to_dict() if "置信度" in fa.columns else {}
    r["confidence_system"] = fb["置信度"].value_counts().to_dict() if "置信度" in fb.columns else {}
    # 覆盖: 品类/客户
    if "产品线" in fa.columns:
        r["fcst_PLs"] = [int(fa["产品线"].nunique()), int(fb["产品线"].nunique())]
    cc = next((c for c in fa.columns if c in ("客户", "客户编号")), None)
    if cc:
        r["fcst_custs"] = [int(fa[cc].nunique()), int(fb[cc].nunique())]
    if mcol and mcol in b.columns:
        r["mcol"] = mcol
        r["forecast_months_v3"] = sorted(fa[mcol].dropna().unique().tolist())
        r["forecast_months_system"] = sorted(fb[mcol].dropna().unique().tolist())
        na = fa[mcol].nunique(); nb = fb[mcol].nunique()
        r["fcst_months_n"] = [int(na), int(nb)]
        r["fcst_sales_per_month"] = [round(float(sa) / max(na, 1), 1), round(float(sb) / max(nb, 1), 1)]
    rep[kind] = r

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(rep, f, ensure_ascii=False, indent=1, default=str)

for kind, r in rep.items():
    print(f"\n===== {kind} =====")
    print(f"行数 v3={r['v3_rows']} system={r['system_rows']}  历史/预测: {r.get('hist_rows')} / {r.get('fcst_rows')}")
    print(f"列: 共有{r['cols_common_n']}  仅v3={r['cols_only_v3']}  仅system={r['cols_only_system']}")
    print(f"预测月: v3={r.get('forecast_months_v3')}  system={r.get('forecast_months_system')}")
    print(f"预测总额: {r.get('fcst_sales_total')}  月均: {r.get('fcst_sales_per_month')}")
    print(f"覆盖: PLs={r.get('fcst_PLs')} 客户={r.get('fcst_custs')}")
    print(f"WAPE v3: {r.get('wape_v3')}")
    print(f"WAPE system: {r.get('wape_system')}")
    print(f"置信度 v3: {r.get('confidence_v3')}")
    print(f"置信度 system: {r.get('confidence_system')}")
print(f"\n报告: {OUT}")
