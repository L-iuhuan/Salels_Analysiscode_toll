# -*- coding: utf-8 -*-
import pandas as pd, numpy as np, io
path = r"C:\Users\45091\Desktop\工作文件\semiconductor_analysis\data\财务分析-5月（6.3）.xlsx"
RAW=['发货日期','销售部门','实际业务员','业务员对应工号','终端客户简称','终端客户名称_客户类别',
     '存货名称','产品线','产品品类（新）','是否新品','发货数量','单位成本','总成本',
     'RMB 未税金额小计','利润']
A=dict(zip(RAW,['date','dept','sales','sid','cust','cust_tier','sku','pline','pcat','is_new',
       'qty','ucost','cost_col','rev','profit']))
out=io.StringIO()
def p(*a): print(*a,file=out)
df=pd.read_excel(path,sheet_name='24-26',usecols=RAW).rename(columns=A)
df['date']=pd.to_datetime(df['date'],errors='coerce'); df=df.dropna(subset=['date'])
for c in ['qty','ucost','cost_col','rev','profit']: df[c]=pd.to_numeric(df[c],errors='coerce')
df['y']=df['date'].dt.year; df['m']=df['date'].dt.month
df['pcat']=df['pcat'].fillna('未归类').replace({'0':'未归类','':'未归类'})
cur=df[(df['y']==2026)&(df['m']<=6)].copy()
yoy=df[(df['y']==2025)&(df['m']<=6)].copy()

def chk(d,label):
    rev=d['rev'].sum(); cost=d['cost_col'].sum(); prof=d['profit'].sum()
    qcost=(d['qty']*d['ucost']).sum()
    d1=prof-(rev-cost); d2=cost-qcost
    margin=prof/rev*100 if rev else 0
    p(f"[{label}] 行{len(d)} 收入{rev/10000:.2f}万 总成本{cost/10000:.2f}万 利润{prof/10000:.2f}万 毛利率{margin:.4f}%")
    p(f"   恒等1 利润=收入-总成本: 差{d1:.2f} {'OK' if abs(d1)<1 else 'FAIL'}")
    p(f"   恒等2 总成本=数量×单位成本: 差{d2:.2f} {'OK' if abs(d2)<1 else 'FAIL'}")
    p(f"   恒等3 利润率=利润/收入: {margin:.4f}%")

p("="*60); p("审计一:行级与整体恒等式(2026H1)")
chk(cur,'整体全量')
p()
chk(cur[cur['qty']>0],'qty>0含赠品(毛利桥口径)')
chk(cur[(cur['qty']>0)&(cur['rev']>0)],'qty>0&rev>0(旧口径)')
chk(cur[cur['qty']<0],'退货子集')

p(); p("="*60); p("审计二:各聚合层恒等式(本期)")
for col,lab in [('pline','产品线'),('pcat','品类'),('sku','SKU'),('cust','客户'),('sales','销售')]:
    g=cur.groupby(col).agg(rev=('rev','sum'),cost=('cost_col','sum'),prof=('profit','sum'))
    g['qcost']=cur.groupby(col).apply(lambda x:(x['qty']*x['ucost']).sum())
    g['d1']=g['prof']-(g['rev']-g['cost']); g['d2']=g['cost']-g['qcost']
    b1=(g['d1'].abs()>1).sum(); b2=(g['d2'].abs()>1).sum()
    p(f"[{lab}] 组{len(g)} 收入{g['rev'].sum()/10000:.2f}万 利润{g['prof'].sum()/10000:.2f}万 恒等1违例{b1} 恒等2违例{b2} {'OK' if b1==0 and b2==0 else 'FAIL'}")

p(); p("="*60); p("审计三:层级勾稽(Σ子层=整体)")
tot=cur['rev'].sum()
sp=cur.groupby('pline')['rev'].sum().sum()
sc=cur.groupby('pcat')['rev'].sum().sum()
ss=cur.groupby('sku')['rev'].sum().sum()
scu=cur.groupby('cust')['rev'].sum().sum()
ssa=cur.groupby('sales')['rev'].sum().sum()
p(f"整体收入={tot/10000:.2f}万")
p(f"  Σ产品线={sp/10000:.2f}万 差{tot-sp:.2f} {'OK' if abs(tot-sp)<1 else 'FAIL'}")
p(f"  Σ品类={sc/10000:.2f}万 差{tot-sc:.2f} {'OK' if abs(tot-sc)<1 else 'FAIL'}")
p(f"  ΣSKU={ss/10000:.2f}万 差{tot-ss:.2f} {'OK' if abs(tot-ss)<1 else 'FAIL'}")
p(f"  Σ客户={scu/10000:.2f}万 差{tot-scu:.2f} {'OK' if abs(tot-scu)<1 else 'FAIL'}(空简称未计入)")
p(f"  Σ销售={ssa/10000:.2f}万 差{tot-ssa:.2f} {'OK' if abs(tot-ssa)<1 else 'FAIL'}")
# 嵌套抽查
top_pline=cur.groupby('pline')['rev'].sum().sort_values(ascending=False).index[0]
sub=cur[cur['pline']==top_pline]
sub_rev=sub['rev'].sum(); sub_cat=sub.groupby('pcat')['rev'].sum().sum()
p(f"\n层级嵌套抽查 产品线[{top_pline}]: 收入{sub_rev/10000:.2f}万 Σ其下品类{sub_cat/10000:.2f}万 差{sub_rev-sub_cat:.2f} 品类{sub['pcat'].nunique()} SKU{sub['sku'].nunique()}")

p(); p("="*60); p("审计四:产品线层概览(供报告补层级)")
gp=cur.groupby('pline').agg(rev=('rev','sum'),prof=('profit','sum'))
gp['gm']=(gp['prof']/gp['rev']*100).round(2); gp['share']=(gp['rev']/tot*100).round(1)
gy=yoy.groupby('pline')['rev'].sum(); gp['yoy']=(gp['rev']/gy-1)*100
gp=gp.sort_values('rev',ascending=False)
p("| 产品线 | 收入(万) | 占比% | 毛利率% | 同比% |")
p("|---|---|---|---|---|")
for nm,r in gp.head(12).iterrows():
    yy=f"{r['yoy']:+.0f}" if pd.notna(r['yoy']) else "—"
    p(f"| {nm} | {r['rev']/10000:.1f} | {r['share']} | {r['gm']} | {yy} |")

p(); p("="*60); p("审计五:报告关键数复核")
dc=cur[cur['pcat']=='DCDC-18V-降压2~4A']; dcy=yoy[yoy['pcat']=='DCDC-18V-降压2~4A']
p(f"DCDC-18V-降压2~4A: 本期{dc['rev'].sum()/10000:.1f}万 毛利率{dc['profit'].sum()/dc['rev'].sum()*100:.2f}% 同比收入{(dc['rev'].sum()/dcy['rev'].sum()-1)*100:+.1f}% 毛利变化{(dc['profit'].sum()-dcy['profit'].sum())/10000:+.1f}万")
p(f"整体: 收入{cur['rev'].sum()/10000:.1f}万 利润{cur['profit'].sum()/10000:.1f}万 毛利率{cur['profit'].sum()/cur['rev'].sum()*100:.2f}% 缺口{(0.35*cur['rev'].sum()-cur['profit'].sum())/10000:.1f}万")
ret=cur[cur['qty']<0]; free=cur[(cur['qty']>0)&(cur['rev']==0)]
p(f"退货{len(ret)}行 收入{ret['rev'].sum()/10000:.1f}万 利润{ret['profit'].sum()/10000:.1f}万")
p(f"赠品{len(free)}行 qty{free['qty'].sum():.0f} 成本{free['cost_col'].sum()/10000:.1f}万 利润{free['profit'].sum()/10000:.1f}万")
p(f"未归类品类(原0/空): {cur[cur['pcat']=='未归类']['rev'].sum()/10000:.1f}万 {len(cur[cur['pcat']=='未归类'])}行")

open(r"C:\Users\45091\Desktop\工作文件\semiconductor_analysis\audit.md","w",encoding="utf-8").write(out.getvalue())
print("done")
