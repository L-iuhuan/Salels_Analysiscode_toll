# -*- coding: utf-8 -*-
"""预测驾驶舱 v3：平台看板体系同构面
- 样式：platform_style.html（平台 template.html CSS 全段原样）
- 组件：tab-bar/kpi-bar>kc（点击翻转）/cb>h3(fa-icon)/data-table/yrf 筛选
- 交互：ECharts 图表 + 基准↔无偏全局切换（平台 yrf 模式）+ KPI 翻转
"""
import sys
import json
import pandas as pd
sys.stdout.reconfigure(encoding='utf-8')

OUT = r'E:\3-其他资料\数据分析\project_analysis\月度滚动预测_20260910'
DEST = r'E:\3-其他资料\数据分析\project_analysis\预测看板_20260916\预测驾驶舱.html'
STYLE = r'E:\3-其他资料\数据分析\project_analysis\预测看板_20260916\platform_style.html'

comp = pd.read_csv(OUT + r'\交付_公司分月.csv')
line_fc = pd.read_csv(OUT + r'\交付_产品线.csv', index_col=0)
conf = pd.read_csv(OUT + r'\看板数据_线级置信分层.csv')
r3 = pd.read_csv(OUT + r'\R3_方向准确率_公司口径.csv')
hist = pd.read_csv(OUT + r'\公司月度长序列80月.csv')
platform_css = open(STYLE, encoding='utf-8').read()

comp['基准万'] = comp['预测'] / 1e4
comp['无偏万'] = comp['无偏'] / 1e4
hist万 = [v / 1e4 for v in hist['金额']]
FUT = list(comp['月'])
F = 1.040
ytd = sum(v for m, v in zip(hist['月'], hist万) if m >= '2026-01')
S4 = round(comp[comp['月'] <= '2026-12']['基准万'].sum() + ytd)
S6 = round(comp['基准万'][:6].sum())
S12 = round(comp['基准万'].sum())
S4F = round((S4 - ytd) * F + ytd)
S6F = round(comp['基准万'][:6].sum() * F)
S12F = round(comp['基准万'].sum() * F)

DATA = {
    'months': FUT,
    'base': [round(float(x)) for x in comp['基准万']],
    'unbiased': [round(float(x)) for x in comp['无偏万']],
    'histMonths': list(hist['月']),
    'histVal': [round(float(x)) for x in hist万],
    'lines': [], 'fva': [['上月延续', 14.7], ['近6月平均', 10.3], ['冠军组合(春节规则)', 7.9], ['线级锚定', 7.4], ['无偏校正', 6.9]],
    'dirMethods': [['近6月平均', 58], ['工作日法', 63], ['组合预测', 68], ['冠军量价系统', 74]],
    'r3': [{'m': r['月'][2:].replace('-', '/'), 'hit': int(r['命中'])} for _, r in r3.iterrows()],
    'kpis': {
        'fy': [S4, S4F, '86,906~90,662', '2026 全年（1-8月实际 + 9-12月）'],
        'm6': [S6, S6F, '45,193~49,981', '未来 6 个月（2026-09 ~ 2027-02）'],
        'm12': [S12, S12F, '91,687~98,396', '未来 12 个月（2026-09 ~ 2027-08）'],
    },
}
for _, r in conf.iterrows():
    v6 = sum(pd.to_numeric(line_fc.loc[r['产品线'], m], errors='coerce') for m in FUT[:6]) / 1e4
    v12 = sum(pd.to_numeric(line_fc.loc[r['产品线'], m], errors='coerce') for m in FUT) / 1e4
    DATA['lines'].append({'n': r['产品线'], 'share': float(r['金额占比%']), 'wape': float(r['WAPE%']), 'g': r['置信档'],
                          'v6': round(float(v6)), 'v12': round(float(v12))})

ADD_CSS = """
/* 预测面补充样式（平台风格内） */
.c2{grid-template-columns:1fr 1fr !important}
.flip-hint{font-size:10px;color:var(--text-tertiary,#94A3B8);margin-top:3px}
.kpi-bar .kc{cursor:pointer}
.kpi-bar .kc .kc-face{transition:opacity .25s}
.kpi-bar .kc .kc-back{display:none}
.kpi-bar .kc.flipped .kc-front{display:none}
.kpi-bar .kc.flipped .kc-back{display:block}
.grade{display:inline-block;min-width:20px;text-align:center;border-radius:4px;font-weight:700;font-size:11px;padding:1px 6px}
.gA{background:#ECFDF5;color:#059669}.gB{background:#FFFBEB;color:#B45309}.gC{background:#FEF2F2;color:#DC2626}
.hit-tl{display:flex;gap:5px;flex-wrap:wrap;margin-top:8px}
.tl{display:inline-flex;gap:6px;align-items:center;border:1px solid var(--bdr,#e2e8f0);border-radius:6px;padding:2px 8px;font-size:11px;background:var(--card,#fff)}
.note-box{background:var(--blue-soft,#EFF6FF);border-left:3px solid var(--primary,#2563EB);padding:10px 14px;border-radius:0 8px 8px 0;font-size:12.5px;line-height:1.75;margin-top:10px}
.switch-group{display:inline-flex;gap:0;border:1px solid var(--bdr,#e2e8f0);border-radius:8px;overflow:hidden}
.switch-group button{padding:6px 14px;border:none;background:var(--card,#fff);color:var(--sub,#64748B);font-size:12px;cursor:pointer}
.switch-group button.on{background:var(--primary,#2563EB);color:#fff}
"""

def kpi(icon, label, front, back):
    """平台 kc 组件 + 翻转（正/背同为 kc 风格；翻转提示改为悬停 title，卡片保持平台 3 段高度）"""
    return ('<div class="kc flipped-able" title="点击翻转查看无偏口径" onclick="this.classList.toggle(\'flipped\')">'
            '<div class="kc-face kc-front"><div class="icon-wrap"><i class="fa-solid %s"></i></div>'
            '<div class="label">%s</div>%s</div>'
            '<div class="kc-face kc-back"><div class="icon-wrap"><i class="fa-solid %s"></i></div>'
            '<div class="label">%s</div>%s</div></div>' % (
                icon, label, front, icon, label + ' · 无偏', back))

def kv(v, sub=''):
    return '<div class="value" style="font-size:22px;font-weight:700;font-variant-numeric:tabular-nums">%s</div>%s' % (
        v, '<div style="font-size:11px;color:var(--sub,#64748B)">%s</div>' % sub if sub else '')

H = []
H.append('<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">')
H.append('<title>月度滚动预测 · 半导体销售分析看板</title>')
H.append('<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" media="print" onload="this.media=\'all\'">')
H.append('<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>')
H.append(platform_css)
H.append('<style>%s</style></head><body>' % ADD_CSS)

# tab-bar（平台同款；单预测面 active，其余灰显仅示意并入位置）
H.append('<div class="tab-bar">')
H.append('<button class="tab-btn active" data-tab="P">月度滚动预测</button>')
H.append('<span style="margin-left:auto;font-size:11px;color:var(--text-tertiary,#94A3B8);padding:10px 14px">本面将并入主看板（A/R/B/C/D/E/F 面之后）｜ 数据截至 2026-08 ｜ 生成 2026-09-16</span>')
H.append('</div>')

H.append('<div class="tab-content active" id="tabP" style="padding:0 var(--space-page,20px)">')

# FACE_META（平台 glossary 样式）
H.append('''<details class="cb" style="margin-bottom:14px"><summary style="cursor:pointer;font-weight:600;font-size:var(--font-card-title,14px)">口径速览（点击展开）</summary>
<ul style="margin:10px 0 4px 20px;line-height:1.9;font-size:12.5px">
<li><b>先定总量再往下分</b>：先预测全公司每月总额，产品线/品类各自预测后按比例对齐——各层加总严格等于总量。</li>
<li><b>平时月份</b>=最近 6 个月平均滚动；<b>春节月份</b>=过去 6 个春节年份的实际规律（节前月 +17%、假期月≈前月 53%）。</li>
<li><b>基准 vs 无偏</b>：无偏 = 基准 ×1.040（修正系统性低估），定目标报计划用无偏。</li>
<li><b>验证</b>：公司月度平均误差 7.7%（无偏校正后 6.9%），方向准确率 74%（20 折+56 折双重回测）。</li>
<li><b>局限</b>：大单/急单转折月属方法盲区需业务补位；单价未单独建模，已知调价请人工加减。</li>
</ul></details>''')

# KPI 区（平台 kpi-bar > kc，5 卡翻转）
H.append('<div class="kpi-bar" style="grid-template-columns:repeat(5,1fr)">')
H.append(kpi('fa-coins', '2026 全年 · 基准', kv('{:,.0f} 万'.format(S4), '{:.2f} 亿'), kv('{:,.0f} 万'.format(S4F), '{:.2f} 亿 · 区间 86,906~90,662'.format(S4F / 1e4))))
H.append(kpi('fa-calendar-days', '未来 6 个月 · 基准', kv('{:,.0f} 万'.format(S6), '{:.2f} 亿'.format(S6 / 1e4)), kv('{:,.0f} 万'.format(S6F), '区间 45,193~49,981')))
H.append(kpi('fa-calendar-check', '未来 12 个月 · 基准', kv('{:,.0f} 万'.format(S12), '{:.2f} 亿'.format(S12 / 1e4)), kv('{:,.0f} 万'.format(S12F), '区间 91,687~98,396')))
H.append(kpi('fa-bullseye', '月度平均误差', kv('6.9%', '无偏校正后 · 校正前 7.7%'), kv('14.7→6.9', '上月延续→近6月均→冠军→无偏')))
H.append(kpi('fa-compass', '方向准确率', kv('74%', '涨跌命中 14/19 月 · 目标 65%'), kv('58/63/68/74', '近6月均/工作日法/组合/冠军量价')))
H.append('</div>')

H.append('<div class="note-box"><b>本月修订（2026-09-16，长历史春节标定）：</b>2027-01 由 11,129 下修至 <b>10,226 万</b>（三法取中）；2027-02 = <b>5,420 万</b>（春节低谷桶：前月×53%）；<b>2026 全年预测不变</b>。</div>')

# 基准/无偏切换（平台 yrf 风格）
H.append('''<div class="cb" style="display:flex;align-items:center;gap:12px"><span style="font-size:12px;color:var(--sub,#64748B)">全局口径：</span>
<div class="switch-group"><button id="swBase" class="on" onclick="setMode('base')">基准</button><button id="swUb" onclick="setMode('ub')">无偏</button></div>
<span style="font-size:11px;color:var(--text-tertiary,#94A3B8)">切换影响：分月预测柱状图数值</span></div>''')

# 图表区
H.append('<div class="cb" id="sec-hist"><h3><i class="fa-solid fa-chart-line" style="color:var(--primary)"></i> 80 个月历史 + 12 个月预测延展（万元）<span class="st">蓝色实线=实际；橙色虚线=基准预测；浅蓝点线=无偏；底部滑块可缩放</span></h3><div id="cHist" style="width:100%;height:420px"></div></div>')
H.append('<div class="c2">'
         '<div class="cb"><h3><i class="fa-solid fa-chart-column" style="color:var(--primary)"></i> 分月预测<span class="st">随全局口径切换；橙=春节规则月</span></h3><div id="cMonth" style="width:100%;height:320px"></div></div>'
         '<div class="cb"><h3><i class="fa-solid fa-crosshairs" style="color:var(--primary)"></i> 产品线：误差 × 金额占比<span class="st">越左越好；气泡=占比；色=置信档</span></h3><div id="cScatter" style="width:100%;height:320px"></div></div></div>')
H.append('<div class="c2">'
         '<div class="cb"><h3><i class="fa-solid fa-stairs" style="color:var(--primary)"></i> 误差改善阶梯（FVA）<span class="st">每步方法的真实贡献</span></h3><div id="cFva" style="width:100%;height:300px"></div></div>'
         '<div class="cb"><h3><i class="fa-solid fa-arrow-trend-up" style="color:var(--primary)"></i> 方向准确率<span class="st">虚线=65% 目标；19 个回测月</span></h3><div id="cDir" style="width:100%;height:300px"></div></div></div>')

# 逐月命中时间线
hits = ''.join('<span class="tl">%s <b style="color:%s">%s</b></span>' % (h['m'], '#059669' if h['hit'] else '#DC2626', '✓' if h['hit'] else '✗') for h in DATA['r3'])
H.append('<div class="cb"><h3><i class="fa-solid fa-check-double" style="color:var(--primary)"></i> 逐月方向命中时间线<span class="st">绿=命中 / 红=未中</span></h3><div class="hit-tl">%s</div></div>' % hits)

# 产品线明细表（平台 data-table）
H.append('<div class="cb"><h3><i class="fa-solid fa-table-list" style="color:var(--primary)"></i> 产品线明细（万元；已对齐公司总量）</h3>'
         '<table class="data-table"><thead><tr><th>产品线</th><th class="ctr">置信档</th><th class="num">月度误差</th><th class="num">金额占比</th><th class="num">未来6个月</th><th class="num">未来12个月</th></tr></thead><tbody id="lineBody"></tbody></table></div>')

# 置信度
H.append('<div class="cb"><h3><i class="fa-solid fa-shield-halved" style="color:var(--primary)"></i> 置信度全景（怎么用这些数）</h3>')
H.append('<div class="kpi-bar" style="grid-template-columns:repeat(3,1fr)">')
for g, icon, desc, back_desc in [('A', 'fa-circle-check', '误差 ≤15% 可直接用于目标', '通用电源管理 63% 金额 · 误差 9.4%'),
                                 ('B', 'fa-circle-half-stroke', '误差 15-25% 可用留余量', '有刷直流/POE/充电控制/硬件锂电 4 条'),
                                 ('C', 'fa-triangle-exclamation', '误差 >25% 仅看结构方向，人工复核', '12 条长尾线 ~11% 金额')]:
    sub = conf[conf['置信档'] == g]
    share = sub['金额占比%'].sum()
    H.append(kpi(icon, '%s 档 · %d 条产品线' % (g, len(sub)), kv('%.0f%% 销售额' % share, desc), kv('%.0f%%' % share, back_desc)))
H.append('</div>')
H.append('<div class="note-box"><b>使用指引：</b>头部线 + B 档 4 条覆盖约 90% 销售额——<b>大数是硬的</b>；C 档 12 条仅占 ~11% 金额，看结构不引数字；SKU 级仅做方向参考。</div></div>')

H.append('</div>')  # tabP

H.append('<script>const D = %s;</script>' % json.dumps(DATA, ensure_ascii=False))
H.append('''<script>
const BLUE='#2563EB',SKY='#0EA5E9',GREEN='#10B981',RED='#EF4444',ORANGE='#F59E0B',SUB='#64748B';
let MODE='base';
const baseOpt={tooltip:{trigger:'axis',backgroundColor:'#fff',borderColor:'#e2e8f0',textStyle:{color:'#1E293B'}},grid:{left:60,right:24,top:40,bottom:52}};
const charts=[];
function mk(id,opt){const c=echarts.init(document.getElementById(id));c.setOption(opt);charts.push(c);return c;}
// 历史+预测
mk('cHist',{...baseOpt,legend:{data:['实际','基准预测','无偏口径'],top:4},
dataZoom:[{type:'slider',start:55,end:100,height:18,bottom:8},{type:'inside'}],
xAxis:{type:'category',data:[...D.histMonths,...D.months],axisLabel:{color:SUB,interval:8}},
yAxis:{type:'value',axisLabel:{color:SUB},splitLine:{lineStyle:{color:'#e2e8f0'}}},
series:[
{name:'实际',type:'line',data:[...D.histVal,...Array(D.months.length).fill(null)],showSymbol:false,lineStyle:{width:2,color:SKY},itemStyle:{color:SKY}},
{name:'基准预测',type:'line',data:[...Array(D.histMonths.length-1).fill(null),D.histVal[D.histVal.length-1],...D.base],lineStyle:{width:2,type:'dashed',color:ORANGE},itemStyle:{color:ORANGE},symbol:'circle',symbolSize:5},
{name:'无偏口径',type:'line',data:[...Array(D.histMonths.length-1).fill(null),Math.round(D.histVal[D.histVal.length-1]*1.04),...D.unbiased],lineStyle:{width:1,type:'dotted',color:'#93C5FD'},itemStyle:{color:'#93C5FD'},symbol:'none'}]});
// 分月（随口径切换）
const cMonth=mk('cMonth',{...baseOpt,legend:{show:false},
xAxis:{type:'category',data:D.months.map(m=>m.slice(2).replace('-','/')),axisLabel:{color:SUB,rotate:38}},
yAxis:{type:'value',axisLabel:{color:SUB},splitLine:{lineStyle:{color:'#e2e8f0'}}},
series:[{name:'v',type:'bar',data:D.base.map((v,i)=>({value:v,itemStyle:{color:D.months[i]>='2027-01'&&D.months[i]<='2027-02'?ORANGE:BLUE}})),barWidth:'52%',itemStyle:{borderRadius:[3,3,0,0]}}]});
function setMode(m){MODE=m;
document.getElementById('swBase').className=m==='base'?'on':'';
document.getElementById('swUb').className=m==='ub'?'on':'';
cMonth.setOption({series:[{data:(m==='base'?D.base:D.unbiased).map((v,i)=>({value:v,itemStyle:{color:D.months[i]>='2027-01'&&D.months[i]<='2027-02'?ORANGE:BLUE}}))}]});}
// 散点
mk('cScatter',{...baseOpt,tooltip:{formatter:p=>p.data[2]+'<br>误差 '+p.data[0]+'% ｜ 占比 '+p.data[1]+'%'},
xAxis:{name:'月度误差%',nameTextStyle:{color:SUB},axisLabel:{color:SUB},splitLine:{lineStyle:{color:'#e2e8f0'}}},
yAxis:{name:'金额占比%',nameTextStyle:{color:SUB},axisLabel:{color:SUB},splitLine:{lineStyle:{color:'#e2e8f0'}}},
series:[{type:'scatter',symbolSize:d=>6+Math.sqrt(d[1])*3.2,
data:D.lines.map(l=>[l.wape,l.share,l.n,l.g]),
itemStyle:{color:p=>p.data[3]==='A'?GREEN:(p.data[3]==='B'?ORANGE:RED),opacity:.78},
label:{show:true,formatter:p=>p.data[2].slice(0,6),position:'top',fontSize:10,color:SUB},labelLayout:{hideOverlap:true}}]});
// FVA
mk('cFva',{...baseOpt,grid:{...baseOpt.grid,left:130},
xAxis:{type:'value',max:16,axisLabel:{color:SUB,formatter:'{value}%'},splitLine:{lineStyle:{color:'#e2e8f0'}}},
yAxis:{type:'category',data:D.fva.map(x=>x[0]).reverse(),axisLabel:{color:'#1E293B'}},
series:[{type:'bar',data:D.fva.map(x=>x[1]).reverse(),barWidth:'52%',
itemStyle:{color:p=>p.dataIndex===4?GREEN:BLUE,borderRadius:[0,4,4,0]},
label:{show:true,position:'right',formatter:'{c}%',color:'#1E293B',fontWeight:600}}]});
// 方向
mk('cDir',{...baseOpt,xAxis:{type:'category',data:D.dirMethods.map(x=>x[0]),axisLabel:{color:SUB,interval:0}},
yAxis:{type:'value',min:30,max:85,axisLabel:{color:SUB,formatter:'{value}%'},splitLine:{lineStyle:{color:'#e2e8f0'}}},
series:[{type:'bar',data:D.dirMethods.map(x=>x[1]),barWidth:'46%',
itemStyle:{color:p=>p.dataIndex===3?GREEN:BLUE,borderRadius:[4,4,0,0]},
label:{show:true,position:'top',formatter:'{c}%',color:'#1E293B',fontWeight:600},
markLine:{silent:true,symbol:'none',lineStyle:{color:ORANGE,type:'dashed'},label:{formatter:'目标 65%',color:ORANGE},data:[{yAxis:65}]}}]});
// 产品线表
document.getElementById('lineBody').innerHTML = D.lines.map(l=>'<tr><td>'+l.n+'</td><td class="ctr"><span class="grade g'+l.g+'">'+l.g+'</span></td><td class="num">'+l.wape.toFixed(1)+'%</td><td class="num">'+l.share.toFixed(1)+'%</td><td class="num">'+l.v6.toLocaleString()+'</td><td class="num">'+l.v12.toLocaleString()+'</td></tr>').join('');
window.addEventListener('resize',()=>charts.forEach(c=>c.resize()));
</script></body></html>''')

import os
with open(DEST, 'w', encoding='utf-8') as f:
    f.write('\n'.join(H))
print('已生成 v3:', DEST, '(%.0f KB)' % (os.path.getsize(DEST) / 1024))
