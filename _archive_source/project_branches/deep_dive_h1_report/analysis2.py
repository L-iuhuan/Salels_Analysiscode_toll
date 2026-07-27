# -*- coding: utf-8 -*-
import pandas as pd, numpy as np, io, re
path = r"C:\Users\45091\Desktop\工作文件\semiconductor_analysis\data\财务分析-5月（6.3）.xlsx"
PERS = r"C:\Users\45091\Desktop\工作文件\semiconductor_analysis\data\部门-人员-职务对应.md"
RAW = ['发货日期','销售部门','实际业务员','业务员对应工号','终端客户简称','终端客户名称_客户类别',
       '存货名称','产品线','产品品类（新）','是否新品','发货数量','未税单价','单位成本',
       '总成本','RMB 未税金额小计','利润']
A=dict(zip(RAW,['date','dept','sales','sid','cust','cust_tier','sku','pline','pcat','is_new',
       'qty','price','ucost','cost_col','rev','profit']))
out=io.StringIO()
def p(*a): print(*a,file=out)

# personnel
ppl_text=open(PERS,encoding='utf-8').read()
ppl=[]
for m in re.finditer(r'\|\s*(\d{6})\s*\|\s*([^|]+?)\s*\|\s*(销售|销售-FAE|产品|技术|技术-测试|职能)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|', ppl_text):
    ppl.append((m.group(1),m.group(2).strip(),m.group(3).strip()))
ppl_df=pd.DataFrame(ppl,columns=['sid','name','post'])
sales_ppl=ppl_df[ppl_df['post'].isin(['销售','销售-FAE'])]
sales_sid=set(sales_ppl['sid']); sales_name=set(sales_ppl['name'])

df=pd.read_excel(path,sheet_name='24-26',usecols=RAW).rename(columns=A)
df['date']=pd.to_datetime(df['date'],errors='coerce'); df=df.dropna(subset=['date'])
for c in ['qty','price','ucost','cost_col','rev','profit']:
    df[c]=pd.to_numeric(df[c],errors='coerce')
df['y']=df['date'].dt.year; df['m']=df['date'].dt.month
df['pcat']=df['pcat'].fillna('未归类').replace({'0':'未归类','':'未归类'})
df['is_new']=df['is_new'].fillna('否')
df['in_role']=df['sid'].isin(sales_sid) | ((df['sid'].isna())&(df['sales'].isin(sales_name)))
cur=df[(df['y']==2026)&(df['m']<=6)].copy()
yoy=df[(df['y']==2025)&(df['m']<=6)].copy()
B_rev=cur['rev'].sum(); B_prof=cur['profit'].sum(); BENCH=B_prof/B_rev*100
HI=BENCH+5

# ===== 新品分析 =====
p("\n## 三、新品分析(按行是否新品标记)")
for lab,d in [('2026H1',cur),('2025H1',yoy)]:
    n=d[d['is_new']=='是'];
    p(f"{lab}: 新品行 {len(n)}, 新品收入 {n['rev'].sum()/10000:.1f}万 ({n['rev'].sum()/d['rev'].sum()*100:.1f}%), 新品毛利 {n['profit'].sum()/10000:.1f}万, 新品毛利率 {(n['profit'].sum()/n['rev'].sum()*100 if n['rev'].sum() else 0):.2f}%")
# 新品存活: 2025年新品 在2026是否仍有收入
n25=yoy[yoy['is_new']=='是']['sku'].unique()
live26=cur[cur['sku'].isin(n25)]
p(f"\n2025年标新品SKU数: {len(n25)}; 2026仍有收入的: {live26['sku'].nunique()}; 基础存活率 {live26['sku'].nunique()/len(n25)*100:.1f}%")
if len(n25):
    live26_rev=cur[cur['sku'].isin(n25)].groupby('sku')['rev'].sum()
    n25_first=yoy[yoy['is_new']=='是'].groupby('sku')['rev'].sum()
    common=n25_first.index.intersection(live26_rev.index)
    income_live=(live26_rev.loc[common]>=n25_first.loc[common]*0.5).sum()
    p(f"收入存活率(2026收入≥2025首期50%): {income_live/len(n25)*100:.1f}%")

# ===== 毛利桥(四效应,overlap SKU,正量行) =====
p("\n## 四、毛利桥(2026H1 vs 2025H1,可比SKU集合)")
pos=lambda d: d[d['qty']>0]
g_cur=pos(cur).groupby('sku').agg(q1=('qty','sum'),rev1=('rev','sum'),cost1=('cost_col','sum'),prof1=('profit','sum'))
g_yoy=pos(yoy).groupby('sku').agg(q0=('qty','sum'),rev0=('rev','sum'),cost0=('cost_col','sum'),prof0=('profit','sum'))
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
p(f"可比SKU数: {len(g)}, 本期收入 {tot1/10000:.1f}万, 上期 {tot0/10000:.1f}万")
p("| 效应 | 贡献(万) | 占比% |")
p("|---|---|---|")
for nm,v in [('量效应',qty_eff),('价效应',price_eff),('成本效应',cost_eff),('结构效应',mix_eff)]:
    p(f"| {nm} | {v/10000:+.1f} | {(v/prof_chg*100 if prof_chg else 0):+.1f} |")
p(f"| 合计(四效应) | {(qty_eff+price_eff+cost_eff+mix_eff)/10000:+.1f} | 100 |")
p(f"| 实际利润变化(可比) | {prof_chg/10000:+.1f} | — |")
p(f"| 残差(交互项) | {(prof_chg-(qty_eff+price_eff+cost_eff+mix_eff))/10000:+.1f} | — |")
# 可比口径验证
gm_overlap1=g['prof1'].sum()/g['rev1'].sum()*100
gm_overlap0=g['prof0'].sum()/g['rev0'].sum()*100
p(f"\n可比SKU自身毛利率: 上期{gm_overlap0:.2f}% -> 本期{gm_overlap1:.2f}% (变化{gm_overlap1-gm_overlap0:+.2f}pct)")
p(f"整体毛利率: 上期36.80% -> 本期34.43% (变化-2.37pct)")
p(f"→ 可比SKU自身毛利率变化 {gm_overlap1-gm_overlap0:+.2f}pct vs 整体变化-2.37pct,主因是{'结构(mix)' if abs(gm_overlap1-gm_overlap0)<1 else '可比产品降价/成本'}")

# ===== 客户:增长 + 流失 =====
p("\n## 五、客户增长与流失")
c_cur=cur.groupby('cust').agg(rev=('rev','sum'),prof=('profit','sum'))
c_yoy=yoy.groupby('cust').agg(rev0=('rev','sum'),prof0=('profit','sum'))
c=c_cur.join(c_yoy,how='outer').fillna(0)
c['growth%']=(c['rev']/c['rev0'].replace(0,np.nan)-1)*100
grow=c[(c['rev0']>0)&(c['rev']>c['rev0']*1.5)].sort_values('rev',ascending=False)
p("### 增长客户(同比>50%且本期收入>100万) TOP8")
p("| 客户 | 本期收入(万) | 同比增速% | 新增收入(万) | 毛利率% |")
p("|---|---|---|---|---|")
for nm,r in grow[grow['rev']>1000000].head(8).iterrows():
    p(f"| {nm} | {r['rev']/10000:.1f} | {r['growth%']:+.0f} | {(r['rev']-r['rev0'])/10000:+.1f} | {r['prof']/r['rev']*100:.1f} |")
loss=c[(c['rev0']>500000)&(c['rev']<c['rev0']*0.5)].sort_values('rev0',ascending=False)
p("\n### 流失客户(上期>50万且本期<上期50%) TOP8")
p("| 客户 | 上期收入(万) | 本期收入(万) | 流失收入(万) | 责任销售 |")
p("|---|---|---|---|---|")
# 责任销售: 该客户本期收入最大的销售
for nm,r in loss.head(8).iterrows():
    s=cur[cur['cust']==nm].groupby('sales')['rev'].sum()
    sn=s.idxmax() if len(s) else '—'
    p(f"| {nm} | {r['rev0']/10000:.1f} | {r['rev']/10000:.1f} | {(r['rev']-r['rev0'])/10000:+.1f} | {sn} |")

# ===== 负毛利产品分级 =====
p("\n## 六、负毛利产品(2026H1,SKU级)")
sk=cur.groupby('sku').agg(rev=('rev','sum'),prof=('profit','sum'),qty=('qty','sum'),pcat=('pcat','first'))
sk=sk[sk['rev']>0]
neg=sk[sk['prof']<0].copy()
neg['loss']=neg['prof']
neg=neg.sort_values('loss')
p(f"负毛利SKU数: {len(neg)}, 合计收入 {neg['rev'].sum()/10000:.1f}万, 合计亏损 {neg['prof'].sum()/10000:.1f}万")
# 豁免: 上市未满6个月(本期标新品)豁免
new_sk=cur[cur['is_new']=='是']['sku'].unique()
neg['exempt']=neg.index.isin(new_sk)
p(f"其中新品豁免(本期标新品,上市<6月口径): {neg['exempt'].sum()}个")
net=neg[~neg['exempt']]
p(f"豁免后净负毛利SKU: {len(net)}个, 亏损 {net['prof'].sum()/10000:.1f}万")
# 客户依赖度分级
p("\n### 净负毛利SKU 客户依赖度分级")
p("| 级别 | SKU数 | 亏损(万) | 含义 |")
p("|---|---|---|---|")
# 对每个负毛利SKU,算其客户中其他正毛利产品占比
detail=[]
for sku,r in net.iterrows():
    sku_custs=cur[cur['sku']==sku]['cust'].unique()
    # 钩子判定: 该SKU的主要客户,其总收入中其他正毛利SKU占比
    risk_levels=[]
    for cu in sku_custs:
        cu_rev=cur[(cur['cust']==cu)&(cur['sku']!=sku)&(cur['profit']>0)]['rev'].sum()
        cu_tot=cur[cur['cust']==cu]['rev'].sum()
        share=cu_rev/cu_tot if cu_tot else 0
        risk_levels.append('low' if share>0.6 else ('high' if share<0.2 else 'mid'))
    risk='high' if 'high' in risk_levels else ('mid' if 'mid' in risk_levels else 'low')
    detail.append((sku,r['pcat'],r['rev'],r['prof'],risk))
nd=pd.DataFrame(detail,columns=['sku','pcat','rev','prof','risk'])
for lv,lb in [('low','低危(独立亏损,其他正毛利>60%)'),('mid','中危(连带,20-60%)'),('high','高危(钩子,<20%)')]:
    sub=nd[nd['risk']==lv]
    p(f"| {lb} | {len(sub)} | {sub['prof'].sum()/10000:.1f} | — |")
p("\n### TOP10 负毛利SKU明细")
p("| SKU | 品类 | 收入(万) | 亏损(万) | 风险 |")
p("|---|---|---|---|---|")
for _,r in nd.head(10).iterrows():
    p(f"| {r['sku']} | {r['pcat']} | {r['rev']/10000:.1f} | {r['prof']/10000:.1f} | {r['risk']} |")

with open(r"C:\Users\45091\Desktop\工作文件\semiconductor_analysis\res_part2.md","w",encoding="utf-8") as f:
    f.write(out.getvalue())
print("part2 done")
