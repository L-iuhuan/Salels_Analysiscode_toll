# -*- coding: utf-8 -*-
import pandas as pd, numpy as np, io
path = r"C:\Users\45091\Desktop\工作文件\semiconductor_analysis\data\财务分析-5月（6.3）.xlsx"
RAW=['发货日期','存货名称','发货数量','未税单价','单位成本','总成本','RMB 未税金额小计','利润']
A=dict(zip(RAW,['date','sku','qty','price','ucost','cost_col','rev','profit']))
out=io.StringIO()
def p(*a): print(*a,file=out)
df=pd.read_excel(path,sheet_name='24-26',usecols=RAW).rename(columns=A)
df['date']=pd.to_datetime(df['date'],errors='coerce'); df=df.dropna(subset=['date'])
for c in ['qty','price','ucost','cost_col','rev','profit']: df[c]=pd.to_numeric(df[c],errors='coerce')
df['y']=df['date'].dt.year; df['m']=df['date'].dt.month
# 用 qty>0 口径(含赠品行,ASP为加权;与34.43%基线一致,退货qty<0进交互项)
df=df[df['qty']>0]
cur=df[(df['y']==2026)&(df['m']<=6)].copy()
yoy=df[(df['y']==2025)&(df['m']<=6)].copy()
p(f"本期(qty>0,含赠品) 收入{cur['rev'].sum()/10000:.1f}万 利润{cur['profit'].sum()/10000:.1f}万 毛利率{cur['profit'].sum()/cur['rev'].sum()*100:.2f}%")
p(f"上期 收入{yoy['rev'].sum()/10000:.1f}万 利润{yoy['profit'].sum()/10000:.1f}万 毛利率{yoy['profit'].sum()/yoy['rev'].sum()*100:.2f}%")

g_cur=cur.groupby('sku').agg(q1=('qty','sum'),rev1=('rev','sum'),cost1=('cost_col','sum'),prof1=('profit','sum'))
g_yoy=yoy.groupby('sku').agg(q0=('qty','sum'),rev0=('rev','sum'),cost0=('cost_col','sum'),prof0=('profit','sum'))
g=g_cur.join(g_yoy,how='inner')
g=g[(g['q1']>0)&(g['q0']>0)&(g['rev1']>0)&(g['rev0']>0)]
g['p0']=g['rev0']/g['q0']; g['p1']=g['rev1']/g['q1']
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
p("| 效应 | 贡献(万) |")
p("|---|---|")
for nm,v in [('量效应',qty_eff),('价效应',price_eff),('成本效应',cost_eff),('结构效应',mix_eff)]:
    p(f"| {nm} | {v/10000:+.1f} |")
p(f"| 合计(四效应) | {(qty_eff+price_eff+cost_eff+mix_eff)/10000:+.1f} |")
p(f"| 实际利润变化(可比) | {prof_chg/10000:+.1f} |")
p(f"| 残差(交互/新品/退市/退货) | {(prof_chg-(qty_eff+price_eff+cost_eff+mix_eff))/10000:+.1f} |")
gm1=g['prof1'].sum()/g['rev1'].sum()*100; gm0=g['prof0'].sum()/g['rev0'].sum()*100
p(f"\n可比SKU自身毛利率: 上期{gm0:.2f}% -> 本期{gm1:.2f}% (变化{gm1-gm0:+.2f}pct)")
# 赠品行对价效应的影响(说明)
free_cur=cur[cur['rev']==0]
p(f"\n本期赠品行(qty>0,rev=0): {len(free_cur)}行, qty={free_cur['qty'].sum():.0f}, 成本{free_cur['cost_col'].sum()/10000:.1f}万, 利润{free_cur['profit'].sum()/10000:.1f}万(赠品成本计入毛利拖累)")
open(r"C:\Users\45091\Desktop\工作文件\semiconductor_analysis\res_bridge.md","w",encoding="utf-8").write(out.getvalue())
print("done")
