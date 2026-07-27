# -*- coding: utf-8 -*-
import pandas as pd, numpy as np, io
path = r"C:\Users\45091\Desktop\工作文件\semiconductor_analysis\data\财务分析-6月（7.6）.xlsx"
RAW=['发货日期','终端客户简称','存货名称','产品品类（新）','型号_产品线（新）',
     '是否新品','发货数量','未税单价','总成本','RMB 未税金额小计','利润']
A=dict(zip(RAW,['date','cust','sku','pcat','pline','is_new','qty','price','cost_col','rev','profit']))
df=pd.read_excel(path,sheet_name='24-26',usecols=RAW).rename(columns=A)
df['date']=pd.to_datetime(df['date'],errors='coerce'); df=df.dropna(subset=['date'])
for c in ['qty','price','cost_col','rev','profit']: df[c]=pd.to_numeric(df[c],errors='coerce')
df['y']=df['date'].dt.year; df['m']=df['date'].dt.month
df['pcat']=df['pcat'].fillna('未归类').replace({'0':'未归类','':'未归类'})
df['is_new']=df['is_new'].fillna('否')
df['half'] = df.apply(lambda r: f"{r['y']}H1" if r['m']<=6 else f"{r['y']}H2", axis=1)

cu = '中兴康讯'
sub = df[df['cust']==cu].copy()
out=io.StringIO()
def p(*a): print(*a,file=out)

# === 1. 5半年度整体 ===
p("== 1. 5半年度整体收入/利润/毛利率 ==")
for h in ['2024H1','2024H2','2025H1','2025H2','2026H1']:
    s=sub[sub['half']==h]
    rev=s['rev'].sum(); prof=s['profit'].sum()
    gm=prof/rev*100 if rev else 0
    nsku=s['sku'].nunique(); npcat=s['pcat'].nunique(); nnew=s[s['is_new']=='是']['sku'].nunique()
    p(f"{h}: 收入{rev/10000:.1f}万 利润{prof/10000:.1f}万 毛利率{gm:.2f}% SKU数{int(nsku)} 品类数{int(npcat)} 新品{int(nnew)}")

# === 2. 品类级变化(5期) ===
p("\n== 2. TOP品类各期收入(万) ==")
gp=sub.groupby(['pcat','half'])['rev'].sum().unstack('half').fillna(0)
gp['total']=gp.sum(axis=1); gp=gp.sort_values('total',ascending=False)
for h in ['2024H1','2024H2','2025H1','2025H2','2026H1']:
    if h not in gp.columns: gp[h]=0
p("| 品类 | 24H1 | 24H2 | 25H1 | 25H2 | 26H1 | 合计 |")
p("|---|---|---|---|---|---|---|")
for cat,r in gp.head(8).iterrows():
    p(f"| {cat} | {r['2024H1']/10000:.1f} | {r['2024H2']/10000:.1f} | {r['2025H1']/10000:.1f} | {r['2025H2']/10000:.1f} | {r['2026H1']/10000:.1f} | {r['total']/10000:.1f} |")

# === 3. 品类毛利率变化 ===
p("\n== 3. TOP品类毛利率(%,与2对应) ==")
for cat in gp.head(5).index:
    vals=[]
    for h in ['2024H1','2024H2','2025H1','2025H2','2026H1']:
        s=sub[(sub['pcat']==cat)&(sub['half']==h)]
        gm=s['profit'].sum()/s['rev'].sum()*100 if s['rev'].sum() else 0
        vals.append(f"{gm:.1f}%")
    p(f"{cat}: {' | '.join(vals)}")

# === 4. 26H1 SKU级明细(按毛利变化 vs 25H1) ===
p("\n== 4. 2026H1 SKU级同比变化(按毛利变化) ==")
g1=sub[sub['half']=='2026H1'].groupby('sku').agg(rev1=('rev','sum'),prof1=('profit','sum'),pcat=('pcat','first'))
g0=sub[sub['half']=='2025H1'].groupby('sku').agg(rev0=('rev','sum'),prof0=('profit','sum'))
g=g1.join(g0,how='outer').fillna(0)
g=g[(g['rev1']>0)|(g['rev0']>0)]
g['gm1']=(g['prof1']/g['rev1']*100).fillna(0)
g['gm0']=(g['prof0']/g['rev0']*100).fillna(0)
g['prof_chg']=g['prof1']-g['prof0']; g['rev_chg']=(g['rev1']/(g['rev0'].replace(0,np.nan))-1)*100
g=g.sort_values('prof_chg')
p("| SKU | 品类 | 25H1收入(万) | 26H1收入(万) | 收入同比 | 26H1毛利率 | 毛利变化(万) |")
p("|---|---|---|---|---|---|---|")
for sku,r in g.iterrows():
    rc=f"{r['rev_chg']:+.0f}%" if pd.notna(r['rev_chg']) and abs(r['rev_chg'])<999 else ('新品' if r['rev0']==0 else f"{r['rev_chg']:+.0f}%")
    gm1=f"{r['gm1']:.1f}%" if r['rev1']>0 else '—'
    p(f"| {sku} | {r['pcat']} | {r['rev0']/10000:.1f} | {r['rev1']/10000:.1f} | {rc} | {gm1} | {r['prof_chg']/10000:+.1f} |")

# === 5. 产品结构迭代:按SKU系列看演进 ===
p("\n== 5. 产品系列迭代(按SKU前缀分组) ==")
prefix_map={}
for sku in sub['sku'].unique():
    # 取前缀(第一个字母+数字组合)
    import re
    m=re.match(r'([A-Z]+[\d]+)', sku)
    prefix=m.group(1)[:6] if m else sku[:6]
    if prefix not in prefix_map: prefix_map[prefix]=[]
    prefix_map[prefix].append(sku)

prefix_rev={}
for pf,skus in prefix_map.items():
    prefix_rev[pf]=sub[sub['sku'].isin(skus)&(sub['half']=='2026H1')]['rev'].sum()
for pf in sorted(prefix_rev, key=lambda k:-prefix_rev[k]):
    skus=prefix_map[pf]
    s=sub[sub['sku'].isin(skus)]
    rev26=s[s['half']=='2026H1']['rev'].sum()
    if rev26<10000: continue
    rev25=s[s['half']=='2025H1']['rev'].sum()
    p(f"  {pf}: 25H1收入{rev25/10000:.1f}万→26H1 {rev26/10000:.1f}万 (SKU:{','.join(skus[:4])}{'...' if len(skus)>4 else ''})")

# === 6. 低毛利维持的效果评估 ===
p("\n== 6. 中兴康讯 vs 整体 对比 ==")
for h in ['2024H1','2024H2','2025H1','2025H2','2026H1']:
    s=sub[sub['half']==h]
    rev=s['rev'].sum(); prof=s['profit'].sum()
    gm=prof/rev*100 if rev else 0
    # 整体同期毛利率
    tot=df[df['half']==h]
    tot_gm=tot['profit'].sum()/tot['rev'].sum()*100 if tot['rev'].sum() else 0
    p(f"  {h}: 中兴康讯毛利率{gm:.2f}% vs 整体{tot_gm:.2f}%(差{gm-tot_gm:+.1f}pct), 中兴收入{rev/10000:.1f}万 占整体{rev/tot['rev'].sum()*100:.1f}%")

open(r"C:\Users\45091\Desktop\工作文件\semiconductor_analysis\deep_zxkx.md","w",encoding="utf-8").write(out.getvalue())
print("done")
