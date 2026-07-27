# -*- coding: utf-8 -*-
import pandas as pd, numpy as np, io
path = r"C:\Users\45091\Desktop\工作文件\semiconductor_analysis\data\财务分析-5月（6.3）.xlsx"
RAW = ['发货日期','实际业务员','存货名称','产品品类（新）','是否新品','发货数量',
       '未税单价','单位成本','总成本','RMB 未税金额小计','利润','出货总金额']
A=dict(zip(RAW,['date','sales','sku','pcat','is_new','qty','price','ucost','cost_col','rev','profit_col','gross']))
out=io.StringIO()
def p(*a): print(*a,file=out)
df=pd.read_excel(path,sheet_name='24-26',usecols=RAW).rename(columns=A)
df['date']=pd.to_datetime(df['date'],errors='coerce')
for c in ['qty','price','ucost','cost_col','rev','profit_col','gross']:
    df[c]=pd.to_numeric(df[c],errors='coerce')
df['y']=df['date'].dt.year; df['m']=df['date'].dt.month
H1=df[df['y']==2026].copy()  # 不预过滤,看全貌

def stat(d,label):
    d2=d.dropna(subset=['date'])
    rev=d2['rev'].sum(); prof=d2['profit_col'].sum()
    gm=prof/rev*100 if rev else float('nan')
    p(f"{label}: 行数={len(d2)} 收入={round(rev/10000,1)}万 利润={round(prof/10000,1)}万 毛利率={round(gm,4)}%")

stat(H1,"A. 2026全年级(含H2,未过滤)")
stat(H1[H1['m']<=6],"B. 2026H1 全量(未过滤,含负/零/0品类)")
stat(H1[H1['m']<=6].dropna(subset=['rev']),"C. H1 仅去NaN收入")
d=H1[H1['m']<=6].dropna(subset=['rev'])
stat(d[d['qty']>0],"D. H1 qty>0")
stat(d[d['qty']>0][d['rev']>0],"E. H1 qty>0 & rev>0 (=我之前)")
stat(d[(d['pcat']!='0')&(d['pcat'].notna())&(d['qty']>0)&(d['rev']>0)],"F. H1 qty>0&rev>0&pcat非0非空(我剔除0后)")

p("\n==== 被排除行的构成(H1, qty>0&rev>0 基础上的差额) ====")
base=H1[H1['m']<=6].dropna(subset=['rev'])
base=base[base['qty']>0]
neg=base[base['rev']<=0]
p("rev<=0行:",len(neg)," 收入=",round(neg['rev'].sum()/10000,1),"万 利润=",round(neg['profit_col'].sum()/10000,1),"万")
zero_cat=base[(base['pcat']=='0')|(base['pcat'].isna())]
p("pcat=0或空 行:",len(zero_cat)," 收入=",round(zero_cat['rev'].sum()/10000,1),"万 利润=",round(zero_cat['profit_col'].sum()/10000,1),"万")
neg_qty=H1[H1['m']<=6][H1[H1['m']<=6]['qty']<=0]
p("qty<=0(退货)行:",len(neg_qty)," 收入=",round(neg_qty['rev'].sum()/10000,1),"万 利润=",round(neg_qty['profit_col'].sum()/10000,1),"万")

p("\n==== 用含税 出货总金额 做分母试算 ====")
d=H1[H1['m']<=6].dropna(subset=['rev'])
d=d[d['qty']>0][d['rev']>0]
g=d['gross'].sum(); r=d['rev'].sum(); pr=d['profit_col'].sum()
p("未税收入:",round(r/10000,1),"万 含税出货总额:",round(g/10000,1),"万 利润:",round(pr/10000,1),"万")
p("利润/含税:",round(pr/g*100,4),"%  利润/未税:",round(pr/r*100,4),"%")

with open(r"C:\Users\45091\Desktop\工作文件\semiconductor_analysis\diag_out.txt","w",encoding="utf-8") as f:
    f.write(out.getvalue())
print("done")
