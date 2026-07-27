import pandas as pd
import numpy as np

df = pd.read_csv('../output/gold/客户全景.csv')
scm = pd.read_csv('../output/silver/silver_customer_monthly.csv')

print("=== 采购节律数据审计 ===\n")

# 1. 检查距上次采购天数分布
print("【距上次采购天数】")
vals = df['距上次采购天数'].dropna()
print(f"  非空值: {len(vals)}/{len(df)}")
print(f"  分布: min={vals.min()}, max={vals.max()}, mean={vals.mean():.1f}, median={vals.median():.1f}")
print(f"  =0 的数量: {(vals==0).sum()} ({(vals==0).sum()/len(vals)*100:.1f}%)")
print(f"  >90 的数量: {(vals>90).sum()}")
print(f"  >180 的数量: {(vals>180).sum()}")

# 2. 检查常规平均采购间隔
print("\n【常规平均采购间隔】")
vals2 = df['常规平均采购间隔'].dropna()
print(f"  非空值: {len(vals2)}/{len(df)}")
print(f"  分布: min={vals2.min():.1f}, max={vals2.max():.1f}, mean={vals2.mean():.1f}, median={vals2.median():.1f}")
print(f"  前10个值: {vals2.head(10).tolist()}")

# 3. 检查零采购月占比
print("\n【零采购月占比】")
if '零采购月占比' in df.columns:
    vals3 = df['零采购月占比'].dropna()
    print(f"  分布: min={vals3.min():.4f}, max={vals3.max():.4f}, mean={vals3.mean():.4f}")
    print(f"  =0 的数量: {(vals3==0).sum()}")

# 4. 检查订单数
print("\n【订单数】")
vals4 = df['订单数'].dropna()
print(f"  分布: min={vals4.min():.0f}, max={vals4.max():.0f}, mean={vals4.mean():.1f}, median={vals4.median():.0f}")

# 5. 查看几个具体客户的silver月度数据来验证
print("\n【Silver月度数据验证】")
sa = df[df['综合价值层级'].isin(['S','A'])].head(3)
scm['_m'] = scm['_月'].astype(str)
latest = scm['_m'].max()

for _, r in sa.iterrows():
    cid = str(r['客户编号'])
    name = r['客户名称']
    last_days = r.get('距上次采购天数', 'N/A')
    interval = r.get('常规平均采购间隔', 'N/A')

    cm = scm[scm['客户编号'].astype(str)==cid].sort_values('_m')
    purchase_months = cm[cm['rev_sum']>0]['_m'].tolist()
    zero_months = cm[cm['rev_sum']==0]['_m'].tolist()

    print(f"\n{name}:")
    print(f"  距上次采购={last_days}天, 间隔={interval}天")
    print(f"  总月份数: {len(cm)}, 有采购月: {len(purchase_months)}, 零采购月: {len(zero_months)}")
    print(f"  最后6月: {purchase_months[-6:]}")
    if len(purchase_months) >= 2:
        # 计算实际采购间隔
        last_months = cm.tail(6)
        gaps = []
        prev = None
        for _, mr in last_months.iterrows():
            if mr['rev_sum'] > 0 and prev is not None:
                gap = pd.Period(mr['_月'], freq='M') - pd.Period(prev, freq='M')
                gaps.append(gap.n)
            if mr['rev_sum'] > 0:
                prev = mr['_月']
        print(f"  近6月采购间隔(月): {gaps}")

# 6. 检查字段来源
print("\n【字段审计】")
print(f"  距上次采购天数 存在: {'距上次采购天数' in df.columns}")
print(f"  常规平均采购间隔 存在: {'常规平均采购间隔' in df.columns}")
print(f"  采购中断预警 存在: {'采购中断预警' in df.columns}")
print(f"  零采购月占比 存在: {'零采购月占比' in df.columns}")
print(f"  首次交易日期 存在: {'首次交易日期' in df.columns}")
