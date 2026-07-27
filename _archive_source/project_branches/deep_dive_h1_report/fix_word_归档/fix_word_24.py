"""只替换Word报告2.4段:老文本→方案A统一表,不动其他内容"""
from docx import Document
from docx.shared import Pt, RGBColor
from docx.oxml.ns import qn, nsdecls
from docx.oxml import parse_xml, OxmlElement
from copy import deepcopy

DOC_PATH = r"C:\Users\45091\Desktop\2026H1销售分析报告_深度版.docx"
doc = Document(DOC_PATH)

GREEN=RGBColor(0x1f,0x7a,0x45); RED=RGBColor(0xa8,0x23,0x0f)
AMBER=RGBColor(0xb0,0x68,0x08); BLUE=RGBColor(0x14,0x3d,0x63)
GRAY=RGBColor(0x5d,0x6b,0x7a)
AMBER_BG='FBF0DA'; GREEN_BG='E7F3EC'; RED_BG='FBE6E1'; SOFT_BG='EEF2F8'

def set_cell_bg(cell, color):
    shading = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{color}"/>')
    cell._tc.get_or_add_tcPr().append(shading)

def make_p(text, style='Normal', bg=None):
    """创建一个段落元素"""
    p = OxmlElement('w:p')
    # 设样式
    pr = OxmlElement('w:pPr')
    if bg:
        shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{bg}"/>')
        pr.append(shd)
    p.append(pr)
    # 设文字
    r_elem = OxmlElement('w:r')
    rpr = OxmlElement('w:rPr')
    r_elem.append(rpr)
    t = OxmlElement('w:t'); t.text = text
    r_elem.append(t)
    p.append(r_elem)
    return p

# --- 1) 定位2.4标题与下一节标题的元素 ---
body = doc.element.body
h24_elem = None
next_h_elem = None
found_h24 = False
for child in body:
    if not child.tag.endswith('}p'):
        continue
    full = ''.join([t.text or '' for t in child.iter() if t.tag.endswith('}t')])
    if not h24_elem and '2.4' in full and '衰退' in full:
        h24_elem = child
        found_h24 = True
        continue
    if found_h24 and not next_h_elem:
        # 找下一个 Heading: 检查pStyle
        pPr = child.find(qn('w:pPr'))
        if pPr is not None:
            se = pPr.find(qn('w:pStyle'))
            if se is not None:
                v = se.get(qn('w:val'))
                if v and ('Heading' in v or v in ('1','2','3','4')):
                    next_h_elem = child
        # 备选:文本含'新品引擎'等下一节标志
        if not next_h_elem and ('新品引擎' in full or '毛利下降归因' in full or '三、' in full):
            next_h_elem = child

if h24_elem is None:
    print("ERROR: 未找到2.4段落"); exit(1)
print(f"找到2.4元素, 下一节: {next_h_elem is not None}")

# --- 2) 收集h24之后、下一节之前的旧元素 ---
old_elems = []
collect = False
for child in body:
    if child is h24_elem:
        collect = True
        continue
    if collect:
        if next_h_elem and child is next_h_elem:
            break
        old_elems.append(child)
print(f"将删除{len(old_elems)}个旧元素")

# --- 3) 构建新内容 ---
# 3a 描述段落
desc = make_p('对低毛利(毛利率<25%)或毛利同比降>50万的品类,统一判定每个拖累SKU:🔴产品力差→整改/停售/汰换; 🟡单客户→客户级谈判; 🟠量缩→用量挽回。')

# 3b 统一判定表
headers = ['品类','品类毛利','同比毛利','拖累SKU','收入(万)','亏损','客户','判定','动作']
rows = [
    ['DCDC-18V\n降压2~4A','12.73%','−514万','STI3452HFI','1,229','−136万','5/12','🔴产品力差','整改提价/限产'],
    ['','','','TMI3214H','71','−11万','1/1','🟡单客户','客户级谈判'],
    ['','','','STI3452I','51','−5.5万','6/6全负','🔴产品力差','停售'],
    ['单C/A口\n快充协议','−0.09%','−30万','IM2405','69','−9.8万','13/14','🔴产品力差','停售,定位失败'],
    ['','','','IM2406','52','18%','19户0负','🟢产品OK','维持观察'],
    ['H桥BDC\n高压36V','40.59%','−335万','品类整体','4,180','—','—','🟠量缩','用量挽回'],
    ['多节锂保\n成都','38.91%','−9万','SIT8252D','4','−0.1万','1/1','🟡单客户','客户级谈判'],
    ['0品类\n(未归类)','−17%','−9万','TMM8512-Q1等','51','多客户负','—','🔴产品差\n+归类缺失','停售,修正归类'],
]

# 建表XML
tbl = OxmlElement('w:tbl')
# 表属性: Table Grid样式
tblPr = OxmlElement('w:tblPr')
tblW = OxmlElement('w:tblW'); tblW.set(qn('w:w'), '9000'); tblW.set(qn('w:type'), 'dxa')
tblPr.append(tblW)
borders = OxmlElement('w:tblBorders')
for edge in ['top','left','bottom','right','insideH','insideV']:
    b = OxmlElement(f'w:{edge}'); b.set(qn('w:val'),'single'); b.set(qn('w:sz'),'4'); b.set(qn('w:color'),'auto')
    borders.append(b)
tblPr.append(borders)
tbl.append(tblPr)

# 表头行
hdr_row = OxmlElement('w:tr')
for h in headers:
    tc = OxmlElement('w:tc')
    tcPr = OxmlElement('w:tcPr')
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{SOFT_BG}"/>')
    tcPr.append(shd)
    tc.append(tcPr)
    p = OxmlElement('w:p')
    r = OxmlElement('w:r')
    rPr = OxmlElement('w:rPr')
    rPr.append(OxmlElement('w:b'))
    r.append(rPr)
    t = OxmlElement('w:t'); t.text = h
    r.append(t); p.append(r); tc.append(p)
    hdr_row.append(tc)
tbl.append(hdr_row)

# 数据行
hi_rows = {0,2,3,7}
for ri, rd in enumerate(rows):
    tr = OxmlElement('w:tr')
    for ci, val in enumerate(rd):
        tc = OxmlElement('w:tc')
        tcPr = OxmlElement('w:tcPr')
        if ri in hi_rows:
            shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{RED_BG}"/>')
            tcPr.append(shd)
        tc.append(tcPr)
        p = OxmlElement('w:p')
        r = OxmlElement('w:r')
        t = OxmlElement('w:t'); t.text = val
        r.append(t); p.append(r); tc.append(p)
        tr.append(tc)
    tbl.append(tr)

# 3c 结论callout
callout = make_p('归因结论:拖累分三类 — 🔴产品力差(多客户负毛利)→整改/停售/汰换; 🟡单客户(仅1户低价)→客户级谈判; 🟠量缩(毛利正常但量跌)→用量挽回。这区别决定了动作不能用同一把锤子。', bg=GREEN_BG)

# --- 4) 插入新内容在h24之后 ---
# 按旧→新顺序插入: desc, tbl, callout (每个用addnext插入到前一个之后)
h24_elem.addnext(callout)
h24_elem.addnext(tbl)
h24_elem.addnext(desc)
print("新内容已插入")

# --- 5) 删除旧内容 ---
for elem in old_elems:
    body.remove(elem)
print(f"旧内容已删除")

doc.save(DOC_PATH)
print("DONE: 2.4段已替换为统一判定表,其余内容未动")
