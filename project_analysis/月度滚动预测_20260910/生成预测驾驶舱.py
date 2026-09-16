# -*- coding: utf-8 -*-
"""预测驾驶舱 HTML 生成器：读 6 个数据 CSV → 单文件自包含看板（内联 CSS/SVG）"""
import sys
import pandas as pd
import numpy as np
sys.stdout.reconfigure(encoding='utf-8')

OUT = r'E:\3-其他资料\数据分析\project_analysis\月度滚动预测_20260910'
DEST = r'E:\3-其他资料\数据分析\project_analysis\预测看板_20260916\预测驾驶舱.html'

# ---------- 数据加载 ----------
comp = pd.read_csv(OUT + r'\交付_公司分月.csv')          # 月/预测/规则/无偏
line_fc = pd.read_csv(OUT + r'\交付_产品线.csv', index_col=0)  # 线×月
conf = pd.read_csv(OUT + r'\看板数据_线级置信分层.csv')     # 产品线/实际合计万/金额占比%/WAPE%/置信档
r3 = pd.read_csv(OUT + r'\R3_方向准确率_公司口径.csv')      # 月/实际/预测/实际向/预测向/命中
hist = pd.read_csv(OUT + r'\公司月度长序列80月.csv')        # 月/金额
cat_fc = pd.read_csv(OUT + r'\交付_品类.csv', index_col=0)

comp['基准万'] = comp['预测'] / 1e4
comp['无偏万'] = comp['无偏'] / 1e4
hist['万'] = hist['金额'] / 1e4
FUT_MONTHS = list(comp['月'])

# 三数（与交付报告一致）
ytd = float(hist[hist['月'] >= '2026-01']['万'].sum())
S4 = float(comp[comp['月'] <= '2026-12']['基准万'].sum()) + ytd
S6 = float(comp['基准万'][:6].sum())
S12 = float(comp['基准万'].sum())
F = 1.040

# ---------- SVG helpers ----------
def svg_bars_monthly(df):
    """12 月双条形（基准/无偏）"""
    n = len(df)
    W, H, pad = 1080, 300, 46
    ymax = max(df['基准万'].max(), df['无偏万'].max()) * 1.12
    bw = W / n * 0.32
    parts = ['<svg viewBox="0 0 %d %d" xmlns="http://www.w3.org/2000/svg" style="width:100%%;height:auto">' % (W, H)]
    for gy in range(5):
        y = pad + (H - 2 * pad) * gy / 4
        v = ymax * (1 - gy / 4)
        parts.append('<line x1="%d" y1="%.0f" x2="%d" y2="%.0f" stroke="#233c55" stroke-width="1"/>' % (pad, y, W - 8, y))
        parts.append('<text x="%d" y="%.0f" fill="#7d93ab" font-size="11" text-anchor="end">%d</text>' % (pad - 4, y + 4, v / 1000 * 1000))
    for i, (_, r) in enumerate(df.iterrows()):
        x0 = pad + (W - 2 * pad) * (i + 0.5) / n
        h1 = (H - 2 * pad) * r['基准万'] / ymax
        h2 = (H - 2 * pad) * r['无偏万'] / ymax
        parts.append('<rect x="%.0f" y="%.0f" width="%.0f" height="%.0f" fill="#2e6da4" rx="2"/>' % (x0 - bw - 1, H - pad - h1, bw, h1))
        parts.append('<rect x="%.0f" y="%.0f" width="%.0f" height="%.0f" fill="#5ba4d8" rx="2"/>' % (x0 + 1, H - pad - h2, bw, h2))
        cny = r['月'] in ('2027-01', '2027-02')
        parts.append('<text x="%.0f" y="%d" fill="%s" font-size="10.5" text-anchor="middle">%s</text>' % (
            x0, H - pad + 16, '#e8a13a' if cny else '#a9bcd1', r['月'][2:].replace('-', '/')))
    parts.append('<rect x="%d" y="10" width="10" height="10" fill="#2e6da4"/><text x="%d" y="19" fill="#a9bcd1" font-size="11">基准</text>' % (W - 150, W - 134))
    parts.append('<rect x="%d" y="10" width="10" height="10" fill="#5ba4d8"/><text x="%d" y="19" fill="#a9bcd1" font-size="11">无偏</text>' % (W - 90, W - 74))
    parts.append('</svg>')
    return ''.join(parts)

def svg_fva_ladder():
    """FVA 阶梯（水平条形，降序改善）"""
    steps = [('上月延续 naive', 14.7), ('近6月平均', 10.3), ('冠军组合(春节规则)', 7.9), ('线级锚定', 7.4), ('无偏校正', 6.9)]
    W, H, pad = 1080, 240, 150
    xmax = 16.0
    parts = ['<svg viewBox="0 0 %d %d" xmlns="http://www.w3.org/2000/svg" style="width:100%%;height:auto">' % (W, H)]
    for i, (name, v) in enumerate(steps):
        y = pad * 0 + 24 + i * 40
        w = (W - pad - 60) * v / xmax
        color = '#5ba4d8' if i < len(steps) - 1 else '#3fa87a'
        parts.append('<text x="%d" y="%.0f" fill="#a9bcd1" font-size="12.5" text-anchor="end">%s</text>' % (pad - 10, y + 15, name))
        parts.append('<rect x="%d" y="%.0f" width="%.0f" height="24" fill="%s" rx="3"/>' % (pad, y, w, color))
        parts.append('<text x="%.0f" y="%.0f" fill="#e8eef5" font-size="12.5" font-weight="600">%.1f%%</text>' % (pad + w + 8, y + 16, v))
    parts.append('<text x="%d" y="%d" fill="#7d93ab" font-size="11">月度平均误差率 WAPE（公司口径，20 折回测）— 越低越好</text>' % (pad, H - 8))
    parts.append('</svg>')
    return ''.join(parts)

def svg_dir_bars():
    methods = [('近6月平均', 58), ('工作日法', 63), ('组合预测', 68), ('冠军量价系统', 74)]
    W, H, pad = 1080, 200, 150
    parts = ['<svg viewBox="0 0 %d %d" xmlns="http://www.w3.org/2000/svg" style="width:100%%;height:auto">' % (W, H)]
    for gy in range(3):
        v = 40 + gy * 30
        y = 20 + (H - 70) * (1 - (v - 30) / 70)
        parts.append('<line x1="%d" y1="%.0f" x2="%d" y2="%.0f" stroke="#233c55"/>' % (pad, y, W - 20, y))
        parts.append('<text x="%d" y="%.0f" fill="#7d93ab" font-size="10.5" text-anchor="end">%d%%</text>' % (pad - 6, y + 4, v))
    ty = 20 + (H - 70) * (1 - (65 - 30) / 70)
    parts.append('<line x1="%d" y1="%.0f" x2="%d" y2="%.0f" stroke="#e8a13a" stroke-dasharray="6 4" stroke-width="1.5"/>' % (pad, ty, W - 20, ty))
    parts.append('<text x="%d" y="%.0f" fill="#e8a13a" font-size="11">目标 65%%</text>' % (W - 90, ty - 6))
    bw = 90
    for i, (name, v) in enumerate(methods):
        x = pad + 40 + i * (W - pad - 100) / 4
        y = 20 + (H - 70) * (1 - (v - 30) / 70)
        h = H - 70 + 20 - y - 30
        best = i == len(methods) - 1
        parts.append('<rect x="%.0f" y="%.0f" width="%d" height="%.0f" fill="%s" rx="3"/>' % (x, y, bw, h, '#3fa87a' if best else '#2e6da4'))
        parts.append('<text x="%.0f" y="%.0f" fill="#e8eef5" font-size="13" font-weight="600" text-anchor="middle">%d%%</text>' % (x + bw / 2, y - 8, v))
        parts.append('<text x="%.0f" y="%d" fill="#a9bcd1" font-size="11.5" text-anchor="middle">%s</text>' % (x + bw / 2, H - 34, name))
    parts.append('</svg>')
    return ''.join(parts)

def svg_history():
    """80 月实际 + 12 月预测延展（含区间带）"""
    W, H, pad = 1080, 340, 52
    hist_v = hist['万'].values
    fut_v = comp['基准万'].values
    fut_ub = comp['无偏万'].values
    allv = np.concatenate([hist_v, fut_ub])
    ymin, ymax = allv.min() * 0.85, allv.max() * 1.08
    N = len(hist_v) + len(fut_v)
    def X(i): return pad + (W - 2 * pad) * i / (N - 1)
    def Y(v): return pad + (H - 2 * pad) * (1 - (v - ymin) / (ymax - ymin))
    parts = ['<svg viewBox="0 0 %d %d" xmlns="http://www.w3.org/2000/svg" style="width:100%%;height:auto">' % (W, H)]
    for gy in range(5):
        y = pad + (H - 2 * pad) * gy / 4
        parts.append('<line x1="%d" y1="%.0f" x2="%d" y2="%.0f" stroke="#233c55"/>' % (pad, y, W - 8, y))
        parts.append('<text x="%d" y="%.0f" fill="#7d93ab" font-size="10.5" text-anchor="end">%.0f</text>' % (pad - 4, y + 4, ymax - (ymax - ymin) * gy / 4))
    # 预测区间带（基准~无偏近似带）
    i0 = len(hist_v) - 1
    pts_lo = [(X(i0 + 1 + j), Y(fut_v[j])) for j in range(len(fut_v))]
    pts_hi = [(X(i0 + 1 + j), Y(fut_ub[j])) for j in range(len(fut_v))]
    band = 'M %s L %s Z' % (' L '.join('%.0f,%.0f' % p for p in pts_lo), ' L '.join('%.0f,%.0f' % p for p in reversed(pts_hi)))
    parts.append('<path d="%s" fill="#2e6da4" opacity="0.18"/>' % band)
    # 实际折线
    d = 'M ' + ' L '.join('%.0f,%.0f' % (X(i), Y(v)) for i, v in enumerate(hist_v))
    parts.append('<path d="%s" fill="none" stroke="#5ba4d8" stroke-width="2"/>' % d)
    # 预测虚线（基准）
    d2 = 'M %.0f,%.0f L ' % (X(i0), Y(hist_v[-1])) + ' L '.join('%.0f,%.0f' % (X(i0 + 1 + j), Y(fut_v[j])) for j in range(len(fut_v)))
    parts.append('<path d="%s" fill="none" stroke="#e8a13a" stroke-width="2" stroke-dasharray="7 5"/>' % d2)
    # 年份刻度
    for yi, y in enumerate(['2020', '2021', '2022', '2023', '2024', '2025', '2026', '2027']):
        idx = next((i for i, m in enumerate(hist['月']) if m.startswith(y)), None)
        if idx is not None:
            parts.append('<text x="%.0f" y="%d" fill="#7d93ab" font-size="11" text-anchor="middle">%s</text>' % (X(idx), H - pad + 18, y))
    idx27 = N - 7
    parts.append('<text x="%.0f" y="%d" fill="#e8a13a" font-size="11" text-anchor="middle">2027</text>' % (X(idx27), H - pad + 18))
    parts.append('<line x1="%.0f" y1="%d" x2="%.0f" y2="%d" stroke="#3a5878" stroke-dasharray="3 4"/>' % (X(i0), pad, X(i0), H - pad))
    parts.append('<text x="%.0f" y="%d" fill="#a9bcd1" font-size="11" text-anchor="middle">↓ 预测起点</text>' % (X(i0), pad + 14))
    parts.append('</svg>')
    return ''.join(parts)

# ---------- HTML 组装 ----------
CSS = """
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:'Microsoft YaHei','PingFang SC','Segoe UI',sans-serif; background:#0b1a2b; color:#dbe6f2; font-size:14px; }
nav { position:sticky; top:0; z-index:9; background:rgba(11,26,43,.96); border-bottom:1px solid #233c55; padding:10px 28px; display:flex; gap:18px; flex-wrap:wrap; }
nav a { color:#8fb3d4; text-decoration:none; font-size:12.5px; padding:4px 10px; border-radius:12px; }
nav a:hover { background:#16304d; color:#fff; }
.wrap { max-width:1400px; margin:0 auto; padding:26px 28px 60px; }
h1 { font-size:23px; color:#fff; margin:6px 0 4px; }
.sub { color:#7d93ab; font-size:12.5px; margin-bottom:18px; }
h2 { font-size:17px; color:#fff; margin:34px 0 12px; padding-left:12px; border-left:4px solid #2e6da4; }
.cards { display:flex; gap:16px; flex-wrap:wrap; }
.card { flex:1; min-width:300px; background:#10233a; border:1px solid #233c55; border-radius:10px; padding:16px 18px; }
.card .t { font-size:13px; color:#8fb3d4; margin-bottom:8px; }
.card .v { font-size:26px; font-weight:700; color:#fff; }
.card .v small { font-size:14px; color:#5ba4d8; font-weight:600; }
.card .r { font-size:11.5px; color:#7d93ab; margin-top:6px; line-height:1.6; }
.panel { background:#10233a; border:1px solid #233c55; border-radius:10px; padding:16px 18px; margin-top:10px; }
table { border-collapse:collapse; width:100%; margin-top:8px; }
th { background:#0f2b46; color:#cfe0f0; padding:7px 8px; font-size:12px; text-align:right; white-space:nowrap; }
th:first-child, td:first-child { text-align:left; }
td { border-bottom:1px solid #1b3450; padding:6px 8px; text-align:right; font-variant-numeric:tabular-nums; font-size:12.5px; }
tr:nth-child(even) td { background:#0d1f35; }
.grade { display:inline-block; min-width:22px; text-align:center; border-radius:4px; font-weight:700; font-size:11.5px; padding:2px 6px; }
.gA { background:#1d5c40; color:#7fe0ae; } .gB { background:#6b5314; color:#ffd97a; } .gC { background:#632626; color:#ff9d9d; }
.note { background:#13293f; border-left:3px solid #e8a13a; padding:10px 14px; border-radius:0 8px 8px 0; font-size:12.5px; line-height:1.75; color:#c4d6e8; margin-top:12px; }
.flow { display:flex; align-items:center; gap:8px; flex-wrap:wrap; margin-top:10px; }
.step { background:#16304d; border:1px solid #2e6da4; color:#cfe0f0; border-radius:8px; padding:9px 13px; font-size:12.5px; }
.arrow { color:#2e6da4; font-size:17px; }
.badge { display:inline-block; background:#1d5c40; color:#7fe0ae; border-radius:12px; padding:4px 12px; font-size:12px; margin:4px 6px 0 0; }
.grid2 { display:grid; grid-template-columns:1fr 1fr; gap:14px; }
.hit { color:#7fe0ae; font-weight:700; } .miss { color:#ff9d9d; font-weight:700; }
.kpi { font-size:12px; color:#7d93ab; }
ul.flowdesc { margin:8px 0 0 20px; line-height:1.8; color:#c4d6e8; font-size:12.5px; }
"""

H = []
H.append('<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8"><title>月度滚动预测驾驶舱</title><style>%s</style></head><body>' % CSS)
H.append('<nav>')
for i, s in enumerate(['执行摘要', '方法体系', '分月预测', '产品线明细', '置信度全景', '准确度验证', '历史趋势', '口径说明'], 1):
    H.append('<a href="#s%d">%d. %s</a>' % (i, i, s))
H.append('</nav><div class="wrap">')
H.append('<h1>月度滚动预测驾驶舱</h1>')
H.append('<div class="sub">生成 2026-09-16 ｜ 数据截至 2026-08（80 个月长历史标定）｜ 口径：RMB 未税 ｜ 单位：万元</div>')

# 一、执行摘要
H.append('<h2 id="s1">一、执行摘要</h2><div class="cards">')
for t, v, v2, r in [
    ('2026 全年（1-8月实际 + 9-12月预测）', '%s <small>（%.2f 亿）</small>' % ('{:,.0f}'.format(S4), S4 / 1e4),
     '无偏口径 {:,.0f} 万（{:.2f} 亿）'.format(S4 * F - ytd * (F - 1), (S4 * F - ytd * (F - 1)) / 1e4),
     '八成把握区间 86,906 ~ 90,662 万'),
    ('未来 6 个月（2026-09 ~ 2027-02）', '%s <small>（%.2f 亿）</small>' % ('{:,.0f}'.format(S6), S6 / 1e4),
     '无偏口径 {:,.0f} 万'.format(S6 * F), '八成把握区间 45,193 ~ 49,981 万'),
    ('未来 12 个月（2026-09 ~ 2027-08）', '%s <small>（%.2f 亿）</small>' % ('{:,.0f}'.format(S12), S12 / 1e4),
     '无偏口径 {:,.0f} 万'.format(S12 * F), '八成把握区间 91,687 ~ 98,396 万')]:
    H.append('<div class="card"><div class="t">%s</div><div class="v">%s</div><div class="kpi" style="margin-top:6px;color:#5ba4d4;font-weight:600">%s</div><div class="r">%s</div></div>' % (t, v, v2, r))
H.append('</div>')
H.append('<div class="note"><b>本月修订（2026-09-16，长历史春节标定）：</b>2027-01 由 11,129 下修至 <b style="color:#e8a13a">10,226 万</b>（三法取中，避免高增长年高估）；2027-02 调整为 <b style="color:#e8a13a">5,420 万</b>（历史上 4 个"春节在 2 月"年份的低谷规律：前月的 53%）；<b>2026 全年预测不变</b>。</div>')

# 二、方法体系
H.append('<h2 id="s2">二、方法体系</h2><div class="panel">')
H.append('<div class="flow"><div class="step">数据底座<br><span class="kpi">2020-2026 · 80 个月</span></div><span class="arrow">→</span>'
         '<div class="step">冠军规则<br><span class="kpi">平时=近6月平均<br>春节月=分桶规则(n=6)</span></div><span class="arrow">→</span>'
         '<div class="step">线级锚定<br><span class="kpi">各线选优后对齐总量</span></div><span class="arrow">→</span>'
         '<div class="step">品类/SKU 分配<br><span class="kpi">份额法</span></div><span class="arrow">→</span>'
         '<div class="step">无偏校正<br><span class="kpi">×1.040</span></div><span class="arrow">→</span>'
         '<div class="step">区间输出<br><span class="kpi">八成把握带</span></div></div>')
H.append('<div style="margin-top:10px">'
         '<span class="badge">20 折回测验证</span><span class="badge">56 折长历史重检</span>'
         '<span class="badge">多智能体复核通过</span><span class="badge">融合测试端到端</span>'
         '<span class="badge">方向准确率 74%（目标 65%）</span></div>')
H.append('<ul class="flowdesc"><li>验证基础：公司月度平均误差 7.7%，无偏校正后 6.9%；方向判断（涨/跌）命中率 74%</li>'
         '<li>方法池：上月延续 / 近3·6·12月平均 / 去年同月 / 趋势外推等 8 种，每条产品线按近期历史回测自动选优</li>'
         '<li>与上一代（归档 2026-06 季度体系）关系：方法主干经对照评估确认延续，新增春节规则/无偏校正/区间输出</li></ul></div>')

# 三、分月预测
H.append('<h2 id="s3">三、分月预测（万元）</h2><div class="panel">')
H.append(svg_bars_monthly(comp))
H.append('<table><tr><th>月</th><th>基准</th><th>无偏口径</th><th>预测规则（通俗）</th></tr>')
RULE_CN = {'ma6': '近 6 个月平均'}
def rule_cn(t):
    if t == 'ma6': return '近 6 个月平均'
    if t.startswith('phase3中枢'): return '春节前月·三法取中（去年1月×增速 / 上年12月×冲量 / 2024年1月×两年增速）'
    if t.startswith('cny02'): return '春节低谷月：前一月 × 53%（4 个同类年份的中位规律）'
    return t
for _, r in comp.iterrows():
    cny = r['月'] in ('2027-01', '2027-02')
    H.append('<tr%s><td>%s</td><td>%s</td><td>%s</td><td style="text-align:left">%s</td></tr>' % (
        ' style="background:#152740"' if cny else '', r['月'], '{:,.0f}'.format(r['基准万']), '{:,.0f}'.format(r['无偏万']), rule_cn(str(r['规则']))))
H.append('</table><div class="kpi" style="margin-top:6px">橙色横条为 2027 年春节月（规则与常规月不同）。</div></div>')

# 四、产品线明细
H.append('<h2 id="s4">四、产品线明细（万元；已对齐公司总量）</h2><div class="panel">')
H.append('<table><tr><th>产品线</th><th>采用的算法</th><th>9-12月合计</th><th>未来6个月</th><th>未来12个月</th><th>金额占比</th><th>置信档</th></tr>')
conf_map = {r['产品线']: (r['金额占比%'], r['置信档'], r['WAPE%']) for _, r in conf.iterrows()}
m4 = ['2026-09', '2026-10', '2026-11', '2026-12']
m6 = FUT_MONTHS[:6]
tot4 = tot6 = tot12 = totshare = 0
for k in line_fc.index:
    v4 = sum(pd.to_numeric(line_fc.loc[k, m], errors='coerce') for m in m4) / 1e4
    v6 = sum(pd.to_numeric(line_fc.loc[k, m], errors='coerce') for m in m6) / 1e4
    v12 = sum(pd.to_numeric(line_fc.loc[k, m], errors='coerce') for m in FUT_MONTHS) / 1e4
    share, g, w = conf_map.get(k, (0, 'C', 0))
    tot4 += v4; tot6 += v6; tot12 += v12; totshare += share
    mc = {'naive': '上月延续', 'ma3': '近3月平均', 'ma6': '近6月平均', 'ma12': '近12月平均', 'snaive': '去年同月',
          'yoy_adj': '去年同月×增速', 'trend6': '近6月趋势外推', 'trend12': '近12月趋势外推'}.get(str(line_fc.loc[k, '选优方法']), str(line_fc.loc[k, '选优方法']))
    H.append('<tr><td>%s</td><td style="text-align:left">%s</td><td>%s</td><td>%s</td><td>%s</td><td>%.1f%%</td><td><span class="grade g%s">%s</span> <span class="kpi">%.0f%%</span></td></tr>' % (
        k, mc, '{:,.0f}'.format(v4), '{:,.0f}'.format(v6), '{:,.0f}'.format(v12), share, g, g, w))
H.append('<tr style="background:#173355;font-weight:700"><td>合计</td><td></td><td>%s</td><td>%s</td><td>%s</td><td>100%%</td><td></td></tr>' % (
    '{:,.0f}'.format(tot4), '{:,.0f}'.format(tot6), '{:,.0f}'.format(tot12)))
H.append('</table></div>')

# 五、置信度全景
cnt = conf['置信档'].value_counts()
share_by = conf.groupby('置信档')['金额占比%'].sum()
H.append('<h2 id="s5">五、置信度全景（怎么用这些数）</h2><div class="panel">')
H.append('<div class="cards">')
for g, desc in [('A', '误差 ≤15%：可直接用于目标与计划'), ('B', '误差 15-25%：可用，留 1/5 余量'), ('C', '误差 >25%：仅看结构方向，建议人工复核')]:
    n = int(cnt.get(g, 0)); s = share_by.get(g, 0)
    H.append('<div class="card"><div class="t"><span class="grade g%s">%s</span> 档 · %d 条产品线</div><div class="v" style="font-size:19px">覆盖 %.0f%% 销售额</div><div class="r">%s</div></div>' % (g, g, n, s, desc))
H.append('</div>')
H.append('<table><tr><th>产品线（置信度升序）</th><th>月度误差</th><th>金额占比</th><th>建议</th></tr>')
for _, r in conf.sort_values('WAPE%').iterrows():
    advice = '可直接使用' if r['置信档'] == 'A' else ('可用，留余量' if r['置信档'] == 'B' else '结构参考，人工复核')
    H.append('<tr><td>%s</td><td><span class="grade g%s">%s</span> %.1f%%</td><td>%.1f%%</td><td style="text-align:left;color:#8fb3d4">%s</td></tr>' % (
        r['产品线'], r['置信档'], r['置信档'], r['WAPE%'], r['金额占比%'], advice))
H.append('</table>')
H.append('<div class="note"><b>使用指引：</b>头部线（通用电源管理，占 63% 金额、误差 9.4%）+ B 档 4 条合计覆盖约 90% 销售额——<b>大数是硬的</b>；C 档 12 条仅占 ~11% 金额，用于看结构占比与方向，不建议直接引用具体数字。SKU 级明细误差普遍 30%+，仅做方向参考。</div></div>')

# 六、准确度验证
H.append('<h2 id="s6">六、准确度验证</h2><div class="panel">')
H.append('<div class="kpi" style="margin-bottom:4px">预测价值added阶梯（FVA）：每一步带来多少真实改善</div>')
H.append(svg_fva_ladder())
H.append('<div class="kpi" style="margin:14px 0 4px">方向准确率：预测下月涨还是跌（19 个回测月）</div>')
H.append(svg_dir_bars())
H.append('<div style="margin-top:10px" class="kpi">逐月命中明细（✓ 方向正确 / ✗ 方向错误）：</div><div>')
for _, r in r3.iterrows():
    H.append('<span title="%s 实际%s 预测%s" style="display:inline-block;margin:3px 4px;padding:3px 8px;border-radius:6px;font-size:11.5px;background:%s">%s <b class="%s">%s</b></span>' % (
        r['月'], '↑' if r['实际向'] > 0 else '↓', '↑' if r['预测向'] > 0 else '↓',
        '#12283f' if r['命中'] else '#3a1e1e', r['月'][2:].replace('-', '/'), 'hit' if r['命中'] else 'miss', '✓' if r['命中'] else '✗'))
H.append('</div></div>')

# 七、历史趋势
H.append('<h2 id="s7">七、历史趋势与预测延展（80 个月 + 12 个月）</h2><div class="panel">')
H.append(svg_history())
H.append('<div class="kpi" style="margin-top:6px">蓝线=实际（2020-01~2026-08）；橙虚线=未来 12 个月基准预测；蓝色带≈基准~无偏区间。2020 为业务起步年（2.0 亿）→ 2025 达 6.75 亿 → 2026 预计 8.72 亿（+29%）。</div></div>')

# 八、口径说明
H.append('<h2 id="s8">八、口径与说明（通俗版）</h2><div class="panel"><ul class="flowdesc">')
for li in ['<b>先定总量再往下分：</b>先预测全公司每月总额，产品线/品类各自预测后按比例对齐——各层加总严格等于总量，大数稳、小数看结构。',
           '<b>平时月份</b>用最近 6 个月平均值向前滚动（56 个月回测选出的最稳方案）；<b>春节月份</b>用过去 6 个春节年份的实际规律：节前月多约 17%（客户提前备货）、假期所在月约为前月 53%。',
           '<b>两列数的用法：</b>"基准"日常跟进用；"无偏口径"（×1.040）修正系统性低估，定目标报计划用。',
           '<b>单价未单独预测</b>（回测显示对总精度提升很小）：若有已知涨价/降价，请在基数上人工加减。',
           '<b>客户维度不下分</b>：按客户逐个预测再汇总误差反而更大（小客户噪声多），客户分析见月度经营看板。',
           '<b>数据基础：</b>ERP 出货明细 2020-01~2026-08，不含税人民币；2024 年前数据来自冻结历史总表，与现行口径逐月核对一致（0.000% 差）。',
           '<b>局限：</b>转折点月（大单/急单）属尾随方法固有盲区，需业务情报补位；2027-01/02 含假期假设（春节 2/6），国务院安排公布后可微调。']:
    H.append('<li>%s</li>' % li)
H.append('</ul></div>')
H.append('<div class="sub" style="margin-top:18px;color:#5a7290">生成脚本：月度滚动预测_20260910/生成预测驾驶舱.py ｜ 数据源：交付 CSV × 6 ｜ 2026-09-16</div>')
H.append('</div></body></html>')

import os
os.makedirs(os.path.dirname(DEST), exist_ok=True)
with open(DEST, 'w', encoding='utf-8') as f:
    f.write('\n'.join(H))
print('已生成:', DEST, '(%.0f KB)' % (os.path.getsize(DEST) / 1024))
