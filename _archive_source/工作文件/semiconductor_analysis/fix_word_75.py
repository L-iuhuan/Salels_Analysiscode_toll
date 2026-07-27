"""Word: 7.5钩子vs产品差→判定表"""
from docx import Document
from docx.oxml.ns import qn,nsdecls
from docx.oxml import parse_xml, OxmlElement

doc=Document(r"C:\Users\45091\Desktop\2026H1销售分析报告_深度版.docx")
body=doc.element.body
SOFT_BG='EEF2F8';GREEN_BG='E7F3EC';RED_BG='FBE6E1';AMBER_BG='FBF0DA'

def tcPr(bg=None):
    p=OxmlElement('w:tcPr')
    if bg:
        shd=OxmlElement('w:shd');shd.set(qn('w:val'),'clear');shd.set(qn('w:color'),'auto');shd.set(qn('w:fill'),bg)
        p.append(shd)
    return p
def cell(text,bg=None):
    c=OxmlElement('w:tc');c.append(tcPr(bg))
    pa=OxmlElement('w:p');pr=OxmlElement('w:pPr');pa.append(pr)
    r=OxmlElement('w:r');rPr=OxmlElement('w:rPr');r.append(rPr)
    t=OxmlElement('w:t');t.text=text;r.append(t);pa.append(r);c.append(pa)
    return c
def hdr_cell(text):
    c=cell(text,bg=SOFT_BG)
    #加粗,p=OxmlElement('w:p');...
    return c
def make_p(text,bg=None):
    p=OxmlElement('w:p');pr=OxmlElement('w:pPr')
    if bg:
        shd=OxmlElement('w:shd');shd.set(qn('w:val'),'clear');shd.set(qn('w:color'),'auto');shd.set(qn('w:fill'),bg)
        pr.append(shd)
    p.append(pr);r=OxmlElement('w:r');rPr=OxmlElement('w:rPr');r.append(rPr)
    t=OxmlElement('w:t');t.text=text;r.append(t);p.append(r)
    return p

# Find 7.5 heading
h75=None;nxt=None;found=False
for child in body:
    if not child.tag.endswith('}p'): continue
    full=''.join([t.text or '' for t in child.iter() if t.tag.endswith('}t')])
    if not h75 and ('7.5' in full or ('钩子' in full and '产品差' in full and '动作不同' in full)):
        h75=child;found=True;continue
    if found and not nxt:
        pPr=child.find(qn('w:pPr'))
        if pPr:
            se=pPr.find(qn('w:pStyle'))
            if se and se.get(qn('w:val')) in ('1','2','3','4'):
                nxt=child
        if not nxt and ('本章结论' in full or '负毛利处置' in full):
            nxt=child

if not h75: print("ERROR 7.5 not found"); exit(1)
print(f"Found 7.5, nxt={nxt is not None}")

# Collect old
old=[];c=False
for child in body:
    if child is h75: c=True; old.append(child); continue
    if c:
        if nxt and child is nxt: break
        old.append(child)
print(f"Remove {len(old)} elems")

# Build table
headers=['判定类型','代表SKU','特征','动作']
rows=[
    ['🔴 产品力差','IM2405/IM2605/STI3452I\nTMS8201EGM-TR','多客户全负毛利\n(产品定位/成本本身有问题)','停售/整改/汰换\n别再投入'],
    ['🟡 钩子','IM8502(CP)','客户其他正毛利占比<20%\n停了连带流失其他生意','客户组合谈判\n不能简单停'],
    ['🟠 个别客户拉低','STI3452HFI/TMI3214H','只对部分客户负毛利\n(产品本身OK,个别客户低价)','客户级谈判提价\n非产品问题'],
]

tbl=OxmlElement('w:tbl')
tp=OxmlElement('w:tblPr')
tw=OxmlElement('w:tblW');tw.set(qn('w:w'),'9000');tw.set(qn('w:type'),'dxa');tp.append(tw)
tbl.append(tp)
# borders
for edge in ['top','left','bottom','right','insideH','insideV']:
    b=OxmlElement(f'w:tblBorders') if edge=='top' else None
    if edge=='top':
        bo=OxmlElement('w:tblBorders')
        for e2 in ['top','left','bottom','right','insideH','insideV']:
            b2=OxmlElement(f'w:{e2}');b2.set(qn('w:val'),'single');b2.set(qn('w:sz'),'4');b2.set(qn('w:color'),'auto')
            bo.append(b2)
        tbl[0].append(bo)

# Header row
hr=OxmlElement('w:tr')
for h in headers:
    c=cell(h,bg=SOFT_BG)
    # Make bold: find rPr in the first paragraph's first run
    for pa in c.iter():
        if pa.tag.endswith('}p'):
            for r in pa.iter():
                if r.tag.endswith('}r'):
                    rp=r.find(qn('w:rPr'))
                    if rp is not None: rp.append(OxmlElement('w:b'))
    hr.append(c)
tbl.append(hr)
# Data
for ri,rd in enumerate(rows):
    tr=OxmlElement('w:tr')
    bg=(RED_BG if ri==0 else (AMBER_BG if ri==1 else ''))
    for v in rd:
        tr.append(cell(v,bg=bg if bg else None))
    tbl.append(tr)

# Insert
h75.addnext(tbl)
for e in old: body.remove(e)
doc.save(r"C:\Users\45091\Desktop\2026H1销售分析报告_深度版.docx")
print("DONE 7.5")
