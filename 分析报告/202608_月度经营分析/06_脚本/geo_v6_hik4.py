# -*- coding: utf-8 -*-
import io, os, sys
import pandas as pd
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
BASE = r"E:\3-其他资料\数据分析\sales_analytics_platform"
sys.path.insert(0, os.path.join(BASE, "dashboard"))
df = pd.read_csv(os.path.join(BASE, "output", "silver", "silver_cleaned_rows.csv"),
                 usecols=["发货日期", "金额", "利润", "数量", "客户类别", "客户编号", "发货地址"],
                 encoding="utf-8-sig", low_memory=False)
df["_d"] = pd.to_datetime(df["发货日期"], errors="coerce")
df["_rev"] = pd.to_numeric(df["金额"], errors="coerce").fillna(0)
df["_cust"] = df["客户编号"].astype(str).str.strip().str.replace("未知客户", "nan")
df["_addr"] = df["发货地址"].astype(str).str.strip()
import geo_resolver as _geo
_geod = _geo.load_dict()
res = {a: _geo.resolve_region(a, _geod) for a in df["_addr"].unique()}
df["_region"] = df["_addr"].map(lambda a: res[a][0])
df["_y"] = df["_d"].dt.year
df["_m"] = df["_d"].dt.month
hk = df[df["_cust"].str.contains("海康", na=False)]
print("海康 rows:", len(hk), " 客户编号值:", hk["_cust"].unique()[:5])
g = hk.groupby(["_y", "_region"])["_rev"].sum().unstack(fill_value=0) / 1e4
pd.set_option("display.width", 250)
print(g.round(1))
for y in (2025, 2026):
    m = hk[(hk["_y"] == y) & (hk["_m"] <= 8)]
    print(y, "1-8月:", round(m["_rev"].sum() / 1e4, 1), "分region:", (m.groupby("_region")["_rev"].sum() / 1e4).round(1).to_dict())
# 对比：2025年海康 浙江 1-8月 明细地址
zj25 = hk[(hk["_y"] == 2025) & (hk["_region"] == "浙江")]
print("2025 浙江 rows:", len(zj25), "rev(万):", round(zj25["_rev"].sum() / 1e4, 2))
if len(zj25):
    print(zj25["_addr"].value_counts().head(5).to_dict())
hk25 = hk[hk["_y"] == 2025]
print("2025 全部 region:", (hk25.groupby("_region")["_rev"].sum() / 1e4).round(1).to_dict())
