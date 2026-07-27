# -*- coding: utf-8 -*-
"""unified 对比(3): 用历史实际裁决 v3 vs system 的量级真伪"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import pandas as pd

CMP = r"E:\3-其他资料\数据分析\project_analysis\unified_compare"

def load(cand, name):
    return pd.read_csv(os.path.join(CMP, cand, name), dtype=str, encoding="utf-8-sig")

def num(s):
    return pd.to_numeric(s, errors="coerce")

# 1) 历史实际 TTM(两候选历史行应一致,用 v3 的)
pv = load("v3", "product_path_forecast.csv")
h = pv[pv["数据类型"] == "历史"].copy()
h["销售额"] = num(h["销售额"])
mcol = next(c for c in h.columns if "桶开始" in c)
h[mcol] = h[mcol].astype(str)
monthly = h.groupby(mcol)["销售额"].sum().sort_index()
print("=== 历史月销售(最近14个月) ===")
print(monthly.tail(14).to_string())
ttm = monthly.tail(12).sum()
print(f"\nTTM(最近12个月)实际: {ttm:,.0f}")
print(f"近3个月月均: {monthly.tail(3).mean():,.0f}  -> 年化(×12): {monthly.tail(3).mean()*12:,.0f}")
print(f"\nv3 预测12个月总额   : 279,263,861  (占TTM {279263861/ttm*100:.0f}%)")
print(f"system 预测12个月总额: 817,889,069  (占TTM {817889069/ttm*100:.0f}%)")

# 2) 头部 SKU 对照: 近3月实际 vs F01桶(=2026-06~08季度)
ps = load("system", "product_path_forecast.csv")
fv = pv[(pv["数据类型"] == "预测") & (pv["桶编号"] == "F01")].copy()
fs = ps[(ps["数据类型"] == "预测") & (ps["桶编号"] == "F01")].copy()
fv["销售额"] = num(fv["销售额"]); fs["销售额"] = num(fs["销售额"])
hv = h[h[mcol] >= sorted(h[mcol].unique())[-3]].copy()  # 最近3个实际月
sku_act = hv.groupby("SKU")["销售额"].sum()  # 最近3个月实际合计
v_f01 = fv.groupby("SKU")["销售额"].sum()
s_f01 = fs.groupby("SKU")["销售额"].sum()
top = s_f01.sort_values(ascending=False).head(8).index
print("\n=== 头部SKU: 近3月实际合计 vs v3-F01 vs system-F01 ===")
print(f"{'SKU':<18}{'近3月实际':>14}{'v3 F01':>14}{'system F01':>14}{'v3/实际':>9}{'sys/实际':>9}")
for sku in top:
    a = sku_act.get(sku, 0); v = v_f01.get(sku, 0); s = s_f01.get(sku, 0)
    print(f"{sku:<18}{a:>14,.0f}{v:>14,.0f}{s:>14,.0f}{v/a if a else 0:>9.2f}{s/a if a else 0:>9.2f}")

# 3) 全体SKU层面比值分布
cmp = pd.DataFrame({"act3m": sku_act, "v3": v_f01, "sys": s_f01}).dropna(subset=["act3m"])
cmp = cmp[cmp["act3m"] > 10000]  # 排除零头
r_v = (cmp["v3"] / cmp["act3m"]).median()
r_s = (cmp["sys"] / cmp["act3m"]).median()
print(f"\nSKU级 F01/近3月实际 中位比值: v3={r_v:.2f}  system={r_s:.2f}  (季度桶合理值应≈1.0)")
