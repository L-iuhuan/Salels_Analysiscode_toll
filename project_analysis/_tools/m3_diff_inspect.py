# -*- coding: utf-8 -*-
"""M3 差异解剖: 对 VALUES_DIFFER/SHAPE_DIFFER 的 gold 表, 打印实际差异行"""
import os, sys, hashlib
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import pandas as pd

PLAT = r"E:\3-其他资料\数据分析\sales_analytics_platform\output\gold"
BASE = r"E:\3-其他资料\数据分析\工作文件\semiconductor_analysis\output\gold"

def load(d, name):
    return pd.read_csv(os.path.join(d, name), dtype=str, encoding="utf-8-sig").fillna("<NA>")

def row_diffs(name, key_cols, max_rows=8, max_cols=12):
    a = load(PLAT, name).set_index(key_cols)
    b = load(BASE, name).set_index(key_cols)
    print(f"\n#### {name}  key={key_cols}  plat={a.shape} base={b.shape}")
    only_a = a.index.difference(b.index); only_b = b.index.difference(a.index)
    if len(only_a): print(f"  仅平台 {len(only_a)} 行: {list(only_a)[:5]}")
    if len(only_b): print(f"  仅②   {len(only_b)} 行: {list(only_b)[:5]}")
    common = a.index.intersection(b.index)
    a2, b2 = a.loc[common], b.loc[common]
    neq = (a2 != b2)
    rows_with_diff = neq.any(axis=1)
    print(f"  共有键 {len(common)} 行, 有差异 {int(rows_with_diff.sum())} 行")
    shown = 0
    for idx in common[rows_with_diff][:max_rows]:
        diffs = [(c, a2.loc[idx, c], b2.loc[idx, c]) for c in a2.columns if neq.loc[idx, c]]
        print(f"  -- {idx}:")
        for c, va, vb in diffs[:max_cols]:
            print(f"     {c}: 平台={va!r}  ②={vb!r}")
        shown += 1
    # 列级差异计数
    col_counts = neq.sum()
    hot = col_counts[col_counts > 0].sort_values(ascending=False)
    print(f"  差异列TOP: {dict(list(hot.items())[:max_cols])}")

pd.set_option("display.width", 200)

# 1) 客户全景: 找业务负责人/渠道类型/RFM 差异客户
row_diffs("客户全景.csv", ["客户编号"], max_rows=6)

# 2) gold_kpi_daily: 看列结构再决定键
kpi = load(PLAT, "gold_kpi_daily.csv")
print(f"\n#### gold_kpi_daily 列: {list(kpi.columns)}")
key = ["日期"] if "日期" in kpi.columns else [kpi.columns[0]]
row_diffs("gold_kpi_daily.csv", key, max_rows=10)

# 3) 销售画像
sp = load(PLAT, "销售画像.csv")
print(f"\n#### 销售画像 列: {list(sp.columns)}")
row_diffs("销售画像.csv", [sp.columns[0]], max_rows=3, max_cols=17)

# 4) 品类擅长 shape 差异
cs = load(PLAT, "品类擅长.csv")
print(f"\n#### 品类擅长 列: {list(cs.columns)}")
row_diffs("品类擅长.csv", list(cs.columns[:2]), max_rows=5)

# 5) 销售人员周期表现
pp = load(PLAT, "销售人员周期表现.csv")
print(f"\n#### 销售人员周期表现 列: {list(pp.columns)}")
row_diffs("销售人员周期表现.csv", list(pp.columns[:2]), max_rows=6)

# 6) 人员 md 哈希
for p, tag in [(r"E:\3-其他资料\数据分析\sales_analytics_platform\data\部门-人员-职务对应.md", "平台"),
               (r"E:\3-其他资料\数据分析\工作文件\semiconductor_analysis\data\部门-人员-职务对应.md", "②")]:
    h = hashlib.md5(open(p, "rb").read()).hexdigest()
    print(f"\n人员md[{tag}] md5={h}")
