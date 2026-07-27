import pandas as pd

# 1. Check 新品标记 distribution
print("=== 新品标记检查 ===")
raw = pd.read_csv('../output/silver/silver_cleaned_rows.csv',
    usecols=["客户编号","产品品种","新品标记","金额","发货日期"])
print(f"总行数: {len(raw)}")
print(f"新品标记 值分布:\n{raw['新品标记'].value_counts().head(20)}")
print(f"新品标记 dtype: {raw['新品标记'].dtype}")

# 2. Filter new products
raw_new = raw[raw["新品标记"].astype(str).str.contains("是")]
print(f"\n标记为'是'的行数: {len(raw_new)}")
print(f"标记为'是'的金额>0的行数: {(raw_new['金额']>0).sum()}")
print(f"标记为'是'的金额=0的行数: {(raw_new['金额']==0).sum()}")
print(f"标记为'是'的金额NaN的行数: {raw_new['金额'].isna().sum()}")

# 3. Sample new products with 0 revenue
zero_new = raw_new[raw_new['金额'].fillna(0) == 0]
if len(zero_new) > 0:
    print(f"\n金额=0的新品行样例:")
    for _, r in zero_new.head(5).iterrows():
        print(f"  客户:{r['客户编号']} 产品:{r['产品品种']} 日期:{r['发货日期']} 金额:{r['金额']}")

# 4. Check 新品采购额 in 客户全景
print("\n=== 客户全景 新品采购额 检查 ===")
df = pd.read_csv('../output/gold/客户全景.csv')
new_amt = df['新品采购额'].fillna(0)
print(f"新品采购额>0的客户: {(new_amt>0).sum()}/{len(df)}")
print(f"新品采购额=0的客户: {(new_amt==0).sum()}/{len(df)}")

# 5. Check 新品采购占比
print(f"\n新品采购占比>0的客户: {(df['新品采购占比'].fillna(0)>0).sum()}/{len(df)}")
print(f"新品采购占比 distribution: min={df['新品采购占比'].min():.4f}, max={df['新品采购占比'].max():.4f}")
print(f"新品采购占比>0的客户占比均值: {df[df['新品采购占比']>0]['新品采购占比'].mean():.4f}")

# 6. Cross-check: 新品采购额 vs cleaned_rows new product sum
print("\n=== 交叉验证 ===")
raw_new["cid"] = raw_new["客户编号"].astype(str)
raw_new_sum = raw_new.groupby("cid")["金额"].sum()
# Check a few customers
sa = df[df['综合价值层级'].isin(['S','A'])].head(5)
for _, r in sa.iterrows():
    cid = str(r['客户编号'])
    name = r['客户名称']
    from_raw = float(raw_new_sum.get(cid, 0)) / 1e4
    from_df = r['新品采购额'] / 1e4 if pd.notna(r['新品采购额']) else 0
    print(f"{name}: cleaned_rows新品合计={from_raw:.1f}万, 客户全景新品采购额={from_df:.1f}万")
