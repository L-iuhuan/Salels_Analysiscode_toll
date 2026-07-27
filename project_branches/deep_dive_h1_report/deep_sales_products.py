# -*- coding: utf-8 -*-
import pandas as pd, numpy as np, io, re
path = r"C:\Users\45091\Desktop\工作文件\semiconductor_analysis\data\财务分析-6月（7.6）.xlsx"
PERS = r"C:\Users\45091\Desktop\工作文件\semiconductor_analysis\data\部门-人员-职务对应.md"
RAW=['发货日期','实际业务员','业务员对应工号','存货名称','产品品类（新）','型号_产品线（新）',
     '发货数量','总成本','RMB 未税金额小计','利润']
A=dict(zip(RAW,['date','sales','sid','sku','pcat','pline','qty','cost','rev','profit']))
ppl_text=open(PERS,encoding='utf-8').read()
ppl=[(m.group(1),m.group(2).strip(),m.group(3).strip()) for m in re.finditer(r'\|\s*(\d{6})\s*\|\s*([^|]+?)\s*\|\s*(销售|销售-FAE|产品|技术|技术-测试|职能)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|', ppl_text)]
ppl_df=pd.DataFrame(ppl,columns=['sid','name','post'])
sales_ppl=ppl_df[ppl_df['post'].isin(['销售','销售-FAE'])]
sales_sid=set(sales_ppl['sid']);sales_name=set(sales_ppl['name'])
df=pd.read_excel(path,sheet_name='24-26',usecols=RAW).rename(columns=A)
df['date']=pd.to_datetime(df['date'],errors='coerce');df=df.dropna(subset=['date'])
for c in ['qty','cost','rev','profit']: df[c]=pd.to_numeric(df[c],errors='coerce')
df['y']=df['date'].dt.year;df['m']=df['date'].dt.month
df['in_role']=df['sid'].isin(sales_sid)|((df['sid'].isna())&(df['sales'].isin(sales_name)))
cur=df[(df['y']==2026)&(df['m']<=6)].copy()
cur_s=cur[cur['in_role']]
BENCH=cur['profit'].sum()/cur['rev'].sum()*100;HI=BENCH+5

out=io.StringIO()
def p(*a): print(*a,file=out)

pline_order=['通用电源管理','有刷直流电机驱动','马达驱动','POE电源管理','充电与控制电源管理',
             '步进电机驱动','车规电机驱动','硬件锂电保护','音频功放','无刷直流电机驱动',
             '磁传感','电脑&计算电源管理','电机驱动','车规电源管理','新显示MLED驱动',
             'dTOF模组','电源模组','未归类']

for nm in sorted(cur_s['sales'].unique()):
    s=cur_s[cur_s['sales']==nm]
    if s['rev'].sum()<50000: continue
    gsk=s.groupby('sku').agg(rev=('rev','sum'),prof=('profit','sum'),pcat=('pcat','first'),pline=('pline','first'))
    gsk['gm']=(gsk['prof']/gsk['rev']*100).round(2)
    gsk=gsk[gsk['rev']>1000]
    # Classify
    def classify(gm,rev):
        if gm>=HI: return '明星'
        if gm<0: return '钩子'
        return '常规'
    gsk['cls']=gsk.apply(lambda r:classify(r['gm'],r['rev']),axis=1)
    # Sort: pline custom order, then gm desc
    gsk['pline_rank']=gsk['pline'].apply(lambda x:pline_order.index(x) if x in pline_order else 99)
    gsk=gsk.sort_values(['pline_rank','gm'],ascending=[True,False])
    p(f"\n## {nm}(H1收入{s['rev'].sum()/10000:.1f}万, 毛利率{s['profit'].sum()/s['rev'].sum()*100:.1f}%)")
    p("| 产品线 | 产品品类 | 产品名称 | H1收入(万) | H1毛利率 | 明星/钩子 |")
    p("|---|---|---|---|---|---|")
    for sku,r in gsk.iterrows():
        p(f"| {r['pline']} | {r['pcat']} | {sku} | {r['rev']/10000:.1f} | {r['gm']}% | {r['cls']} |")

open(r"C:\Users\45091\Desktop\工作文件\semiconductor_analysis\deep_sales_products.md","w",encoding="utf-8").write(out.getvalue())
print("done",len(cur_s['sales'].unique()))
