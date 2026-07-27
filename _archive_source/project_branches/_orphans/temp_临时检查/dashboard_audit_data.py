import pandas as pd

cxp = pd.read_csv('../output/silver/silver_customer_x_product.csv')
df = pd.read_csv('../output/gold/客户全景.csv')

# 1. Check Top5 for first 3 customers
print("=== Top5 产品抽样 ===")
sa = df[df['综合价值层级'].isin(['S', 'A'])].head(5)
for _, r in sa.iterrows():
    cid = str(r['客户编号'])
    name = r['客户名称']
    cp = cxp[cxp['客户编号'].astype(str) == cid]
    top = cp.sort_values('rev_sum', ascending=False).head(8)
    products = top['产品品种'].tolist()
    unique = list(dict.fromkeys(products))  # remove dups while preserving order
    print(f"{name}: total rows={len(cp)}, top unique={len(unique)}/{len(products)}")
    for _, t in top.iterrows():
        prod = str(t['产品品种'])
        rev = float(t['rev_sum'])
        print(f"  {prod[:60]}: {rev:.0f}")
    print()

# 2. Check 采购节律
print("=== 采购节律抽样 ===")
for _, r in sa.head(3).iterrows():
    name = r['客户名称']
    last_days = r.get('距上次采购天数', 'N/A')
    interval = r.get('常规平均采购间隔', 'N/A')
    orders = r.get('订单数', 'N/A')
    zero_pct = r.get('零采购月占比', 'N/A')
    print(f"{name}: 距上次={last_days}天, 间隔={interval}天, 订单数={orders}, 零采购月={zero_pct}%")
