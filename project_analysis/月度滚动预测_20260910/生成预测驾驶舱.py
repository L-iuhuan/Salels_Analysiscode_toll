# -*- coding: utf-8 -*-
"""预测驾驶舱 v2（交互版）：平台看板 token + 翻转卡 + ECharts 交互
参考：预测看板_20260916/参考_翻转看板_index.html 的翻转方法（kpi-card/kpi-inner/kpi-face/flipped）
设计体系：sales_analytics_platform/dashboard/template.html 的 CSS 变量（浅色 #f5f6f8/#2563EB）
"""
import sys
import json
import pandas as pd
import numpy as np
sys.stdout.reconfigure(encoding='utf-8')

OUT = r'E:\3-其他资料\数据分析\project_analysis\月度滚动预测_20260910'
DEST = r'E:\3-其他资料\数据分析\project_analysis\预测看板_20260916\预测驾驶舱.html'

comp = pd.read_csv(OUT + r'\交付_公司分月.csv')
line_fc = pd.read_csv(OUT + r'\交付_产品线.csv', index_col=0)
conf = pd.read_csv(OUT + r'\看板数据_线级置信分层.csv')
r3 = pd.read_csv(OUT + r'\R3_方向准确率_公司口径.csv')
hist = pd.read_csv(OUT + r'\公司月度长序列80月.csv')

comp['基准万'] = comp['预测'] / 1e4
comp['无偏万'] = comp['无偏'] / 1e4
hist万 = [v / 1e4 for v in hist['金额']]
FUT = list(comp['月'])
F = 1.040
ytd = sum(v for m, v in zip(hist['月'], hist万) if m >= '2026-01')
S4 = round(comp[comp['月'] <= '2026-12']['基准万'].sum() + ytd)
S6 = round(comp['基准万'][:6].sum())
S12 = round(comp['基准万'].sum())
S4F = round((S4 - ytd) * F + ytd)  # 无偏只作用于预测部分（与交付报告口径一致）
S6F = round(comp['基准万'][:6].sum() * F)
S12F = round(comp['基准万'].sum() * F)
F = 1.040

# 注入 JS 的数据
DATA = {
    'months': FUT,
    'base': [float(x) for x in comp['基准万']],
    'unbiased': [float(x) for x in comp['无偏万']],
    'histMonths': list(hist['月']),
    'histVal': [float(x) for x in hist万],
    'lines': [], 'fva': [['上月延续', 14.7], ['近6月平均', 10.3], ['冠军组合(春节规则)', 7.9], ['线级锚定', 7.4], ['无偏校正', 6.9]],
    'dirMethods': [['近6月平均', 58], ['工作日法', 63], ['组合预测', 68], ['冠军量价系统', 74]],
    'r3': [{'m': r['月'][2:].replace('-', '/'), 'hit': int(r['命中'])} for _, r in r3.iterrows()],
}
for _, r in conf.iterrows():
    v6 = sum(pd.to_numeric(line_fc.loc[r['产品线'], m], errors='coerce') for m in FUT[:6]) / 1e4
    v12 = sum(pd.to_numeric(line_fc.loc[r['产品线'], m], errors='coerce') for m in FUT) / 1e4
    DATA['lines'].append({'n': r['产品线'], 'share': float(r['金额占比%']), 'wape': float(r['WAPE%']), 'g': r['置信档'], 'v6': round(float(v6)), 'v12': round(float(v12))})

CSS = """
:root{--bg:#f5f6f8;--card:#fff;--text:#1E293B;--sub:#64748B;--bdr:#e2e8f0;--blue:#2563EB;
--danger:#EF4444;--success:#10B981;--warning:#F59E0B;--sky:#0EA5E9;--blue-soft:#EFF6FF;--blue-hover:#DBEAFE;
--radius-sm:6px;--radius-md:8px;--radius-lg:12px;--gap-sm:8px;--gap-md:16px;--gap-lg:20px;
--shadow-sm:0 1px 2px rgba(15,23,42,.04);--shadow-md:0 4px 12px rgba(15,23,42,.06);--shadow-lg:0 12px 32px rgba(15,23,42,.10);
--font-sm:12px;--font-md:13px;--font-card-title:14px;--font-lg:16px;--font-display:28px;
--stripe:#F6F7F9}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--bg);color:var(--text);font-family:-apple-system,'Microsoft YaHei','Segoe UI',sans-serif;font-size:14px;line-height:1.5}
.page{max-width:1440px;margin:0 auto;padding:var(--gap-lg)}
header{background:var(--card);border:1px solid var(--bdr);border-radius:var(--radius-lg);box-shadow:var(--shadow-sm);padding:14px 20px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:var(--gap-sm)}
h1{font-size:var(--font-lg);font-weight:600}
.sub{color:var(--sub);font-size:var(--font-sm)}
.badge{display:inline-block;background:var(--blue-soft);color:var(--blue);border-radius:12px;padding:3px 10px;font-size:var(--font-sm);margin-left:6px}
.badge.g{background:#ECFDF5;color:#059669}.badge.o{background:#FFFBEB;color:#B45309}
h2{font-size:var(--font-card-title);font-weight:600;margin:22px 0 10px;display:flex;align-items:center;gap:6px}
h2 .n{background:var(--blue);color:#fff;border-radius:6px;width:20px;height:20px;display:inline-flex;align-items:center;justify-content:center;font-size:11px}
/* 翻转卡（方法移植自参考看板） */
.kpi-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:var(--gap-md)}
@media(max-width:1100px){.kpi-grid{grid-template-columns:repeat(2,1fr)}}
.kpi-card{perspective:1000px;cursor:pointer}
.kpi-inner{position:relative;width:100%;min-height:148px;transition:transform .6s cubic-bezier(.4,0,.2,1);transform-style:preserve-3d}
.kpi-card.flipped .kpi-inner{transform:rotateY(180deg)}
.kpi-face{position:absolute;inset:0;backface-visibility:hidden;-webkit-backface-visibility:hidden;background:var(--card);border:1px solid var(--bdr);border-radius:var(--radius-lg);box-shadow:var(--shadow-sm);padding:16px 18px;overflow:hidden;transition:box-shadow .3s,border-color .3s}
.kpi-face:hover{box-shadow:var(--shadow-md);border-color:var(--blue-hover)}
.kpi-face::before{content:'';position:absolute;bottom:0;left:18%;right:18%;height:2px;background:linear-gradient(90deg,transparent,var(--blue),transparent);opacity:0;transition:opacity .3s}
.kpi-face:hover::before{opacity:.55}
.kpi-back{transform:rotateY(180deg)}
.kpi-label{font-size:var(--font-sm);color:var(--sub)}
.kpi-value{font-size:24px;font-weight:700;color:var(--text);margin:6px 0 2px;font-variant-numeric:tabular-nums}
.kpi-value small{font-size:13px;color:var(--sub);font-weight:600}
.kpi-hint{font-size:10.5px;color:var(--sub);opacity:.65;margin-top:4px}
.kpi-extra{font-size:11.5px;color:var(--blue);margin-top:3px;font-weight:600}
.kpi-glow{position:absolute;top:-26px;right:-26px;width:74px;height:74px;border-radius:50%;background:linear-gradient(135deg,var(--blue),var(--sky));opacity:.07;filter:blur(22px);pointer-events:none}
/* 图表卡 */
.chart-grid{display:grid;grid-template-columns:1fr 1fr;gap:var(--gap-md)}
.chart-card{background:var(--card);border:1px solid var(--bdr);border-radius:var(--radius-lg);box-shadow:var(--shadow-sm);padding:14px 16px}
.chart-card.wide{grid-column:1/-1}
.chart-title{font-size:var(--font-card-title);font-weight:600;margin-bottom:2px}
.chart-note{font-size:11.5px;color:var(--sub);margin-bottom:8px}
.chart-body{height:320px}
.chart-body.tall{height:380px}
/* 表格 */
table{border-collapse:collapse;width:100%;margin-top:6px;font-size:var(--font-md)}
th{background:var(--blue);color:#fff;padding:7px 9px;font-size:var(--font-sm);text-align:right;white-space:nowrap;font-weight:600}
th:first-child,td:first-child{text-align:left}
td{border-bottom:1px solid var(--bdr);padding:6px 9px;text-align:right;font-variant-numeric:tabular-nums}
tbody tr:nth-child(even){background:var(--stripe)}
tbody tr:hover{background:var(--blue-hover)}
.grade{display:inline-block;min-width:20px;text-align:center;border-radius:4px;font-weight:700;font-size:11px;padding:1px 6px}
.gA{background:#ECFDF5;color:#059669}.gB{background:#FFFBEB;color:#B45309}.gC{background:#FEF2F2;color:#DC2626}
.note{background:var(--blue-soft);border-left:3px solid var(--blue);padding:10px 14px;border-radius:0 var(--radius-md) var(--radius-md) 0;font-size:12.5px;line-height:1.75;color:var(--text);margin-top:12px}
.chips{display:flex;gap:8px;flex-wrap:wrap;margin:6px 0 2px}
.chip{border:1px solid var(--bdr);background:var(--card);border-radius:14px;padding:3px 12px;font-size:12px;cursor:pointer;color:var(--sub)}
.chip.active{background:var(--blue);color:#fff;border-color:var(--blue)}
.hit-tl{display:flex;gap:5px;flex-wrap:wrap;margin-top:8px}
.tl{display:inline-flex;gap:6px;align-items:center;border:1px solid var(--bdr);border-radius:6px;padding:2px 8px;font-size:11px;background:var(--card)}
.tl b{font-size:12px}
details{background:var(--card);border:1px solid var(--bdr);border-radius:var(--radius-lg);padding:12px 16px;margin-top:10px}
summary{font-weight:600;cursor:pointer;font-size:var(--font-card-title)}
details ul{margin:8px 0 2px 20px;line-height:1.9;color:var(--text);font-size:12.5px}
footer{color:var(--sub);font-size:11.5px;text-align:center;margin:26px 0 8px}
"""

def flip_card(front_html, back_html, glow=''):
    return ('<div class="kpi-card" onclick="flipCard(this)"><div class="kpi-inner">'
            '<div class="kpi-face kpi-front">%s</div>'
            '<div class="kpi-face kpi-back">%s</div></div></div>' % (front_html, back_html))

def face(label, value, extra, hint, glow=''):
    return '<div class="kpi-glow"%s></div><div class="kpi-label">%s</div><div class="kpi-value">%s</div><div class="kpi-extra">%s</div><div class="kpi-hint">%s</div>' % (
        " style=\"background:linear-gradient(135deg,%s)\"" % glow if glow else '', label, value, extra, hint)

H = []
H.append('<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8"><title>月度滚动预测驾驶舱</title>')
H.append('<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>')
H.append('<style>%s</style></head><body><div class="page">' % CSS)

H.append('<header><div><h1>月度滚动预测驾驶舱 <span class="badge">20+56 折验证</span><span class="badge g">方向准确率 74%</span><span class="badge o">2027-01 已修订</span></h1>'
         '<div class="sub">生成 2026-09-16 ｜ 数据截至 2026-08（80 个月长历史标定）｜ RMB 未税 ｜ 单位：万元</div></div>'
         '<div class="sub">点击卡片可翻转查看无偏口径</div></header>')

# KPI 翻转卡（正=基准，背=无偏）
H.append('<h2><span class="n">1</span>三个数（点击翻转）</h2><div class="kpi-grid">')
H.append(flip_card(
    face('2026 全年 · 基准', '{:,.0f}<small>（{:.2f} 亿）</small>'.format(S4, S4 / 1e4), '1-8月实际 + 9-12月预测', '点击翻转 → 无偏口径'),
    face('2026 全年 · 无偏', '{:,.0f}<small>（{:.2f} 亿）</small>'.format(S4F, S4F / 1e4), '基准 × 1.040（修正系统性低估）', '八成区间 86,906~90,662')))
H.append(flip_card(
    face('未来 6 个月 · 基准', '{:,.0f}<small>（{:.2f} 亿）</small>'.format(S6, S6 / 1e4), '2026-09 ~ 2027-02', '点击翻转 → 无偏口径'),
    face('未来 6 个月 · 无偏', '{:,.0f}'.format(S6F), '含春节月规则标定（n=6）', '八成区间 45,193~49,981')))
H.append(flip_card(
    face('未来 12 个月 · 基准', '{:,.0f}<small>（{:.2f} 亿）</small>'.format(S12, S12 / 1e4), '2026-09 ~ 2027-08', '点击翻转 → 无偏口径'),
    face('未来 12 个月 · 无偏', '{:,.0f}'.format(S12F), '定目标报计划用无偏口径', '八成区间 91,687~98,396')))
H.append(flip_card(
    face('月度平均误差', '6.9<small>%</small>', '无偏校正后（校正前 7.7%）', '点击翻转 → 误差阶梯'),
    face('误差改善阶梯', '14.7 → 10.3 → 7.9 → 6.9', '上月延续→近6月均→冠军组合→无偏', '单位：%（越低越好）'),
    ''))
H.append(flip_card(
    face('方向准确率', '74<small>%</small>', '涨跌方向命中 14/19 月', '点击翻转 → 各方法对比'),
    face('方向准确率对比', '58 / 63 / 68 / 74', '近6月均/工作日法/组合/冠军量价', '目标 ≥65%（冠军达标）'),
    'linear-gradient(135deg,#10B981,#34D399)'))
H.append('</div>')
H.append('<div class="note"><b>本月修订（2026-09-16）：</b>2027-01 由 11,129 下修至 <b>10,226 万</b>（三法取中）；2027-02 = <b>5,420 万</b>（春节低谷桶：前月×53%）；<b>2026 全年不变</b>。</div>')

# 图表区
H.append('<h2><span class="n">2</span>预测图表（可交互）</h2><div class="chart-grid">')
H.append('<div class="chart-card wide"><div class="chart-title">80 个月历史 + 12 个月预测延展</div><div class="chart-note">蓝色实线=实际（2020-01~2026-08）；橙色虚线=未来 12 月基准预测；浅蓝带=基准~无偏区间；底部滑块可缩放时间轴</div><div class="chart-body tall" id="cHist"></div></div>')
H.append('<div class="chart-card"><div class="chart-title">分月预测：基准 vs 无偏</div><div class="chart-note">悬停看数值；点图例可隐藏系列；橙色月份为春节规则月</div><div class="chart-body" id="cMonth"></div></div>')
H.append('<div class="chart-card"><div class="chart-title">产品线：误差 vs 金额占比</div><div class="chart-note">横轴=月度误差（越左越好）；气泡大小=金额占比；颜色=置信档</div><div class="chart-body" id="cScatter"></div></div>')
H.append('<div class="chart-card"><div class="chart-title">误差改善阶梯（FVA）</div><div class="chart-note">每步方法的真实贡献，越低越好</div><div class="chart-body" id="cFva"></div></div>')
H.append('<div class="chart-card"><div class="chart-title">方向准确率（涨跌判断）</div><div class="chart-note">虚线=65% 目标；19 个回测月</div><div class="chart-body" id="cDir"></div></div>')
H.append('</div>')

# 逐月命中时间线
hits = ''.join('<span class="tl">%s <b style="color:%s">%s</b></span>' % (h['m'], '#059669' if h['hit'] else '#DC2626', '✓' if h['hit'] else '✗') for h in DATA['r3'])
H.append('<div class="chart-card wide" style="margin-top:14px"><div class="chart-title">逐月方向命中时间线</div><div class="chart-note">19 个回测月的涨跌方向判断结果（绿=命中 / 红=未中）</div><div class="hit-tl">%s</div></div>' % hits)

# 产品线明细
H.append('<h2><span class="n">3</span>产品线明细（万元）</h2><div class="chart-card"><table><thead><tr><th>产品线</th><th>置信档</th><th>月度误差</th><th>金额占比</th><th>未来6个月</th><th>未来12个月</th></tr></thead><tbody id="lineBody"></tbody></table></div>')

# 置信度
H.append('<h2><span class="n">4</span>置信度全景（点击翻转看清单）</h2><div class="kpi-grid" style="grid-template-columns:repeat(3,1fr)">')
for g, desc, glow in [('A', '误差 ≤15% 可直接用于目标', 'linear-gradient(135deg,#10B981,#34D399)'),
                      ('B', '误差 15-25% 可用留余量', 'linear-gradient(135deg,#F59E0B,#FBBF24)'),
                      ('C', '误差 >25% 仅看结构方向', 'linear-gradient(135deg,#EF4444,#F87171)')]:
    sub = conf[conf['置信档'] == g]
    share = sub['金额占比%'].sum()
    lines_str = '、'.join(sub.sort_values('WAPE%')['产品线'].head(6)) + ('…' if len(sub) > 6 else '')
    H.append(flip_card(
        face('%s 档 · %d 条产品线' % (g, len(sub)), '%.0f<small>%% 销售额</small>' % share, desc, '点击翻转 → 档内清单', glow),
        face('%s 档清单' % g, '%.0f%%' % share, lines_str, '误差 %s' % ('≤15%' if g == 'A' else ('15-25%' if g == 'B' else '>25%')), glow)))
H.append('</div>')
H.append('<div class="note"><b>使用指引：</b>头部线（通用电源管理，63% 金额、误差 9.4%）+ B 档 4 条覆盖约 90% 销售额——<b>大数是硬的</b>；C 档 12 条仅占 ~11% 金额，看结构不引数字；SKU 级仅做方向参考。</div>')

# 口径说明
H.append('''<h2><span class="n">5</span>口径与说明</h2><details open><summary>通俗版方法说明（点标题折叠）</summary><ul>
<li><b>先定总量再往下分：</b>先预测全公司每月总额，产品线/品类各自预测后按比例对齐——各层加总严格等于总量。</li>
<li><b>平时月份</b>用最近 6 个月平均滚动；<b>春节月份</b>用 6 个春节年份的实际规律：节前月 +17%（客户备货）、假期月约为前月 53%。</li>
<li><b>两列数用法：</b>"基准"日常跟；"无偏"（×1.040）修正系统性低估，定目标用。</li>
<li><b>单价未单独建模</b>（对总精度提升很小）：已知调价请人工加减。</li>
<li><b>局限：</b>大单/急单转折月属方法盲区需业务情报补位；2027-01/02 含假期假设（春节 2/6），安排公布后可微调。</li>
</ul></details>''')
H.append('<footer>生成脚本：月度滚动预测_20260910/生成预测驾驶舱.py ｜ 数据源：交付 CSV ×5 ｜ 交互方法参考：参考_翻转看板_index.html ｜ 设计体系：平台看板 token</footer>')
H.append('</div><script>')
H.append('const D = %s;' % json.dumps(DATA, ensure_ascii=False))

JS = '''
function flipCard(el){el.classList.toggle('flipped');}
const BLUE='#2563EB',SKY='#0EA5E9',GREEN='#10B981',RED='#EF4444',ORANGE='#F59E0B',SUB='#64748B';
const baseOpt={tooltip:{trigger:'axis',backgroundColor:'#fff',borderColor:'#e2e8f0',textStyle:{color:'#1E293B'}},
grid:{left:56,right:24,top:36,bottom:46}};
function mk(id,opt){const c=echarts.init(document.getElementById(id));c.setOption(opt);return c;}
const charts=[];
// 历史+预测
charts.push(mk('cHist',{...baseOpt,legend:{data:['实际','基准预测','无偏口径'],top:4},
tooltip:{...baseOpt.tooltip,trigger:'axis'},
dataZoom:[{type:'slider',start:55,end:100,height:18,bottom:6},{type:'inside'}],
xAxis:{type:'category',data:[...D.histMonths,...D.months],axisLabel:{color:SUB,interval:8}},
yAxis:{type:'value',axisLabel:{color:SUB},splitLine:{lineStyle:{color:'#e2e8f0'}}},
series:[
{name:'实际',type:'line',data:[...D.histVal,...Array(D.months.length).fill(null)],showSymbol:false,lineStyle:{width:2,color:SKY},itemStyle:{color:SKY}},
{name:'基准预测',type:'line',data:[...Array(D.histMonths.length-1).fill(null),D.histVal[D.histVal.length-1],...D.base],lineStyle:{width:2,type:'dashed',color:ORANGE},itemStyle:{color:ORANGE},symbol:'circle',symbolSize:5},
{name:'无偏口径',type:'line',data:[...Array(D.histMonths.length-1).fill(null),Math.round(D.histVal[D.histVal.length-1]*1.04),...D.unbiased],lineStyle:{width:1,type:'dotted',color:'#93C5FD'},itemStyle:{color:'#93C5FD'},symbol:'none'}]}));
// 分月
charts.push(mk('cMonth',{...baseOpt,legend:{data:['基准','无偏'],top:4},
xAxis:{type:'category',data:D.months.map(m=>m.slice(2).replace('-','/')),axisLabel:{color:SUB,rotate:38}},
yAxis:{type:'value',axisLabel:{color:SUB},splitLine:{lineStyle:{color:'#e2e8f0'}}},
series:[{name:'基准',type:'bar',data:D.base.map((v,i)=>({value:v,itemStyle:{color:[9,10].includes(i)||D.months[i]>='2027-01'?ORANGE:BLUE}})),barWidth:'34%',itemStyle:{borderRadius:[3,3,0,0]}},
{name:'无偏',type:'bar',data:D.unbiased,itemStyle:{color:'#93C5FD'},barWidth:'34%',itemStyle:{borderRadius:[3,3,0,0]}}]}));
// 散点
charts.push(mk('cScatter',{...baseOpt,tooltip:{formatter:p=>p.data[3]+'<br>误差 '+p.data[0]+'% ｜ 占比 '+p.data[1]+'%'},
xAxis:{name:'月度误差%',nameTextStyle:{color:SUB},axisLabel:{color:SUB},splitLine:{lineStyle:{color:'#e2e8f0'}}},
yAxis:{name:'金额占比%',nameTextStyle:{color:SUB},axisLabel:{color:SUB},splitLine:{lineStyle:{color:'#e2e8f0'}}},
series:[{type:'scatter',symbolSize:d=>6+Math.sqrt(d[1])*3.2,
data:D.lines.map(l=>[l.wape,l.share,l.n].slice(0,2).concat([l.n,l.g])),
itemStyle:{color:p=>p.data[3]==='A'?GREEN:(p.data[3]==='B'?ORANGE:RED),opacity:.78},
label:{show:true,formatter:p=>p.data[2].slice(0,6),position:'top',fontSize:10,color:SUB},
labelLayout:{hideOverlap:true}}]}));
// FVA
charts.push(mk('cFva',{...baseOpt,grid:{...baseOpt.grid,left:130},
xAxis:{type:'value',max:16,axisLabel:{color:SUB,formatter:'{value}%'},splitLine:{lineStyle:{color:'#e2e8f0'}}},
yAxis:{type:'category',data:D.fva.map(x=>x[0]).reverse(),axisLabel:{color:'#1E293B'}},
series:[{type:'bar',data:D.fva.map(x=>x[1]).reverse(),barWidth:'52%',
itemStyle:{color:p=>p.dataIndex===4?GREEN:BLUE,borderRadius:[0,4,4,0]},
label:{show:true,position:'right',formatter:'{c}%',color:'#1E293B',fontWeight:600}}]}));
// 方向
charts.push(mk('cDir',{...baseOpt,xAxis:{type:'category',data:D.dirMethods.map(x=>x[0]),axisLabel:{color:SUB,interval:0}},
yAxis:{type:'value',min:30,max:85,axisLabel:{color:SUB,formatter:'{value}%'},splitLine:{lineStyle:{color:'#e2e8f0'}}},
series:[{type:'bar',data:D.dirMethods.map(x=>x[1]),barWidth:'46%',
itemStyle:{color:p=>p.dataIndex===3?GREEN:BLUE,borderRadius:[4,4,0,0]},
label:{show:true,position:'top',formatter:'{c}%',color:'#1E293B',fontWeight:600},
markLine:{silent:true,symbol:'none',lineStyle:{color:ORANGE,type:'dashed'},label:{formatter:'目标 65%',color:ORANGE},data:[{yAxis:65}]}}]}));
// 产品线表
document.getElementById('lineBody').innerHTML = D.lines.map(l=>'<tr><td>'+l.n+'</td><td><span class="grade g'+l.g+'">'+l.g+'</span></td><td>'+l.wape.toFixed(1)+'%</td><td>'+l.share.toFixed(1)+'%</td><td>'+l.v6.toLocaleString()+'</td><td>'+l.v12.toLocaleString()+'</td></tr>').join('');
window.addEventListener('resize',()=>charts.forEach(c=>c.resize()));
'''
H.append(JS)
H.append('</script></body></html>')

import os
os.makedirs(os.path.dirname(DEST), exist_ok=True)
with open(DEST, 'w', encoding='utf-8') as f:
    f.write('\n'.join(H))
print('已生成 v2:', DEST, '(%.0f KB)' % (os.path.getsize(DEST) / 1024))
