# -*- coding: utf-8 -*-
import pandas as pd, numpy as np, io, re
path = r"C:\Users\45091\Desktop\工作文件\semiconductor_analysis\data\财务分析-5月（6.3）.xlsx"
PERS = r"C:\Users\45091\Desktop\工作文件\semiconductor_analysis\data\部门-人员-职务对应.md"
RAW = ['发货日期','实际业务员','业务员对应工号','终端客户简称','存货名称','产品品类（新）',
       '是否新品','发货数量','未税单价','单位成本','总成本','RMB 未税金额小计','利润']
A=dict(zip(RAW,['date','sales','sid','cust','sku','pcat','is_new','qty','price','ucost','cost_col','rev','profit']))
out=io.StringIO()
def p(*a): print(*a,file=out)
ppl_text=open(PERS,encoding='utf-8').read()
ppl=[(m.group(1),m.group(2).strip(),m.group(3).strip()) for m in re.finditer(r'\|\s*(\d{6})\s*\|\s*([^|]+?)\s*\|\s*(销售|销售-FAE|产品|技术|技术-测试|职能)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|', ppl_text)]
ppl_df=pd.DataFrame(ppl,columns=['sid','name','post'])
sales_ppl=ppl_df[ppl_df['post'].isin(['销售','销售-FAE'])]
sales_sid=set(sales_ppl['sid']); sales_name=set(sales_ppl['name'])
sid2dept=dict(zip(ppl_df['sid'],ppl_df['post']))

df=pd.read_excel(path,sheet_name='24-26',usecols=RAW).rename(columns=A)
df['date']=pd.to_datetime(df['date'],errors='coerce'); df=df.dropna(subset=['date'])
for c in ['qty','price','ucost','cost_col','rev','profit']:
    df[c]=pd.to_numeric(df[c],errors='coerce')
df['y']=df['date'].dt.year; df['m']=df['date'].dt.month
df['in_role']=df['sid'].isin(sales_sid) | ((df['sid'].isna())&(df['sales'].isin(sales_name)))
cur=df[(df['y']==2026)&(df['m']<=6)].copy()
yoy=df[(df['y']==2025)&(df['m']<=6)].copy()
B_rev=cur['rev'].sum(); B_prof=cur['profit'].sum(); BENCH=B_prof/B_rev*100; HI=BENCH+5

cur_s=cur[cur['in_role']].copy()
yoy_s=yoy[(yoy['in_role'])|(yoy['sales'].isin(sales_name))].copy()
p(f"\n在职销售(2026H1有记录): {cur_s['sales'].nunique()}人")

# SKU级毛利率(本期,用于高/低判定)
sku_gm=cur.groupby('sku').apply(lambda x: x['profit'].sum()/x['rev'].sum() if x['rev'].sum() else 0)
hi_skus=set(sku_gm[sku_gm>=HI/100].index)
lo_skus=set(sku_gm[(sku_gm<BENCH/100)&(sku_gm>=0)].index)
neg_skus=set(sku_gm[sku_gm<0].index)

# ===== 附件2: 销售结构优化榜 =====
p("\n## 附件2: 销售人员结构优化榜(2026H1)")
def sales_stat(d):
    g=d.groupby('sales').agg(rev=('rev','sum'),prof=('profit','sum'))
    g['gm']=g['prof']/g['rev']*100
    # 高毛利SKU占比
    hi=d[d['sku'].isin(hi_skus)].groupby('sales')['rev'].sum()
    g['hi_share']=g.index.map(lambda s: hi.get(s,0)/g.loc[s,'rev']*100 if g.loc[s,'rev'] else 0)
    return g
sc=sales_stat(cur_s); sy=sales_stat(yoy_s)
sc['hi_share_y']=sc.index.map(lambda s: sy.loc[s,'hi_share'] if s in sy.index else np.nan)
sc['hi_chg']=sc['hi_share']-sc['hi_share_y']
sc=sc.sort_values('rev',ascending=False)
p("| 排名 | 销售 | 收入(万) | 毛利率% | 高毛利SKU占比% | 占比同比变化pct |")
p("|---|---|---|---|---|---|")
for i,(nm,r) in enumerate(sc.iterrows(),1):
    chg=f"{r['hi_chg']:+.1f}" if pd.notna(r['hi_chg']) else "—"
    p(f"| {i} | {nm} | {r['rev']/10000:.1f} | {r['gm']:.1f} | {r['hi_share']:.1f} | {chg} |")
p(f"\n标杆(高毛利占比最高): {sc['hi_share'].idxmax()} {sc['hi_share'].max():.1f}%")
p(f"标杆(占比提升最大): {sc['hi_chg'].idxmax()} {sc['hi_chg'].max():+.1f}pct")

# ===== 附件3: 品类结构四档 =====
p("\n## 附件3: 各品类结构化现状(2026H1)")
pc=cur.groupby('pcat').agg(rev=('rev','sum'),prof=('profit','sum'))
pc=pc[pc.index!='未归类']
pc['gm']=(pc['prof']/pc['rev']*100).round(2)
pc['lvl']=pd.cut(pc['gm'],bins=[-999,0,BENCH,HI,999],labels=['负毛利','低毛利','中毛利','高毛利'])
tot=pc['rev'].sum()
p("| 档位 | 品类数 | 收入(万) | 占比% | 加权毛利率% |")
p("|---|---|---|---|---|")
for lv in ['高毛利','中毛利','低毛利','负毛利']:
    sub=pc[pc['lvl']==lv]
    p(f"| {lv} | {len(sub)} | {sub['rev'].sum()/10000:.1f} | {sub['rev'].sum()/tot*100:.1f} | {(sub['prof'].sum()/sub['rev'].sum()*100 if sub['rev'].sum() else 0):.2f} |")

# ===== 附件5: 销售×SKU 价格分析 =====
p("\n## 附件5: 销售维度价格分析(同SKU不同销售价差)")
pos=cur_s[cur_s['qty']>0]
ps=pos.groupby(['sku','sales']).agg(rev=('rev','sum'),qty=('qty','sum')).reset_index()
ps['unit_price']=ps['rev']/ps['qty']
# 每SKU的中位价与销售数
sku_price=ps.groupby('sku')['unit_price'].agg(['median','count']).reset_index()
sku_price=sku_price[sku_price['count']>=2]
ps=ps.merge(sku_price[['sku','median']],on='sku')
ps['price_ratio']=ps['unit_price']/ps['median']
low=ps[(ps['price_ratio']<0.9)&(ps['rev']>50000)].copy()
low=low.sort_values('price_ratio')
p(f"有多个销售在售的SKU数: {len(sku_price)}; 价低于同SKU中位90%的销售×SKU组合: {len(low)}")
p("\n### 提价机会(价低于同SKU中位90%,收入>5万) TOP15")
p("| SKU | 销售 | 当前单价 | 中位单价 | 价比 | 收入(万) | 提价空间(万) |")
p("|---|---|---|---|---|---|---|")
for _,r in low.head(15).iterrows():
    gap=(r['median']-r['unit_price'])*r['qty']
    p(f"| {r['sku']} | {r['sales']} | {r['unit_price']:.4f} | {r['median']:.4f} | {r['price_ratio']:.2f} | {r['rev']/10000:.1f} | {gap/10000:+.1f} |")
low['gap']=(low['median']-low['unit_price'])*low['qty']
p(f"\n价差提价空间合计(理论,提到中位): {low['gap'].sum()/10000:.1f}万 (按全部低于中位90%的组合)")

# ===== 附件6: 销售35%达成分方案 =====
p("\n## 附件6: 销售人员35%毛利达成分方案")
gap_total=0.35*B_rev-B_prof
p(f"公司毛利缺口(到35%): {gap_total/10000:.1f}万 (需提升{35-BENCH:.2f}pct)")
# 每销售潜力
plan=[]
for nm in sc.index:
    s_cur=cur_s[cur_s['sales']==nm]
    rev=s_cur['rev'].sum(); prof=s_cur['profit'].sum(); gm=prof/rev*100 if rev else 0
    # 结构潜力: 低毛利SKU(含负)收入的20%切到高毛利
    lo_rev=s_cur[s_cur['sku'].isin(lo_skus|neg_skus)]['rev'].sum()
    hi_gm_avg=cur_s[cur_s['sku'].isin(hi_skus)].groupby('sku').apply(lambda x:x['profit'].sum()/x['rev'].sum() if x['rev'].sum() else 0).mean() if cur_s['sku'].isin(hi_skus).any() else BENCH/100
    lo_gm_avg=s_cur[s_cur['sku'].isin(lo_skus|neg_skus)].groupby('sku').apply(lambda x:x['profit'].sum()/x['rev'].sum() if x['rev'].sum() else 0).mean() if (s_cur['sku'].isin(lo_skus|neg_skus)).any() else 0
    struct_pot=lo_rev*0.2*max(hi_gm_avg-lo_gm_avg,0)
    # 提价潜力: 该销售低于中位90%的组合提价到中位
    price_pot=low[low['sales']==nm]['gap'].sum() if nm in set(low['sales']) else 0
    plan.append(dict(sales=nm,rev=rev,prof=prof,gm=gm,lo_rev=lo_rev,
                     struct_pot=struct_pot,price_pot=price_pot))
P=pd.DataFrame(plan)
P['planA']=P['struct_pot']           # 纯结构
P['planB']=P['price_pot']            # 纯提价
P['planC']=P['struct_pot']*0.7+P['price_pot']*0.3
P=P.sort_values('rev',ascending=False)
p(f"\n三方案合计贡献(万): A结构={P['planA'].sum()/10000:.1f}  B提价={P['planB'].sum()/10000:.1f}  C组合={P['planC'].sum()/10000:.1f}")
p(f"缺口{gap_total/10000:.1f}万 → A覆盖{P['planA'].sum()/gap_total*100:.0f}%  B覆盖{P['planB'].sum()/gap_total*100:.0f}%  C覆盖{P['planC'].sum()/gap_total*100:.0f}%")
p("\n### 逐销售拆解(方案C·组合,按收入排序)")
p("| 销售 | 收入(万) | 现毛利率% | 结构潜力(万) | 提价潜力(万) | 方案C贡献(万) | 达成后毛利率% |")
p("|---|---|---|---|---|---|---|")
for _,r in P.iterrows():
    after_gm=(r['prof']+r['planC'])/r['rev']*100 if r['rev'] else 0
    p(f"| {r['sales']} | {r['rev']/10000:.1f} | {r['gm']:.1f} | {r['struct_pot']/10000:+.1f} | {r['price_pot']/10000:+.1f} | {r['planC']/10000:+.1f} | {after_gm:.1f} |")

with open(r"C:\Users\45091\Desktop\工作文件\semiconductor_analysis\res_part4.md","w",encoding="utf-8") as f:
    f.write(out.getvalue())
print("part4 done")
