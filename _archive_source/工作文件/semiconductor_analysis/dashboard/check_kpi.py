import pandas as pd

df = pd.read_csv('../output/gold/客户全景.csv')

# 1. Check 收入增长率 vs YoY同比增速
print("=== 收入增长率 vs YoY同比增速 ===")
sa = df[df['综合价值层级'].isin(['S','A'])].head(10)
for _, r in sa.iterrows():
    name = r['客户名称']
    growth = r.get('收入增长率', 'N/A')
    yoy = r.get('YoY同比增速', 'N/A')
    print(f"{name}: 收入增长率={growth}, YoY同比增速={yoy}")

# 2. Check if they're actually the same column
print(f"\n收入增长率列存在: {'收入增长率' in df.columns}")
print(f"YoY同比增速列存在: {'YoY同比增速' in df.columns}")

# 3. Check values distribution
if '收入增长率' in df.columns and 'YoY同比增速' in df.columns:
    growth_vals = df['收入增长率'].dropna().head(100)
    yoy_vals = df['YoY同比增速'].dropna().head(100)
    same = (growth_vals.values == yoy_vals.values).sum()
    print(f"前100个值中相同的数量: {same}/100")

# 4. Check what "近1月" data we have
print("\n=== 近1月数据 ===")
print(f"近1月收入列存在: {'近1月收入' in df.columns}")
print(f"近1月利润列存在: {'近1月利润' in df.columns}")
print(f"近1月数量列存在: {'近1月数量' in df.columns}")
# Check all columns with '1月' or '月'
cols_with_month = [c for c in df.columns if '月' in c and '1' in c]
print(f"含'月'和'1'的列: {cols_with_month}")

# Silver latest month data
scm = pd.read_csv('../output/silver/silver_customer_monthly.csv')
scm['_m'] = scm['_月'].astype(str)
latest = scm['_m'].max()
print(f"\nSilver最新月份: {latest}")

# 5. Check if we can compute 近1月 from silver
cid = str(df.iloc[0]['客户编号'])
cm = scm[scm['客户编号'].astype(str) == cid]
latest_data = cm[cm['_m'] == latest]
print(f"\n{df.iloc[0]['客户名称']} 在{latest}:")
if len(latest_data) > 0:
    print(f"  rev={latest_data['rev_sum'].sum():.0f}, profit={latest_data['profit_clip_sum'].sum():.0f}, qty={latest_data['qty_sum'].sum():.0f}")

# 6. 品种变化
print("\n=== 品种变化 ===")
cxp = pd.read_csv('../output/silver/silver_customer_x_product.csv')
cxp['_m'] = cxp['_月'].astype(str) if '_月' in cxp.columns else None
if '_月' in cxp.columns:
    cxp_latest = cxp[cxp['_m'] == latest]
    cxp_prev = cxp[cxp['_m'] == '2025-' + latest[5:]]  # same month last year
    print(f"桥接表最新月={latest}, 去年同期=2025-{latest[5:]}")
    for _, r in sa.head(3).iterrows():
        cid2 = str(r['客户编号'])
        cur = set(cxp_latest[cxp_latest['客户编号'].astype(str) == cid2]['产品品种'].unique())
        prev = set(cxp_prev[cxp_prev['客户编号'].astype(str) == cid2]['产品品种'].unique())
        added = cur - prev
        removed = prev - cur
        print(f"{r['客户名称']}: 当前{len(cur)}品种, 新增{len(added)}, 流失{len(removed)}")
