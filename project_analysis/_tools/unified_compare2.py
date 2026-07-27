# -*- coding: utf-8 -*-
"""unified 对比(2): 粒度分层对账 —— 找出 2.93x 总额差异的来源"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import pandas as pd

CMP = r"E:\3-其他资料\数据分析\project_analysis\unified_compare"

def load(cand, name):
    return pd.read_csv(os.path.join(CMP, cand, name), dtype=str, encoding="utf-8-sig")

def num(s):
    return pd.to_numeric(s, errors="coerce")

print("======== 产品路径: 粒度分层 ========")
grans = {}
for cand in ("v3", "system"):
    df = load(cand, "product_path_forecast.csv")
    f = df[df["数据类型"] == "预测"].copy()
    f["销售额"] = num(f["销售额"])
    has_cat = f["品类"].notna() & (f["品类"].astype(str).str.strip() != "")
    has_sku = f["SKU"].notna() & (f["SKU"].astype(str).str.strip() != "")
    lev_pl = f[~has_cat & ~has_sku]
    lev_cat = f[has_cat & ~has_sku]
    lev_sku = f[has_sku]
    grans[cand] = {"pl": lev_pl, "cat": lev_cat, "sku": lev_sku}
    print(f"\n[{cand}] 预测行 {len(f)}  总额 {f['销售额'].sum():,.0f}")
    for tag, lev in (("产品线级(无品类无SKU)", lev_pl), ("品类级(有品类无SKU)", lev_cat), ("SKU级", lev_sku)):
        print(f"  {tag}: {len(lev)} 行, 销售额 {lev['销售额'].sum():,.0f}, PL数 {lev['产品线'].nunique()}")
    # 桶结构(列名动态探测)
    bcols = [c for c in f.columns if "桶" in c]
    buckets = f[bcols].drop_duplicates().sort_values(bcols[0])
    print("  桶定义:", buckets.to_dict("records")[:6])

print("\n======== 产品路径: 产品线清单差异 ========")
pv = load("v3", "product_path_forecast.csv"); ps = load("system", "product_path_forecast.csv")
fv = pv[pv["数据类型"] == "预测"]; fs = ps[ps["数据类型"] == "预测"]
only_v3 = sorted(set(fv["产品线"].dropna().unique()) - set(fs["产品线"].dropna().unique()))
only_sys = sorted(set(fs["产品线"].dropna().unique()) - set(fv["产品线"].dropna().unique()))
print(f"  仅v3: {only_v3}   仅system: {only_sys}")

print("\n======== 产品路径: 按产品线对账(最细粒度层) ========")
tv = ts = None
for cand in ("v3", "system"):
    g = grans[cand]
    lev = g["sku"] if len(g["sku"]) else (g["cat"] if len(g["cat"]) else g["pl"])
    t = lev.groupby("产品线")["销售额"].sum().sort_values(ascending=False)
    print(f"[{cand}] 最细粒度预测总额 {t.sum():,.0f}")
    if cand == "v3": tv = t
    else: ts = t
cmp_t = pd.DataFrame({"v3": tv, "system": ts}).fillna(0)
cmp_t["diff"] = cmp_t["v3"] - cmp_t["system"]
cmp_t["ratio"] = (cmp_t["v3"] / cmp_t["system"].replace(0, float("nan"))).round(2)
print(cmp_t.to_string())

print("\n======== 客户路径: 按客户类别对账 ========")
for cand in ("v3", "system"):
    df = load(cand, "customer_path_forecast.csv")
    f = df[df["数据类型"] == "预测"].copy()
    f["销售额"] = num(f["销售额"])
    t = f.groupby("客户类别")["销售额"].agg(["count", "sum"])
    print(f"[{cand}] 总额 {f['销售额'].sum():,.0f}")
    print(t.to_string())

print("\n======== 客户路径: KA/AA 逐客户对账(两候选共有部分) ========")
kv = load("v3", "customer_path_forecast.csv"); ks = load("system", "customer_path_forecast.csv")
fv2 = kv[(kv["数据类型"] == "预测") & (kv["客户类别"].isin(["KA>1亿", "AA>5000万"]))].copy()
fs2 = ks[(ks["数据类型"] == "预测") & (ks["客户类别"].isin(["KA>1亿", "AA>5000万"]))].copy()
fv2["销售额"] = num(fv2["销售额"]); fs2["销售额"] = num(fs2["销售额"])
sv = fv2.groupby("客户")["销售额"].sum(); ss = fs2.groupby("客户")["销售额"].sum()
cm = pd.DataFrame({"v3": sv, "system": ss}).fillna(0)
cm["ratio"] = (cm["v3"] / cm["system"].replace(0, float("nan"))).round(3)
print(f"KA/AA 客户数: v3={len(sv)} system={len(ss)} 共有={len(set(sv.index)&set(ss.index))}")
print(f"KA/AA 总额: v3={sv.sum():,.0f} system={ss.sum():,.0f} 比值={sv.sum()/ss.sum():.3f}")
bad = cm[abs(cm["ratio"] - 1) > 0.01]
print(f"比值偏离1%以上的客户数: {len(bad)}")
if len(bad): print(bad.head(10).to_string())
