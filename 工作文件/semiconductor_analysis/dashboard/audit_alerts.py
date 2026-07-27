import pandas as pd

# 1. 审计告警数据
print("=== 告警类型分布 ===")
alerts = pd.read_csv('../output/gold/异常日志.csv')
print(f"总告警数: {len(alerts)}")
print(f"告警等级分布:\n{alerts['异常等级'].value_counts()}")
print(f"\n告警类型分布:\n{alerts['异常类型'].value_counts().head(10)}")

# 检查"营收断崖"类告警
cliff = alerts[alerts['异常类型'] == '营收断崖']
print(f"\n营收断崖告警数: {len(cliff)}")
print(f"详情样例:")
for _, r in cliff.head(5).iterrows():
    print(f"  {r['异常详情'][:100]}")

# 检查是否有"近3月月均0"的消息
zero_msgs = alerts[alerts['异常详情'].str.contains('近3月月均', na=False)]
print(f"\n含'近3月月均'的告警: {len(zero_msgs)}")
if len(zero_msgs) > 0:
    for _, r in zero_msgs.head(5).iterrows():
        print(f"  [{r['异常等级']}] {r['异常详情'][:120]}")

# 2. 审计采购节律
print("\n=== 采购节律抽样(前5客户) ===")
df = pd.read_csv('../output/gold/客户全景.csv')
for _, r in df.head(5).iterrows():
    name = r['客户名称']
    last = r.get('距上次采购天数', 'N/A')
    interval = r.get('常规平均采购间隔', 'N/A')
    orders = r.get('订单数', 'N/A')
    zero_pct = r.get('零采购月占比', 'N/A')
    first = r.get('首次交易日期', 'N/A')
    print(f"{name}: 距上次={last}天, 间隔={interval}天, 订单={orders}, 零采月={zero_pct}%, 首次={first}")

# 3. 检查近12月综合毛利字段
print("\n=== 近12月综合毛利 ===")
print(f"近12月毛利字段存在: {'近12月毛利' in df.columns}")
if '近12月毛利' in df.columns:
    top3 = df.nlargest(3, '近12月毛利')
    for _, r in top3.iterrows():
        print(f"  {r['客户名称']}: 近12月毛利={r['近12月毛利']:.0f}元 = {r['近12月毛利']/1e4:.1f}万元")

# 4. 检查客户月度采购量数据
print("\n=== 月度采购量数据 ===")
scm = pd.read_csv('../output/silver/silver_customer_monthly.csv')
print(f"Silver月度列: {list(scm.columns)}")
print(f"qty_sum存在: {'qty_sum' in scm.columns}")
if 'qty_sum' in scm.columns:
    cid = str(df.iloc[0]['客户编号'])
    cm = scm[scm['客户编号'].astype(str) == cid].sort_values('_月').tail(6)
    print(f"\n{df.iloc[0]['客户名称']} 最近6月采购量:")
    for _, r in cm.iterrows():
        print(f"  {r['_月']}: qty={r['qty_sum']:.0f}, rev={r['rev_sum']:.0f}")
