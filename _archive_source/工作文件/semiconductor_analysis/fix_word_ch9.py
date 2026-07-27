"""Word: 第九章 销售引导卡片→统一表格"""
from docx import Document
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

doc=Document(r"C:\Users\45091\Desktop\2026H1销售分析报告_深度版.docx")
body=doc.element.body
SOFT_BG='EEF2F8';GREEN_BG='E7F3EC'

def cell(text,bg=None):
    c=OxmlElement('w:tc');p=OxmlElement('w:tcPr')
    if bg:
        shd=OxmlElement('w:shd');shd.set(qn('w:val'),'clear');shd.set(qn('w:color'),'auto');shd.set(qn('w:fill'),bg)
        p.append(shd)
    c.append(p);pa=OxmlElement('w:p');pa.append(OxmlElement('w:pPr'))
    r=OxmlElement('w:r');r.append(OxmlElement('w:rPr'))
    t=OxmlElement('w:t');t.text=text;r.append(t);pa.append(r);c.append(pa)
    return c
def hcell(text): return cell(text,bg=SOFT_BG)

def mk_table(headers,rows,width='9000'):
    tbl=OxmlElement('w:tbl')
    tp=OxmlElement('w:tblPr');tw=OxmlElement('w:tblW');tw.set(qn('w:w'),width);tw.set(qn('w:type'),'dxa');tp.append(tw)
    bo=OxmlElement('w:tblBorders')
    for e in ['top','left','bottom','right','insideH','insideV']:
        b=OxmlElement(f'w:{e}');b.set(qn('w:val'),'single');b.set(qn('w:sz'),'4');b.set(qn('w:color'),'auto');bo.append(b)
    tp.append(bo);tbl.append(tp)
    hr=OxmlElement('w:tr')
    for h in headers: hr.append(hcell(h))
    tbl.append(hr)
    for rd in rows:
        tr=OxmlElement('w:tr')
        for v in rd: tr.append(cell(v))
        tbl.append(tr)
    return tbl

# Find 第九章 start & 十章 start
h9=None;h10=None
for child in body:
    if not child.tag.endswith('}p'): continue
    full=''.join([t.text or '' for t in child.iter() if t.tag.endswith('}t')])
    if not h9 and ('贺淼淼' in full and ('需重点关注' in full or '最大销售' in full or '关注客户' in full)):
        h9=child
        continue
    if h9 and not h10:
        if ('价格与买赠' in full or 'ASP口径' in full or '十、' in full):
            h10=child

if not h9:
    # fallback: find 九 heading
    for child in body:
        if not child.tag.endswith('}p'): continue
        full=''.join([t.text or '' for t in child.iter() if t.tag.endswith('}t')])
        if '九、' in full and ('销售' in full or '人员' in full):
            # Find the content AFTER this heading
            pass
    print("FALLBACK: searching by 九 heading")
    found_h9=False
    for child in body:
        if not child.tag.endswith('}p'): continue
        full=''.join([t.text or '' for t in child.iter() if t.tag.endswith('}t')])
        if not h9 and ('九、' in full or '销售人员' in full) and ('管理' in full or '需求' in full):
            found_h9=True; continue
        if found_h9 and not h9 and ('贺淼淼' in full or '周小力' in full or '刘仲涵' in full):
            h9=child
            break

if not h9: print("ERROR: 未找到第九章内容"); exit(1)
print(f"Found 9 start, h10={h10 is not None}")

# Collect old between h9 and h10
old=[];c=False
for child in body:
    if child is h9: c=True; old.append(child); continue
    if c:
        if h10 and child is h10: break
        old.append(child)
print(f"Remove {len(old)} elems")

# Build tables — one per sales person
tables_data = [
    ('贺淼淼(6,180万)',['客户','采购(万)','高毛利占比(同比)','当前低毛利SKU','→引导到','动作'],
     [['中兴康讯','1,390','1%(+0pct)','STI3452HFI(−23%,531万)\nSTI3454I(12%,168万)','TMI3286B(47%)','提价/限产+导入TMI7604R替换'],
      ['长虹集团','596','27%(−23pct)','TMI3257N(7%,47万)\nTMI3253SHFN(3%,45万)','TMI3286B(47%)','提价+新品替换'],
      ['金锐显','188','59%(−10pct)','TMI3410(30%,18万)\nTMI6240I(28%,16万)','TMI3113B(54%)\nTMI6220(50%)','提价+新品替换'],
      ['成都旭光/芯德','136/103','0%/2%','STI3470D(25%,85万)\nTMI3253SH(18%,48万)','TMI3286B(47%)','定向导入高毛利替代品'],
      ['可固化','创维556/彤兴449/比亚迪345','63%+/43%+/56%+','—','—','固化打法+放大收入']]),
    ('周小力(5,402万)',['客户','采购(万)','高毛利占比(同比)','当前低毛利SKU','→引导到','动作'],
     [['共进','1,057','14%(−22pct)','STI3452HFI(−2%,268万)\nSTI3453(2%,170万)','TMI3286B(47%)','提价+TMI6011替换'],
      ['TPLINK','586','19%(+19pct)','TMI8152(23%,138万)\nTMI3244T(23%,61万)','TMI8160(40%)\nTMI3286B(47%)','提价+新品替换'],
      ['通则康威','433','28%(−8pct)','TMI3244T(28%,93万)\nTMI3253S(19%,54万)','TMI3286B(47%)','提价+新品替换'],
      ['芯睿视/星网智慧','253/190','8%/0%(−27%/−18%)','TMI8152(19%,140万)\nTMI3253S(9%,79万)','TMI8160(40%)\nTMI3286B(47%)','提价+新品替换'],
      ['九联/九联科技','159','6%(+6pct)','TMI3257N(10%,78万)\nTMI3258N(15%,60万)','TMI3286B(47%)','提价+新品替换']]),
    ('刘仲涵(4,417万)',['客户','采购(万)','高毛利占比(同比)','当前低毛利SKU','→引导到','动作'],
     [['追觅','1,966','5%(−62pct)','TMI8180G(31%,1,350万)\nTMI6240(33%,287万)','TMI8870(46%)\nTMI6220(50%)','用量挽回+TMI8180G买赠审查'],
      ['杉川','427','28%(−71pct)','TMI3411(34%,3.5万)\nTMI3252(6%,0.9万)','TMI3113B(54%)\nTMI3286B(47%)','查高毛利品崩塌原因'],
      ['九安智能','369','17%(−5pct)','STI34061(34%,69万)\nTMI6030-18(34%,58万)','TMI3113B(54%)\nTMI6050(43%)','提价+新品替换'],
      ['拓竹/湘凡/添可','48/35/96','0%/5%/0%','TMI3342B(29%,48万)\nTMI2605S(2%,34万)','TMI3342(52%)\nTMI5330(43%)','提价+新品替换'],
      ['可固化','乐动206/一微367/云鲸155','83%/92%/75%','—','—','固化']]),
    ('颜蓉蓉(2,755万)',['客户','采购(万)','高毛利占比(同比)','当前低毛利SKU','→引导到','动作'],
     [['兆驰','1,195','28%(−5pct)','STI3452HFI(−2%,245万)\nTMI3253T(−9%,165万)','TMI3286B(47%)','提价+引导高毛利替代品'],
      ['感臻','239','23%(+13pct)','TMI3252S(18%,98万)\nTMI3253S(18%,75万)','TMI3286B(47%)','提价+新品替换'],
      ['CVTE','354','20%(+20pct)','TMI6263BH(31%,72万)','TMI6263AH(61%)','提价到中位'],
      ['可固化','TCL346/三诺95/亿联83','43%/83%/30%','—','—','固化']]),
    ('袁坤(1,475万)·标杆',['打法','做法','效果','推广'],
     [['主动调结构','每月给重点客户推3个高毛利新品\n+返点与高毛利SKU占比挂钩','康冠+56pct/启盛+99pct\n华曦达+75pct','提炼为全员SOP,不排名次']]),
]

# Insert all tables + titles in reverse order so they appear in correct order
tbls = []
for title,headers,rows in reversed(tables_data):
    # Title paragraph
    tp=OxmlElement('w:p');tpr=OxmlElement('w:pPr');tp.append(tpr)
    tr=OxmlElement('w:r');trpr=OxmlElement('w:rPr');trpr.append(OxmlElement('w:b'));tr.append(trpr)
    t=OxmlElement('w:t');t.text=title;tr.append(t);tp.append(tr)
    tt = mk_table(headers,rows)
    tbls.append(tt)
    tbls.append(tp)

# Insert after h9
prev = h9
for elem in tbls:
    prev.addnext(elem)
    prev = elem

for e in old: body.remove(e)
doc.save(r"C:\Users\45091\Desktop\2026H1销售分析报告_深度版.docx")
print("DONE ch9")
