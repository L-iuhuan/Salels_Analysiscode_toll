# -*- coding: utf-8 -*-
import pandas as pd, numpy as np, io
path = r"C:\Users\45091\Desktop\工作文件\semiconductor_analysis\data\财务分析-5月（6.3）.xlsx"
RAW = ['发货日期','销售部门','实际业务员','业务员对应工号','终端客户简称',
       '终端客户名称_客户类别','存货名称','产品线','产品品类（新）','是否新品',
       '发货数量','未税单价','单位成本','总成本','RMB 未税金额小计','利润']
ALIAS = dict(zip(RAW, ['date','dept','sales','sales_id','cust','cust_tier',
       'sku','pline','pcat','is_new','qty','price','ucost','cost','rev','profit']))
out = io.StringIO()
def p(*a): print(*a, file=out)

df = pd.read_excel(path, sheet_name='24-26', usecols=RAW)
df = df.rename(columns=ALIAS)
df['date'] = pd.to_datetime(df['date'], errors='coerce')
df = df.dropna(subset=['date'])
for c in ['qty','price','ucost','cost','rev','profit']:
    df[c] = pd.to_numeric(df[c], errors='coerce')
df = df[(df['qty']>0) & (df['rev']>0)]
df['y'] = df['date'].dt.year
df['m'] = df['date'].dt.month
p("raw->clean rows:", len(df))
p("date range:", df['date'].min().date(), "->", df['date'].max().date())

# 2026 各月完整性
p("\n== 2026 by month (收入/利润/毛利率/行数) ==")
g = df[df['y']==2026].groupby('m').agg(rev=('rev','sum'),profit=('profit','sum'),n=('rev','count'))
g['gm%'] = (g['profit']/g['rev']*100).round(2)
g['rev万'] = (g['rev']/10000).round(1)
p(g[['rev万','gm%','n']].to_string())

# H1 整体毛利率测试(关键)
cur = df[(df['y']==2026)&(df['m']<=6)]
yoy = df[(df['y']==2025)&(df['m']<=6)]
def gm(d): return d['profit'].sum()/d['rev'].sum()*100
p("\n==== 关键测试 ====")
p("2026H1 收入(万):", round(cur['rev'].sum()/10000,1),
  " 利润(万):", round(cur['profit'].sum()/10000,1),
  " 毛利率%:", round(gm(cur),2))
p("2025H1 收入(万):", round(yoy['rev'].sum()/10000,1),
  " 毛利率%:", round(gm(yoy),2))
p("同比收入增速%:", round((cur['rev'].sum()/yoy['rev'].sum()-1)*100,2))
p("毛利率是否>=34%:", gm(cur)>=34)

# 6月数据完整性粗查(行数与5月比较)
n6 = len(df[(df['y']==2026)&(df['m']==6)])
n5 = len(df[(df['y']==2026)&(df['m']==5)])
p("\n6月行数:", n6, " 5月行数:", n5, " 6月/5月:", round(n6/n5,2) if n5 else "NA")
p("6月最新发货日期:", df[(df['y']==2026)&(df['m']==6)]['date'].max().date())

# 品类概览(产品品类新)
p("\n== 2026H1 各品类(产品品类新) 收入/毛利率 ==")
gc = cur.groupby('pcat').agg(rev=('rev','sum'),profit=('profit','sum'))
gc['gm%'] = (gc['profit']/gc['rev']*100).round(2)
gc['rev万'] = (gc['rev']/10000).round(1)
gc = gc.sort_values('rev',ascending=False)
p(gc[['rev万','gm%']].to_string())
p("品类数:", cur['pcat'].nunique(), " SKU数:", cur['sku'].nunique(),
  " 客户数:", cur['cust'].nunique(), " 销售数:", cur['sales'].nunique())

# 新品标记时间因素核查:同SKU在25vs26的是否新品标记是否变化
p("\n== 新品标记时间因素核查(同SKU跨年标记变化) ==")
nm = df.groupby(['sku','y'])['is_new'].first().reset_index()
piv = nm.pivot(index='sku',columns='y',values='is_new')
if 2025 in piv.columns and 2026 in piv.columns:
    both = piv.dropna(subset=[2025,2026])
    changed = both[both[2025]!=both[2026]]
    p("25&26都有记录的SKU数:", len(both), " 标记发生变化的SKU数:", len(changed))
    p("变化样例(前10):")
    p(changed.head(10).to_string())

with open(r"C:\Users\45091\Desktop\工作文件\semiconductor_analysis\test_out.txt","w",encoding="utf-8") as f:
    f.write(out.getvalue())
print("done")
