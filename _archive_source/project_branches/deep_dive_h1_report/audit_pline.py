# -*- coding: utf-8 -*-
import pandas as pd, numpy as np, io
path = r"C:\Users\45091\Desktop\工作文件\semiconductor_analysis\data\财务分析-5月（6.3）.xlsx"
RAW=['发货日期','存货名称','型号_产品线（新）','产品线','产品品类（新）','发货数量','单位成本',
     '总成本','RMB 未税金额小计','利润']
A=dict(zip(RAW,['date','sku','pline2','pline1','pcat','qty','ucost','cost_col','rev','profit']))
out=io.StringIO()
def p(*a): print(*a,file=out)
df=pd.read_excel(path,sheet_name='24-26',usecols=RAW).rename(columns=A)
df['date']=pd.to_datetime(df['date'],errors='coerce'); df=df.dropna(subset=['date'])
for c in ['qty','ucost','cost_col','rev','profit']: df[c]=pd.to_numeric(df[c],errors='coerce')
df['y']=df['date'].dt.year; df['m']=df['date'].dt.month
df['pcat']=df['pcat'].fillna('未归类').replace({'0':'未归类','':'未归类'})
df['pline2']=df['pline2'].fillna('未归类').replace({'0':'未归类','':'未归类'})
cur=df[(df['y']==2026)&(df['m']<=6)].copy()
yoy=df[(df['y']==2025)&(df['m']<=6)].copy()
tot=cur['rev'].sum()

p("== 列对比:产品线(旧) vs 型号_产品线(新) ==")
p(f"产品线(旧) 非空行: {cur['pline1'].notna().sum()} 去重数: {cur['pline1'].nunique()}")
p(f"型号_产品线(新) 非空行: {cur['pline2'].notna().sum()} 去重数: {cur['pline2'].nunique()}")

p(); p("== 恒等式与勾稽(用型号_产品线新) ==")
g=cur.groupby('pline2').agg(rev=('rev','sum'),cost=('cost_col','sum'),prof=('profit','sum'))
g['qcost']=cur.groupby('pline2').apply(lambda x:(x['qty']*x['ucost']).sum())
g['d1']=g['prof']-(g['rev']-g['cost']); g['d2']=g['cost']-g['qcost']
p(f"产品线组数: {len(g)} Σ收入={g['rev'].sum()/10000:.2f}万 (整体{tot/10000:.2f}万 差{tot-g['rev'].sum():.2f})")
p(f"恒等1违例: {(g['d1'].abs()>1).sum()}  恒等2违例: {(g['d2'].abs()>1).sum()}")

p(); p("== 产品线层概览(型号_产品线新, 2026H1) ==")
gp=cur.groupby('pline2').agg(rev=('rev','sum'),prof=('profit','sum'))
gp['gm']=(gp['prof']/gp['rev']*100).round(2); gp['share']=(gp['rev']/tot*100).round(1)
gy=yoy.groupby('pline2')['rev'].sum(); gp['yoy']=(gp['rev']/gy-1)*100
gp=gp.sort_values('rev',ascending=False)
p("| 产品线 | 收入(万) | 占比% | 毛利率% | 同比% | 品类数 | SKU数 |")
p("|---|---|---|---|---|---|---|")
for nm,r in gp.iterrows():
    sub=cur[cur['pline2']==nm]
    yy=f"{r['yoy']:+.0f}" if pd.notna(r['yoy']) and r['rev']>0 else "—"
    p(f"| {nm} | {r['rev']/10000:.1f} | {r['share']} | {r['gm']} | {yy} | {sub['pcat'].nunique()} | {sub['sku'].nunique()} |")

p(); p("== 嵌套勾稽抽查(产品线>品类>SKU) ==")
top=gp.index[0]
sub=cur[cur['pline2']==top]
sub_rev=sub['rev'].sum(); cat_sum=sub.groupby('pcat')['rev'].sum().sum(); sku_sum=sub.groupby('sku')['rev'].sum().sum()
p(f"产品线[{top}]: 收入{sub_rev/10000:.2f}万 | Σ品类{cat_sum/10000:.2f}万 差{sub_rev-cat_sum:.2f} | ΣSKU{sku_sum/10000:.2f}万 差{sub_rev-sku_sum:.2f} | 品类{sub['pcat'].nunique()} SKU{sub['sku'].nunique()}")

p(); p("== 头号拖累品类DCDC-18V-降压2~4A 所属产品线 ==")
dc=cur[cur['pcat']=='DCDC-18V-降压2~4A']
p(f"该品类下涉及产品线: {dc['pline2'].unique().tolist()}")
p(f"各产品线收入: {dc.groupby('pline2')['rev'].sum().to_dict()}")

open(r"C:\Users\45091\Desktop\工作文件\semiconductor_analysis\audit_pline.md","w",encoding="utf-8").write(out.getvalue())
print("done")
