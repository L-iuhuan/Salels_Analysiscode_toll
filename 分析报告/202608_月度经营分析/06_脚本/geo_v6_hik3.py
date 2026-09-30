# -*- coding: utf-8 -*-
import io, os, sys
import pandas as pd
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
BASE = r"E:\3-其他资料\数据分析\sales_analytics_platform"
import glob
cands = glob.glob(os.path.join(BASE, "output", "**", "silver_cleaned_rows.parquet"), recursive=True) + \
        glob.glob(os.path.join(BASE, "output", "**", "silver_cleaned_rows.csv"), recursive=True)
cands = sorted(set(cands), key=os.path.getmtime, reverse=True)
print(cands[:3])
df = pd.read_csv(os.path.join(BASE, "output", "silver", "silver_cleaned_rows.csv"))
print("cols:", [c for c in df.columns][:30])
hk = df[df["_cust"].astype(str).str.contains("海康", na=False)]
print("海康 rows:", len(hk))
hk2 = hk.copy()
hk2["_y"] = pd.to_datetime(hk2["_d"]).dt.year
g = hk2.groupby(["_y", "_region"])["_rev"].sum().unstack(fill_value=0)
pd.set_option("display.width", 200)
print((g / 1e4).round(1))
# 2025/2026 1-8月 浙江
for y in (2025, 2026):
    m = hk2[(hk2["_y"] == y) & (pd.to_datetime(hk2["_d"]).dt.month <= 8)]
    print(y, "1-8月 分region(万):", (m.groupby("_region")["_rev"].sum() / 1e4).round(1).to_dict())
