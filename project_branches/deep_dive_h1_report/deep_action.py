# -*- coding: utf-8 -*-
import pandas as pd, numpy as np, io, re
path = r"C:\Users\45091\Desktop\工作文件\semiconductor_analysis\data\财务分析-5月（6.3）.xlsx"
PERS = r"C:\Users\45091\Desktop\工作文件\semiconductor_analysis\data\部门-人员-职务对应.md"
RAW=['发货日期','销售部门','实际业务员','业务员对应工号','终端客户简称','终端客户名称_客户类别',
     '存货名称','型号_产品线（新）','产品品类（新）','是否新品','发货数量','未税单价','单位成本',
     '总成本','RMB 未税金额小计','利润']
A=dict(zip(RAW,['date','dept','sales','sid','cust','cust_tier','sku','pline','pcat','is_new',
       'qty','price','ucost','cost_col','rev','profit']))
out=io.StringIO()
def p(*a): print(*a,file=out)
def line(): p("\n"+"="*70+"\n")
ppl_text=open(PERS,encoding='utf-8').read()
ppl=[(m.group(1),m.group(2).strip(),m.group(3).strip()) for m in re.finditer(r'\|\s*(\d{6})\s*\|\s*([^|]+?)\s*\|\s*(销售|销售-FAE|产品|技术|技术-测试|职能)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|', ppl_text)]
ppl_df=pd.DataFrame(ppl,columns=['sid','name','post'])
sales_ppl=ppl_df[ppl_df['post'].isin(['销售','销售-FAE'])]
sales_sid=set(sales_ppl['sid']); sales_name=set(sales_ppl['name'])
df=pd.read_excel(path,sheet_name='24-26',usecols=RAW).rename(columns=A)
df['date']=pd.to_datetime(df['date'],errors='coerce'); df=df.dropna(subset=['date'])
for c in ['qty','price','ucost','cost_col','rev','profit']: df[c]=pd.to_numeric(df[c],errors='coerce')
df['y']=df['date'].dt.year; df['m']=df['date'].dt.month
df['pcat']=df['pcat'].fillna('未归类').replace({'0':'未归类','':'未归类'})
df['pline']=df['pline'].fillna('未归类').replace({'0':'未归类','':'未归类'})
df['in_role']=df['sid'].isin(sales_sid) | ((df['sid'].isna())&(df['sales'].isin(sales_name)))
cur=df[(df['y']==2026)&(df['m']<=6)].copy()      # 2026H1
yoy=df[(df['y']==2025)&(df['m']<=6)].copy()      # 2025H1
f2025=df[df['y']==2025].copy()                   # 2025全年
f2024=df[df['y']==2024].copy()                   # 2024全年
BENCH=cur['profit'].sum()/cur['rev'].sum()*100; HI=BENCH+5

# === 1. 典型客户:24/25全年+H1采购口径 + SKU级同比明细 ===
line(); p("## 1. 典型客户采购口径(24全年/25全年/25H1/26H1)+SKU级同比明细")
for cu in ['追觅','中兴康讯','共进','长虹集团']:
    line(); p(f"### {cu}")
    # 全年/半年口径
    for nm,d in [('2024全年',f2024),('2025全年',f2025),('2025H1(同比基期)',yoy),('2026H1(本期)',cur)]:
        sub=d[d['cust']==cu]
        rev=sub['rev'].sum(); prof=sub['profit'].sum()
        gm=prof/rev*100 if rev else 0
        p(f"  {nm}: 采购{rev/10000:.1f}万 利润{prof/10000:.1f}万 毛利率{gm:.2f}%")
    # H1同比
    r26=cur[cur['cust']==cu]['rev'].sum(); r25=yoy[yoy['cust']==cu]['rev'].sum()
    p(f"  H1同比: 采购{(r26/r25-1)*100:+.1f}% ({r25/10000:.1f}→{r26/10000:.1f}万)")
    # SKU级同比明细(2026H1 vs 2025H1)
    p("\n  SKU级同比明细(按毛利变化升序,标★为高毛利SKU≥39.4%):")
    g1=cur[cur['cust']==cu].groupby('sku').agg(rev1=('rev','sum'),prof1=('profit','sum'),pcat=('pcat','first'))
    g0=yoy[yoy['cust']==cu].groupby('sku').agg(rev0=('rev','sum'),prof0=('profit','sum'))
    g=g1.join(g0,how='outer').fillna(0)
    g=g[(g['rev1']>0)|(g['rev0']>0)]
    g['gm1']=(g['prof1']/g['rev1']*100).round(2).fillna(0)
    g['prof_chg']=g['prof1']-g['prof0']
    g['rev_chg']=(g['rev1']/(g['rev0'].replace(0,np.nan))-1)*100
    g['hi']=(g['prof1']/g['rev1']).fillna(0)>=HI/100
    g=g.sort_values('prof_chg')
    p("  | SKU | 品类 | 25H1收入(万) | 26H1收入(万) | 收入同比% | 26H1毛利率% | 毛利变化(万) |")
    p("  |---|---|---|---|---|---|---|")
    for sku,r in g.head(12).iterrows():
        star='★' if r['hi'] else ' '
        rc=f"{r['rev_chg']:+.0f}" if pd.notna(r['rev_chg']) and r['rev_chg']<999 else "新品"
        p(f"  | {star}{sku} | {r['pcat']} | {r['rev0']/10000:.1f} | {r['rev1']/10000:.1f} | {rc} | {r['gm1']} | {r['prof_chg']/10000:+.1f} |")

# === 2. 销售客户级具体引导清单 ===
line(); p("## 2. 销售客户级具体引导清单(哪户+当前低毛利品+引导到哪个高毛利品+怎么做)")
cur_s=cur[cur['in_role']]
# 全公司高毛利SKU池(供推荐)
sku_gm_all=cur.groupby('sku').apply(lambda x:x['profit'].sum()/x['rev'].sum() if x['rev'].sum() else 0)
hi_pool=sku_gm_all[sku_gm_all>=HI/100].index
for nm in ['贺淼淼','周小力','刘仲涵','颜蓉蓉']:
    line(); p(f"### {nm}")
    s_cur=cur_s[cur_s['sales']==nm]
    # 每客户的高毛利占比
    for cu in s_cur['cust'].unique():
        sc=s_cur[s_cur['cust']==cu]
        rev=sc['rev'].sum()
        if rev<300000: continue
        scy=yoy[(yoy['sales']==nm)&(yoy['cust']==cu)]
        rev0=scy['rev'].sum()
        # 高毛利SKU
        gsk=sc.groupby('sku').agg(rev=('rev','sum'),prof=('profit','sum'))
        gsk['gm']=(gsk['prof']/gsk['rev']*100).round(2)
        hi_skus=gsk[gsk['gm']>=HI].index
        hi_share=gsk.loc[gsk.index.isin(hi_skus),'rev'].sum()/rev*100 if rev else 0
        # 同比高毛利占比变化
        gsky=scy.groupby('sku').agg(rev=('rev','sum'),prof=('profit','sum'))
        gsky['gm']=(gsky['prof']/gsky['rev']*100).round(2) if (gsky['rev']>0).any() else 0
        hi0=set(gsky[gsky['gm']>=HI].index) if (gsky['rev']>0).any() else set()
        hi_share0=scy[scy['sku'].isin(hi0)]['rev'].sum()/rev0*100 if rev0 else 0
        chg=hi_share-hi_share0
        # 只列需关注的(占比<40%或同比降>5pct)
        if hi_share<40 or chg<-5:
            # 当前低毛利SKU TOP
            lo=gsk[gsk['gm']<BENCH].sort_values('rev',ascending=False).head(2)
            p(f"  - {cu}: 采购{rev/10000:.1f}万 高毛利占比{hi_share:.0f}%(同比{chg:+.0f}pct)")
            for sku,lr in lo.iterrows():
                # 推荐同品类高毛利SKU
                cat=cur[cur['sku']==sku]['pcat'].mode()
                cat=cat[0] if len(cat) else None
                cand=cur[(cur['pcat']==cat)].groupby('sku').agg(rev=('rev','sum'),prof=('profit','sum'))
                cand['gm']=(cand['prof']/cand['rev']*100).round(2)
                cand_hi=cand[cand['gm']>=HI].sort_values('rev',ascending=False)
                sug=cand_hi.head(1).index[0] if len(cand_hi) else "(无同品类高毛利SKU)"
                sug_gm=cand_hi.head(1)['gm'].iloc[0] if len(cand_hi) else 0
                p(f"      当前低毛利:{sku}({lr['gm']:.0f}%,收入{lr['rev']/10000:.1f}万) → 建议引导到同品类 {sug}(毛利{sug_gm:.0f}%)")

# === 3. DCDC-18V-降压2~4A提价具体方法 ===
line(); p("## 3. DCDC-18V-降压2~4A提价具体方法(各SKU当前ASP/目标/提价额/涉及客户)")
dc=cur[cur['pcat']=='DCDC-18V-降压2~4A']
gsk=dc.groupby('sku').agg(rev=('rev','sum'),prof=('profit','sum'),qty=('qty','sum'),ncust=('cust','nunique'))
gsk=gsk[gsk['rev']>50000].copy()
gsk['asp']=(gsk['rev']/gsk['qty']).round(4)
gsk['gm']=(gsk['prof']/gsk['rev']*100).round(2)
# 目标ASP:该SKU跨全公司中位ASP(若该SKU只在DCDC-18V,用该品类高毛利SKU的ASP水平参考)
# 简单:目标毛利率15%反推目标ASP = 当前单位成本/(1-15%)
gsk['ucost']=(dc.groupby('sku').apply(lambda x:(x['cost_col'].sum()/x['qty'].sum()))).round(4)
gsk['target_asp']=(gsk['ucost']/(1-0.15)).round(4)  # 目标毛利15%反推
gsk['price_up']=(gsk['target_asp']-gsk['asp'])*gsk['qty']  # 提价额
gsk=gsk.sort_values('rev',ascending=False)
p("| SKU | 收入(万) | 毛利率% | 当前ASP | 单位成本 | 目标ASP(毛利15%) | 提价额(万) | 涉及客户数 |")
p("|---|---|---|---|---|---|---|---|")
for sku,r in gsk.iterrows():
    p(f"| {sku} | {r['rev']/10000:.1f} | {r['gm']} | {r['asp']} | {r['ucost']} | {r['target_asp']} | {r['price_up']/10000:+.1f} | {int(r['ncust'])} |")

# === 4. 三方案逐销售具体动作 ===
line(); p("## 4. 三方案逐销售具体动作(直接可用)")
# 方案A:每销售 低毛利SKU→高毛利SKU替换
line(); p("### 方案A·结构优化:每销售低毛利SKU→高毛利SKU替换清单")
for nm in ['贺淼淼','周小力','刘仲涵','颜蓉蓉','胡定昊']:
    s_cur=cur_s[cur_s['sales']==nm]
    gsk=s_cur.groupby('sku').agg(rev=('rev','sum'),prof=('profit','sum'),pcat=('pcat','first'))
    gsk['gm']=(gsk['prof']/gsk['rev']*100).round(2)
    lo=gsk[gsk['gm']<BENCH].sort_values('rev',ascending=False).head(3)
    hi=gsk[gsk['gm']>=HI].sort_values('rev',ascending=False).head(3)
    p(f"\n{nm}:")
    p("  低毛利SKU(切20%出去):")
    for sku,r in lo.iterrows():
        p(f"    - {sku}({r['pcat']},{r['gm']:.0f}%,收入{r['rev']/10000:.1f}万)→ 切{r['rev']*0.2/10000:.1f}万到高毛利")
    p("  高毛利SKU(承接):")
    for sku,r in hi.iterrows():
        p(f"    - {sku}({r['pcat']},{r['gm']:.0f}%,收入{r['rev']/10000:.1f}万)")

# 方案B:每销售 低价SKU提价清单
line(); p("### 方案B·提价:每销售低价SKU→提到中位")
# 复用附件5的低价组合
pos=cur_s[cur_s['qty']>0]
ps=pos.groupby(['sku','sales']).agg(rev=('rev','sum'),qty=('qty','sum')).reset_index()
ps['asp']=ps['rev']/ps['qty']
sk_med=ps.groupby('sku')['asp'].agg(['median','count']).reset_index()
sk_med=sk_med[sk_med['count']>=2]
ps=ps.merge(sk_med[['sku','median']],on='sku')
ps['ratio']=ps['asp']/ps['median']
low=ps[(ps['ratio']<0.9)&(ps['rev']>50000)].copy()
low['gap']=(low['median']-low['asp'])*low['qty']*0.35*0.85  # 可执行
for nm in ['贺淼淼','刘仲涵','周小力','胡定凡','颜蓉蓉']:
    sub=low[low['sales']==nm].sort_values('gap',ascending=False).head(4)
    if len(sub)==0: continue
    p(f"\n{nm}:")
    for _,r in sub.iterrows():
        p(f"  - {r['sku']}: 当前ASP{r['asp']:.4f}→中位{r['median']:.4f}(价比{r['ratio']:.2f}),收入{r['rev']/10000:.1f}万,可执行提价{r['gap']/10000:+.1f}万")

# 方案C:组合(每销售 A的70%+B的30%)
line(); p("### 方案C·组合:结构优化70%+提价30%(每销售合计)")
# 用之前res_asp的数据逻辑重算每销售
sc=cur_s.groupby('sales').agg(rev=('rev','sum'),prof=('profit','sum'))
sc['gm']=sc['prof']/sc['rev']*100
sku_gm_s=cur_s.groupby('sku').apply(lambda x:x['profit'].sum()/x['rev'].sum() if x['rev'].sum() else 0)
hi_skus=set(sku_gm_s[sku_gm_s>=HI/100].index)
lo_skus=set(sku_gm_s[(sku_gm_s<BENCH/100)&(sku_gm_s>=0)].index)
neg_skus=set(sku_gm_s[sku_gm_s<0].index)
exec_by_sales=low.groupby('sales')['gap'].sum()
p("| 销售 | 收入(万) | 现毛利率 | 结构潜力(万,A) | 提价(万,B) | 方案C(A70%+B30%) | 达成后毛利率 |")
p("|---|---|---|---|---|---|---|")
for nm in sc.sort_values('rev',ascending=False).head(8).index:
    s_cur=cur_s[cur_s['sales']==nm]
    rev=s_cur['rev'].sum(); prof=s_cur['profit'].sum(); gm=prof/rev*100
    lo_rev=s_cur[s_cur['sku'].isin(lo_skus|neg_skus)]['rev'].sum()
    hi_gm_avg=cur_s[cur_s['sku'].isin(hi_skus)].groupby('sku').apply(lambda x:x['profit'].sum()/x['rev'].sum() if x['rev'].sum() else 0).mean() if cur_s['sku'].isin(hi_skus).any() else BENCH/100
    lo_gm_avg=s_cur[s_cur['sku'].isin(lo_skus|neg_skus)].groupby('sku').apply(lambda x:x['profit'].sum()/x['rev'].sum() if x['rev'].sum() else 0).mean() if (s_cur['sku'].isin(lo_skus|neg_skus)).any() else 0
    struct=lo_rev*0.2*max(hi_gm_avg-lo_gm_avg,0)
    price=exec_by_sales.get(nm,0)
    c_val=struct*0.7+price*0.3
    after=(prof+c_val)/rev*100
    p(f"| {nm} | {rev/10000:.1f} | {gm:.1f} | +{struct/10000:.1f} | +{price/10000:.1f} | +{c_val/10000:.1f} | {after:.1f} |")

with open(r"C:\Users\45091\Desktop\工作文件\semiconductor_analysis\deep_action.md","w",encoding="utf-8") as f:
    f.write(out.getvalue())
print("done")
