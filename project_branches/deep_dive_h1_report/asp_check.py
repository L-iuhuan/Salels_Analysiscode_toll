# -*- coding: utf-8 -*-
import pandas as pd, numpy as np, io
path = r"C:\Users\45091\Desktop\工作文件\semiconductor_analysis\data\财务分析-5月（6.3）.xlsx"
RAW=['发货日期','实际业务员','存货名称','发货数量','未税单价','原币含税单价',
     'RMB 未税金额小计','利润','助理备注','业务类型','销售类型名称']
A=dict(zip(RAW,['date','sales','sku','qty','price_untax','price_tax','rev','profit','note','biz','saletype']))
out=io.StringIO()
def p(*a): print(*a,file=out)
df=pd.read_excel(path,sheet_name='24-26',usecols=RAW).rename(columns=A)
df['date']=pd.to_datetime(df['date'],errors='coerce'); df=df.dropna(subset=['date'])
for c in ['qty','price_untax','price_tax','rev','profit']: df[c]=pd.to_numeric(df[c],errors='coerce')
df['y']=df['date'].dt.year; df['m']=df['date'].dt.month
cur=df[(df['y']==2026)&(df['m']<=6)].copy()
p("2026H1 总行数(含负/零):",len(cur))
p("\n== 按 qty/rev 分布 ==")
p("qty>0 & rev>0 (正常付费行):", len(cur[(cur['qty']>0)&(cur['rev']>0)]))
p("qty>0 & rev==0 (疑赠送/免费行):", len(cur[(cur['qty']>0)&(cur['rev']==0)]))
p("qty>0 & rev<0 (负收入):", len(cur[(cur['qty']>0)&(cur['rev']<0)]))
p("qty==0 & rev>0:", len(cur[(cur['qty']==0)&(cur['rev']>0)]))
p("qty<0 (退货):", len(cur[(cur['qty']<0)]))
# 看赠送行的样子
free=cur[(cur['qty']>0)&(cur['rev']==0)]
p("\n== 赠送行(qty>0,rev=0) 样例 ==")
p("数量:",len(free)," 总赠送qty:",free['qty'].sum())
if len(free):
    p(free[['date','sales','sku','qty','price_untax','rev','note','biz']].head(15).to_string())
# 检查 未税单价 vs rev/qty 一致性(付费行)
paid=cur[(cur['qty']>0)&(cur['rev']>0)].copy()
paid['asp']=paid['rev']/paid['qty']
paid['diff']=(paid['price_untax']-paid['asp']).abs()
p("\n== 未税单价列 vs rev/qty(ASP) 一致性(付费行) ==")
p("行数:",len(paid)," 不一致(diff>0.01)行数:",(paid['diff']>0.01).sum())
p("mean diff:",round(paid['diff'].mean(),4))
# 找疑似买赠:同sku同sales有 rev=0 行 + rev>0 行
combo=cur[(cur['qty']>0)].groupby(['sku','sales']).agg(has_free=('rev',lambda s:(s==0).sum()),paid=('rev',lambda s:(s>0).sum())).reset_index()
promo=combo[(combo['has_free']>0)&(combo['paid']>0)]
p(f"\n== 疑似买赠(sku×sales 同时有付费行和免费行): {len(promo)} 组 ==")
p(promo.head(10).to_string())
# ASP差异:含免费行 vs 不含
p("\n== ASP差异对比(有买赠的sku×sales) ==")
for _,r in promo.head(5).iterrows():
    sub=cur[(cur['sku']==r['sku'])&(cur['sales']==r['sales'])&(cur['qty']>0)]
    asp_with_free=sub['rev'].sum()/sub['qty'].sum()
    paid_sub=sub[sub['rev']>0]
    asp_paid_only=paid_sub['rev'].sum()/paid_sub['qty'].sum() if paid_sub['qty'].sum() else 0
    p(f"  {r['sku']} | {r['sales']}: 含免费ASP={asp_with_free:.4f} vs 仅付费ASP={asp_paid_only:.4f} (差{(1-asp_with_free/asp_paid_only)*100:.1f}%)")
open(r"C:\Users\45091\Desktop\工作文件\semiconductor_analysis\asp_check.md","w",encoding="utf-8").write(out.getvalue())
print("done")
