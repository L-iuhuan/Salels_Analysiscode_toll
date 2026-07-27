import pandas as pd

raw = pd.read_csv('../output/silver/silver_cleaned_rows.csv',
    usecols=['客户编号','产品品种','新品标记','金额'])
raw_new = raw[raw['新品标记'].astype(str).str.contains('是')]
raw_new['cid'] = raw_new['客户编号'].astype(str)
prods = raw_new.groupby(['cid','产品品种'])['金额'].sum().reset_index()
small = prods[(prods['金额']>0)&(prods['金额']<10000)].sort_values('金额')
print(f'金额<1万元的新品: {len(small)}个')
print('最小金额样例:')
for _,r in small.head(10).iterrows():
    print(f'  {r["cid"]} / {r["产品品种"]}: {r["金额"]:.0f}元 = {r["金额"]/1e4:.4f}万')

# Check: how many would display as "0.0万"?
zero_display = prods[(prods['金额']>0)&(prods['金额']/1e4<0.05)]
print(f'\n显示为0.0万(金额<500元)的: {len(zero_display)}个')
# How many display as 0.1万?
tiny = prods[(prods['金额']/1e4>=0.05)&(prods['金额']/1e4<0.1)]
print(f'显示为0.1万的(500-1000元): {len(tiny)}个')
