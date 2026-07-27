# -*- coding: utf-8 -*-
import pandas as pd, numpy as np, io, re, os
path = r"C:\Users\45091\Desktop\工作文件\semiconductor_analysis\data\财务分析-5月（6.3）.xlsx"
PERS = r"C:\Users\45091\Desktop\工作文件\semiconductor_analysis\data\部门-人员-职务对应.md"
RAW = ['发货日期','销售部门','实际业务员','业务员对应工号','终端客户简称','终端客户名称_客户类别',
       '存货名称','产品线','产品品类（新）','是否新品','发货数量','未税单价','单位成本',
       '总成本','RMB 未税金额小计','利润']
A=dict(zip(RAW,['date','dept','sales','sid','cust','cust_tier','sku','pline','pcat','is_new',
       'qty','price','ucost','cost_col','rev','profit']))
out=io.StringIO()
def p(*a): print(*a,file=out)
def md(*a): print(*a,file=out)

# ---- load personnel ----
ppl_text=open(PERS,encoding='utf-8').read()
ppl=[]
for m in re.finditer(r'\|\s*(\d{6})\s*\|\s*([^|]+?)\s*\|\s*(销售|销售-FAE|产品|技术|技术-测试|职能)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|', ppl_text):
    ppl.append((m.group(1),m.group(2).strip(),m.group(3).strip(),m.group(5).strip()))
ppl_df=pd.DataFrame(ppl,columns=['sid','name','post','mgr'])
sales_ppl=ppl_df[ppl_df['post'].isin(['销售','销售-FAE'])].copy()
p("\n== 销售岗位人员(在册) ==",len(sales_ppl))
p(sales_ppl['post'].value_counts().to_string())

# ---- load data ----
df=pd.read_excel(path,sheet_name='24-26',usecols=RAW).rename(columns=A)
df['date']=pd.to_datetime(df['date'],errors='coerce'); df=df.dropna(subset=['date'])
for c in ['qty','price','ucost','cost_col','rev','profit']:
    df[c]=pd.to_numeric(df[c],errors='coerce')
df['y']=df['date'].dt.year; df['m']=df['date'].dt.month
df['pcat']=df['pcat'].fillna('未归类').replace({'0':'未归类','':'未归类'})
# 销售在册标记
sales_sid_set=set(sales_ppl['sid'])
sales_name_set=set(sales_ppl['name'])
df['sales_in_role']=df['sid'].isin(sales_sid_set) | ((df['sid'].isna())&(df['sales'].isin(sales_name_set)))

cur=df[(df['y']==2026)&(df['m']<=6)].copy()
yoy=df[(df['y']==2025)&(df['m']<=6)].copy()
qoq=df[(df['y']==2025)&(df['m']>=7)].copy()

def base(d,label):
    rev=d['rev'].sum(); prof=d['profit'].sum(); cost=d['cost_col'].sum()
    gm=prof/rev*100 if rev else 0
    p(f"| {label} | {rev/10000:.1f} | {cost/10000:.1f} | {prof/10000:.1f} | {gm:.2f} | {len(d)} |")
    return dict(rev=rev,prof=prof,cost=cost,gm=gm,n=len(d))
p("\n## 一、基线(全量口径,含退货)")
p("| 期间 | 收入(万) | 成本(万) | 利润(万) | 毛利率% | 行数 |")
p("|---|---|---|---|---|---|")
B_cur=base(cur,'2026H1 本期'); B_yoy=base(yoy,'2025H1 同比'); B_qoq=base(qoq,'2025H2 环比')
gap=0.35*B_cur['rev']-B_cur['prof']
p(f"\n距35%目标毛利缺口: {gap/10000:.1f}万 (需提升 {35-B_cur['gm']:.2f}pct)")
p(f"同比毛利率变化: {B_cur['gm']-B_yoy['gm']:+.2f}pct (2025H1 {B_yoy['gm']:.2f}% -> 2026H1 {B_cur['gm']:.2f}%)")
p(f"同比收入增速: {(B_cur['rev']/B_yoy['rev']-1)*100:+.2f}%")

# 整体基准
BENCH=B_cur['gm']; HI=BENCH+5; LO=BENCH
p(f"\n毛利率基准(整体): {BENCH:.2f}%  高毛利线: ≥{HI:.2f}%  低毛利线: <{LO:.2f}%")

# ---- 品类分析 ----
p("\n## 二、品类(产品品类新)结构 2026H1")
pc_cur=cur.groupby('pcat').agg(rev=('rev','sum'),prof=('profit','sum'),n=('rev','count'))
pc_cur['gm']=(pc_cur['prof']/pc_cur['rev']*100).round(2)
pc_yoy=yoy.groupby('pcat').agg(rev_y=('rev','sum'),prof_y=('profit','sum'))
pc=pc_cur.join(pc_yoy,how='left').fillna(0)
pc['rev_growth%']=(pc['rev']/pc['rev_y'].replace(0,np.nan)-1)*100
pc['prof_growth']=(pc['prof']-pc['prof_y'])
pc['share%']=(pc['rev']/B_cur['rev']*100)
pc=pc.sort_values('rev',ascending=False)
p("\n### TOP15 品类(按本期收入)")
p("| 品类 | 收入(万) | 占比% | 毛利率% | 同比收入增速% | 新增毛利(万) |")
p("|---|---|---|---|---|---|")
for i,(_,r) in enumerate(pc.head(15).iterrows()):
    p(f"| {_.strip() if False else r.name} | {r['rev']/10000:.1f} | {r['share%']:.1f} | {r['gm']:.2f} | {r['rev_growth%']:+.1f} | {r['prof_growth']/10000:+.1f} |")
p(f"\n品类总数: {len(pc)} (其中未归类 {pc.loc['未归类','n'] if '未归类' in pc.index else 0}行)")

# 明星品类(收入增+毛利增)
star=pc[(pc['rev_growth%']>10)&(pc['prof_growth']>0)].sort_values('prof_growth',ascending=False)
p("\n### 明星品类(同比收入+10%且新增毛利为正) TOP5")
p("| 品类 | 收入(万) | 毛利率% | 同比增速% | 新增毛利(万) |")
p("|---|---|---|---|---|")
for _,r in star.head(5).iterrows():
    p(f"| {r.name} | {r['rev']/10000:.1f} | {r['gm']:.2f} | {r['rev_growth%']:+.1f} | {r['prof_growth']/10000:+.1f} |")
# 衰退品类
dec=pc[pc['rev_growth%']<-10].sort_values('prof_growth')
p("\n### 衰退品类(同比收入<-10%) TOP5")
p("| 品类 | 收入(万) | 毛利率% | 同比增速% | 毛利变化(万) |")
p("|---|---|---|---|---|")
for _,r in dec.head(5).iterrows():
    p(f"| {r.name} | {r['rev']/10000:.1f} | {r['gm']:.2f} | {r['rev_growth%']:+.1f} | {r['prof_growth']/10000:+.1f} |")

# 高毛利品类占比
hi_cur=cur[cur['pcat'].isin(pc[pc['gm']>=HI].index)]['rev'].sum()/B_cur['rev']*100
hi_yoy=yoy[yoy['pcat'].isin(pc[pc['gm']>=HI].index)]['rev'].sum()/B_yoy['rev']*100 if B_yoy['rev'] else 0
p(f"\n高毛利品类(≥{HI:.1f}%)收入占比: 同比{hi_yoy:.1f}% -> 本期{hi_cur:.1f}% (变化{hi_cur-hi_yoy:+.1f}pct)")

with open(r"C:\Users\45091\Desktop\工作文件\semiconductor_analysis\res_part1.md","w",encoding="utf-8") as f:
    f.write(out.getvalue())
print("part1 done")
