# -*- coding: utf-8 -*-
import pandas as pd, numpy as np, io, re
path = r"C:\Users\45091\Desktop\工作文件\semiconductor_analysis\data\财务分析-5月（6.3）.xlsx"
PERS = r"C:\Users\45091\Desktop\工作文件\semiconductor_analysis\data\部门-人员-职务对应.md"
RAW=['发货日期','实际业务员','业务员对应工号','存货名称','产品品类（新）','是否新品',
     '发货数量','未税单价','单位成本','总成本','RMB 未税金额小计','利润']
A=dict(zip(RAW,['date','sales','sid','sku','pcat','is_new','qty','price','ucost','cost_col','rev','profit']))
out=io.StringIO()
def p(*a): print(*a,file=out)
ppl_text=open(PERS,encoding='utf-8').read()
ppl=[(m.group(1),m.group(2).strip(),m.group(3).strip()) for m in re.finditer(r'\|\s*(\d{6})\s*\|\s*([^|]+?)\s*\|\s*(销售|销售-FAE|产品|技术|技术-测试|职能)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|', ppl_text)]
ppl_df=pd.DataFrame(ppl,columns=['sid','name','post'])
sales_ppl=ppl_df[ppl_df['post'].isin(['销售','销售-FAE'])]
sales_sid=set(sales_ppl['sid']); sales_name=set(sales_ppl['name'])
df=pd.read_excel(path,sheet_name='24-26',usecols=RAW).rename(columns=A)
df['date']=pd.to_datetime(df['date'],errors='coerce'); df=df.dropna(subset=['date'])
for c in ['qty','price','ucost','cost_col','rev','profit']: df[c]=pd.to_numeric(df[c],errors='coerce')
df['y']=df['date'].dt.year; df['m']=df['date'].dt.month
df['in_role']=df['sid'].isin(sales_sid) | ((df['sid'].isna())&(df['sales'].isin(sales_name)))
cur=df[(df['y']==2026)&(df['m']<=6)].copy()
cur_s=cur[cur['in_role']].copy()
B_rev=cur['rev'].sum(); B_prof=cur['profit'].sum(); BENCH=B_prof/B_rev*100; HI=BENCH+5
sku_gm=cur.groupby('sku').apply(lambda x: x['profit'].sum()/x['rev'].sum() if x['rev'].sum() else 0)
hi_skus=set(sku_gm[sku_gm>=HI/100].index)
lo_skus=set(sku_gm[(sku_gm<BENCH/100)&(sku_gm>=0)].index)
neg_skus=set(sku_gm[sku_gm<0].index)

# sku×sales: 拆付费/赠送
pos=cur_s[cur_s['qty']>0].copy()
pos['is_free']=(pos['rev']==0)
g=pos.groupby(['sku','sales']).agg(
    rev=('rev','sum'), paid_qty=('qty',lambda s: s[pos.loc[s.index,'rev']>0].sum()),
    free_qty=('qty',lambda s: s[pos.loc[s.index,'rev']==0].sum()),
    total_qty=('qty','sum'), has_free=('is_free','max'))
g=g.reset_index()
g=g[g['total_qty']>0]
g['blended_asp']=g['rev']/g['total_qty']               # 含赠送加权ASP
g['paid_asp']=g['rev']/g['paid_qty'].replace(0,np.nan) # 仅付费ASP
# 中位ASP(按含赠送,跨销售)
sku_median=g.groupby('sku')['blended_asp'].agg(['median','count']).reset_index()
sku_median=sku_median[sku_median['count']>=2]
g=g.merge(sku_median[['sku','median']],on='sku')
g['price_ratio']=g['paid_asp']/g['median']   # 用付费ASP算价比(剔除促销干扰)
low=g[(g['price_ratio']<0.9)&(g['rev']>50000)].copy()
# 提价空间(真实,基于付费ASP vs 中位)
low['gap_theory']=(low['median']-low['paid_asp'])*low['paid_qty']
low['gap_theory']=low['gap_theory'].clip(lower=0)
# 促销价值(赠送量按付费ASP计的让利,单独杠杆)
low['promo_value']=low['paid_asp']*low['free_qty']
def tier_rate(r):
    if r<0.70: return 0.15
    elif r<0.85: return 0.35
    else: return 0.60
low['rate']=low['price_ratio'].apply(tier_rate)
low['gap_exec']=low['gap_theory']*low['rate']*0.85

p("## 附件5/6 重算(ASP=含赠送加权;提价空间用付费ASP vs 中位,剔除促销干扰)")
p(f"低价组合数(付费ASP<中位90%): {len(low)}")
p(f"真实提价-理论上限(付费ASP提到中位): {low['gap_theory'].sum()/10000:.1f}万")
p(f"真实提价-可执行(分档×85%): {low['gap_exec'].sum()/10000:.1f}万")
p(f"买赠促销让利(赠送量×付费ASP,单独杠杆,不计入提价): {low['promo_value'].sum()/10000:.1f}万")
p(f"  含买赠的组合: {(low['has_free']==True).sum()}个, 促销让利 {low[low['has_free']==True]['promo_value'].sum()/10000:.1f}万")
p(f"  纯低价组合(无买赠): {(low['has_free']==False).sum()}个, 真实提价可执行 {low[low['has_free']==False]['gap_exec'].sum()/10000:.1f}万")

p("\n### 含买赠的组合(低ASP系促销驱动,需审查促销策略,非提价)")
p("| SKU | 销售 | 含赠ASP | 付费ASP | 中位ASP | 赠送量 | 促销让利(万) | 真实提价可执行(万) |")
p("|---|---|---|---|---|---|---|---|")
for _,r in low[low['has_free']==True].sort_values('promo_value',ascending=False).iterrows():
    p(f"| {r['sku']} | {r['sales']} | {r['blended_asp']:.4f} | {r['paid_asp']:.4f} | {r['median']:.4f} | {r['free_qty']:.0f} | {r['promo_value']/10000:.1f} | {r['gap_exec']/10000:.1f} |")

p("\n### 真实提价机会TOP15(纯低价,无买赠,按可执行排序)")
p("| SKU | 销售 | 含赠ASP | 付费ASP | 中位ASP | 价比 | 收入(万) | 理论提价(万) | 可执行(万) |")
p("|---|---|---|---|---|---|---|---|---|")
pure=low[low['has_free']==False].sort_values('gap_exec',ascending=False)
for _,r in pure.head(15).iterrows():
    p(f"| {r['sku']} | {r['sales']} | {r['blended_asp']:.4f} | {r['paid_asp']:.4f} | {r['median']:.4f} | {r['price_ratio']:.2f} | {r['rev']/10000:.1f} | {r['gap_theory']/10000:.1f} | {r['gap_exec']/10000:.1f} |")

# 方案6重算
gap_total=0.35*B_rev-B_prof
p(f"\n公司毛利缺口: {gap_total/10000:.1f}万")
sc=cur_s.groupby('sales').agg(rev=('rev','sum'),prof=('profit','sum'))
sc['gm']=sc['prof']/sc['rev']*100
exec_by_sales=low.groupby('sales')['gap_exec'].sum()
plan=[]
for nm in sc.index:
    s_cur=cur_s[cur_s['sales']==nm]
    rev=s_cur['rev'].sum(); prof=s_cur['profit'].sum(); gm=prof/rev*100 if rev else 0
    lo_rev=s_cur[s_cur['sku'].isin(lo_skus|neg_skus)]['rev'].sum()
    hi_gm_avg=cur_s[cur_s['sku'].isin(hi_skus)].groupby('sku').apply(lambda x:x['profit'].sum()/x['rev'].sum() if x['rev'].sum() else 0).mean() if cur_s['sku'].isin(hi_skus).any() else BENCH/100
    lo_gm_avg=s_cur[s_cur['sku'].isin(lo_skus|neg_skus)].groupby('sku').apply(lambda x:x['profit'].sum()/x['rev'].sum() if x['rev'].sum() else 0).mean() if (s_cur['sku'].isin(lo_skus|neg_skus)).any() else 0
    struct_pot=lo_rev*0.2*max(hi_gm_avg-lo_gm_avg,0)
    price_pot=exec_by_sales.get(nm,0)
    plan.append(dict(sales=nm,rev=rev,prof=prof,gm=gm,struct=struct_pot,price=price_pot))
P=pd.DataFrame(plan)
P['planA']=P['struct']; P['planB']=P['price']; P['planC']=P['struct']*0.7+P['price']*0.3
p(f"\n三方案合计(万): A结构={P['planA'].sum()/10000:.1f}  B提价(可执行,剔除促销)={P['planB'].sum()/10000:.1f}  C组合={P['planC'].sum()/10000:.1f}")
p(f"缺口{gap_total/10000:.1f}万 → A覆盖{P['planA'].sum()/gap_total*100:.0f}%  B覆盖{P['planB'].sum()/gap_total*100:.0f}%  C覆盖{P['planC'].sum()/gap_total*100:.0f}%")
P=P.sort_values('rev',ascending=False)
p("\n### 逐销售(方案C) 单位万")
p("| 销售 | 收入 | 现毛利率 | 结构潜力 | 提价(可执行) | 方案C | 达成后毛利率 |")
p("|---|---|---|---|---|---|---|")
for _,r in P.iterrows():
    after=(r['prof']+r['struct']*0.7+r['price']*0.3)/r['rev']*100 if r['rev'] else 0
    p(f"| {r['sales']} | {r['rev']/10000:.1f} | {r['gm']:.1f} | {r['struct']/10000:+.1f} | {r['price']/10000:+.1f} | {(r['struct']*0.7+r['price']*0.3)/10000:+.1f} | {after:.1f} |")
open(r"C:\Users\45091\Desktop\工作文件\semiconductor_analysis\res_asp.md","w",encoding="utf-8").write(out.getvalue())
print("done")
