"""Word: 追加附件-销售产品清单,不动其他内容,保存为"分析+附件"版"""
import pandas as pd, numpy as np, re
from docx import Document
from docx.shared import Pt, Inches
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

# === 数据(同deep_sales_products.py) ===
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

pline_order=['通用电源管理','有刷直流电机驱动','马达驱动','POE电源管理','充电与控制电源管理',
             '步进电机驱动','车规电机驱动','硬件锂电保护','音频功放','无刷直流电机驱动',
             '磁传感','电脑&计算电源管理','电机驱动','车规电源管理','新显示MLED驱动',
             'dTOF模组','电源模组','未归类']

# === Word building ===
DOC_PATH = r"C:\Users\45091\Desktop\2026H1销售分析报告_深度版.docx"
OUT_PATH = r"C:\Users\45091\Desktop\2026H1销售分析报告_分析+附件.docx"
doc=Document(DOC_PATH)
body=doc.element.body
SOFT_BG='EEF2F8';GREEN_BG='E7F3EC';RED_BG='FBE6E1';AMBER_BG='FBF0DA'

def cell(text,bg=None,fs=7.5):
    c=OxmlElement('w:tc');p=OxmlElement('w:tcPr')
    if bg:
        shd=OxmlElement('w:shd');shd.set(qn('w:val'),'clear');shd.set(qn('w:color'),'auto');shd.set(qn('w:fill'),bg)
        p.append(shd)
    c.append(p);pa=OxmlElement('w:p');pa.append(OxmlElement('w:pPr'))
    r=OxmlElement('w:r');r.append(OxmlElement('w:rPr'));t=OxmlElement('w:t');t.text=str(text)
    r.append(t);pa.append(r);c.append(pa)
    return c

def hcell(text): return cell(text,bg=SOFT_BG)

def make_p(text,bg=None):
    p=OxmlElement('w:p');pr=OxmlElement('w:pPr')
    if bg:
        shd=OxmlElement('w:shd');shd.set(qn('w:val'),'clear');shd.set(qn('w:color'),'auto');shd.set(qn('w:fill'),bg)
        pr.append(shd)
    p.append(pr);r=OxmlElement('w:r');rp=OxmlElement('w:rPr');rp.append(OxmlElement('w:b'));r.append(rp)
    t=OxmlElement('w:t');t.text=text;r.append(t);p.append(r)
    return p

def mk_table(headers,rows):
    tbl=OxmlElement('w:tbl')
    tp=OxmlElement('w:tblPr');tw=OxmlElement('w:tblW');tw.set(qn('w:w'),'9000');tw.set(qn('w:type'),'dxa');tp.append(tw)
    bo=OxmlElement('w:tblBorders')
    for e in ['top','left','bottom','right','insideH','insideV']:
        b=OxmlElement(f'w:{e}');b.set(qn('w:val'),'single');b.set(qn('w:sz'),'4');b.set(qn('w:color'),'auto');bo.append(b)
    tp.append(bo);tbl.append(tp)
    hr=OxmlElement('w:tr')
    for h in headers: hr.append(hcell(h))
    tbl.append(hr)
    for ri,rd in enumerate(rows):
        tr=OxmlElement('w:tr')
        cls=rd[-1] if rd else ''
        bg=None
        if cls=='明星': bg=GREEN_BG
        elif cls=='钩子': bg=RED_BG
        for v in rd: tr.append(cell(v,bg=bg))
        tbl.append(tr)
    return tbl

# Find last element of appendix section (附件E)
last_appendix=None
for p in doc.paragraphs:
    if p.style.name.startswith('Heading') and ('附件E' in p.text or '数据待补' in p.text):
        # find this paragraph's element
        for child in body:
            if child.tag.endswith('}p'):
                full=''.join([t.text or '' for t in child.iter() if t.tag.endswith('}t')])
                if '附件E' in full or '数据待补' in full:
                    last_appendix=child
        break

if not last_appendix:
    # fallback: find footer-related, or use last section end
    for child in reversed(list(body)):
        if child.tag.endswith('}p'):
            full=''.join([t.text or '' for t in child.iter() if t.tag.endswith('}t')])
            if '数据待补' in full or '翁创伟' in full:
                last_appendix=child;break

if not last_appendix:
    # final fallback: last paragraph in document
    for child in reversed(list(body)):
        if child.tag.endswith('}p') and last_appendix is None:
            last_appendix=child;break

print(f"Append after: {last_appendix is not None}")

# Build all sales product tables
sales_list=sorted(cur_s['sales'].unique())
elems=[]
for nm in sales_list:
    s=cur_s[cur_s['sales']==nm]
    rev=s['rev'].sum();prof=s['profit'].sum()
    if rev<50000: continue
    gm=prof/rev*100
    gsk=s.groupby('sku').agg(rev=('rev','sum'),prof=('profit','sum'),pcat=('pcat','first'),pline=('pline','first'))
    gsk['gm']=(gsk['prof']/gsk['rev']*100).round(2)
    gsk=gsk[gsk['rev']>1000]
    def classify(gm,rev):
        if gm>=HI: return '明星'
        if gm<0: return '钩子'
        return '常规'
    gsk['cls']=gsk.apply(lambda r:classify(r['gm'],r['rev']),axis=1)
    gsk['pline_rank']=gsk['pline'].apply(lambda x:pline_order.index(x) if x in pline_order else 99)
    gsk=gsk.sort_values(['pline_rank','gm'],ascending=[True,False])

    elems.append(make_p(f'{nm}(H1收入{rev/10000:.1f}万,毛利率{gm:.1f}%)'))
    hd=['产品线','产品品类','产品名称','H1收入(万)','H1毛利率','明星/钩子']
    rows=[]
    for sku,r in gsk.iterrows():
        rows.append([r['pline'],r['pcat'],sku,f"{r['rev']/10000:.2f}",f"{r['gm']:.2f}%",r['cls']])
    elems.append(mk_table(hd,rows))
    elems.append(make_p(''))  # spacer

# Insert after last_appendix
prev=last_appendix
for e in elems:
    prev.addnext(e)
    prev=e

doc.save(OUT_PATH)
print(f"DONE: {OUT_PATH}")
