# -*- coding: utf-8 -*-
"""Build full 18-page PPT (v3) - restructured per critique, July data, softer tone, new analyses."""
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
from pptx import Presentation
from pptx.util import Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from PIL import Image as PILImage

SLIDE_W = Emu(14400213)
SLIDE_H = Emu(8099425)
SCALE = 1.181

def emu(v):
    return Emu(int(v * SCALE * 12700))

PRIMARY = RGBColor(0x00, 0x43, 0x7C)
ACCENT = RGBColor(0xF1, 0x81, 0x01)
POSITIVE = RGBColor(0x8F, 0xC3, 0x1F)
CYAN = RGBColor(0x00, 0xA0, 0xE9)
TEAL = RGBColor(0x01, 0xAD, 0xA1)
TEXT = RGBColor(0x26, 0x26, 0x26)
TEXT_GRAY = RGBColor(0x59, 0x59, 0x59)
TEXT_LIGHT = RGBColor(0x8C, 0x8C, 0x8C)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
BG_CARD = RGBColor(0xF7, 0xF9, 0xFB)
BG_LIGHT = RGBColor(0xF2, 0xF5, 0xF9)
BORDER_CLR = RGBColor(0xE3, 0xE8, 0xEF)
WARNING_BG = RGBColor(0xFD, 0xF3, 0xE7)
WARNING_ORANGE = RGBColor(0xF3, 0x98, 0x00)
RED_DARK = RGBColor(0xC5, 0x28, 0x28)

FONT = "HarmonyOS Sans SC"
MEDIA = r'E:\3-其他资料\工作文件\ppt_project\media'
CHARTS = r'E:\3-其他资料\工作文件\ppt_project\charts'
DECK = r'E:\3-其他资料\工作文件\ppt_project\deck.pptx'

prs = Presentation()
prs.slide_width = SLIDE_W
prs.slide_height = SLIDE_H
blank = prs.slide_layouts[6]


def add_text(slide, x, y, w, h, text, size=14, color=TEXT, bold=False,
             align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, font=FONT, line_spacing=1.0):
    box = slide.shapes.add_textbox(emu(x), emu(y), emu(w), emu(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = 0
    tf.margin_right = 0
    tf.margin_top = 0
    tf.margin_bottom = 0
    p = tf.paragraphs[0]
    p.text = text
    p.font.size = Pt(size)
    p.font.color.rgb = color
    p.font.bold = bold
    p.font.name = font
    p.alignment = align
    p.space_before = Pt(0)
    p.space_after = Pt(0)
    if line_spacing != 1.0:
        p.line_spacing = Pt(size * line_spacing)
    return box


def add_paras(slide, x, y, w, h, paras, size=12, font=FONT, anchor=MSO_ANCHOR.TOP, line_spacing=1.4):
    box = slide.shapes.add_textbox(emu(x), emu(y), emu(w), emu(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = 0
    tf.margin_right = 0
    tf.margin_top = 0
    tf.margin_bottom = 0
    for pi, runs in enumerate(paras):
        p = tf.paragraphs[0] if pi == 0 else tf.add_paragraph()
        p.space_before = Pt(0)
        p.space_after = Pt(4)
        p.line_spacing = Pt(size * line_spacing)
        for text, color, bold in runs:
            r = p.add_run()
            r.text = text
            r.font.size = Pt(size)
            r.font.color.rgb = color
            r.font.bold = bold
            r.font.name = font
    return box


def add_rect(slide, x, y, w, h, fill=None, border=None, border_w=1):
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, emu(x), emu(y), emu(w), emu(h))
    if fill:
        shape.fill.solid()
        shape.fill.fore_color.rgb = fill
    else:
        shape.fill.background()
    if border:
        shape.line.color.rgb = border
        shape.line.width = Pt(border_w)
    else:
        shape.line.fill.background()
    shape.shadow.inherit = False
    return shape


def add_round_rect(slide, x, y, w, h, fill=None, border=None, border_w=1, radius=0.08):
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, emu(x), emu(y), emu(w), emu(h))
    shape.adjustments[0] = radius
    if fill:
        shape.fill.solid()
        shape.fill.fore_color.rgb = fill
    else:
        shape.fill.background()
    if border:
        shape.line.color.rgb = border
        shape.line.width = Pt(border_w)
    else:
        shape.line.fill.background()
    shape.shadow.inherit = False
    return shape


def add_ellipse(slide, x, y, w, h, fill=None):
    shape = slide.shapes.add_shape(MSO_SHAPE.OVAL, emu(x), emu(y), emu(w), emu(h))
    if fill:
        shape.fill.solid()
        shape.fill.fore_color.rgb = fill
    else:
        shape.fill.background()
    shape.line.fill.background()
    shape.shadow.inherit = False
    return shape


def add_bg(slide, bg_name):
    slide.shapes.add_picture(os.path.join(MEDIA, bg_name), 0, 0, prs.slide_width, prs.slide_height)


def add_image_fit(slide, img_path, x, y, max_w, max_h):
    img = PILImage.open(img_path)
    ratio = img.size[0] / img.size[1]
    if max_w / max_h > ratio:
        h = max_h
        w = h * ratio
    else:
        w = max_w
        h = w / ratio
    x_c = x + (max_w - w) / 2
    y_c = y + (max_h - h) / 2
    slide.shapes.add_picture(img_path, emu(x_c), emu(y_c), emu(w), emu(h))


def page_title(slide, title, subtitle=None):
    add_rect(slide, 42, 62, 8, 24, fill=PRIMARY)
    add_text(slide, 62, 56, 820, 36, title, size=23, color=TEXT, bold=True, anchor=MSO_ANCHOR.MIDDLE)
    if subtitle:
        add_text(slide, 62, 92, 820, 22, subtitle, size=13, color=TEXT_LIGHT, anchor=MSO_ANCHOR.MIDDLE)


def takeaway_bar(slide, text_runs, y=492, style='light'):
    if style == 'warning':
        add_round_rect(slide, 42, y, 876, 34, fill=WARNING_BG, radius=0.16)
        add_rect(slide, 42, y, 4, 34, fill=ACCENT)
    else:
        add_round_rect(slide, 42, y, 876, 34, fill=BG_LIGHT, radius=0.16)
        add_rect(slide, 42, y, 4, 34, fill=PRIMARY)
    box = slide.shapes.add_textbox(emu(60), emu(y), emu(845), emu(34))
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    tf.margin_left = 0
    p = tf.paragraphs[0]
    p.space_before = Pt(0)
    p.space_after = Pt(0)
    for text, color, bold in text_runs:
        r = p.add_run()
        r.text = text
        r.font.size = Pt(11.5)
        r.font.color.rgb = color
        r.font.bold = bold
        r.font.name = FONT


def section_label(slide, x, y, text, color=TEXT_GRAY):
    add_text(slide, x, y, 460, 20, text, size=12.5, color=color, bold=True)


def add_table(slide, x, y, w, h, headers, rows, col_widths=None, header_fill=PRIMARY,
              row_fills=None, cell_colors=None, font_size=10, header_size=10.5, first_col_bold=False):
    """Add a styled table. cell_colors: dict {(r,c): RGBColor} for cell text color."""
    n_rows = len(rows) + 1
    n_cols = len(headers)
    tbl_shape = slide.shapes.add_table(n_rows, n_cols, emu(x), emu(y), emu(w), emu(h))
    table = tbl_shape.table
    if col_widths:
        total = sum(col_widths)
        for ci, cw in enumerate(col_widths):
            table.columns[ci].width = Emu(int(emu(w) * cw / total))
    # header
    for ci, h in enumerate(headers):
        cell = table.cell(0, ci)
        cell.text = h
        p = cell.text_frame.paragraphs[0]
        p.font.size = Pt(header_size)
        p.font.bold = True
        p.font.name = FONT
        p.font.color.rgb = WHITE
        p.alignment = PP_ALIGN.CENTER
        cell.fill.solid()
        cell.fill.fore_color.rgb = header_fill
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        cell.margin_top = Pt(2)
        cell.margin_bottom = Pt(2)
    # body
    for ri, row in enumerate(rows):
        for ci, v in enumerate(row):
            cell = table.cell(ri + 1, ci)
            cell.text = str(v)
            p = cell.text_frame.paragraphs[0]
            p.font.size = Pt(font_size)
            p.font.name = FONT
            p.font.bold = first_col_bold and ci == 0
            p.alignment = PP_ALIGN.CENTER if ci != 1 else PP_ALIGN.LEFT
            color = TEXT
            if cell_colors and (ri, ci) in cell_colors:
                color = cell_colors[(ri, ci)]
            p.font.color.rgb = color
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.margin_top = Pt(1)
            cell.margin_bottom = Pt(1)
            if row_fills and ri in row_fills:
                cell.fill.solid()
                cell.fill.fore_color.rgb = row_fills[ri]
            else:
                cell.fill.solid()
                cell.fill.fore_color.rgb = WHITE if ri % 2 == 0 else BG_LIGHT
    return table


# ==================== P1: COVER ====================
print('P1...')
s = prs.slides.add_slide(blank)
add_bg(s, 'bg_cover.png')
add_text(s, 55, 250, 520, 40, "拓尔微电子股份有限公司", size=22, color=WHITE)
add_text(s, 55, 300, 720, 60, "2026年7月经营分析汇报", size=40, color=WHITE, bold=True)
add_rect(s, 55, 378, 70, 3, fill=CYAN)
add_text(s, 55, 398, 640, 26, "主讲：总经理｜汇报对象：销售负责人及业务员｜2026年8月",
         size=13, color=RGBColor(0xD0, 0xD8, 0xE4))
add_text(s, 55, 495, 400, 22, "www.toll-semi.com", size=11, color=TEXT_GRAY)


# ==================== P2: 一页看懂本月 ====================
print('P2...')
s = prs.slides.add_slide(blank)
add_bg(s, 'bg_content.png')
page_title(s, "一页看懂本月", "2026年7月 · 增收不增利——三个数字需要全员记住")

cards = [
    (42, "收入（万元）", "7,760", PRIMARY, "同比 +40.9%｜环比 +5.3%", POSITIVE),
    (342, "毛利率", "30.25%", ACCENT, "同比 -5.14pct｜环比 -2.38pct", ACCENT),
    (642, "销量（亿颗）", "4.95", PRIMARY, "同比 +61%｜环比 +14.8%", POSITIVE),
]
for cx, label, number, num_color, change, chg_color in cards:
    add_round_rect(s, cx, 128, 276, 118, fill=BG_CARD, border=BORDER_CLR, radius=0.07)
    add_text(s, cx + 18, 140, 150, 20, label, size=12.5, color=TEXT_LIGHT)
    add_text(s, cx + 18, 160, 240, 50, number, size=40, color=num_color, bold=True)
    add_text(s, cx + 18, 216, 240, 20, change, size=11, color=chg_color, bold=True)

section_label(s, 42, 258, "1-7月毛利率走势（%）：4月后连续下行")
add_image_fit(s, os.path.join(CHARTS, 'p2_margin_sparkline.png'), 42, 280, 876, 108)

add_paras(s, 42, 396, 876, 90, [
    [("收入7,760万元，同比多增2,254万；", PRIMARY, True),
     ("同期增量利润约399万，", TEXT, False),
     ("增量转化率不足两成", ACCENT, True),
     ("——收入的“量”未能转化为利润的“质”。", TEXT, False)],
    [("1-7月累计收入5.08亿（+35.2%）、利润1.71亿（同比+3,354万）；", TEXT, False),
     ("销量同比+61%的同时，累计毛利率由36.59%降至33.66%。自2月以来，收入与毛利率的背离已持续6个月。", TEXT, False)],
], size=11.5)

takeaway_bar(s, [("定调：", PRIMARY, True),
                 ("本月为典型“增收不增利”——收入增长未转化为利润。后续从归因、客户与结构、到对策逐层展开。", TEXT, False)])


# ==================== P3: H1整改复盘 ====================
print('P3...')
s = prs.slides.add_slide(blank)
add_bg(s, 'bg_content.png')
page_title(s, "回头看：H1整改5项，落地1项", "对照H1报告整改项逐条核查的客观结果")

chips = [(42, "3", "项恶化", ACCENT), (200, "1", "项未落地", WARNING_ORANGE), (358, "1", "项落地", POSITIVE)]
for cx, num, label, clr in chips:
    add_round_rect(s, cx, 122, 140, 40, fill=BG_CARD, border=BORDER_CLR, radius=0.12)
    add_paras(s, cx, 122, 140, 40, [[(num + " ", clr, True), (label, TEXT_GRAY, False)]], size=15, anchor=MSO_ANCHOR.MIDDLE)
    s.shapes[-1].text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
add_text(s, 560, 122, 358, 40, "H1报告整改项逐条核查结果", size=11.5, color=TEXT_LIGHT, align=PP_ALIGN.RIGHT, anchor=MSO_ANCHOR.MIDDLE)

items = [
    ("1", "DCDC-18V 2-4A 限价/提价、拔烂果", "恶化", ACCENT, "品类毛利从12.9%跌至2.8%，7月单月少赚230万"),
    ("2", "停售负毛利型号（STI3452HFI等）", "未落地", WARNING_ORANGE, "H1半年亏136万，7月仍在售、持续亏损"),
    ("3", "挽回追觅/小米等量缩大客户", "恶化", ACCENT, "追觅H1月均1,966万→7月仅14万；小米-191万"),
    ("4", "中兴康讯/共进采购结构转向", "恶化", ACCENT, "中兴康讯7月客户毛利-11.7%，结构进一步恶化"),
    ("5", "新品立项绑定高毛利品类", "落地", POSITIVE, "新品占比12.2%→15.7%，毛利39.1%→37.5%（唯一落地项）"),
]
for i, (num, title, status, st_color, detail) in enumerate(items):
    y = 172 + i * 56
    add_ellipse(s, 42, y + 8, 26, 26, fill=st_color)
    add_text(s, 42, y + 8, 26, 26, num, size=13, color=WHITE, bold=True, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    add_text(s, 80, y, 350, 24, title, size=13, color=TEXT, bold=True, anchor=MSO_ANCHOR.MIDDLE)
    add_text(s, 80, y + 26, 350, 20, status, size=10.5, color=st_color, bold=True)
    add_text(s, 440, y + 4, 478, 44, detail, size=11.5, color=TEXT_GRAY, anchor=MSO_ANCHOR.MIDDLE, line_spacing=1.3)

takeaway_bar(s, [("建议：", PRIMARY, True),
                 ("本月对H1整改未落地项启动专项复盘，明确根因（KPI挂钩、限量决策、产品资源）与改进动作（待决策）。", TEXT, False)],
             style='warning')


# ==================== P4: 毛利桥与结构效应 ====================
print('P4...')
s = prs.slides.add_slide(blank)
add_bg(s, 'bg_content.png')
page_title(s, "毛利桥：四个效应拆解与结构时间轴", "同比可比毛利率36.69%→29.70%（-6.99pct）；环比成本、结构双双转负")

section_label(s, 42, 120, "毛利桥：量/价/成本/结构四效应（同比 vs 环比）")
add_image_fit(s, os.path.join(CHARTS, 'p5_waterfall.png'), 42, 142, 435, 250)
section_label(s, 500, 120, "结构效应月度时间轴（与毛利率叠加）")
add_image_fit(s, os.path.join(CHARTS, 'p8_structure_timeline.png'), 500, 142, 418, 250)

add_paras(s, 42, 400, 876, 82, [
    [("可比口径（同型号同客户，覆盖91%收入）", PRIMARY, True),
     ("剔除新品与流失客户干扰，反映存量业务真实变化。同比量效应+917万是唯一利润来源，价效应-266万对应ASP下行，结构效应-79万反映低毛利品类占比上升。", TEXT, False)],
    [("环比新增两项拖累：", PRIMARY, True),
     ("成本效应-66万（晶圆、封测涨价开始向出货成本传导）+ 结构效应-45万", ACCENT, True),
     ("。结构效应自4月拐点后连续为负，与毛利率下行完全同步——这是7月急跌的主要构成。", TEXT, False)],
], size=11)

takeaway_bar(s, [("一句话：", PRIMARY, True),
                 ("放量赚的钱被降价和成本上涨吃掉大半；结构效应连续为负说明高毛利品类在卖少——销售结构问题浮出水面。", TEXT, False)])


# ==================== P5: 三级下钻 ====================
print('P5...')
s = prs.slides.add_slide(blank)
add_bg(s, 'bg_content.png')
page_title(s, "拖累在哪：三级下钻定位", "拖累高度集中于通用电源管理一条线，并非全线溃败")

section_label(s, 42, 122, "三级下钻：产品线 → 品类 → 单品")
add_image_fit(s, os.path.join(CHARTS, 'p6_drilldown.png'), 42, 144, 430, 240)
section_label(s, 500, 122, "四条产品线毛利率：今年7月 vs 去年同期")
add_image_fit(s, os.path.join(CHARTS, 'p6_product_margin.png'), 500, 144, 418, 240)

add_paras(s, 42, 392, 876, 92, [
    [("按产品线→品类→单品逐层拆解：", PRIMARY, True),
     ("通用电源管理收入4,876万（占62.8%），毛利率同比-8.2pct；其中DCDC-18V-降压2~4A品类7月毛利率仅2.8%（H1为12.9%），单月减利约230万；该品类的主要拖累来自单品STI3452HFI。", TEXT, False)],
    [("四条产品线分化明显：", PRIMARY, True),
     ("通用电源管理-8.2pct、POE -17.3pct，有刷直流持平，充电控制+5.9pct——", TEXT, False),
     ("拖累高度集中，其余产品线毛利率整体稳定。", ACCENT, True)],
], size=11.5)

takeaway_bar(s, [("呼应整改：", PRIMARY, True),
                 ("STI3452HFI上半年就在整改名单（“停售负毛利型号”项），未停掉、7月仍在售——整改未落地，问题才累积到现在。", TEXT, False)])


# ==================== P6: STI3452HFI 专案（压缩版） ====================
print('P6...')
s = prs.slides.add_slide(blank)
add_bg(s, 'bg_content.png')
page_title(s, "STI3452HFI 专案：一颗料的三重问题", "负毛利 + 以价换量 + 成本上升17.3%——7月收入373万、侵蚀利润48万")

section_label(s, 42, 122, "品类成本效应分布（7月，万元）——成本压力非该型号独有")
add_image_fit(s, os.path.join(CHARTS, 'p7_cost_effect.png'), 42, 144, 500, 250)

# Right side: redesigned fuller panel（三重问题 + 成本归因迷你图 + 处置方向）
add_round_rect(s, 570, 144, 348, 250, fill=BG_CARD, border=BORDER_CLR, radius=0.05)
add_text(s, 590, 156, 310, 22, "三重问题与成本归因", size=13.5, color=PRIMARY, bold=True)
add_paras(s, 590, 186, 310, 84, [
    [("① 负毛利　", ACCENT, True), ("7月-26.4%，单月亏98万", TEXT, False)],
    [("② 以价换量　", ACCENT, True), ("均价0.10元，同比-11.4%", TEXT, False)],
    [("③ 成本上升　", ACCENT, True), ("单位成本+17.3%", TEXT, False)],
], size=11, line_spacing=1.4)
add_text(s, 590, 274, 310, 18, "成本上涨归因（占涨幅比重）", size=10.5, color=TEXT_GRAY, bold=True)
add_image_fit(s, os.path.join(CHARTS, 'p6_cost_mini.png'), 590, 294, 310, 46)
add_rect(s, 590, 350, 310, 1, fill=BORDER_CLR)
add_paras(s, 590, 358, 310, 30, [
    [("处置方向：", PRIMARY, True), ("建议明确停售或提价，作为整改复盘首个落地议题（待决策）", TEXT, False)],
], size=10.5, line_spacing=1.3)

takeaway_bar(s, [("说明：", PRIMARY, True),
                 ("成本归因（晶圆/封测涨价）涉及供应链谈判，本页仅作示例性呈现；详细成本拆解供产品与采购条线专项参考。", TEXT, False)])


# ==================== P7: 客户分群 ====================
print('P7...')
s = prs.slides.add_slide(blank)
add_bg(s, 'bg_content.png')
page_title(s, "客户分群：增量93%来自中小客户", "KA/AA/KM三大客群合计利润仅+236万，毛利率各降5pct以上")
section_label(s, 42, 122, "四客群1-7月收入与毛利率")
add_image_fit(s, os.path.join(CHARTS, 'p9_customers.png'), 42, 144, 430, 240)
section_label(s, 500, 122, "利润拖累与增长客户（万）")
add_image_fit(s, os.path.join(CHARTS, 'p9_diverging.png'), 500, 144, 418, 240)
add_paras(s, 42, 392, 876, 92, [
    [("利润增量3,354万中，", PRIMARY, True),
     ("MM中小客户贡献3,118万（占93%）", POSITIVE, True),
     ("；KA/AA/KM三大客群合计仅+236万，且毛利率各降5pct以上。", TEXT, False)],
    [("拖累端集中于大客户：", PRIMARY, True),
     ("追觅-453万、中兴康讯-233万、小米-191万；增长端以海康（+312万）、石头（+240万）为代表，均由高毛利新品驱动。", TEXT, False)],
], size=11.5)
takeaway_bar(s, [("错配提示：", PRIMARY, True),
                 ("资源投入最重的KA/AA客群回报相对偏低，建议逐户分析毛利率下滑原因并制定结构调整方案。", TEXT, False)])


# ==================== P8: 客户品类组合分析（升级） ====================
print('P8...')
s = prs.slides.add_slide(blank)
add_bg(s, 'bg_content.png')
page_title(s, "客户品类组合：DCDC-18V系列集中度决定毛利水平", "DCDC-18V系列（以降压2~4A为主力子品类）采购集中度与客户毛利率呈负相关")
section_label(s, 42, 122, "DCDC-18V采购集中度 vs 客户毛利率（气泡=收入）")
add_image_fit(s, os.path.join(CHARTS, 'p8_portfolio.png'), 42, 144, 470, 250)

# Right: compact concentration table
add_text(s, 540, 122, 380, 20, "主导品类集中度与客户毛利率（1-7月）", size=12.5, color=TEXT_GRAY, bold=True)
conc_rows = [
    ("中兴康讯", "DCDC-18V 88.9%", "-3.0%"),
    ("共进", "DCDC-18V 78.3%", "14.8%"),
    ("兆驰", "DCDC-18V 66.8%", "18.9%"),
    ("微浦", "DCDC-18V 60.3%", "17.9%"),
    ("创维数字", "DCDC-18V 33.2%", "34.8%"),
    ("海康威视", "DCDC-18V 22.7%", "35.1%"),
    ("CVTE", "DCDC-18V 22.9%", "26.8%"),
]
cell_colors = {}
for ri, r in enumerate(conc_rows):
    margin_val = float(r[2].replace('%', ''))
    if margin_val < 0:
        cell_colors[(ri, 2)] = RED_DARK
    elif margin_val >= 30:
        cell_colors[(ri, 2)] = POSITIVE
    else:
        cell_colors[(ri, 2)] = TEXT
add_table(s, 540, 146, 378, 240, ["客户", "主导品类集中度", "毛利率"], conc_rows,
          col_widths=[3, 4, 2], cell_colors=cell_colors, font_size=10, first_col_bold=True)

add_paras(s, 42, 402, 876, 82, [
    [("集中度与毛利率呈明显负相关：", PRIMARY, True),
     ("中兴康讯DCDC-18V系列集中度88.9%对应客户毛利-3.0%，共进78.3%对应14.8%；而海康威视、CVTE同样采购DCDC-18V，但集中度控制在23%左右，毛利率分别保持35.1%、26.8%。", TEXT, False)],
    [("口径与管理含义：", PRIMARY, True),
     ("DCDC-18V为系列合并口径（含降压2~4A、5~12A等子品类，其中降压2~4A为主力，如中兴康讯该子品类占其收入84.5%）。客户毛利率低，关键不在客户本身，而在于其采购结构里低毛利品类的占比——", TEXT, False),
     ("调整品类组合比更换客户更现实。", ACCENT, True)],
], size=11)
takeaway_bar(s, [("建议：", PRIMARY, True),
                 ("对DCDC-18V集中度超60%的客户（中兴康讯/共进/兆驰/微浦），逐户制定品类结构优化目标（建议，待决策）。", TEXT, False)])


# ==================== P9: 应用领域分化（表格） ====================
print('P9...')
s = prs.slides.add_slide(blank)
add_bg(s, 'bg_content.png')
page_title(s, "应用领域分化与资源再配置", "网通收入占27%、毛利率仅22%且同比-11.4pct——资源错配最明显的领域")

domain_rows = [
    ("网通", "12,595", "22.0%", "-11.4pct", "10.2%", "结构优化为主"),
    ("安防", "8,656", "37.8%", "-1.8pct", "16.7%", "保持"),
    ("数码", "5,260", "39.3%", "-0.6pct", "5.7%", "保持"),
    ("智能清洁", "5,177", "41.7%", "+5.9pct", "18.0%", "加大资源投入"),
    ("充电头", "1,882", "41.4%", "+6.4pct", "30.4%", "加大资源投入"),
]
cell_colors = {}
for ri, r in enumerate(domain_rows):
    chg = r[3]
    if chg.startswith('-') and abs(float(chg.replace('pct', '').replace('%', '').replace('+', ''))) > 5:
        cell_colors[(ri, 3)] = RED_DARK
    elif chg.startswith('+'):
        cell_colors[(ri, 3)] = POSITIVE
    if r[5] == "加大资源投入":
        cell_colors[(ri, 5)] = POSITIVE
    if r[5] == "结构优化为主":
        cell_colors[(ri, 5)] = ACCENT
add_table(s, 42, 130, 876, 210, ["应用领域", "1-7月收入(万)", "毛利率", "同比变化", "新品渗透度", "资源建议"],
          domain_rows, col_widths=[3, 3, 2, 2.5, 2.5, 3], cell_colors=cell_colors, font_size=11, header_size=11.5, first_col_bold=True)

add_paras(s, 42, 360, 876, 118, [
    [("分化格局清晰：", PRIMARY, True),
     ("智能清洁（41.7%、+5.9pct）、充电头（41.4%、+6.4pct）毛利率超41%且持续提升；安防、数码基本持平；网通22.0%、同比-11.4pct，且收入体量最大（1.36亿、占27%）。", TEXT, False)],
    [("新品渗透形成正向循环：", PRIMARY, True),
     ("充电头新品渗透度30.4%、智能清洁18.0%、安防16.7%，而网通仅10.2%、数码5.7%——", TEXT, False),
     ("高毛利领域正是新品渗透最快的领域。", ACCENT, True)],
    [("资源含义：", PRIMARY, True),
     ("网通以22%的毛利率承载了27%的收入与相应FAE/PM资源；同样的资源投向智能清洁、充电头，边际回报约为网通的1.9倍。", TEXT, False)],
], size=11.5)
takeaway_bar(s, [("建议：", PRIMARY, True),
                 ("FAE/PM资源向智能清洁、充电头倾斜；网通领域以结构优化为主、不追加资源（建议，待决策）。", TEXT, False)])


# ==================== P10: 单价离散度（新增，稳健口径） ====================
print('P10...')
s = prs.slides.add_slide(blank)
add_bg(s, 'bg_content.png')
page_title(s, "单价离散度：极端值虚高，真实价差收敛", "按成交量加权后，多数SKU跨客户价差实际很小；大客户凭量获结构性低价")

section_label(s, 42, 122, "STI3452HFI 各客户成交价与成交量分布（7月）")
add_image_fit(s, os.path.join(CHARTS, 'p10_distribution.png'), 42, 144, 470, 250)
section_label(s, 540, 122, "稳健价差比 vs 极端值比（7月规模TOP SKU）")
add_image_fit(s, os.path.join(CHARTS, 'p10_robust.png'), 540, 144, 378, 250)

add_paras(s, 42, 402, 876, 82, [
    [("以成交量加权口径看，", PRIMARY, True),
     ("多数SKU的跨客户价差实际较小（稳健价差比1.15-1.38x）；若仅取最高/最低值，部分SKU价差看似超2倍，但这类极端值几乎全部是成交量不足1%的样品单、试产单，不代表真实成交价差。", TEXT, False)],
    [("值得关注的是，", PRIMARY, True),
     ("中兴康讯、CVTE、SAMSUNG等大客户在多个SKU上既是最大成交量买家、也是最低价买家（如STI3452HFI中兴康讯以0.099元成交62.6%的量）。这是量价挂钩的正常结果，", TEXT, False),
     ("建议核查大客户低价与其量级、毛利贡献是否匹配量价阶梯纪律。", ACCENT, True)],
], size=11)
takeaway_bar(s, [("价格管理建议：", PRIMARY, True),
                 ("重点核查量价阶梯的匹配性（大客户低价是否对应足够的量与毛利贡献），而非笼统的价差问题。", TEXT, False)])


# ==================== P11: 追觅专项① ====================
print('P11...')
s = prs.slides.add_slide(blank)
add_bg(s, 'bg_content.png')
page_title(s, "追觅专项①：平量降价，量平价塌", "销量持平（6,525 vs 6,573万颗），销售额-19%、利润-41%、毛利率-12.5pct")
section_label(s, 42, 122, "追觅2026逐月销售额（柱）与毛利率（线）")
add_image_fit(s, os.path.join(CHARTS, 'p12_monthly.png'), 42, 144, 430, 240)
section_label(s, 500, 122, "四指标同比变化（2026年1-7月 vs 去年同期）")
add_image_fit(s, os.path.join(CHARTS, 'p12_changes.png'), 500, 144, 418, 240)
add_paras(s, 42, 392, 876, 92, [
    [("量平价塌：", PRIMARY, True),
     ("主力电机驱动由TMI8180A迭代至TMI8180G后ASP下降27%，叠加买赠让利756万颗——卖的数量一颗没少，每颗赚的钱塌了。", TEXT, False)],
    [("逐月看，", PRIMARY, True),
     ("销售额自1月734万逐月下行，3月曾单月亏损（毛利率-13.6%），4月短暂反弹后持续走低，6月断崖、7月仅14万见底——这是全年下行趋势的终点，不是7月突发。", TEXT, False)],
], size=11.5)
takeaway_bar(s, [("案例启示：", PRIMARY, True),
                 ("降价换量在该客户身上未见效——用让利维持旧型号，而非用新品迭代赢回毛利。", TEXT, False)])


# ==================== P12: 追觅专项② ====================
print('P12...')
s = prs.slides.add_slide(blank)
add_bg(s, 'bg_content.png')
page_title(s, "追觅专项②：主力归零 + 新品空白", "五个主力型号7月全部停摆；2026年新增SKU仅3个且均为10万元以下试单")
section_label(s, 42, 122, "追觅分型号：H1销售额 vs 7月销售额")
add_image_fit(s, os.path.join(CHARTS, 'p13_models.png'), 42, 144, 876, 236)
add_paras(s, 42, 390, 876, 94, [
    [("双柱齐崩：", PRIMARY, True),
     ("TMI8180G（H1月均472万颗、销售额1,350万）与TMI6240（月均340万颗、287万）7月双双归零，五个主力型号全部停摆；仅TMI8870存5万颗、TMI8180A为残单退货。", TEXT, False)],
    [("新品端同样空白：", PRIMARY, True),
     ("下一代TMI8180I已进入石头、未进入追觅；新品类探索（H桥BDC低压13万、LED驱动68万）均未起量。追觅2026Q1扫地机全球销量销售额双第一——", TEXT, False),
     ("需求在增长，是我们在新一代产品上未能补位。", ACCENT, True)],
], size=11.5)
takeaway_bar(s, [("案例启示：", PRIMARY, True),
                 ("大客户的份额护城河在下一代产品。建议业务部门先定性TMI8180G为永久淘汰还是过渡空窗，再决定挽回或止损（待决策）。", TEXT, False)])


# ==================== P13: 正反样本 ====================
print('P13...')
s = prs.slides.add_slide(blank)
add_bg(s, 'bg_content.png')
page_title(s, "正反样本：两种打法都已验证", "海康靠高毛利新品抢增量、CVTE靠压低调高——两条路径均可复制")
section_label(s, 42, 122, "CVTE采购结构调整前后（堆积占比）")
add_image_fit(s, os.path.join(CHARTS, 'p14_cvte.png'), 42, 144, 430, 240)
section_label(s, 500, 122, "海康威视：收入与毛利率前后对比")
add_image_fit(s, os.path.join(CHARTS, 'p14_hikvision.png'), 500, 144, 418, 240)
add_paras(s, 42, 392, 876, 92, [
    [("海康威视（增长型）：", PRIMARY, True),
     ("收入1,168万→1,525万（+31%），毛利率34.7%→35.1%逆势稳住——导入POE-PD、PSE高毛利新品（TME7352 209万、TMI3342C 144万、TME7624 115万）。", TEXT, False)],
    [("CVTE（扭转型）：", PRIMARY, True),
     ("毛利率20.8%→26.8%（+6.0pct）——主动将DCDC-18V占比从36%压至18%，让USB（占比26%、毛利33%）与PMU LNB（占比28%、约39%）成为主力，并导入PSE新品TMI7604R。", TEXT, False)],
], size=11.5)
takeaway_bar(s, [("可复制打法：", POSITIVE, True),
                 ("打法一用高毛利新品抢增量（海康），打法二压低毛利品类、扶高毛利品类（CVTE）——建议提炼为全员SOP（建议，待决策）。", TEXT, False)])


# ==================== P14: 新品 ====================
print('P14...')
s = prs.slides.add_slide(blank)
add_bg(s, 'bg_content.png')
page_title(s, "新品：经验证的增长引擎", "新品占比升至15.7%、毛利率37.5%高于整体7.3pct；但21个新品毛利率低于25%、10个亏损")
section_label(s, 42, 122, "新品毛利分档：SKU数（柱）与档内加权毛利率（线）")
add_image_fit(s, os.path.join(CHARTS, 'p15_tiers.png'), 42, 144, 430, 240)
section_label(s, 500, 122, "四个起量新品样本")
add_image_fit(s, os.path.join(CHARTS, 'p15_rising.png'), 500, 144, 418, 240)
add_paras(s, 42, 392, 876, 92, [
    [("结构向好但有尾巴：", PRIMARY, True),
     ("68个新品毛利率≥45%（占新品收入34.7%、档内加权55.6%）；但21个低于25%、10个亏损，集中在车规电机驱动（导入期定价过低）与电脑&计算品类——剔除差品后新品毛利本应为43.4%，差品拉低4.5pct。", TEXT, False)],
    [("起量样本验证方向：", PRIMARY, True),
     ("TMI7604R（1-7月360万、40家客户，接受度最广）、TMI8180I（7月91万、较H1月均+474%）、TMI8116-Q1（+263%）、TME7352（1月2万→5月110万）；新品主要落在PSE、POE-PD二合一等高毛利品类。", TEXT, False)],
], size=11.5)
takeaway_bar(s, [("方向已验证——", POSITIVE, True),
                 ("车规新品定价需重算；建议对5-8个高毛利低覆盖新品配专项资源加速放量（待决策）。", TEXT, False)])


# ==================== P15: SKU进出账 ====================
print('P15...')
s = prs.slides.add_slide(blank)
add_bg(s, 'bg_content.png')
page_title(s, "KA/AA SKU进出账：铺货≠赚钱", "新增312个/流失200个、净+112个；净贡献收入+1,019万、利润+362万")
section_label(s, 42, 122, "近12月SKU新增 vs 流失：收入与利润（万）")
add_image_fit(s, os.path.join(CHARTS, 'p16_sku.png'), 42, 144, 510, 236)

# Right: 2x2 model table
add_text(s, 578, 122, 340, 20, "四种进出模式（按利/质变化）", size=12.5, color=TEXT_GRAY, bold=True)
model_rows = [
    ("量利质齐升", "海康+110万/+4.2pct", "最健康"),
    ("量利增毛利降", "石头+153万/-12.5pct", "需关注"),
    ("流失高毛利品", "比亚迪-95万/-24.2pct", "受损"),
    ("流失低毛利品", "TCL毛利+12.4pct", "反改善"),
]
cell_colors = {(0, 2): POSITIVE, (1, 2): WARNING_ORANGE, (2, 2): RED_DARK, (3, 2): CYAN}
add_table(s, 578, 146, 340, 180, ["模式", "代表客户", "性质"], model_rows,
          col_widths=[3, 4, 2], cell_colors=cell_colors, font_size=9.5, first_col_bold=True)

add_paras(s, 42, 392, 876, 92, [
    [("总账为正、结构存忧：", PRIMARY, True),
     ("新增SKU带来收入1,787万、利润721万，流失损失收入768万、利润359万。但石头新增利润+153万、毛利率-12.5pct，中兴康讯+35万、-13.3pct——", TEXT, False),
     ("新增SKU毛利率低于存量，量在增、质在降。", ACCENT, True)],
    [("正面与反面并存：", PRIMARY, True),
     ("海康（+110万/+4.2pct）、拓竹（+15万/+8.0pct）量利质齐升；比亚迪流失车规H桥利润-95万、毛利-24.2pct；TCL流失DCDC-18V后毛利+12.4pct。AA客户在DCDC-18V上新增SKU最多（12个），收入仅65万、利润10万。", TEXT, False)],
], size=11.5)
takeaway_bar(s, [("建议建立新增SKU毛利门槛审批制：", PRIMARY, True),
                 ("新增SKU毛利率低于该客户现有毛利率的，需审批后方可导入（建议，即刻执行）。", TEXT, False)])


# ==================== P16: 方案菜单（简化表格） ====================
print('P16...')
s = prs.slides.add_slide(blank)
add_bg(s, 'bg_content.png')
page_title(s, "毛利提升方案菜单：做加法，不做减法", "以下方案均为布局建议，不以削减现有销售额为代价；优先级以总经理决策为准")

plan_rows = [
    ("亏损SKU处置", "26个负毛利SKU逐一定性（停售/整改/维持）", "+314万/年", "评估客户依赖度"),
    ("品类结构调整", "增量倾斜/价格修复/迭代替代/搭配销售/结构化返利", "年化+1~2pct", "需客户配合"),
    ("交叉销售", "30个高毛利品类向KA/AA渗透（复制CVTE模式）", "视试点而定", "选3-5家先行"),
    ("价格管理", "多客户SKU价差收敛，用结构化返利替代直接提价", "月增利约58万", "避免一刀切"),
    ("新品推广加速", "5-8个高毛利低覆盖新品配专项资源", "视覆盖而定", "车规定价需重算"),
    ("成本优化", "晶圆集采、封测锁价、高成本SKU整改", "降本10-15%", "采购+产品线联合"),
]
add_table(s, 42, 128, 876, 250, ["方案方向", "核心内容", "潜在收益（测算）", "前提/风险"],
          plan_rows, col_widths=[2.5, 5, 2.5, 3], font_size=10.5, header_size=11.5, first_col_bold=True)

add_paras(s, 42, 392, 876, 90, [
    [("组合测算（仅供排序参考）：", PRIMARY, True),
     ("仅处置负毛利SKU→增利314万（毛利率约36.0%）；叠加限量10%+交叉销售→约1,100万（37.5%）；再叠加限量20%+价格管理→约1,800万（39.0%）；全面推进理论上限约2,500万（40.0%）。", TEXT, False)],
    [("推进建议：", PRIMARY, True),
     ("建议优先推进 品类结构调整（增量倾斜+返利引导）与 新品加速，同步准备价格修复与迭代替代；各方案可在1-2家客户先行试点。", TEXT, False),
     ("具体取舍与优先级不做预设，以总经理现场决策为准。", ACCENT, True)],
], size=11.5)
takeaway_bar(s, [("定位说明：", PRIMARY, True),
                 ("本页为方案布局与测算，不构成决策结论；各方向的责任、时限与投入以总经理决策为准。", TEXT, False)])


# ==================== P17: forecast与长库龄 ====================
print('P17...')
s = prs.slides.add_slide(blank)
add_bg(s, 'bg_content.png')
page_title(s, "forecast与长库龄：销售侧的直接责任", "长库龄存货5,510万占总库存26.2%；金额-5.8%但型号数+33.6%——旧品未清完、新品又进入")
section_label(s, 42, 122, "长库龄状态分类（金额与占比）")
add_image_fit(s, os.path.join(CHARTS, 'p18_inventory.png'), 42, 144, 470, 240)

# Right: TOP risk models table
add_text(s, 540, 122, 378, 20, "TOP风险型号（金额与库龄）", size=12.5, color=TEXT_GRAY, bold=True)
inv_rows = [
    ("SM2101AB", "968万", "2.6年", "长库龄"),
    ("APPLE5S_A3", "358万", "—", "已停产"),
    ("G0190_3_1", "302万", "4.0年", "长库龄"),
    ("TMI8876R", "293万", "12.9年", "极度困难"),
    ("IM8502", "282万", "—", "完全无销售"),
]
cell_colors = {(1, 3): RED_DARK, (3, 3): RED_DARK, (4, 3): RED_DARK}
add_table(s, 540, 146, 378, 200, ["型号", "金额", "库龄", "状态"],
          inv_rows, col_widths=[3, 2, 2, 2.5], cell_colors=cell_colors, font_size=10, first_col_bold=True)

add_paras(s, 42, 400, 876, 82, [
    [("实质呆滞约2,966万（占47.8%）：", PRIMARY, True),
     ("极度困难560型/2,576万（46.7%）+完全无销售21型/390万+消化困难16型/727万。根因以产品停产（28.9%）与版本迭代（25.9%）为主；产品线集中在马达驱动（1,940万）与充电控制（1,330万），合计59.4%。", TEXT, False)],
    [("与销售的关系：", PRIMARY, True),
     ("长库龄型号多源于forecast偏差与迭代切换未及时递减——forecast由销售填报，库存积压的资金占用计入公司成本。", TEXT, False)],
], size=11)
takeaway_bar(s, [("建议：", PRIMARY, True),
                 ("排单前先做库存扣减（见效最快）；forecast准确度回溯与考核挂钩事宜，建议专项讨论后定（待决策）。", TEXT, False)])


# ==================== P18: 行动建议清单 ====================
print('P18...')
s = prs.slides.add_slide(blank)
add_bg(s, 'bg_content.png')
page_title(s, "行动建议清单", "按“立即执行 / 建立机制 / 持续跟踪”三层推进；最终责任与时限以总经理决策为准")

actions = [
    ("立即", "26个负毛利SKU逐一定性（停售/整改/维持），STI3452HFI优先", "销售+产品", "2-3周", "定性完成率100%"),
    ("立即", "追觅定性与止损/挽回方案", "追觅客户经理+产品线", "2周", "输出明确结论"),
    ("立即", "车规新品定价校准", "产品线", "本月", "新品毛利率≥35%"),
    ("立即", "新增SKU毛利门槛审批制", "销售管理", "即刻", "审批覆盖率"),
    ("立即", "H1整改未落地专项复盘", "销售负责人", "本月内", "有方案/有目标/有决策"),
    ("机制", "CVTE模式复制（中兴康讯/共进/兆驰等3-5家）", "KA客户经理", "本月启动", "高毛利品类占比+5pct"),
    ("机制", "明星新品加速：5-8个高毛利低覆盖新品配专项资源", "PM+FAE", "本月立项", "客户覆盖家数"),
    ("机制", "客户毛利健康度评分卡月度输出", "销售管理", "9月起", "月度出表"),
    ("机制", "forecast准确度回溯 + 排单前库存扣减", "销售+采购", "9月起", "forecast准确率"),
    ("跟踪", "DCDC-18V低价客户价格修复（低于均价90%的分3个月提至90%以上）", "KA/AA客户经理", "3个月", "月增利约20万"),
]
layer_colors = {"立即": ACCENT, "机制": PRIMARY, "跟踪": TEAL}
layer_bg = {"立即": WARNING_BG, "机制": BG_LIGHT, "跟踪": RGBColor(0xEA, 0xF7, 0xF6)}

tbl_shape = s.shapes.add_table(11, 5, emu(42), emu(120), emu(876), emu(320))
table = tbl_shape.table
table.columns[0].width = emu(58)
table.columns[1].width = emu(420)
table.columns[2].width = emu(160)
table.columns[3].width = emu(90)
table.columns[4].width = emu(148)
headers = ["阶段", "建议动作", "建议牵头方", "建议时限", "衡量口径"]
for ci, h in enumerate(headers):
    cell = table.cell(0, ci)
    cell.text = h
    p = cell.text_frame.paragraphs[0]
    p.font.size = Pt(11)
    p.font.bold = True
    p.font.name = FONT
    p.font.color.rgb = WHITE
    p.alignment = PP_ALIGN.CENTER
    cell.fill.solid()
    cell.fill.fore_color.rgb = PRIMARY
    cell.vertical_anchor = MSO_ANCHOR.MIDDLE
    cell.margin_top = Pt(2)
    cell.margin_bottom = Pt(2)
for ri, (layer, action, owner, qixian, kpi) in enumerate(actions):
    vals = [layer, action, owner, qixian, kpi]
    for ci, v in enumerate(vals):
        cell = table.cell(ri + 1, ci)
        cell.text = v
        p = cell.text_frame.paragraphs[0]
        p.font.name = FONT
        p.alignment = PP_ALIGN.CENTER if ci != 1 else PP_ALIGN.LEFT
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        cell.margin_top = Pt(1)
        cell.margin_bottom = Pt(1)
        if ci == 0:
            p.font.size = Pt(10)
            p.font.bold = True
            p.font.color.rgb = layer_colors[layer]
        else:
            p.font.size = Pt(9.5)
            p.font.color.rgb = TEXT
            p.font.bold = False
        cell.fill.solid()
        cell.fill.fore_color.rgb = layer_bg[layer]

add_paras(s, 42, 450, 876, 34, [
    [("现场对齐议题（待总经理定调，非结论）：", ACCENT, True),
     ("①下半年考核口径是否加毛利、加结构？②上半年整改只落地1项，怎么让整改真正落地？③海康、CVTE已验证“卖对产品”的路子，要不要复制、怎么复制？", TEXT, False)],
], size=11)

takeaway_bar(s, [("本页为行动建议而非决策结论——", PRIMARY, True),
                 ("各项动作的牵头方、时限与考核口径，以总经理现场决策为准。", TEXT, False)])


# ==================== SAVE ====================
prs.save(DECK)
total = len(prs.slides._sldIdLst)
print('\nSaved: {} ({:.0f} KB, {} slides)'.format(DECK, os.path.getsize(DECK) / 1024, total))
