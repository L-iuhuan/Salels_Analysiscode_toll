# -*- coding: utf-8 -*-
import pandas as pd, numpy as np, io
path = r"C:\Users\45091\Desktop\工作文件\semiconductor_analysis\data\财务分析-5月（6.3）.xlsx"
RAW=['发货日期','实际业务员','终端客户简称','终端客户名称','终端客户名称_客户类别','存货名称',
     '发货数量','总成本','RMB 未税金额小计','利润']
A=dict(zip(RAW,['date','sales','cust','cust_full','cust_tier','sku','qty','cost','rev','profit']))
df=pd.read_excel(path,sheet_name='24-26',usecols=RAW).rename(columns=A)
df['date']=pd.to_datetime(df['date'],errors='coerce'); df=df.dropna(subset=['date'])
for c in ['qty','cost','rev','profit']: df[c]=pd.to_numeric(df[c],errors='coerce')
df['y']=df['date'].dt.year; df['m']=df['date'].dt.month
cur=df[(df['y']==2026)&(df['m']<=6)]
big=cur[cur['cust_tier'].isin(['KA>1亿','AA>5000万'])].copy()
# 按客户简称合并(同一简称不同tier行合并为一个大客户)
g=big.groupby(['cust']).agg(
    rev=('rev','sum'),prof=('profit','sum'),n=('rev','count'),
    full=('cust_full',lambda s: s.dropna().unique()[:1]),
    tier=('cust_tier',lambda s: s.mode().iat[0] if len(s.mode()) else s.iloc[0]))
g['gm']=(g['prof']/g['rev']*100).round(2)
g['rev万']=(g['rev']/10000).round(1)
g=g.reset_index().sort_values(['tier','rev'],ascending=[True,False])
out=io.StringIO()
def p(*a): print(*a,file=out)
p(f"KA/AA 客户数(按简称): {len(g)} (KA {len(g[g.tier=='KA>1亿'])}, AA {len(g[g.tier=='AA>5000万'])})")
p(f"合计收入: {g['rev'].sum()/10000:.1f}万, 占整体 {g['rev'].sum()/cur['rev'].sum()*100:.1f}%")
p("\n| # | 层级 | 客户简称 | 全称(样例) | 收入(万) | 毛利率% | 行数 |")
p("|---|---|---|---|---|---|---|")
for i,(_,r) in enumerate(g.iterrows(),1):
    full=r['full'][0] if len(r['full']) else ''
    p(f"| {i} | {r['tier']} | {r['cust']} | {full} | {r['rev万']} | {r['gm']} | {r['n']} |")
# 疑似重复/脏数据:简称很像的
p("\n## 疑似重复(简称相似)")
names=g['cust'].tolist()
import difflib
seen=set()
for i,n1 in enumerate(names):
    for n2 in names[i+1:]:
        if difflib.SequenceMatcher(None,n1,n2).ratio()>0.6:
            p(f"  {n1}  <->  {n2}")
open(r"C:\Users\45091\Desktop\工作文件\semiconductor_analysis\ka_list.md","w",encoding="utf-8").write(out.getvalue())
print("done",len(g))
