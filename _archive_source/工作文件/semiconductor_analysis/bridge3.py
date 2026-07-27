# -*- coding: utf-8 -*-
import pandas as pd, numpy as np, io
path = r"C:\Users\45091\Desktop\工作文件\semiconductor_analysis\data\财务分析-5月（6.3）.xlsx"
RAW=['发货日期','存货名称','实际业务员','发货数量','未税单价','单位成本','总成本','RMB 未税金额小计','利润']
A=dict(zip(RAW,['date','sku','sales','qty','price','ucost','cost_col','rev','profit']))
out=io.StringIO()
def p(*a): print(*a,file=out)
df=pd.read_excel(path,sheet_name='24-26',usecols=RAW).rename(columns=A)
df['date']=pd.to_datetime(df['date'],errors='coerce'); df=df.dropna(subset=['date'])
for c in ['qty','price','ucost','cost_col','rev','profit']: df[c]=pd.to_numeric(df[c],errors='coerce')
df['y']=df['date'].dt.year; df['m']=df['date'].dt.month
# 不过滤:全量行(含退货qty<0、赠品rev=0、credit)
cur=df[(df['y']==2026)&(df['m']<=6)].copy()
yoy=df[(df['y']==2025)&(df['m']<=6)].copy()
p(f"本期(全量含退货) 收入{cur['rev'].sum()/10000:.1f}万 利润{cur['profit'].sum()/10000:.1f}万 毛利率{cur['profit'].sum()/cur['rev'].sum()*100:.2f}%")
# 退货量
ret=cur[cur['qty']<0]
p(f"本期退货行: {len(ret)}行, qty={ret['qty'].sum():.0f}, 收入{ret['rev'].sum()/10000:.1f}万, 利润{ret['profit'].sum()/10000:.1f}万")

# 毛利桥:可比SKU(两期都有付费销售rev>0),net含退货/赠品
def sku_agg(d):
    return d.groupby('sku').agg(q=('qty','sum'),rev=('rev','sum'),cost=('cost_col','sum'),prof=('profit','sum'),
                                paid_rev=('rev',lambda s:s[s>0].sum()), paid_qty=('qty',lambda s:s[d.loc[s.index,'rev']>0].sum()))
g_cur=sku_agg(cur); g_yoy=sku_agg(yoy)
g=g_cur.join(g_yoy,how='inner',lsuffix='1',rsuffix='0')
# 可比:两期都有付费销售
g=g[(g['paid_rev1']>0)&(g['paid_rev0']>0)&(g['q1']!=0)&(g['q0']!=0)]
g['p0']=g['rev0']/g['q0']; g['p1']=g['rev1']/g['q1']   # net ASP含退货/赠品
g['uc0']=g['cost0']/g['q0']; g['uc1']=g['cost1']/g['q1']
g['m0']=g['prof0']/g['rev0']
tot1=g['rev1'].sum(); tot0=g['rev0'].sum()
g['share0']=g['rev0']/tot0; g['share1']=g['rev1']/tot1
qty_eff=((g['q1']-g['q0'])*g['p0']*g['m0']).sum()
price_eff=((g['p1']-g['p0'])*g['q1']*g['m0']).sum()
cost_eff=((g['uc0']-g['uc1'])*g['q1']).sum()
mix_eff=((g['share1']-g['share0'])*g['m0']*tot1).sum()
prof_chg=g['prof1'].sum()-g['prof0'].sum()
p(f"\n可比SKU数:{len(g)} 本期收入{tot1/10000:.1f}万 上期{tot0/10000:.1f}万")
p(f"可比本期利润{g['prof1'].sum()/10000:.1f}万 上期{g['prof0'].sum()/10000:.1f}万 变化{prof_chg/10000:+.1f}万")
p("| 效应 | 贡献(万) |")
p("|---|---|")
for nm,v in [('量效应',qty_eff),('价效应',price_eff),('成本效应',cost_eff),('结构效应',mix_eff)]:
    p(f"| {nm} | {v/10000:+.1f} |")
p(f"| 合计(四效应) | {(qty_eff+price_eff+cost_eff+mix_eff)/10000:+.1f} |")
p(f"| 实际利润变化(可比) | {prof_chg/10000:+.1f} |")
p(f"| 残差(交互/新品/退市) | {(prof_chg-(qty_eff+price_eff+cost_eff+mix_eff))/10000:+.1f} |")
gm1=g['prof1'].sum()/g['rev1'].sum()*100; gm0=g['prof0'].sum()/g['rev0'].sum()*100
p(f"\n可比SKU自身毛利率(净): 上期{gm0:.2f}% -> 本期{gm1:.2f}% (变化{gm1-gm0:+.2f}pct)")

# ASP净口径 vs 不含退货 对比(附件5用)
p("\n== 附件5 ASP:净口径(含退货) vs 不含退货 ==")
# TMI8180G 刘仲涵 净ASP
for sku,sl in [('TMI8180G','刘仲涵'),('TMI31601F','胡定凡'),('TMI8870','刘仲涵')]:
    sub=cur[(cur['sku']==sku)&(cur['sales']==sl)]
    net_asp=sub['rev'].sum()/sub['qty'].sum() if sub['qty'].sum() else 0
    pos=sub[sub['qty']>0]
    pos_asp=pos['rev'].sum()/pos['qty'].sum() if pos['qty'].sum() else 0
    paid=sub[sub['rev']>0]
    paid_asp=paid['rev'].sum()/paid['qty'].sum() if paid['qty'].sum() else 0
    p(f"  {sku}|{sl}: 净ASP(含退货)={net_asp:.4f} vs 不含退货={pos_asp:.4f} vs 付费ASP={paid_asp:.4f} (退货行{(sub['qty']<0).sum()}笔)")
open(r"C:\Users\45091\Desktop\工作文件\semiconductor_analysis\res_bridge2.md","w",encoding="utf-8").write(out.getvalue())
print("done")
