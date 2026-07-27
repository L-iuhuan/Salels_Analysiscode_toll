"""Word: 8.4中兴康讯→四维度深度模块"""
from docx import Document
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

doc=Document(r"C:\Users\45091\Desktop\2026H1销售分析报告_深度版.docx")
body=doc.element.body
SOFT_BG='EEF2F8';GREEN_BG='E7F3EC';RED_BG='FBE6E1';AMBER_BG='FBF0DA'

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
def make_p(text,bg=None):
    p=OxmlElement('w:p');pr=OxmlElement('w:pPr')
    if bg:
        shd=OxmlElement('w:shd');shd.set(qn('w:val'),'clear');shd.set(qn('w:color'),'auto');shd.set(qn('w:fill'),bg)
        pr.append(shd)
    p.append(pr);r=OxmlElement('w:r');rPr=OxmlElement('w:rPr');r.append(rPr)
    t=OxmlElement('w:t');t.text=text;r.append(t);p.append(r)
    return p

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
    for ri,rd in enumerate(rows):
        tr=OxmlElement('w:tr')
        for v in rd: tr.append(cell(v,bg=GREEN_BG if ri==len(rows)-1 else None))
        tbl.append(tr)
    return tbl

# Find 中兴康讯 section in 8.4
target=None;nxt=None;found=False
for child in body:
    if not child.tag.endswith('}p'): continue
    full=''.join([t.text or '' for t in child.iter() if t.tag.endswith('}t')])
    if not target and '中兴康讯' in full and ('下跌' in full or '价格型' in full or '贺淼淼' in full):
        target=child;found=True;continue
    if found and not nxt:
        if ('共进' in full and ('下跌' in full or '价格型' in full or '周小力' in full)):
            nxt=child
        if not nxt and ('本章结论' in full or '大客户板块' in full):
            nxt=child
            break

if not target:
    print("ERROR: 未找到中兴康讯"); exit(1)
print(f"Found, next: {nxt is not None}")

# Collect old
old=[];c=False
for child in body:
    if child is target: c=True; old.append(child); continue
    if c:
        if nxt and child is nxt: break
        old.append(child)
print(f"Remove {len(old)} elems")

# Build 4-dimension content
elems=[]

# D1: 5半年度走势
elems.append(make_p('【维度1】5半年度收入/利润/毛利率走势'))
d1h=['指标','2024H1','2024H2','2025H1','2025H2','2026H1']
d1r=[
    ['收入(万)','1,834.6','843.7','1,073.1','889.3','1,390.3'],
    ['利润(万)','189.5','144.3','167.8','152.3','−4.1'],
    ['毛利率','10.33%','17.11%','15.64%','17.12%','−0.29%'],
    ['SKU数','19','17','17','19','28'],
    ['品类数','9','6','6','9','11'],
    ['新品SKU','2','1','1','3','7'],
    ['毛利率 vs 整体差','−22.6pct','−19.1pct','−21.2pct','−18.6pct','−34.7pct(恶化!)'],
]
elems.append(mk_table(d1h,d1r))
elems.append(make_p('中兴康讯5期毛利率长期低于整体19-35pct,26H1转负(−0.29%),低毛利维持不仅没有改善反而在加速恶化。SKU数从19扩到28,但新增SKU(7个26H1新品)合计仅80万收入,不足以扭转。'))

# D2: 品类结构演变
elems.append(make_p('【维度2】品类结构:84%压在DCDC-18V上,该品类毛利率从4.2%→−6.3%持续恶化'))
d2h=['品类','24H1','24H2','25H1','25H2','26H1','5期合计','毛利率趋势']
d2r=[
    ['DCDC-18V-降压2~4A','1,491','654','860','737','1,171(占84%)','4,914','4.2%→10.6%→10.6%→12.3%→−6.3%'],
    ['LDO通用/双通道','217','145','161','80','53','656','37%→41%→37%→43%→31%(仍正)'],
    ['DCDC-18V-降压5~12A','52','22','28','36','65','203','36%→35%→33%→32%→24%(下滑)'],
    ['PSE(新品)','0','0','0','1','73','75','新品导入,26H1毛利率35.7%'],
]
elems.append(mk_table(d2h,d2r))

# D3: SKU级产品系列迭代
elems.append(make_p('【维度3】产品系列迭代:STI345(负毛利)放量 vs TMI325/760(正毛利)跟进'))
d3h=['系列','25H1收入','26H1收入','变化','代表SKU','26H1毛利率','判断']
d3r=[
    ['STI345系列','679万','886万','+207万(+30%)','STI3452HFI/STI3453/STI3454I','−6.3%','老品负毛利放量,越卖越亏'],
    ['TMI325系列','208万','340万','+132万(+63%)','TMI3253SHF(35.7%,+160%)\nTMI3253SZ(12.9%,+83万)','多数正毛利','正毛利新品增长,迭代方向'],
    ['TMI760/新品','0万','73万','+73万(全新)','TMI7604R(PSE,35.7%)','35.7%','全新高毛利导入'],
    ['TMI605系列','161万','53万','−108万(−67%)','TMI6050(LDO)','31%','高毛利老品被砍,需恢复'],
]
elems.append(mk_table(d3h,d3r))
elems.append(make_p('迭代态势:STI345系列(老品,负毛利)还在放量+207万;TMI325系列(新品,正毛利)增速更快+132万;TMI760(PSE)全新导入73万。方向是把STI345的份额加速切到TMI325/760。'))

# D4: 效果评估+战略建议
elems.append(make_p('【维度4】低毛利维持效果评估:5个半年度,毛利率差从未收窄'))
d4h=['指标','结论']
d4r=[
    ['低毛利维持效果','5个半年度毛利率始终低于整体19-35pct,从未接近。26H1甚至转负(−0.29%),证明低毛利策略未换来客户增长或结构改善'],
    ['产品结构','SKU从19→28扩了9个,品类从9→11扩了2个,但DCDC-18V占比从81%升到84%(更集中),而非分散到高毛利品类'],
    ['新品导入量','26H1导入7个新品(历史最高),但合计仅80万收入(占5.8%),新品量远不足以扭转老品负毛利拖累'],
    ['战略建议(不再维持)','①STI3452HFI提价/限产(从−23%往正拉,核心动作);②导入TMI7604R(PSE)+TMI3253SHF替换STI3453;③恢复TMI6050(LDO,毛利31%)用量;④不再以低价维持该客户——5期证明低毛利维持无效,转为"利润导向"'],
]
elems.append(mk_table(d4h,d4r,width='9500'))

# Insert in reverse
for elem in reversed(elems):
    target.addnext(elem)

for e in old: body.remove(e)
doc.save(r"C:\Users\45091\Desktop\2026H1销售分析报告_深度版.docx")
print("DONE 中兴康讯")
