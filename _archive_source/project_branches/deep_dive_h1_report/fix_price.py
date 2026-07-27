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

# 重建低价组合
pos=cur_s[cur_s['qty']>0]
ps=pos.groupby(['sku','sales']).agg(rev=('rev','sum'),qty=('qty','sum')).reset_index()
ps['unit_price']=ps['rev']/ps['qty']
sku_price=ps.groupby('sku')['unit_price'].agg(['median','count']).reset_index()
sku_price=sku_price[sku_price['count']>=2]
ps=ps.merge(sku_price[['sku','median']],on='sku')
ps['price_ratio']=ps['unit_price']/ps['median']
low=ps[(ps['price_ratio']<0.9)&(ps['rev']>50000)].copy()
low['gap_theory']=(low['median']-low['unit_price'])*low['qty']  # 理论:提到中位

# 分档实现率
def tier_rate(r):
    if r<0.70: return 0.15
    elif r<0.85: return 0.35
    else: return 0.60
low['rate']=low['price_ratio'].apply(tier_rate)
low['gap_exec']=low['gap_theory']*low['rate']*0.85   # 可执行=理论×实现率×(1-流失15%)

p("## 附件5/6 修正:理论上限 vs 可执行")
p(f"低价组合数: {len(low)}")
p(f"理论提价上限(全提到中位): {low['gap_theory'].sum()/10000:.1f}万")
p(f"可执行提价空间(分档实现率×85%): {low['gap_exec'].sum()/10000:.1f}万")
p(f"  价比<0.70 组合数{(low['price_ratio']<0.70).sum()} 理论{low[low['price_ratio']<0.70]['gap_theory'].sum()/10000:.1f}万 可执行{low[low['price_ratio']<0.70]['gap_exec'].sum()/10000:.1f}万")
p(f"  0.70-0.85 组合数{((low['price_ratio']>=0.70)&(low['price_ratio']<0.85)).sum()} 理论{low[(low['price_ratio']>=0.70)&(low['price_ratio']<0.85)]['gap_theory'].sum()/10000:.1f}万 可执行{low[(low['price_ratio']>=0.70)&(low['price_ratio']<0.85)]['gap_exec'].sum()/10000:.1f}万")
p(f"  0.85-0.90 组合数{((low['price_ratio']>=0.85)&(low['price_ratio']<0.90)).sum()} 理论{low[(low['price_ratio']>=0.85)&(low['price_ratio']<0.90)]['gap_theory'].sum()/10000:.1f}万 可执行{low[(low['price_ratio']>=0.85)&(low['price_ratio']<0.90)]['gap_exec'].sum()/10000:.1f}万")

# 附件6重算
gap_total=0.35*B_rev-B_prof
p(f"\n公司毛利缺口(到35%): {gap_total/10000:.1f}万")
sc=cur_s.groupby('sales').agg(rev=('rev','sum'),prof=('profit','sum'))
sc['gm']=sc['prof']/sc['rev']*100
plan=[]
exec_by_sales=low.groupby('sales')['gap_exec'].sum()
for nm in sc.index:
    s_cur=cur_s[cur_s['sales']==nm]
    rev=s_cur['rev'].sum(); prof=s_cur['profit'].sum(); gm=prof/rev*100 if rev else 0
    lo_rev=s_cur[s_cur['sku'].isin(lo_skus|neg_skus)]['rev'].sum()
    hi_gm_avg=cur_s[cur_s['sku'].isin(hi_skus)].groupby('sku').apply(lambda x:x['profit'].sum()/x['rev'].sum() if x['rev'].sum() else 0).mean() if cur_s['sku'].isin(hi_skus).any() else BENCH/100
    lo_gm_avg=s_cur[s_cur['sku'].isin(lo_skus|neg_skus)].groupby('sku').apply(lambda x:x['profit'].sum()/x['rev'].sum() if x['rev'].sum() else 0).mean() if (s_cur['sku'].isin(lo_skus|neg_skus)).any() else 0
    struct_pot=lo_rev*0.2*max(hi_gm_avg-lo_gm_avg,0)
    price_pot=exec_by_sales.get(nm,0)   # 用可执行
    plan.append(dict(sales=nm,rev=rev,prof=prof,gm=gm,struct=struct_pot,price=price_pot))
P=pd.DataFrame(plan)
P['planA']=P['struct']
P['planB']=P['price']
P['planC']=P['struct']*0.7+P['price']*0.3
p(f"\n三方案合计(万): A结构={P['planA'].sum()/10000:.1f}  B提价(可执行)={P['planB'].sum()/10000:.1f}  C组合={P['planC'].sum()/10000:.1f}")
p(f"缺口{gap_total/10000:.1f}万 → A覆盖{P['planA'].sum()/gap_total*100:.0f}%  B覆盖{P['planB'].sum()/gap_total*100:.0f}%  C覆盖{P['planC'].sum()/gap_total*100:.0f}%")
P=P.sort_values('rev',ascending=False)
p("\n### 逐销售(方案C,按收入排序) 单位万")
p("| 销售 | 收入 | 现毛利率 | 结构潜力 | 提价(可执行) | 方案C | 达成后毛利率 |")
p("|---|---|---|---|---|---|---|")
for _,r in P.iterrows():
    after=(r['prof']+r['struct']*0.7+r['price']*0.3)/r['rev']*100 if r['rev'] else 0
    p(f"| {r['sales']} | {r['rev']/10000:.1f} | {r['gm']:.1f} | {r['struct']/10000:+.1f} | {r['price']/10000:+.1f} | {(r['struct']*0.7+r['price']*0.3)/10000:+.1f} | {after:.1f} |")

open(r"C:\Users\45091\Desktop\工作文件\semiconductor_analysis\res_fix.md","w",encoding="utf-8").write(out.getvalue())
print("done")
