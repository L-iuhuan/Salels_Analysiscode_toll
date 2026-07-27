"""只替换Word报告里的毛利桥勾稽链文字→勾稽表,不动其他内容"""
from docx import Document
from docx.shared import Pt, RGBColor
from docx.oxml.ns import qn, nsdecls
from docx.oxml import parse_xml, OxmlElement

DOC_PATH = r"C:\Users\45091\Desktop\2026H1销售分析报告_深度版.docx"
doc = Document(DOC_PATH)

BLUE=RGBColor(0x14,0x3d,0x63)
GREEN=RGBColor(0x1f,0x7a,0x45); RED=RGBColor(0xa8,0x23,0x0f)
GRAY=RGBColor(0x5d,0x6b,0x7a)
SOFT_BG='EEF2F8'; GREEN_BG='E7F3EC'; AMBER_BG='FBF0DA'

def set_cell_bg(cell, color):
    shading = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{color}"/>')
    cell._tc.get_or_add_tcPr().append(shading)

def make_p(text, bg=None):
    p = OxmlElement('w:p')
    pr = OxmlElement('w:pPr')
    if bg:
        shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{bg}"/>')
        pr.append(shd)
    p.append(pr)
    r_elem = OxmlElement('w:r')
    r_elem.append(OxmlElement('w:rPr'))
    t = OxmlElement('w:t'); t.text = text
    r_elem.append(t); p.append(r_elem)
    return p

# --- 1) 定位勾稽链段落 ---
body = doc.element.body
target_elem = None
next_h_elem = None
found_target = False

for child in body:
    if not child.tag.endswith('}p'):
        continue
    full = ''.join([t.text or '' for t in child.iter() if t.tag.endswith('}t')])
    # 找包含"三项正效应"和"交互残差"的段落
    if not target_elem and '三项正效应' in full and '交互残差' in full:
        target_elem = child
        found_target = True
        continue
    if found_target and not next_h_elem:
        pPr = child.find(qn('w:pPr'))
        if pPr is not None:
            se = pPr.find(qn('w:pStyle'))
            if se is not None:
                v = se.get(qn('w:val'))
                if v and ('Heading' in v or v in ('1','2','3','4')):
                    next_h_elem = child
        if not next_h_elem and ('交互残差是什么' in full or '关于' in full):
            next_h_elem = child

if target_elem is None:
    # 备选:找包含"四效应合计"的段落
    for child in body:
        if not child.tag.endswith('}p'): continue
        full = ''.join([t.text or '' for t in child.iter() if t.tag.endswith('}t')])
        if '四效应合计' in full and '5,327' in full:
            target_elem = child
            found_target = True
            continue
        if found_target and not next_h_elem:
            pPr = child.find(qn('w:pPr'))
            if pPr is not None:
                se = pPr.find(qn('w:pStyle'))
                if se is not None:
                    v = se.get(qn('w:val'))
                    if v and ('Heading' in v or v in ('1','2','3','4')):
                        next_h_elem = child
            if not next_h_elem and ('交互残差' in full or '关于' in full):
                next_h_elem = child

if target_elem is None:
    print("ERROR: 未找到勾稽链段落"); exit(1)
print(f"找到目标元素, 下一节: {next_h_elem is not None}")

# --- 2) 收集旧元素 ---
old_elems = []
collect = False
for child in body:
    if child is target_elem:
        collect = True
        old_elems.append(child)
        continue
    if collect:
        if next_h_elem and child is next_h_elem:
            break
        old_elems.append(child)
print(f"将删除{len(old_elems)}个旧元素")

# --- 3) 构建勾稽表 ---
headers = ['','说明','金额(万)']
rows = [
    ['三项正效应','量+5,342 + 成本+1,371 + 结构+225','+6,938'],
    ['＋ 价效应','降价流失','−1,611'],
    ['＝ 四效应合计','可比SKU上的加法分解','+5,327'],
    ['－ 交互残差','量/价/成本同变交叉项,变化大则残差大','−2,867'],
    ['＝ 可比SKU利润变化','518个两期都有SKU的实际利润变化','+2,460'],
    ['＋ 非可比SKU贡献','新品导入 − 退市SKU(不在可比集)','+564'],
    ['＝ 整体利润变化','真正的同比利润净增(11,809→14,833)','+3,024'],
]

tbl = OxmlElement('w:tbl')
tblPr = OxmlElement('w:tblPr')
tblW = OxmlElement('w:tblW'); tblW.set(qn('w:w'), '8000'); tblW.set(qn('w:type'), 'dxa')
tblPr.append(tblW)
borders = OxmlElement('w:tblBorders')
for edge in ['top','left','bottom','right','insideH','insideV']:
    b = OxmlElement(f'w:{edge}'); b.set(qn('w:val'),'single'); b.set(qn('w:sz'),'4'); b.set(qn('w:color'),'auto')
    borders.append(b)
tblPr.append(borders)
tbl.append(tblPr)

# Header
hdr_row = OxmlElement('w:tr')
for h in headers:
    tc = OxmlElement('w:tc')
    tcPr = OxmlElement('w:tcPr')
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{SOFT_BG}"/>')
    tcPr.append(shd)
    tc.append(tcPr)
    p = OxmlElement('w:p')
    r = OxmlElement('w:r')
    rPr = OxmlElement('w:rPr'); rPr.append(OxmlElement('w:b'))
    r.append(rPr)
    t = OxmlElement('w:t'); t.text = h
    r.append(t); p.append(r); tc.append(p)
    hdr_row.append(tc)
tbl.append(hdr_row)

# Rows: highlight step 7 (overall) and step 3 (four-effect total)
highlight = {2, 6}  # 0-indexed: row 3 and row 7
for ri, rd in enumerate(rows):
    tr = OxmlElement('w:tr')
    for ci, val in enumerate(rd):
        tc = OxmlElement('w:tc')
        tcPr = OxmlElement('w:tcPr')
        if ri in highlight:
            shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{GREEN_BG}"/>')
            tcPr.append(shd)
        tc.append(tcPr)
        p = OxmlElement('w:p')
        r = OxmlElement('w:r')
        t = OxmlElement('w:t'); t.text = val
        r.append(t); p.append(r); tc.append(p)
        tr.append(tc)
    tbl.append(tr)

# 说明callout
note = make_p('交互残差是什么:毛利桥用加法分解,但量/价/成本同时变会产生交叉项(量变×价变的部分),既不算纯量效应也不算纯价效应,加起来就是交互残差。它不是算错,变化越剧烈残差越大。非可比SKU贡献才是不在可比集的新品/退市部分。', bg=GREEN_BG)

# --- 4) 插入新内容 ---
target_elem.addnext(note)
target_elem.addnext(tbl)
print("新内容已插入")

# --- 5) 删除旧内容 ---
for elem in old_elems:
    body.remove(elem)
print("旧内容已删除")

doc.save(DOC_PATH)
print("DONE: 勾稽链已替换为勾稽表,其余内容未动")
