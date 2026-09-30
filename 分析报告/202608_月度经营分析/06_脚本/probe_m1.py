# -*- coding: utf-8 -*-
import pandas as pd, glob, os, sys
GOLD = r"E:\3-其他资料\数据分析\sales_analytics_platform\output\gold"
SILVER = r"E:\3-其他资料\数据分析\sales_analytics_platform\output\silver"
out = []
for fn in ["客户全景.csv", "KA_AA客户状况.csv", "客户预警.csv"]:
    p = os.path.join(GOLD, fn)
    if not os.path.isfile(p):
        out.append(f"MISSING {fn}")
        continue
    df = pd.read_csv(p, encoding="utf-8-sig")
    cols = list(df.columns)
    out.append(f"== {fn} cols={cols[:8]}")
    for c in ["客户名称", "客户编号"]:
        if c in df.columns:
            vals = df[c].astype(str)
            n_unk = (vals == "未知客户").sum()
            n_nan = vals.isin(["nan", "None", ""]).sum()
            out.append(f"   {c}: rows={len(df)} 未知客户={n_unk} nan/empty={n_nan} sample={vals.head(3).tolist()}")
sp = os.path.join(SILVER, "silver_cleaned_rows.csv")
sdf = pd.read_csv(sp, nrows=200000, encoding="utf-8-sig", usecols=["客户编号"])
v = sdf["客户编号"].astype(str)
out.append(f"== silver_cleaned_rows(前20万行) 客户编号: 未知客户={(v=='未知客户').sum()} nan={(v=='nan').sum()}")
with open(r"E:\3-其他资料\数据分析\sales_analytics_platform\output\_m1_probe.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(out))
print("done")
