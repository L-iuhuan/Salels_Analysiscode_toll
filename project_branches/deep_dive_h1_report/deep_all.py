# -*- coding: utf-8 -*-
import pandas as pd, numpy as np, io, re
path = r"C:\Users\45091\Desktop\工作文件\semiconductor_analysis\data\财务分析-5月（6.3）.xlsx"
PERS = r"C:\Users\45091\Desktop\工作文件\semiconductor_analysis\data\部门-人员-职务对应.md"
RAW=['发货日期','销售部门','实际业务员','业务员对应工号','终端客户简称','终端客户名称','终端客户名称_客户类别',
     '存货名称','型号_产品线（新）','产品线','产品品类（新）','是否新品','发货数量','未税单价',
     '单位成本','总成本','RMB 未税金额小计','利润']
A=dict(zip(RAW,['date','dept','sales','sid','cust','cust_full','cust_tier','sku','pline','pline1','pcat','is_new',
       'qty','price','ucost','cost_col','rev','profit']))
out=io.StringIO()
def p(*a): print(*a,file=out)
def line(): p("\n"+"="*70+"\n")
# personnel
ppl_text=open(PERS,encoding='utf-8').read()
ppl=[(m.group(1),m.group(2).strip(),m.group(3).strip()) for m in re.finditer(r'\|\s*(\d{6})\s*\|\s*([^|]+?)\s*\|\s*(销售|销售-FAE|产品|技术|技术-测试|职能)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|', ppl_text)]
ppl_df=pd.DataFrame(ppl,columns=['sid','name','post'])
sales_ppl=ppl_df[ppl_df['post'].isin(['销售','销售-FAE'])]
sales_sid=set(sales_ppl['sid']); sales_name=set(sales_ppl['name'])
# load
df=pd.read_excel(path,sheet_name='24-26',usecols=RAW).rename(columns=A)
df['date']=pd.to_datetime(df['date'],errors='coerce'); df=df.dropna(subset=['date'])
for c in ['qty','price','ucost','cost_col','rev','profit']: df[c]=pd.to_numeric(df[c],errors='coerce')
df['y']=df['date'].dt.year; df['m']=df['date'].dt.month
df['pcat']=df['pcat'].fillna('未归类').replace({'0':'未归类','':'未归类'})
df['pline']=df['pline'].fillna('未归类').replace({'0':'未归类','':'未归类'})
df['is_new']=df['is_new'].fillna('否')
df['in_role']=df['sid'].isin(sales_sid) | ((df['sid'].isna())&(df['sales'].isin(sales_name)))
cur=df[(df['y']==2026)&(df['m']<=6)].copy()
yoy=df[(df['y']==2025)&(df['m']<=6)].copy()
BENCH=cur['profit'].sum()/cur['rev'].sum()*100; HI=BENCH+5

# === 1. 产品线完整(17条)+通用电源管理下24品类 ===
line(); p("## 1. 17条产品线完整表(2026H1,占比合计=100%)")
tot=cur['rev'].sum()
gp=cur.groupby('pline').agg(rev=('rev','sum'),prof=('profit','sum'))
gp['gm']=(gp['prof']/gp['rev']*100).round(2); gp['share']=(gp['rev']/tot*100).round(2)
gy=yoy.groupby('pline')['rev'].sum(); gp['yoy']=(gp['rev']/gy-1)*100
gp['ncat']=cur.groupby('pline')['pcat'].nunique(); gp['nsku']=cur.groupby('pline')['sku'].nunique()
gp=gp.sort_values('rev',ascending=False)
p("| 产品线 | 收入(万) | 占比% | 毛利率% | 同比% | 品类数 | SKU数 |")
p("|---|---|---|---|---|---|---|")
for nm,r in gp.iterrows():
    yy=f"{r['yoy']:+.0f}" if pd.notna(r['yoy']) else "—"
    p(f"| {nm} | {r['rev']/10000:.1f} | {r['share']} | {r['gm']} | {yy} | {int(r['ncat'])} | {int(r['nsku'])} |")
p(f"\n合计: 收入{gp['rev'].sum()/10000:.1f}万 占比{gp['share'].sum():.2f}% 毛利率{gp['prof'].sum()/gp['rev'].sum()*100:.2f}%")
# 通用电源管理下24品类
line(); p("## 2. 通用电源管理下24品类(TOP6+其他18,合计=26772=62%)")
gpm=cur[cur['pline']=='通用电源管理']
gpc=gpm.groupby('pcat').agg(rev=('rev','sum'),prof=('profit','sum'))
gpc['gm']=(gpc['prof']/gpc['rev']*100).round(2); gpc['share']=(gpc['rev']/gpm['rev'].sum()*100).round(1)
gpcy=yoy[yoy['pline']=='通用电源管理'].groupby('pcat')['rev'].sum()
gpc['yoy']=(gpc['rev']/gpcy-1)*100
gpc=gpc.sort_values('rev',ascending=False)
p(f"通用电源管理总: 收入{gpm['rev'].sum()/10000:.1f}万 毛利{gpm['profit'].sum()/10000:.1f}万 毛利率{gpm['profit'].sum()/gpm['rev'].sum()*100:.2f}% 品类数{gpm['pcat'].nunique()}")
p("| 品类 | 收入(万) | 占该线% | 毛利率% | 同比% |")
p("|---|---|---|---|---|")
top6=gpc.head(6); other=gpc.iloc[6:]
for nm,r in top6.iterrows():
    yy=f"{r['yoy']:+.0f}" if pd.notna(r['yoy']) else "—"
    p(f"| {nm} | {r['rev']/10000:.1f} | {r['share']} | {r['gm']} | {yy} |")
p(f"| 其他{len(other)}品类 | {other['rev'].sum()/10000:.1f} | {other['rev'].sum()/gpm['rev'].sum()*100:.1f} | {(other['prof'].sum()/other['rev'].sum()*100).round(2) if other['rev'].sum() else 0} | — |")
p(f"\n合计验证: TOP6+其他{len(other)}={len(gpc)}品类, 收入{(top6['rev'].sum()+other['rev'].sum())/10000:.1f}万 = 通用电源管理{gpm['rev'].sum()/10000:.1f}万")

# === 3. 明星品类TOP SKU ===
line(); p("## 3. 5个明星品类各TOP5 SKU(归因到产品)")
stars=['DCDC-5V-降压1~3A','USB单通道/多通道2.4A/3A','H桥BDC-中大功率(合封系列20V/30V/40V/60V )','PSE','DCDC-30V/40V降压1~6A通用系列']
for sc in stars:
    line(); p(f"### 明星品类: {sc}")
    sub=cur[cur['pcat']==sc]; suby=yoy[yoy['pcat']==sc]
    p(f"品类合计: 收入{sub['rev'].sum()/10000:.1f}万 毛利率{sub['profit'].sum()/sub['rev'].sum()*100:.2f}%")
    gsk=sub.groupby('sku').agg(rev=('rev','sum'),prof=('profit','sum'),qty=('qty','sum'))
    gsk['gm']=(gsk['prof']/gsk['rev']*100).round(2)
    gsky=suby.groupby('sku')['rev'].sum(); gsk['yoy']=(gsk['rev']/gsky-1)*100
    gsk['prof_chg']=gsk['prof']-suby.groupby('sku')['profit'].sum()
    gsk=gsk.sort_values('rev',ascending=False).head(5)
    p("| SKU | 收入(万) | 毛利率% | 同比% | 毛利变化(万) |")
    p("|---|---|---|---|---|")
    for sku,r in gsk.iterrows():
        yy=f"{r['yoy']:+.0f}" if pd.notna(r['yoy']) and r['yoy']<999 else "新品"
        p(f"| {sku} | {r['rev']/10000:.1f} | {r['gm']} | {yy} | {r['prof_chg']/10000:+.1f} |")

# === 4. 衰退/低毛利品类归因(拖累SKU+全客户vs个别客户) ===
line(); p("## 4. 低毛利/衰退品类归因(拖累SKU,产品力差vs客户拉低)")
pc=cur.groupby('pcat').agg(rev=('rev','sum'),prof=('profit','sum'))
pc=pc[pc.index!='未归类']; pc['gm']=(pc['prof']/pc['rev']*100).round(2)
pcy=yoy.groupby('pcat')['profit'].sum(); pc['prof_chg']=pc['prof']-pcy
weak=pc[(pc['gm']<25)|(pc['prof_chg']<-50)].sort_values('prof_chg')
for cat,r in weak.head(8).iterrows():
    line(); p(f"### 品类: {cat} (收入{r['rev']/10000:.1f}万 毛利率{r['gm']}% 毛利变化{r['prof_chg']/10000:+.1f}万)")
    sub=cur[cur['pcat']==cat]
    gsk=sub.groupby('sku').agg(rev=('rev','sum'),prof=('profit','sum'))
    gsk['gm']=(gsk['prof']/gsk['rev']*100).round(2); gsk=gsk.sort_values('prof')
    p("拖累SKU(毛利最低/亏损):")
    for sku,sr in gsk.head(3).iterrows():
        # 判断全客户低毛利vs个别客户
        skc=sub[sub['sku']==sku].groupby('cust').agg(rev=('rev','sum'),prof=('profit','sum'))
        skc['gm']=(skc['prof']/skc['rev']*100).round(2)
        n_neg=(skc['gm']<0).sum(); n_tot=len(skc)
        verdict="全客户低毛利→产品力差" if (skc['gm']<25).sum()>=max(2,n_tot*0.5) else "个别客户拉低→客户问题"
        p(f"  - {sku}: 收入{sr['rev']/10000:.1f}万 毛利{sr['gm']}% 亏{sr['prof']/10000:+.1f}万 | 客户数{n_tot} 其中负毛利{n_neg}户 → {verdict}")

# === 5. DCDC-18V-降压2~4A全貌 ===
line(); p("## 5. DCDC-18V-降压2~4A全貌")
dc=cur[cur['pcat']=='DCDC-18V-降压2~4A']
p(f"品类: 收入{dc['rev'].sum()/10000:.1f}万 利润{dc['profit'].sum()/10000:.1f}万 毛利率{dc['profit'].sum()/dc['rev'].sum()*100:.2f}%")
# 最大客户TOP5
gc=dc.groupby('cust').agg(rev=('rev','sum'),prof=('profit','sum'))
gc['gm']=(gc['prof']/gc['rev']*100).round(2); gc=gc.sort_values('rev',ascending=False)
p("\n最大客户TOP5:")
p("| 客户 | 收入(万) | 占该品类% | 毛利率% |")
p("|---|---|---|---|")
for cu,r in gc.head(5).iterrows():
    p(f"| {cu} | {r['rev']/10000:.1f} | {r['rev']/dc['rev'].sum()*100:.1f} | {r['gm']} |")
cr3=gc.head(3)['rev'].sum()/dc['rev'].sum()*100; cr5=gc.head(5)['rev'].sum()/dc['rev'].sum()*100
p(f"\nCR3={cr3:.1f}% CR5={cr5:.1f}%")
# 拖累SKU + 优质SKU
gsk=dc.groupby('sku').agg(rev=('rev','sum'),prof=('profit','sum'))
gsk['gm']=(gsk['prof']/gsk['rev']*100).round(2); gsk=gsk.sort_values('prof')
p("\n拖累SKU(毛利最低):")
for sku,r in gsk.head(5).iterrows():
    p(f"  - {sku}: 收入{r['rev']/10000:.1f}万 毛利{r['gm']}% 亏{r['prof']/10000:+.1f}万")
p("\n优质SKU(毛利>20%):")
good=gsk[gsk['gm']>20].sort_values('rev',ascending=False)
for sku,r in good.head(5).iterrows():
    p(f"  - {sku}: 收入{r['rev']/10000:.1f}万 毛利{r['gm']}% 利{r['prof']/10000:+.1f}万")
# 深度依赖客户(该客户收入中此品类占比>50%)
p("\n深度依赖客户(该客户收入中DCDC-18V-降压2~4A占比>30%):")
cust_tot=cur.groupby('cust')['rev'].sum()
dep=[]
for cu in gc.index:
    share=dc[dc['cust']==cu]['rev'].sum()/cust_tot[cu]*100 if cust_tot[cu] else 0
    if share>30 and gc.loc[cu,'rev']>500000:
        dep.append((cu,gc.loc[cu,'rev']/10000,share,gc.loc[cu,'gm']))
for cu,rev,sh,gm in sorted(dep,key=lambda x:-x[1])[:8]:
    p(f"  - {cu}: 该品类收入{rev:.1f}万 占其采购{sh:.0f}% 毛利率{gm}%")

# === 6. 负毛利22 SKU明细 ===
line(); p("## 6. 22个净负毛利SKU明细")
sku_gm=cur.groupby('sku').apply(lambda x:x['profit'].sum()/x['rev'].sum() if x['rev'].sum() else 0)
new_skus=set(cur[cur['is_new']=='是']['sku'].unique())
sk=cur.groupby('sku').agg(rev=('rev','sum'),prof=('profit','sum'),pcat=('pcat','first'),qty=('qty','sum'))
sk=sk[sk['rev']>0]; neg=sk[sk['prof']<0].copy()
neg['exempt']=neg.index.isin(new_skus); net=neg[~neg['exempt']].copy()
net=net.sort_values('prof')
p(f"净负毛利SKU数: {len(net)} 合计亏损{net['prof'].sum()/10000:.1f}万")
p("| SKU | 品类 | 收入(万) | 亏损(万) | 风险级 | 钩子or产品差 | 全量or个别客户负毛利 |")
p("|---|---|---|---|---|---|---|")
# 风险级+钩子判定
for sku,r in net.iterrows():
    sub=cur[cur['sku']==sku]
    skc=sub.groupby('cust').agg(rev=('rev','sum'),prof=('profit','sum'))
    skc['gm']=(skc['prof']/skc['rev']*100).round(2)
    n_cust=len(skc); n_neg=(skc['gm']<0).sum()
    # 风险: 主客户其他正毛利占比
    main_cust=skc['rev'].idxmax()
    other_rev=cur[(cur['cust']==main_cust)&(cur['sku']!=sku)&(cur['profit']>0)]['rev'].sum()
    main_tot=cur[cur['cust']==main_cust]['rev'].sum()
    share=other_rev/main_tot if main_tot else 0
    risk='低危' if share>0.6 else ('高危' if share<0.2 else '中危')
    is_hook = share<0.2
    product_weak = (skc['gm']<0).sum()>=max(2,n_cust*0.5)
    verdict = '钩子(客户依赖)' if is_hook else ('产品差(全客户负毛利)' if product_weak else '个别客户拉低')
    scope = '全量负毛利' if n_neg==n_cust else f'个别客户负毛利({n_neg}/{n_cust}户)'
    p(f"| {sku} | {r['pcat']} | {r['rev']/10000:.1f} | {r['prof']/10000:.1f} | {risk} | {verdict} | {scope} |")
# 测算:仅处置负毛利能否达35%
gap=0.35*cur['rev'].sum()-cur['profit'].sum()
recover=net['prof'].sum()*-1  # 处置后减亏
p(f"\n仅处置负毛利: 减亏{recover/10000:.1f}万, 缺口{gap/10000:.1f}万, {'能' if recover>=gap else '不能'}单独达35%(差{(gap-recover)/10000:.1f}万)")

# === 7. 大客户增长/下跌TOP + 大客户毛利桥 ===
line(); p("## 7. KA/AA大客户增长TOP10/下跌TOP10")
big=cur[cur['cust_tier'].isin(['KA>1亿','AA>5000万']) & cur['cust'].notna()]['cust'].unique()
cc=cur[cur['cust'].isin(big)].groupby('cust').agg(rev=('rev','sum'),prof=('profit','sum'))
ccy=yoy[yoy['cust'].isin(big)].groupby('cust').agg(rev0=('rev','sum'),prof0=('profit','sum'))
c=cc.join(ccy,how='outer').fillna(0)
c['rev_chg']=(c['rev']/c['rev0'].replace(0,np.nan)-1)*100
c['prof_chg']=c['prof']-c['prof0']; c['gm']=(c['prof']/c['rev']*100).round(2) if c['rev'].sum() else 0
c['gm0']=(c['prof0']/c['rev0']*100).round(2) if c['rev0'].sum() else 0
p("### 增长TOP10(按毛利变化降序)")
grow=c[c['prof_chg']>0].sort_values('prof_chg',ascending=False).head(10)
p("| 客户 | 本期收入(万) | 毛利率(上→本) | 毛利变化(万) | 收入增速% |")
p("|---|---|---|---|---|")
for cu,r in grow.iterrows():
    p(f"| {cu} | {r['rev']/10000:.1f} | {r['gm0']}→{r['gm']} | {r['prof_chg']/10000:+.1f} | {r['rev_chg']:+.0f} |")
p("\n### 下跌TOP10(按毛利变化升序)")
dec=c[c['prof_chg']<0].sort_values('prof_chg').head(10)
p("| 客户 | 本期收入(万) | 毛利率(上→本) | 毛利变化(万) | 收入增速% |")
p("|---|---|---|---|---|")
for cu,r in dec.iterrows():
    p(f"| {cu} | {r['rev']/10000:.1f} | {r['gm0']}→{r['gm']} | {r['prof_chg']/10000:+.1f} | {r['rev_chg']:+.0f} |")
# 大客户毛利桥(可比SKU)
line(); p("## 7b. 大客户板块毛利桥(可比SKU)")
bcur=cur[cur['cust'].isin(big)]; byoy=yoy[yoy['cust'].isin(big)]
def sku_agg(d):
    return d.groupby('sku').agg(q=('qty','sum'),rev=('rev','sum'),cost=('cost_col','sum'),prof=('profit','sum'))
gc_=sku_agg(bcur); gy_=sku_agg(byoy)
g=gc_.join(gy_,how='inner',lsuffix='1',rsuffix='0')
g=g[(g['rev1']>0)&(g['rev0']>0)&(g['q1']!=0)&(g['q0']!=0)]
g['p0']=g['rev0']/g['q0']; g['p1']=g['rev1']/g['q1']
g['uc0']=g['cost0']/g['q0']; g['uc1']=g['cost1']/g['q1']; g['m0']=g['prof0']/g['rev0']
t1=g['rev1'].sum(); t0=g['rev0'].sum()
g['s0']=g['rev0']/t0; g['s1']=g['rev1']/t1
qe=((g['q1']-g['q0'])*g['p0']*g['m0']).sum()
pe=((g['p1']-g['p0'])*g['q1']*g['m0']).sum()
ce=((g['uc0']-g['uc1'])*g['q1']).sum()
me=((g['s1']-g['s0'])*g['m0']*t1).sum()
pchg=g['prof1'].sum()-g['prof0'].sum()
p(f"可比SKU数{len(g)} 本期收入{t1/10000:.1f}万 上期{t0/10000:.1f}万 利润变化{pchg/10000:+.1f}万")
p(f"| 量效应 | {qe/10000:+.1f}万 |")
p(f"| 价效应 | {pe/10000:+.1f}万 |")
p(f"| 成本效应 | {ce/10000:+.1f}万 |")
p(f"| 结构效应 | {me/10000:+.1f}万 |")
p(f"| 四效应合计 | {(qe+pe+ce+me)/10000:+.1f}万 |")
p(f"| 交互残差 | {(pchg-(qe+pe+ce+me))/10000:+.1f}万 |")

# === 8. 典型客户画像 ===
line(); p("## 8. 三个典型客户画像")
for cu in ['中兴康讯','追觅','共进']:
    line(); p(f"### {cu}")
    sub=cur[cur['cust']==cu]; suby=yoy[yoy['cust']==cu]
    p(f"年采购额: 本期{sub['rev'].sum()/10000:.1f}万 上期{suby['rev'].sum()/10000:.1f}万")
    p(f"综合毛利率: 本期{sub['profit'].sum()/sub['rev'].sum()*100:.2f}% 上期{suby['profit'].sum()/suby['rev'].sum()*100:.2f}% 利润{sub['profit'].sum()/10000:.1f}万")
    # 主营品类
    gpc=sub.groupby('pcat').agg(rev=('rev','sum'),prof=('profit','sum'))
    gpc['gm']=(gpc['prof']/gpc['rev']*100).round(2); gpc['share']=(gpc['rev']/sub['rev'].sum()*100).round(1)
    gpc=gpc.sort_values('rev',ascending=False)
    p("主要需求品类TOP5:")
    for cat,r in gpc.head(5).iterrows():
        p(f"  - {cat}: 收入{r['rev']/10000:.1f}万 占{r['share']}% 毛利{r['gm']}%")

# === 9. 销售需求结构×周期 ===
line(); p("## 9. 销售名下客户需求结构×周期(9.2重构)")
cur_s=cur[cur['in_role']]
for nm in ['贺淼淼','周小力','刘仲涵','颜蓉蓉','袁坤']:
    s_cur=cur_s[cur_s['sales']==nm]
    p(f"\n### {nm} (收入{s_cur['rev'].sum()/10000:.1f}万)")
    # 客户需求结构: 高毛利品同比增减
    cstat=[]
    for cu in s_cur['cust'].unique():
        sc=s_cur[s_cur['cust']==cu]; scy=yoy[(yoy['sales']==nm)&(yoy['cust']==cu)]
        rev=sc['rev'].sum(); rev0=scy['rev'].sum()
        if rev<50000: continue
        hi=sc[sc['pcat'].map(lambda c: sku_gm.get('',0))>0]  # placeholder
        # 高毛利SKU占比
        sku_g=sc.groupby('sku')['profit'].sum()/sc.groupby('sku')['rev'].sum()
        hi_skus=sku_g[sku_g>=HI/100].index
        hi_rev=sc[sc['sku'].isin(hi_skus)]['rev'].sum()
        hi_share=hi_rev/rev*100 if rev else 0
        scy_skus=scy[scy['sku'].isin(hi_skus)]['rev'].sum() if rev0 else 0
        hi_share0=scy_skus/rev0*100 if rev0 else 0
        chg=hi_share-hi_share0
        cycle='放量' if rev>rev0*1.15 else ('收缩' if rev<rev0*0.85 else '稳定')
        cstat.append((cu,rev/10000,hi_share,chg,cycle))
    # 按 cycle+chg 排序给建议
    for cu,rev,hs,chg,cyc in sorted(cstat,key=lambda x:-x[1])[:6]:
        advice='引导回归高毛利' if (chg<-5 and cyc!='放量') else ('固化高毛利' if chg>5 else '维持')
        p(f"  - {cu}: 收入{rev:.1f}万 高毛利占比{hs:.0f}%(同比{chg:+.0f}pct) 周期{cyc} → {advice}")

with open(r"C:\Users\45091\Desktop\工作文件\semiconductor_analysis\deep_all.md","w",encoding="utf-8") as f:
    f.write(out.getvalue())
print("done")
