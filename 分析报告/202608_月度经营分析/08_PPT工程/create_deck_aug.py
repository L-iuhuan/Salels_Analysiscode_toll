# -*- coding: utf-8 -*-
"""create_deck_aug.py - 构建2026年8月经营分析汇报PPT（17页）."""
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
from pptx import Presentation
from pptx.util import Pt, Emu, Inches
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from PIL import Image as PILImage
import json

# === 路径 ===
BASE = os.path.dirname(os.path.abspath(__file__))
MEDIA = os.path.join(BASE, 'assets_media')
CHARTS = os.path.join(BASE, 'charts')
DATA_DIR = os.path.join(os.path.dirname(BASE), '05_过程数据')
DECK = os.path.join(BASE, '2026年8月经营分析汇报.pptx')

# === 尺寸（沿用7月工程EMU换算） ===
SLIDE_W = Emu(14400213)
SLIDE_H = Emu(8099425)
SCALE = 1.181

def emu(v):
    return Emu(int(v * SCALE * 12700))

# === 配色 ===
PRIMARY = RGBColor(0x00, 0x43, 0x7C)
ACCENT = RGBColor(0xF1, 0x81, 0x01)
POSITIVE = RGBColor(0x8F, 0xC3, 0x1F)
CYAN = RGBColor(0x00, 0xA0, 0xE9)
TEAL = RGBColor(0x01, 0xAD, 0xA1)
NEG = RGBColor(0xC0, 0x50, 0x4D)
TEXT = RGBColor(0x26, 0x26, 0x26)
TEXT_GRAY = RGBColor(0x59, 0x59, 0x59)
TEXT_LIGHT = RGBColor(0x8C, 0x8C, 0x8C)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
BG_CARD = RGBColor(0xF7, 0xF9, 0xFB)
BG_LIGHT = RGBColor(0xF2, 0xF5, 0xF9)
BORDER_CLR = RGBColor(0xE3, 0xE8, 0xEF)
WARNING_BG = RGBColor(0xFD, 0xF3, 0xE7)
WARNING_ORANGE = RGBColor(0xF3, 0x98, 0x00)

FONT = "HarmonyOS Sans SC"

prs = Presentation()
prs.slide_width = SLIDE_W
prs.slide_height = SLIDE_H
blank = prs.slide_layouts[6]


def load_json(name):
    with open(os.path.join(DATA_DIR, name), encoding='utf-8') as f:
        return json.load(f)


# === 基础形状 ===
def add_text(slide, x, y, w, h, text, size=14, color=TEXT, bold=False,
             align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, font=FONT, line_spacing=1.0):
    box = slide.shapes.add_textbox(emu(x), emu(y), emu(w), emu(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = 0; tf.margin_right = 0; tf.margin_top = 0; tf.margin_bottom = 0
    p = tf.paragraphs[0]
    p.text = text
    p.font.size = Pt(size)
    p.font.color.rgb = color
    p.font.bold = bold
    p.font.name = font
    p.alignment = align
    p.space_before = Pt(0); p.space_after = Pt(0)
    if line_spacing != 1.0:
        p.line_spacing = Pt(size * line_spacing)
    return box


def add_paras(slide, x, y, w, h, paras, size=12, font=FONT, anchor=MSO_ANCHOR.TOP, line_spacing=1.4):
    box = slide.shapes.add_textbox(emu(x), emu(y), emu(w), emu(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = 0; tf.margin_right = 0; tf.margin_top = 0; tf.margin_bottom = 0
    for pi, runs in enumerate(paras):
        p = tf.paragraphs[0] if pi == 0 else tf.add_paragraph()
        p.space_before = Pt(0); p.space_after = Pt(4)
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
        shape.fill.solid(); shape.fill.fore_color.rgb = fill
    else:
        shape.fill.background()
    if border:
        shape.line.color.rgb = border; shape.line.width = Pt(border_w)
    else:
        shape.line.fill.background()
    shape.shadow.inherit = False
    return shape


def add_round_rect(slide, x, y, w, h, fill=None, border=None, border_w=1, radius=0.08):
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, emu(x), emu(y), emu(w), emu(h))
    shape.adjustments[0] = radius
    if fill:
        shape.fill.solid(); shape.fill.fore_color.rgb = fill
    else:
        shape.fill.background()
    if border:
        shape.line.color.rgb = border; shape.line.width = Pt(border_w)
    else:
        shape.line.fill.background()
    shape.shadow.inherit = False
    return shape


def add_ellipse(slide, x, y, w, h, fill=None):
    shape = slide.shapes.add_shape(MSO_SHAPE.OVAL, emu(x), emu(y), emu(w), emu(h))
    if fill:
        shape.fill.solid(); shape.fill.fore_color.rgb = fill
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
        h = max_w / ratio
        w = max_w
    else:
        w = max_h * ratio
        h = max_h
    if w > max_w:
        w = max_w; h = w / ratio
    if h > max_h:
        h = max_h; w = h * ratio
    x_c = x + (max_w - w) / 2
    y_c = y + (max_h - h) / 2
    slide.shapes.add_picture(img_path, emu(x_c), emu(y_c), emu(w), emu(h))


def page_title(slide, title, subtitle=None, act=None):
    # act: 1=诊断, 2=漏账（橙条加宽）, 3=引擎
    bar_color = ACCENT if act == 2 else PRIMARY
    bar_h = 28 if act == 2 else 24
    add_rect(slide, 42, 62, 8, bar_h, fill=bar_color)
    add_text(slide, 62, 60, 820, 32, title, size=22, color=TEXT, bold=True, anchor=MSO_ANCHOR.MIDDLE)
    if subtitle:
        add_text(slide, 62, 94, 820, 22, subtitle, size=13, color=TEXT_LIGHT, anchor=MSO_ANCHOR.MIDDLE)


def page_number(slide, n):
    add_text(slide, 840, 500, 80, 18, f'{n}/17', size=11, color=TEXT_GRAY, align=PP_ALIGN.RIGHT)


def takeaway_bar(slide, text_runs, y=480, style='light'):
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
    p.space_before = Pt(0); p.space_after = Pt(0)
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
    n_rows = len(rows) + 1
    n_cols = len(headers)
    tbl_shape = slide.shapes.add_table(n_rows, n_cols, emu(x), emu(y), emu(w), emu(h))
    table = tbl_shape.table
    if col_widths:
        total = sum(col_widths)
        for ci, cw in enumerate(col_widths):
            table.columns[ci].width = Emu(int(emu(w) * cw / total))
    for ci, h in enumerate(headers):
        cell = table.cell(0, ci)
        cell.text = h
        p = cell.text_frame.paragraphs[0]
        p.font.size = Pt(header_size); p.font.bold = True; p.font.name = FONT
        p.font.color.rgb = WHITE; p.alignment = PP_ALIGN.CENTER
        cell.fill.solid(); cell.fill.fore_color.rgb = header_fill
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        cell.margin_top = Pt(2); cell.margin_bottom = Pt(2)
    for ri, row in enumerate(rows):
        for ci, v in enumerate(row):
            cell = table.cell(ri + 1, ci)
            cell.text = str(v)
            p = cell.text_frame.paragraphs[0]
            p.font.size = Pt(font_size); p.font.name = FONT
            p.font.bold = first_col_bold and ci == 0
            p.alignment = PP_ALIGN.CENTER if ci != 1 else PP_ALIGN.LEFT
            color = TEXT
            if cell_colors and (ri, ci) in cell_colors:
                color = cell_colors[(ri, ci)]
            p.font.color.rgb = color
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.margin_top = Pt(1); cell.margin_bottom = Pt(1)
            if row_fills and ri in row_fills:
                cell.fill.solid(); cell.fill.fore_color.rgb = row_fills[ri]
            else:
                cell.fill.solid(); cell.fill.fore_color.rgb = WHITE if ri % 2 == 0 else BG_LIGHT
    return table


# === 数据加载 ===
report = load_json('report_data.json')
analysis2 = load_json('analysis2.json')
analysis3 = load_json('analysis3.json')
supplement = load_json('supplement.json')
recompute = load_json('recompute.json')

ov = report['ov']
cls = report['cls']

# === 幻灯片构建 ===

def build_p1():
    print('P1...')
    s = prs.slides.add_slide(blank)
    add_bg(s, 'bg_cover.png')
    add_text(s, 55, 250, 520, 40, '拓尔微电子股份有限公司', size=22, color=WHITE)
    add_text(s, 55, 300, 720, 60, '2026年8月经营分析汇报', size=40, color=WHITE, bold=True)
    add_rect(s, 55, 378, 70, 3, fill=CYAN)
    add_text(s, 55, 398, 640, 26, '主讲：总经理｜汇报对象：销售负责人及业务员｜2026年9月',
             size=13, color=RGBColor(0xD0, 0xD8, 0xE4))
    add_text(s, 55, 495, 400, 22, 'www.toll-semi.com', size=11, color=TEXT_GRAY)
    page_number(s, 1)


def build_p2():
    print('P2...')
    s = prs.slides.add_slide(blank)
    add_bg(s, 'bg_content.png')
    page_title(s, '8月经营总览', '量减价稳，结构改善')
    # KPI四卡
    rev = ov['cur']['rev'] / 1e4
    pft = ov['cur']['pft'] / 1e4
    rev_yoy = ov['yoy']['rev'] * 100
    rev_mom = ov['mom']['rev'] * 100
    pft_yoy = ov['yoy']['pft'] * 100
    pft_mom = ov['mom']['pft'] * 100
    margin = ov['cur']['m'] * 100
    margin_delta = ov['mom']['m'] * 100
    ytd = ov['ytd']['rev'] / 1e8
    ytd_yoy = ov['ytdd']['rev'] * 100
    cards = [
        (42, '收入（万元）', f'{rev:,.1f}', PRIMARY, f'同比 {rev_yoy:+.1f}%｜环比 {rev_mom:+.1f}%', TEXT),
        (272, '利润（万元）', f'{pft:,.1f}', PRIMARY, f'同比 {pft_yoy:+.1f}%｜环比 {pft_mom:+.1f}%', TEXT),
        (502, '毛利率', f'{margin:.2f}%', PRIMARY, f'环比{margin_delta:+.2f}pct', TEXT),
        (732, 'YTD收入', f'{ytd:.2f}亿', PRIMARY, f'同比+{ytd_yoy:.0f}%', TEXT),
    ]
    for cx, label, number, num_color, change, chg_color in cards:
        add_round_rect(s, cx, 120, 210, 108, fill=BG_CARD, border=BORDER_CLR, radius=0.07)
        add_text(s, cx + 12, 128, 180, 20, label, size=11.5, color=TEXT_LIGHT)
        add_text(s, cx + 12, 150, 190, 44, number, size=28, color=num_color, bold=True)
        add_text(s, cx + 12, 198, 190, 20, change, size=10.5, color=chg_color, bold=True)
    # 主线三句
    add_paras(s, 42, 250, 876, 82, [
        [(f'① 量效应{-461:.0f}万为唯一负贡献', PRIMARY, True), ('；价格与品类结构双双转正。', TEXT, False)],
        [('② 价+结构双正，为2025年2月以来首次非春节月。', PRIMARY, True)],
        [('③ 增量利润93%来自MM中小客户，KA大客群利润零增长。', PRIMARY, True)],
    ], size=12.5, line_spacing=1.5)
    # 三幕导览条
    add_round_rect(s, 42, 348, 876, 50, fill=BG_LIGHT, border=BORDER_CLR, radius=0.12)
    add_text(s, 60, 360, 260, 28, '第一幕·诊断', size=13, color=PRIMARY, bold=True, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    add_text(s, 350, 360, 260, 28, '第二幕·漏账', size=13, color=ACCENT, bold=True, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    add_text(s, 640, 360, 260, 28, '第三幕·引擎', size=13, color=POSITIVE, bold=True, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    add_text(s, 350, 388, 260, 16, '客户品类对冲矩阵→第8页', size=9, color=TEXT_GRAY, align=PP_ALIGN.CENTER)
    takeaway_bar(s, [('定调：', PRIMARY, True),
                     ('本月为“量减价稳、结构改善”，方向成立，9月验证。', TEXT, False)])
    page_number(s, 2)


def build_p3():
    print('P3...')
    s = prs.slides.add_slide(blank)
    add_bg(s, 'bg_content.png')
    page_title(s, '问题跟踪总览')
    # 问题跟踪表（上月5项+本月4新增）
    headers = ['来源', '问题', '状态', '备注']
    rows = [
        ('上月', 'DCDC-18V 2-4A 限价/提价', '△恶化', '品类毛利率继续承压'),
        ('上月', '停售负毛利型号（STI3452HFI等）', '✗未落地', '8月仍在售、持续亏损'),
        ('上月', '挽回追觅/小米等量缩大客户', '✗未落地', '追觅8月仅13.5万'),
        ('上月', '中兴康讯/共进采购结构转向', '△恶化', '中兴亏损扩大至-69万'),
        ('上月', '新品立项绑定高毛利品类', '√见效', '新品占比19.8%'),
        ('本月新增', '音频功放毛利率骤降', '△新上榜', '40%→7.4%'),
        ('本月新增', 'DCDC-18V成本侵蚀（STI3453FI）', '△新上榜', '单位成本+24.2%'),
        ('本月新增', 'SKU新增毛利率门槛', '□待建立', '新增SKU质在降'),
        ('本月新增', 'PSE/车规等新品推广责任人', '□待会议定', '见P16空表'),
    ]
    cell_colors = {}
    for ri, r in enumerate(rows):
        if r[2].startswith('√'): cell_colors[(ri, 2)] = POSITIVE
        elif r[2].startswith('△') or r[2].startswith('✗'): cell_colors[(ri, 2)] = NEG if r[2].startswith('✗') else ACCENT
        else: cell_colors[(ri, 2)] = TEXT_GRAY
    add_table(s, 42, 120, 876, 330, headers, rows, col_widths=[2, 5, 2, 3],
              cell_colors=cell_colors, font_size=10.5, first_col_bold=True)
    takeaway_bar(s, [('公信力：', PRIMARY, True),
                     ('上月两项预警本月兑现为失血；已见效项为新品占比提升。', TEXT, False)])
    page_number(s, 3)


def build_p4():
    print('P4...')
    s = prs.slides.add_slide(blank)
    add_bg(s, 'bg_content.png')
    page_title(s, '毛利桥四因子分解', '环比量效应-461万为唯一负贡献')
    section_label(s, 42, 118, '环比瀑布（万元）')
    add_image_fit(s, os.path.join(CHARTS, 'p04_waterfall_mom.png'), 42, 140, 520, 280)
    section_label(s, 590, 118, '同比瀑布（万元，小图）')
    add_image_fit(s, os.path.join(CHARTS, 'p04_waterfall_yoy.png'), 580, 140, 340, 220)
    add_paras(s, 42, 430, 876, 55, [
        [('口径说明：', PRIMARY, True),
         ('可比口径=两期均有销售的SKU集合（同比394个/环比444个）；四因子恒等式自洽，环比由recompute.json重算。', TEXT, False)],
    ], size=11)
    takeaway_bar(s, [('结论：', PRIMARY, True),
                     ('量效应是环比唯一拖累；同比缺口主因仍是价效应-470万。', TEXT, False)])
    page_number(s, 4)


def build_p5():
    print('P5...')
    s = prs.slides.add_slide(blank)
    add_bg(s, 'bg_content.png')
    page_title(s, '环比回落解剖（本月专项）')
    # 左三证据卡
    evidences = [
        ('① 回落集中于7月冲高项', '中兴506万峰值回落\n大华238→96万\nPOE协议类-73%'),
        ('② 新客户+216万在补位', '胜辉时代+69万\n星网智慧+58万\n华橙+46万、SJIT+43万'),
        ('③ 价格全线平稳', '同SKU均价环比基本持平\n未出现系统性降价'),
    ]
    for i, (title, body) in enumerate(evidences):
        y = 120 + i * 118
        add_round_rect(s, 42, y, 360, 105, fill=BG_CARD, border=BORDER_CLR, radius=0.07)
        add_text(s, 58, y + 8, 330, 24, title, size=13, color=PRIMARY, bold=True)
        add_text(s, 58, y + 34, 330, 64, body, size=11, color=TEXT)
    # 右阈值尺
    add_round_rect(s, 440, 120, 478, 360, fill=BG_CARD, border=BORDER_CLR, radius=0.07)
    add_text(s, 460, 134, 440, 24, '9月阈值尺：环比量效应', size=14, color=PRIMARY, bold=True)
    # 绘制色阶条
    add_rect(s, 460, 170, 440, 24, fill=ACCENT)
    add_rect(s, 460, 194, 440, 24, fill=WARNING_ORANGE)
    add_rect(s, 460, 218, 440, 24, fill=NEG)
    add_text(s, 460, 250, 440, 20, '≥ -3%     正常回调', size=11, color=TEXT)
    add_text(s, 460, 274, 440, 20, '-3% ~ -5%  关注区间', size=11, color=TEXT)
    add_text(s, 460, 298, 440, 20, '≤ -5%     需求走弱预警', size=11, color=TEXT)
    add_text(s, 460, 350, 440, 50,
             '判断结论不上页面，由汇报人口播：\n“透支回调，9月见分晓”。',
             size=11, color=TEXT_GRAY)
    takeaway_bar(s, [('本月专项：', PRIMARY, True),
                     ('回落集中在7月冲高项，新客户补位+216万；价格平稳意味着并非需求崩塌。', TEXT, False)])
    page_number(s, 5)


def build_p6():
    print('P6...')
    s = prs.slides.add_slide(blank)
    add_bg(s, 'bg_content.png')
    page_title(s, '毛利桥长周期回顾', '价+结构双正为2025-02来首次非春节月')
    section_label(s, 42, 118, '31个月长周期：量 / 价 / 毛利率')
    add_image_fit(s, os.path.join(CHARTS, 'p06_longcycle.png'), 42, 140, 876, 290)
    add_paras(s, 42, 440, 876, 70, [
        [('① 量-毛利相关0.93，量主导波动；', PRIMARY, True),
         ('② 量-结构反向-0.55，量缩时常伴随结构改善；', TEXT, False)],
        [('③ 降价是长期主题：', PRIMARY, True),
         ('31个月价仅5次为正，累计约-2,360万。', TEXT, False)],
    ], size=11)
    takeaway_bar(s, [('信号：', PRIMARY, True),
                     ('价+结构双正为近两年多首次，结构改善方向成立，需9月继续验证。', TEXT, False)])
    page_number(s, 6)


def build_p7():
    print('P7...')
    s = prs.slides.add_slide(blank)
    add_bg(s, 'bg_content.png')
    page_title(s, '客户分群：KA与MM', '增量93%来自MM客户，KA增量不赚钱', act=2)
    section_label(s, 42, 118, 'KA vs MM 利润增量')
    add_image_fit(s, os.path.join(CHARTS, 'p07_ka_mm.png'), 42, 140, 420, 260)
    # 右侧要点
    ka_dp = cls['KA']['dpft'] / 1e4
    mm_dp = cls['MM']['dpft'] / 1e4
    ka_rev_yoy = (cls['KA']['rev_y'] - cls['KA']['rev_ly_y']) / cls['KA']['rev_ly_y'] * 100
    mm_share = mm_dp / ((ov['ytd']['pft'] - ov['lytd']['pft']) / 1e4) * 100
    add_paras(s, 480, 140, 438, 260, [
        [('KA：', PRIMARY, True), (f'利润{ka_dp:+.0f}万（收入同比+{ka_rev_yoy:.0f}%）', TEXT, False)],
        [('MM：', PRIMARY, True), (f'利润+{mm_dp:.0f}万，占增量{mm_share:.0f}%', TEXT, False)],
        [('户均产出：', PRIMARY, True), ('11万→17.6万（+60%），毛利率38.7%持平', TEXT, False)],
        [('过渡：', ACCENT, True), ('KA的利润漏在哪？下一页按品类拆解。', TEXT, False)],
    ], size=12, line_spacing=1.6)
    takeaway_bar(s, [('错配：', PRIMARY, True),
                     ('资源投入最重的KA回报偏低，需逐户分析毛利率下滑原因。', TEXT, False)])
    page_number(s, 7)


def build_p8():
    print('P8...')
    s = prs.slides.add_slide(blank)
    add_bg(s, 'bg_content.png')
    page_title(s, '客户品类对冲矩阵', '三个品类，三种对冲形态', act=2)
    section_label(s, 42, 118, 'H桥BDC / DCDC-18V / PSE 三列对比')
    add_image_fit(s, os.path.join(CHARTS, 'p08_hedge_matrix.png'), 42, 140, 876, 300)
    add_paras(s, 42, 450, 876, 55, [
        [('① H桥BDC：', PRIMARY, True), ('需求还在，换了客户承接——石头+189万对冲追觅/小米下滑的33%。', TEXT, False)],
        [('② DCDC-18V：', PRIMARY, True), ('五客户全负，品类级失血，无对冲。', TEXT, False)],
        [('③ PSE：', PRIMARY, True), ('海康+59万/大华+65万/中兴+33万，品类级红利。', TEXT, False)],
    ], size=11)
    takeaway_bar(s, [('结构含义：', PRIMARY, True),
                     ('同品类在不同客户间可转移；DCDC-18V是共性失血点，PSE是共性红利点。', TEXT, False)], style='warning')
    page_number(s, 8)


def build_p9():
    print('P9...')
    s = prs.slides.add_slide(blank)
    add_bg(s, 'bg_content.png')
    page_title(s, '大客户风险跟踪', '中兴康讯连亏扩大，追觅SKU流失', act=2)
    section_label(s, 42, 118, '中兴康讯月度利润')
    add_image_fit(s, os.path.join(CHARTS, 'p09_zte_trend.png'), 42, 140, 420, 240)
    # 追觅卡
    add_round_rect(s, 480, 140, 438, 240, fill=BG_CARD, border=BORDER_CLR, radius=0.07)
    add_text(s, 496, 154, 410, 24, '追觅：SKU流失', size=14, color=PRIMARY, bold=True)
    add_text(s, 496, 188, 410, 120,
             '• 6个SKU流失\n• 带走利润809万\n• 8月收入仅13.5万\n• 已做：STI停售\n• 方案切换评估中',
             size=12, color=TEXT, line_spacing=1.4)
    add_paras(s, 42, 392, 876, 75, [
        [('中兴康讯：', PRIMARY, True),
         ('6-8月连亏扩大，亏损集中于DCDC-18V品类（占其收入86%）；PSE采购+33万为正，同线对冲已在发生。', TEXT, False)],
    ], size=11.5)
    takeaway_bar(s, [('止损动作：', PRIMARY, True),
                     ('STI已停售；中兴需双管齐下：压降DCDC-18V占比+导入高毛利新品。', TEXT, False)])
    page_number(s, 9)


def build_p10():
    print('P10...')
    s = prs.slides.add_slide(blank)
    add_bg(s, 'bg_content.png')
    page_title(s, '成本监控', '成本压力品类换防，重点单品易主', act=2)
    section_label(s, 42, 118, '品类成本效应（8月 vs 7月，万元）')
    add_image_fit(s, os.path.join(CHARTS, 'p10_cost_shift.png'), 42, 140, 420, 240)
    # 右侧卡
    add_round_rect(s, 480, 140, 438, 240, fill=BG_CARD, border=BORDER_CLR, radius=0.07)
    add_text(s, 496, 154, 410, 24, 'STI3453FI 成本侵蚀榜首', size=14, color=PRIMARY, bold=True)
    add_text(s, 496, 188, 410, 140,
             '• 8月收入51.7万，利润-4.4万（已转亏）\n• 单位成本较7月+24.2%\n• 成本侵蚀-10.9万\n\n注：STI3452HFI成本效应转正+6.1万，\n总亏损由-98.3万收窄至-76.1万。',
             size=11, color=TEXT, line_spacing=1.35)
    takeaway_bar(s, [('重点单品：', PRIMARY, True),
                     ('STI3453FI接替STI3452HFI成为成本侵蚀榜首，需优先处置。', TEXT, False)])
    page_number(s, 10)


def build_p11():
    print('P11...')
    s = prs.slides.add_slide(blank)
    add_bg(s, 'bg_content.png')
    page_title(s, '产品线：音频功放毛利率下滑', '音频功放毛利率40%→7.4%', act=2)
    add_image_fit(s, os.path.join(CHARTS, 'p11_audio_cliff.png'), 42, 140, 480, 280)
    add_paras(s, 540, 140, 378, 280, [
        [('归因：', PRIMARY, True)],
        [('TMS8525GM', ACCENT, True), ('（毛利60%）失量约70%，高毛利型号缩量。', TEXT, False)],
        [('TMS8007SP', ACCENT, True), ('负毛利放量，TPLINK为主力客户。', TEXT, False)],
        [('结果：', PRIMARY, True), ('音频功放整体毛利率从40%骤降至7.4%。', TEXT, False)],
    ], size=12, line_spacing=1.5)
    takeaway_bar(s, [('处置：', PRIMARY, True),
                     ('对TMS8007SP等负毛利型号启动停售/提价评估。', TEXT, False)])
    page_number(s, 11)


def build_p12():
    print('P12...')
    s = prs.slides.add_slide(blank)
    add_bg(s, 'bg_content.png')
    page_title(s, '应用领域结构', '网通毛利率26%→16%，修复空间约1,500万/年', act=2)
    section_label(s, 42, 118, '应用领域毛利率变化（1月→8月）')
    add_image_fit(s, os.path.join(CHARTS, 'p12_domain_stack.png'), 42, 140, 520, 260)
    # 机会框
    add_round_rect(s, 580, 140, 338, 260, fill=RGBColor(0xEA, 0xF7, 0xF6), border=TEAL, radius=0.08)
    add_text(s, 596, 154, 310, 24, '机会框：网通修复空间', size=14, color=TEAL, bold=True)
    add_text(s, 596, 188, 310, 180,
             '• 网通毛利率从26%降至16%，拖累最大\n• 修复空间≈1,500万/年\n• 为全公司最大单一改善池\n• 资源倾斜方向：智能清洁、充电头、安防',
             size=12, color=TEXT, line_spacing=1.5)
    takeaway_bar(s, [('情绪翻转：', POSITIVE, True),
                     ('网通虽拖但空间大；智能清洁毛利率45%唯一上升，已验证路径可复制。', TEXT, False)])
    page_number(s, 12)


def build_p13():
    print('P13...')
    s = prs.slides.add_slide(blank)
    add_bg(s, 'bg_content.png')
    page_title(s, '结构改善样本', '三条路径已在大客户验证')
    # 满版三卡
    cards = [
        ('大华：PSE路径', 'PSE放量+64.9万利润\n毛利率提升\n安防高毛利新品驱动', POSITIVE),
        ('TPLINK：换品类路径', '品类切换+51万\nDCDC-18V压降\nPOE-PD协议放量', CYAN),
        ('共进：高毛利新品路径', 'TMI6011渗透\n毛利50-60%\n三客户验证', TEAL),
    ]
    for i, (title, body, color) in enumerate(cards):
        x = 42 + i * 300
        add_round_rect(s, x, 120, 280, 340, fill=BG_CARD, border=color, border_w=2, radius=0.08)
        add_rect(s, x, 120, 280, 8, fill=color)
        add_text(s, x + 16, 140, 250, 28, title, size=16, color=color, bold=True)
        add_text(s, x + 16, 180, 250, 260, body, size=13, color=TEXT, line_spacing=1.6)
    takeaway_bar(s, [('转折：', POSITIVE, True),
                     ('问题说完了，说解法——三条路径均已验证，接下来是怎么放大。', TEXT, False)])
    page_number(s, 13)


def build_p14():
    print('P14...')
    s = prs.slides.add_slide(blank)
    add_bg(s, 'bg_content.png')
    page_title(s, '新品结构', f'新品占比{report["newp"]["share_m"]*100:.1f}%上行')
    section_label(s, 42, 118, '新品SKU毛利分档')
    add_image_fit(s, os.path.join(CHARTS, 'p14_new_product.png'), 42, 140, 460, 260)
    add_paras(s, 520, 140, 398, 260, [
        [(f'132个SKU中仅{report["bands"][4][1]:.0f}个负毛利', PRIMARY, True)],
        [('四种放量模式：', PRIMARY, True)],
        [('绑定型：', ACCENT, True), ('TMI8180I（石头91%）/ TME7352（海康97%）', TEXT, False)],
        [('分散型：', ACCENT, True), ('TMI7604R（42家客户）', TEXT, False)],
        [('车规梯队：', ACCENT, True), ('TMI8116-Q1等', TEXT, False)],
    ], size=12, line_spacing=1.5)
    takeaway_bar(s, [('方向：', POSITIVE, True),
                     ('新品是验证的增长引擎；车规定价需重算，高毛利低覆盖新品需配资源。', TEXT, False)])
    page_number(s, 14)


def build_p15():
    print('P15...')
    s = prs.slides.add_slide(blank)
    add_bg(s, 'bg_content.png')
    page_title(s, 'SKU进出账', 'KA+AA净增85个SKU，净影响+762万')
    section_label(s, 42, 118, 'KA+AA SKU进出（收入/利润，万元）')
    add_image_fit(s, os.path.join(CHARTS, 'p15_sku_inout.png'), 42, 140, 500, 260)
    add_paras(s, 560, 140, 358, 260, [
        [('总账：', PRIMARY, True), ('新增151个/流失66个，净增85个', TEXT, False)],
        [('收入影响：', PRIMARY, True), ('新增2,162万 - 流失167万 = +1,995万', TEXT, False)],
        [('利润影响：', PRIMARY, True), ('新增845万 - 流失83万 = +762万', TEXT, False)],
        [('结构：', PRIMARY, True), ('新增品类TOP高毛利主导', TEXT, False)],
    ], size=12, line_spacing=1.5)
    takeaway_bar(s, [('建议：', PRIMARY, True),
                     ('建立新增SKU毛利门槛审批制，低于客户现有毛利率的需审批后导入。', TEXT, False)])
    page_number(s, 15)


def build_p16():
    print('P16...')
    s = prs.slides.add_slide(blank)
    add_bg(s, 'bg_content.png')
    page_title(s, '跨领域推广构想', '已验证路径推向新客户群')
    # 点阵图
    section_label(s, 42, 118, 'PSE前30大客户：12家未渗透')
    add_image_fit(s, os.path.join(CHARTS, 'p16_pse_dots.png'), 42, 140, 400, 180)
    add_paras(s, 460, 140, 458, 180, [
        [('三方向：', PRIMARY, True)],
        [('① PSE', ACCENT, True), ('向TOP30中12家未渗透客户推广', TEXT, False)],
        [('② H桥→工业执行器', ACCENT, True), ('已自发：领充251万 / 大豪130万', TEXT, False)],
        [('③ TMI6011', ACCENT, True), ('进海康/大华，复制共进路径', TEXT, False)],
    ], size=12, line_spacing=1.5)
    # 底部三行空表
    add_table(s, 42, 340, 876, 130,
              ['推广路径', '建议责任人', '建议时限'],
              [('① PSE向12家未渗透客户', '', ''),
               ('② H桥向工业执行器（领充/大豪模式）', '', ''),
               ('③ TMI6011进海康/大华', '', '')],
              col_widths=[5, 3, 2], font_size=12, header_size=12, first_col_bold=True)
    add_text(s, 42, 476, 876, 20,
             '留白=提请本次会议确定推广责任人',
             size=10, color=TEXT_GRAY, align=PP_ALIGN.CENTER)
    takeaway_bar(s, [('诉求：', PRIMARY, True),
                     ('三条已验证路径的推广责任人建议今天确定。', TEXT, False)])
    page_number(s, 16)


def build_p17():
    print('P17...')
    s = prs.slides.add_slide(blank)
    add_bg(s, 'bg_backcover.png')
    add_text(s, 55, 80, 800, 50, '9月跟踪信号与行动事项', size=28, color=WHITE, bold=True)
    add_rect(s, 55, 142, 80, 3, fill=ACCENT)
    add_text(s, 55, 160, 800, 30,
             '价+结构双正为2025-02来首次，方向成立，9月验证',
             size=15, color=WHITE)
    # 三信号表
    add_table(s, 55, 210, 820, 180,
              ['跟踪信号', '阈值', '责任人', '时限'],
              [('价+结构双正延续', '价效应>0 且 结构效应>0', '', ''),
               ('量效应回调幅度', '≥-3%正常 / ≤-5%走弱预警', '', ''),
               ('STI停售后真实毛利', '剔除STI后毛利率变化', '', '')],
              col_widths=[4, 4, 2, 2], font_size=12, header_size=12, first_col_bold=True)
    add_text(s, 55, 410, 820, 30,
             '行动项提请本次会议确定',
             size=16, color=ACCENT, bold=True, align=PP_ALIGN.CENTER)
    page_number(s, 17)


# === 构建并保存 ===
build_p1(); build_p2(); build_p3(); build_p4(); build_p5()
build_p6(); build_p7(); build_p8(); build_p9(); build_p10()
build_p11(); build_p12(); build_p13(); build_p14(); build_p15()
build_p16(); build_p17()

prs.save(DECK)
total = len(prs.slides._sldIdLst)
print(f'\n已保存：{DECK}（{total}页，{os.path.getsize(DECK)/1024:.0f} KB）')
