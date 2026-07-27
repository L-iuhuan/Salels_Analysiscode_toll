# -*- coding: utf-8 -*-
import pandas as pd, numpy as np, io
path = r"C:\Users\45091\Desktop\工作文件\semiconductor_analysis\data\财务分析-5月（6.3）.xlsx"
RAW = ['发货日期','销售部门','实际业务员','业务员对应工号','代理商/直供名称','终端客户简称',
       '终端客户名称_客户类别','存货名称','产品线','产品品类（新）','产品类别','是否新品',
       '发货数量','未税单价','单位成本','总成本','RMB 未税金额小计','利润','销售模式']
ALIAS = dict(zip(RAW, ['date','dept','sales','sales_id','agent','cust','cust_tier',
       'sku','pline','pcat_new','pcate','is_new','qty','price','ucost','cost','rev','profit','mode']))
out = io.StringIO()
def p(*a): print(*a, file=out)

df = pd.read_excel(path, sheet_name='24-26', usecols=RAW)
df = df.rename(columns=ALIAS)
p("raw rows:", len(df))
df['date'] = pd.to_datetime(df['date'], errors='coerce')
df = df.dropna(subset=['date'])
for c in ['qty','price','ucost','cost','rev','profit']:
    df[c] = pd.to_numeric(df[c], errors='coerce')
df = df[(df['qty']>0) & (df['rev']>0)]
p("after clean:", len(df))
p("date range:", df['date'].min(), "->", df['date'].max())
df['y'] = df['date'].dt.year
df['m'] = df['date'].dt.month
p("\n== by year ==")
g = df.groupby('y').agg(rev=('rev','sum'), cost=('cost','sum'), profit=('profit','sum'), n=('rev','count'))
g['gm%'] = (g['profit']/g['rev']*100).round(2)
p(g.to_string())
p("\n== 2026 by month ==")
g26 = df[df['y']==2026].groupby('m').agg(rev=('rev','sum'), profit=('profit','sum'))
g26['gm%'] = (g26['profit']/g26['rev']*100).round(2)
p(g26.to_string())

cur = df[(df['y']==2026)&(df['m']<=5)]
yoy  = df[(df['y']==2025)&(df['m']<=5)]
qoq  = df[(df['y']==2025)&(df['m']>=7)]
def agg(d):
    return dict(rev=round(d['rev'].sum(),2), cost=round(d['cost'].sum(),2),
                profit=round(d['profit'].sum(),2), n=len(d))
for name,d in [("cur 2026M1-5",cur),("yoy 2025M1-5",yoy),("qoq 2025H2",qoq)]:
    a=agg(d); a['gm%']=round(a['profit']/a['rev']*100,2)
    p(name, a)
p("\nunique cust:", cur['cust'].nunique(), "sales:", cur['sales'].nunique(),
  "agent:", cur['agent'].nunique(), "sku:", cur['sku'].nunique())
with open(r"C:\Users\45091\Desktop\工作文件\semiconductor_analysis\scout_out.txt","w",encoding="utf-8") as f:
    f.write(out.getvalue())
print("done")
