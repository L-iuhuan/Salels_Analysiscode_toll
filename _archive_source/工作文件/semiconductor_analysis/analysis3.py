# -*- coding: utf-8 -*-
import pandas as pd, numpy as np, io, re
path = r"C:\Users\45091\Desktop\工作文件\semiconductor_analysis\data\财务分析-5月（6.3）.xlsx"
PERS = r"C:\Users\45091\Desktop\工作文件\semiconductor_analysis\data\部门-人员-职务对应.md"
RAW = ['发货日期','销售部门','实际业务员','业务员对应工号','终端客户简称','终端客户名称_客户类别',
       '存货名称','产品品类（新）','是否新品','发货数量','未税单价','单位成本',
       '总成本','RMB 未税金额小计','利润']
A=dict(zip(RAW,['date','dept','sales','sid','cust','cust_tier','sku','pcat','is_new',
       'qty','price','ucost','cost_col','rev','profit']))
out=io.StringIO()
def p(*a): print(*a,file=out)
ppl_text=open(PERS,encoding='utf-8').read()
ppl=[(m.group(1),m.group(2).strip(),m.group(3).strip()) for m in re.finditer(r'\|\s*(\d{6})\s*\|\s*([^|]+?)\s*\|\s*(销售|销售-FAE|产品|技术|技术-测试|职能)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|', ppl_text)]
ppl_df=pd.DataFrame(ppl,columns=['sid','name','post'])
sales_ppl=ppl_df[ppl_df['post'].isin(['销售','销售-FAE'])]
sid2name=dict(zip(sales_ppl['sid'],sales_ppl['name']))
sales_sid=set(sales_ppl['sid']); sales_name=set(sales_ppl['name'])

df=pd.read_excel(path,sheet_name='24-26',usecols=RAW).rename(columns=A)
df['date']=pd.to_datetime(df['date'],errors='coerce'); df=df.dropna(subset=['date'])
for c in ['qty','price','ucost','cost_col','rev','profit']:
    df[c]=pd.to_numeric(df[c],errors='coerce')
df['y']=df['date'].dt.year; df['m']=df['date'].dt.month
df['pcat']=df['pcat'].fillna('未归类').replace({'0':'未归类','':'未归类'})
df['is_new']=df['is_new'].fillna('否')
df['in_role']=df['sid'].isin(sales_sid) | ((df['sid'].isna())&(df['sales'].isin(sales_name)))
cur=df[(df['y']==2026)&(df['m']<=6)].copy()
yoy=df[(df['y']==2025)&(df['m']<=6)].copy()
B_rev=cur['rev'].sum(); B_prof=cur['profit'].sum(); BENCH=B_prof/B_rev*100; HI=BENCH+5

# ===== 四类归因: KA/AA客户 =====
p("\n## 七、大客户四类归因(KA/AA客户,2026H1 vs 2025H1)")
big=cur[cur['cust_tier'].isin(['KA>1亿','AA>5000万']) & cur['cust'].notna()]['cust'].unique()
p(f"KA/AA大客户数: {len(big)}")
# SKU级每期: cust×sku
def cust_sku(d):
    g=d.groupby(['cust','sku']).agg(q=('qty','sum'),rev=('rev','sum'),cost=('cost_col','sum'),prof=('profit','sum')).reset_index()
    return g
cs_cur=cust_sku(cur); cs_yoy=cust_sku(yoy)
m=cs_cur.merge(cs_yoy,on=['cust','sku'],how='outer',suffixes=('_1','_0')).fillna(0)
# SKU级毛利率(本期,用于高/低判定)
sku_gm_cur=cur.groupby('sku').apply(lambda x: x['profit'].sum()/x['rev'].sum() if x['rev'].sum() else 0)
res=[]
for cu in big:
    sub=m[m['cust']==cu]
    if sub['rev_1'].sum()==0 or sub['rev_0'].sum()==0: continue
    tot_chg=(sub['rev_1'].sum()/sub['rev_0'].sum()-1)*100
    # overlap
    ov=sub[(sub['rev_1']>0)&(sub['rev_0']>0)]
    if len(ov)==0: continue
    gm1=ov['prof_1'].sum()/ov['rev_1'].sum()*100
    gm0=ov['prof_0'].sum()/ov['rev_0'].sum()*100
    gm_chg=gm1-gm0
    # 高/低毛利SKU(按本期SKU毛利)
    ov=ov.copy(); ov['sku_gm']=ov['sku'].map(sku_gm_cur)
    hi=ov[ov['sku_gm']>=HI/100]; lo=ov[ov['sku_gm']<BENCH/100]
    hi_chg=(hi['rev_1'].sum()/hi['rev_0'].sum()-1)*100 if hi['rev_0'].sum() else (200 if hi['rev_1'].sum()>0 else 0)
    lo_chg=(lo['rev_1'].sum()/lo['rev_0'].sum()-1)*100 if lo['rev_0'].sum() else (200 if lo['rev_1'].sum()>0 else 0)
    uc_chg=((ov['cost_1'].sum()/ov['q_1'].sum())/(ov['cost_0'].sum()/ov['q_0'].sum())-1)*100 if ov['q_0'].sum() else 0
    # 判定
    typ='量缩型' if tot_chg<-15 else ('结构切换型' if (tot_chg>=-5 and abs(gm_chg)<=1 and hi_chg<0 and lo_chg>0) else
        ('价格型' if gm_chg<-2 else ('成本型' if uc_chg>5 else '其他/量增型')))
    res.append(dict(cust=cu,rev1=sub['rev_1'].sum(),rev0=sub['rev_0'].sum(),tot_chg=tot_chg,
                    gm1=gm1,gm0=gm0,gm_chg=gm_chg,hi_chg=hi_chg,lo_chg=lo_chg,uc_chg=uc_chg,typ=typ,
                    prof1=sub['prof_1'].sum(),prof0=sub['prof_0'].sum()))
R=pd.DataFrame(res)
p("\n### 四类归因分布")
p("| 类型 | 客户数 | 本期收入(万) | 毛利变化(万) |")
p("|---|---|---|---|")
for typ,sub in R.groupby('typ'):
    p(f"| {typ} | {len(sub)} | {sub['rev1'].sum()/10000:.1f} | {(sub['prof1'].sum()-sub['prof0'].sum())/10000:+.1f} |")
p("\n### 毛利下降的大客户明细(按毛利变化升序)")
R['prof_chg']=R['prof1']-R['prof0']
dec=R[R['prof_chg']<0].sort_values('prof_chg')
p("| 客户 | 类型 | 本期收入(万) | 毛利率(上→本) | 毛利变化(万) | 总采购增速% | 高毛利SKU增速% | 低毛利SKU增速% |")
p("|---|---|---|---|---|---|---|---|")
for _,r in dec.head(15).iterrows():
    p(f"| {r['cust']} | {r['typ']} | {r['rev1']/10000:.1f} | {r['gm0']:.1f}->{r['gm1']:.1f} | {r['prof_chg']/10000:+.1f} | {r['tot_chg']:+.0f} | {r['hi_chg']:+.0f} | {r['lo_chg']:+.0f} |")

# ===== 附件1: 结构切换型 + 毛利下降大客户 产品明细 =====
p("\n## 附件1: 大客户结构变化明细(毛利下降的大客户)")
struct_dec=dec[dec['typ'].isin(['结构切换型','价格型'])].head(6)
for _,r in struct_dec.iterrows():
    cu=r['cust']
    p(f"\n### 客户 {cu} (类型:{r['typ']}, 毛利率{r['gm0']:.1f}%→{r['gm1']:.1f}%, 毛利变化{r['prof_chg']/10000:+.1f}万)")
    # 责任销售
    s=cur[cur['cust']==cu].groupby('sales')['rev'].sum()
    p(f"责任销售: {s.idxmax() if len(s) else '—'}")
    custrows=cs_cur[cs_cur['cust']==cu].merge(cs_yoy[cs_yoy['cust']==cu][['sku','rev','prof']],on='sku',how='outer',suffixes=('_1','_0')).fillna(0)
    custrows['sku_gm']=custrows['sku'].map(sku_gm_cur)
    custrows['rev_chg']=custrows['rev_1']-custrows['rev_0'] if 'rev_0' in custrows else 0
    custrows['prof_chg']=custrows['prof_1']-custrows['prof_0']
    down=custrows[custrows['rev_1']<custrows['rev_0']*0.9].sort_values('prof_chg').head(3)
    up=custrows[(custrows['rev_1']>custrows['rev_0']*1.1)&(custrows['sku_gm']>=HI/100)].sort_values('prof_chg',ascending=False).head(3)
    newin=custrows[(custrows['rev_0']==0)&(custrows['rev_1']>0)].sort_values('prof_1',ascending=False).head(3)
    p("- 采购下降产品(致毛利↓):")
    for _,x in down.iterrows():
        p(f"  - {x['sku']} (毛利{x['sku_gm']*100:.0f}%): 收入{x['rev_0']/10000:.1f}→{x['rev_1']/10000:.1f}万, 毛利变化{x['prof_chg']/10000:+.1f}万")
    p("- 采购上升高毛利产品(致毛利↑):")
    if len(up):
        for _,x in up.iterrows():
            p(f"  - {x['sku']} (毛利{x['sku_gm']*100:.0f}%): 收入{x['rev_0']/10000:.1f}→{x['rev_1']/10000:.1f}万, 毛利变化{x['prof_chg']/10000:+.1f}万")
    else: p("  - (无)")
    p("- 新导入产品(致毛利↑):")
    if len(newin):
        for _,x in newin.iterrows():
            p(f"  - {x['sku']} (毛利{x['sku_gm']*100:.0f}%): 新增收入{x['rev_1']/10000:.1f}万, 毛利{x['prof_1']/10000:+.1f}万")
    else: p("  - (无)")

with open(r"C:\Users\45091\Desktop\工作文件\semiconductor_analysis\res_part3.md","w",encoding="utf-8") as f:
    f.write(out.getvalue())
print("part3 done")
