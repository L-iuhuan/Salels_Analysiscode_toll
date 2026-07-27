import pandas as pd, json

# === 1. Check new product count mismatch ===
print("=== 1. 新品明细计数审计 ===")
with open('data/b_custs.json', encoding='utf-8') as f:
    call = json.load(f)
for c in call[:5]:
    nd = c.get('new_detail', [])
    nc = c.get('new_count', 0)
    if len(nd) != nc:
        print(f"MISMATCH: {c['n']}: new_count={nc}, new_detail length={len(nd)}")
    else:
        print(f"OK: {c['n']}: count={nc}, detail={len(nd)}")

# === 2. Check 品种/在采 - what are pc and ap? ===
print("\n=== 2. 品种/在采 字段来源 ===")
df = pd.read_csv('../output/gold/客户全景.csv')
print("品种总数(全历史累计):", df['品种总数'].describe())
print("在采品种数:", df['在采品种数'].describe() if '在采品种数' in df.columns else 'NOT FOUND')
# These are ALL-TIME counts, not last 12 months!
print("→ 品种总数是 ALL-TIME 累计, 不是在采(近12月)")

# === 3. Check 品类数字段 ===
print("\n=== 3. 品类数 ===")
print("实际品类数:", df['实际品类数'].describe() if '实际品类数' in df.columns else 'NOT FOUND')
print("产品线数:", df['产品线数'].describe() if '产品线数' in df.columns else 'NOT FOUND')
# Show sample
sa = df[df['综合价值层级'].isin(['S','A'])].head(3)
for _,r in sa.iterrows():
    print(f"{r['客户名称']}: 品种总数={r['品种总数']}, 在采={r['在采品种数']}, 品类数={r.get('实际品类数','N/A')}, 产品线数={r.get('产品线数','N/A')}")

# === 4. Check 主导产品线/品类 for pie chart ===
print("\n=== 4. 饼图数据 - 主导产品线 vs 品类 ===")
for _,r in sa.head(3).iterrows():
    print(f"{r['客户名称']}: 主导产品线={r.get('主导产品线','N/A')} (占比={r.get('主导产品线占比','N/A')})")
    print(f"  主导品类={r.get('主导品类','N/A')} (占比={r.get('主导品类占比','N/A')})")

# === 5. Check B面近12月唯一品种数 ===
print("\n=== 5. 近12月实际在采品种(从桥接表) ===")
cxp = pd.read_csv('../output/silver/silver_customer_x_product.csv')
cxp['_ym'] = cxp['_月'].astype(str)
latest = cxp['_ym'].max()
cutoff = f"{int(latest[:4])-1}-{latest[5:]}"
cxp_12m = cxp[(cxp['_ym'] >= cutoff) & (cxp['_ym'] <= latest)]
for _,r in sa.head(3).iterrows():
    cid = str(r['客户编号'])
    cp = cxp_12m[cxp_12m['客户编号'].astype(str) == cid]
    unique_prods = cp['产品品种'].nunique()
    unique_cats = cp['产品一级分类'].nunique() if '产品一级分类' in cp.columns else 0
    print(f"{r['客户名称']}: 近12月唯一品种={unique_prods}, 唯一品类={unique_cats}")
