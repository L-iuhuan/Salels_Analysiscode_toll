# -*- coding: utf-8 -*-
import pandas as pd, numpy as np, io
path = r"C:\Users\45091\Desktop\工作文件\semiconductor_analysis\data\财务分析-5月（6.3）.xlsx"
RAW = ['发货日期','实际业务员','业务员对应工号','终端客户简称','存货名称','产品品类（新）',
       '是否新品','发货数量','未税单价','单位成本','总成本','RMB 未税金额小计','利润']
ALIAS = dict(zip(RAW,['date','sales','sales_id','cust','sku','pcat','is_new',
       'qty','price','ucost','cost_col','rev','profit_col']))
out = io.StringIO()
def p(*a): print(*a, file=out)
df = pd.read_excel(path, sheet_name='24-26', usecols=RAW).rename(columns=ALIAS)
df['date']=pd.to_datetime(df['date'],errors='coerce'); df=df.dropna(subset=['date'])
for c in ['qty','price','ucost','cost_col','rev','profit_col']:
    df[c]=pd.to_numeric(df[c],errors='coerce')
df=df[(df['qty']>0)&(df['rev']>0)]
df['y']=df['date'].dt.year; df['m']=df['date'].dt.month
cur=df[(df['y']==2026)&(df['m']<=6)]
cur=cur[cur['pcat']!='0']  # 剔除0品类

# 基础重算
df['cost_calc'] = df['qty']*df['ucost']        # 数量×单位成本
df['profit_calc'] = df['rev'] - df['cost_calc'] # 收入-(数量×单位成本)
cur=df[(df['y']==2026)&(df['m']<=6)&(df['pcat']!='0')]

rev=cur['rev'].sum()
p("==== 2026H1 (剔除0品类) 三种口径对比 ====")
p("收入P列(未税金额小计):", round(rev,2), "=", round(rev/10000,1),"万")
p()
p("口径A(我之前): 利润=Q列(利润), 毛利率=", round(cur['profit_col'].sum()/rev*100,4),"%")
p("口径B(总成本列): 利润=收入-总成本列, 毛利率=", round((rev-cur['cost_col'].sum())/rev*100,4),"%")
p("口径C(基础公式): 总成本=数量×单位成本, 利润=收入-总成本, 毛利率=", round((rev-cur['cost_calc'].sum())/rev*100,4),"%")
p()
# 一致性检查
p("==== 列间一致性(全量clean) ====")
d=df
p("总成本列 vs 数量×单位成本: 差额=", round((d['cost_col']-d['cost_calc']).sum(),2),
  " 相对差%=", round((d['cost_col'].sum()-d['cost_calc'].sum())/d['cost_col'].sum()*100,4))
p("利润列 vs (收入-总成本列): 差额=", round((d['profit_col']-(d['rev']-d['cost_col'])).sum(),2))
p("利润列 vs (收入-数量×单位成本): 差额=", round((d['profit_col']-(d['rev']-d['cost_calc'])).sum(),2))
p()
p("==== 分月毛利率(基础公式C) ====")
gm=df[(df['y']==2026)&(df['pcat']!='0')].groupby('m').apply(
    lambda x: pd.Series({'rev万':round(x['rev'].sum()/10000,1),
                         'gm%':round((x['rev'].sum()-x['cost_calc'].sum())/x['rev'].sum()*100,2),
                         'n':len(x)}))
p(gm.to_string())
p()
# 新品标记跨年分布
p("==== 是否新品列 按年分布 ====")
nk=df.groupby(['y','is_new']).agg(n=('rev','count'),rev万=('rev',lambda s:round(s.sum()/10000,1)))
p(nk.to_string())
p()
# 25&26都有的SKU里,是否新品标记是否真有变化(逐行核查)
p("==== 同SKU跨年 是否新品 标记变化(逐SKU两期对比) ====")
def yflag(sub):
    return sub.groupby('y')['is_new'].agg(lambda s: s.dropna().unique().tolist())
chk=df.groupby('sku').apply(yflag)
p("25&26都有记录的SKU数:", sum(1 for s in [chk] if True) if False else "see below")
both=chk.unstack('y') if False else None
# simpler
skuy=df.groupby(['sku','y'])['is_new'].first().unstack('y')
if 2025 in skuy.columns and 2026 in skuy.columns:
    b=skuy.dropna(subset=[2025,2026])
    diff=b[b[2025]!=b[2026]]
    p("两期都有记录SKU数:",len(b)," 标记不同SKU数:",len(diff))
    if len(diff): p(diff.head(15).to_string())
# 2024 vs 2026
if 2024 in skuy.columns and 2026 in skuy.columns:
    b24=skuy.dropna(subset=[2024,2026])
    d24=b24[b24[2024]!=b24[2026]]
    p("24&26都有记录SKU数:",len(b24)," 标记不同SKU数:",len(d24))
    if len(d24): p(d24.head(15).to_string())

with open(r"C:\Users\45091\Desktop\工作文件\semiconductor_analysis\verify_out.txt","w",encoding="utf-8") as f:
    f.write(out.getvalue())
print("done")
