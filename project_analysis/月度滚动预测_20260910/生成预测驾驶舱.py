# -*- coding: utf-8 -*-
"""预测驾驶舱 v5 终版：议会裁决形态（结论带+主图脊柱+逐层下钻）+ 用户三点修改
1. 增加产品线多线图（解决"只有总数没图可做"）+ 行点击高亮联动
2. 口径条 = 平台 face-meta 浮层组件（点开浮在上面，非内嵌折叠）
3. 图表 token/设计/颜色全对齐平台（--chart-1~6/红涨绿跌/chart-guide/btn-toggle/data-table）
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
lhist = pd.read_csv(OUT + r'\线级月度长序列80月.csv')
e12 = pd.read_csv(OUT + r'\E12b_量价集成_对比.csv')
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

# 置信带：E12b 实际/预测比率池 q10/q90（独立口径）
pool = (e12['实际'] / e12['combo_volxasp']).dropna()
q10, q90 = float(pool.quantile(0.10)), float(pool.quantile(0.90))
band_lo = [None] * (len(hist万) - 1) + [hist万[-1]] + [round(v * q10) for v in comp['基准万']]
band_hi = [None] * (len(hist万) - 1) + [hist万[-1]] + [round(v * q90) for v in comp['基准万']]
band_rng = [None if a is None else round(b - a) for a, b in zip(band_lo, band_hi)]

# Top 线（金额占比 Top6）历史+预测
lh = lhist.pivot_table(index='月', columns='产品线', values='金额', aggfunc='sum', fill_value=0.0).sort_index() / 1e4
months_h = list(lh.index)
top6 = list(conf.head(6)['产品线'])
lines_top = []
for name in top6:
    hv = [round(float(v)) for v in lh[name].reindex(months_h, fill_value=0).values] if name in lh.columns else [0] * len(months_h)
    fv = [round(float(pd.to_numeric(line_fc.loc[name, m], errors='coerce')) / 1e4) for m in FUT]
    g = conf[conf['产品线'] == name]['置信档'].iloc[0]
    lines_top.append({'n': name, 'hist': hv, 'fut': fv, 'share': float(conf[conf['产品线'] == name]['金额占比%'].iloc[0]), 'g': g})

LINES = []
for _, r in conf.iterrows():
    v6 = sum(pd.to_numeric(line_fc.loc[r['产品线'], m], errors='coerce') for m in FUT[:6]) / 1e4
    v12 = sum(pd.to_numeric(line_fc.loc[r['产品线'], m], errors='coerce') for m in FUT) / 1e4
    LINES.append({'n': r['产品线'], 'share': float(r['金额占比%']), 'wape': float(r['WAPE%']), 'g': r['置信档'],
                  'v6': round(float(v6)), 'v12': round(float(v12))})

DATA = {
    'histMonths': months_h, 'histVal': [round(float(x)) for x in hist万],
    'months': FUT, 'base': [round(float(x)) for x in comp['基准万']], 'unbiased': [round(float(x)) for x in comp['无偏万']],
    'bandLo': band_lo, 'bandRng': band_rng,
    'linesTop': lines_top, 'lines': LINES,
    'kpis': {'fy': [S4, S4F, '86,906~90,662'], 'm6': [S6, S6F, '45,193~49,981'], 'm12': [S12, S12F, '91,687~98,396']},
    'cover': {'A': round(float(conf[conf['置信档'] == 'A']['金额占比%'].sum()), 1),
              'B': round(float(conf[conf['置信档'] == 'B']['金额占比%'].sum()), 1),
              'C': round(float(conf[conf['置信档'] == 'C']['金额占比%'].sum()), 1)},
}

ADD_CSS = """
.c2{grid-template-columns:1fr 1fr !important}
/* L0 结论带（无卡通栏） */
.conclusion{display:flex;align-items:flex-end;justify-content:space-between;gap:24px;flex-wrap:wrap;padding:var(--space-card) var(--space-page) 4px}
.conclusion .lead{font-size:var(--font-lg);font-weight:var(--weight-heading);color:var(--text-primary);max-width:46%;line-height:1.5}
.conclusion .lead small{display:block;font-size:var(--font-sm);color:var(--text-tertiary);font-weight:var(--weight-body);margin-top:4px}
.nums{display:flex;gap:28px;flex-wrap:wrap}
.num-item .num-label{font-size:var(--font-xs);color:var(--text-tertiary)}
.num-item .num-val{font-size:26px;font-weight:700;color:var(--text-primary);font-variant-numeric:tabular-nums;line-height:1.2}
.num-item .num-sub{font-size:11px;color:var(--text-muted)}
/* 窗口芯片高亮联动 */
.chip-on-num{color:var(--primary) !important}
/* 月历条 */
.cal-grid{display:grid;grid-template-columns:repeat(12,1fr);gap:6px}
.cal-cell{border:1px solid var(--border);border-radius:var(--radius-sm);padding:6px 4px;text-align:center;background:var(--surface)}
.cal-cell.cny{background:var(--warning-bg);border-color:var(--warning)}
.cal-cell .m{font-size:11px;color:var(--text-tertiary)}
.cal-cell .v{font-size:13px;font-weight:700;font-variant-numeric:tabular-nums;color:var(--text-primary)}
.cal-cell .u{font-size:10px;color:var(--text-muted)}
/* 覆盖堆叠条 */
.cover-bar{display:flex;height:26px;border-radius:6px;overflow:hidden;border:1px solid var(--border)}
.cover-bar div{display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:600;color:#fff}
.covA{background:var(--success)}.covB{background:var(--warning)}.covC{background:var(--text-muted)}
/* 分档组头 */
.ghd{background:var(--surface-subtle) !important;font-weight:600;color:var(--text-secondary)}
.ghd td{padding:6px 10px;font-size:var(--font-xs)}
tr.dim td{color:var(--text-muted) !important}
tr.dim .num{color:var(--text-muted) !important}
.grade{display:inline-block;min-width:20px;text-align:center;border-radius:4px;font-weight:700;font-size:11px;padding:1px 6px}
.gA{background:var(--success-bg);color:var(--success-text)}.gB{background:var(--warning-bg);color:var(--warning-text)}.gC{background:var(--danger-bg);color:var(--danger-text)}
tr.rowlink{cursor:pointer}
tr.rowlink:hover{background:var(--table-hover)}
/* 证据条 */
.ev-bar{display:flex;gap:28px;flex-wrap:wrap;align-items:center}
.ev-item{display:flex;align-items:baseline;gap:6px}
.ev-item .v{font-size:18px;font-weight:700;font-variant-numeric:tabular-nums}
.ev-item .l{font-size:var(--font-xs);color:var(--text-tertiary)}
.ev-item .d{font-size:11px;color:var(--success-text);font-weight:600}
/* 分月明细表折叠辅助 */
details.cb summary{list-style:none}
"""

def face_meta():
    """平台 face-meta 浮层组件（口径与修订说明）"""
    return ('<div class="face-meta" id="faceMetaP"><div class="face-meta-summary" onclick="toggleFaceMeta(\'P\')">'
            '<i class="fa-solid fa-circle-info"></i><span>口径与修订说明 · 点击展开</span></div>'
            '<div class="face-meta-body" id="faceMetaBodyP">'
            '<div class="face-meta-theme">本面预测规则与数据来源说明（浮层，点击外部或滚动自动收起）</div>'
            '<div class="face-meta-sections">'
            '<div class="face-meta-section"><div class="face-meta-title">本月修订（2026-09-16）</div>'
            '<div class="face-meta-row"><span>2027-01</span>由 11,129 下修至 10,226 万（2020-2026 长历史春节分桶标定，三法取中）；2027-02 = 5,420 万（低谷月≈前月×53%）；2026 全年不变。</div></div>'
            '<div class="face-meta-section"><div class="face-meta-title">口径</div>'
            '<div class="face-meta-row"><span>基准</span>冠军规则输出（平时=近6月平均；春节月=6 个春节年份规律）。</div>'
            '<div class="face-meta-row"><span>无偏</span>基准 ×1.040——修正近 6% 系统性低估，定目标报计划用无偏。</div>'
            '<div class="face-meta-row"><span>区间</span>主图浅色带=八成把握区间（历史回测误差分布的第 10~90 分位）。</div>'
            '<div class="face-meta-row"><span>数据</span>ERP 出货明细 2020-01~2026-08（80 个月，不含税人民币）。</div></div>'
            '<div class="face-meta-section"><div class="face-meta-title">注意</div>'
            '<div class="face-meta-row"><span>单价</span>未单独预测（回测显示对总精度提升很小）；已知调价请人工加减。</div>'
            '<div class="face-meta-row"><span>盲区</span>大单/急单转折月属尾随方法固有盲区，需业务情报补位。</div></div>'
            '</div></div></div>')

GUIDE = {
    'g_hist': '<p><b>读图：</b>蓝实线=实际出货（2020-01~2026-08）；橙虚线=未来 12 个月基准预测；浅蓝点线=无偏口径（×1.040，定目标用）；浅蓝带=八成把握区间。</p><p><b>春节月：</b>浅黄竖带为春节假期所在月（预测规则特殊处理：低谷月≈前月×53%）。</p><p><b>窗口芯片：</b>点"全年/6个月/12个月"高亮对应预测窗口，并与顶部三个数联动。</p><p><b>操作：</b>底部滑块或滚轮缩放时间轴；悬停看数值；点图例隐藏系列。</p>',
    'g_lines': '<p><b>内容：</b>金额占比 Top 6 产品线的月度出货（实线=历史，虚线=预测）。</p><p><b>配色：</b>与产品线明细表行一致；点击表中行可在此图单独高亮该线。</p><p><b>读法：</b>看头部线走势是否延续，长尾线（步进/车规）波动大属正常。</p>',
    'g_cal': '<p><b>内容：</b>未来 12 个月分月读数（基准/无偏）。</p><p><b>橙色格：</b>春节月（2027-02，低谷规则≈前月×53%）。</p><p><b>用法：</b>报计划用无偏值，日常跟进用基准值。</p>',
    'g_cover': '<p><b>口径：</b>按 2025-01~2026-08 共 20 个月逐月回测（生产同款链路），统计每条线的月度误差 WAPE。</p><p><b>分档：</b>A≤15% 可直接用于目标；B 15-25% 可用留余量；C>25% 仅看结构方向（不建议引用具体数字）。</p>',
    'g_ev': '<p><b>验证方式：</b>2022-01~2026-08 共 56 个月逐月模拟回测（walk-forward，每月只用此前数据预测下月，无前视）。</p><p><b>误差 6.9%：</b>公司月度平均误差（无偏校正后；校正前 7.7%）。</p><p><b>方向 74%：</b>19 个回测月中 14 个月涨跌方向判断正确（目标 ≥65%）。</p>',
}

def guide_btn(key):
    return ('<span class="chart-guide-wrap"><button class="chart-guide-btn" data-guide-key="%s" '
            'onclick="TABS.popover.toggle(this,event)"><i class="fa-regular fa-circle-question"></i></button></span>' % key)

H = []
H.append('<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">')
H.append('<title>月度滚动预测 · 半导体销售分析看板</title>')
H.append('<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" media="print" onload="this.media=\'all\'">')
H.append('<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>')
H.append(platform_css)
H.append('<style>%s</style></head><body>' % ADD_CSS)

H.append('<div class="tab-bar"><button class="tab-btn active" data-tab="P">月度滚动预测</button>'
         '<span style="margin-left:auto;font-size:11px;color:var(--text-tertiary);padding:10px 14px">数据截至 2026-08 ｜ 生成 2026-09-16</span></div>')

H.append('<div class="tab-content active" id="tabP">')

# L0 结论带
H.append('<div class="conclusion"><div class="lead">未来 12 个月预计出货 9.0 亿，八成把握落在 8.3 ~ 9.7 亿'
         '<small>春节 2/6：2027-02 为低谷月，已按 6 个春节年份规律标定</small></div>')
H.append('<div class="nums">')
for lbl, v, s in [('2026 全年', S4, S4F), ('未来 6 个月', S6, S6F), ('未来 12 个月', S12, S12F)]:
    H.append('<div class="num-item" id="num_%s"><div class="num-label">%s</div><div class="num-val">%s</div><div class="num-sub">无偏 %s</div></div>' % (
        lbl.replace(' ', '').replace('个月', 'm').replace('全年', 'fy'), lbl, '{:,.0f}'.format(v), '{:,.0f}'.format(s)))
H.append('</div></div>')

# face-meta 口径条（浮层）
H.append(face_meta())

# L1 主图（窗口芯片移入标题下工具行，避免与 .st 右上注释重叠）
H.append('<div class="cb" style="position:relative"><h3><i class="fa-solid fa-chart-line" style="color:var(--primary)"></i> 80 个月历史 + 12 个月预测（万元）%s'
         '<span class="st">蓝实线=实际 · 橙虚线=基准 · 浅蓝带=八成区间 · 黄带=春节月</span></h3>'
         '<div class="btn-toggle-group">'
         '<button class="btn-toggle active" data-win="fy" onclick="setWin(this)">全年</button>'
         '<button class="btn-toggle" data-win="m6" onclick="setWin(this)">6 个月</button>'
         '<button class="btn-toggle" data-win="m12" onclick="setWin(this)">12 个月</button></div>'
         '<div id="cHist" style="width:100%%;height:430px"></div></div>' % guide_btn('g_hist'))

# L2 产品线多线图
H.append('<div class="cb"><h3><i class="fa-solid fa-layer-group" style="color:var(--primary)"></i> 头部产品线走势（万元）%s'
         '<span class="st">实线=历史 · 虚线=预测 · 点明细表行可单独高亮</span></h3>'
         '<div id="cLines" style="width:100%%;height:360px"></div></div>' % guide_btn('g_lines'))

# L3 月历读数条
H.append('<div class="cb"><h3><i class="fa-solid fa-calendar-days" style="color:var(--primary)"></i> 分月读数（基准 / 无偏，万元）%s'
         '<span class="st">橙底=春节月</span></h3><div class="cal-grid" id="calGrid"></div></div>' % guide_btn('g_cal'))

# L4 产品线层
H.append('<div class="cb"><h3><i class="fa-solid fa-shield-halved" style="color:var(--primary)"></i> 钱在哪些线？（金额覆盖与可信度）%s'
         '<span class="st">A 直接用 · B 留余量 · C 看结构</span></h3>'
         '<div class="cover-bar"><div class="covA" style="width:%s%%">A %.1f%%</div><div class="covB" style="width:%s%%">B %.1f%%</div><div class="covC" style="width:%s%%">C %.1f%%</div></div>'
         % (guide_btn('g_cover'), DATA['cover']['A'], DATA['cover']['A'], DATA['cover']['B'], DATA['cover']['B'], DATA['cover']['C'], DATA['cover']['C']))
H.append('<table class="data-table" style="margin-top:12px"><thead><tr><th>产品线</th><th class="ctr">档</th><th class="num">月度误差</th><th class="num">金额占比</th><th class="num">未来6个月</th><th class="num">未来12个月</th></tr></thead><tbody id="lineBody"></tbody></table></div>')

# L5 证据条 + 折叠附录
H.append('<div class="cb"><h3><i class="fa-solid fa-certificate" style="color:var(--primary)"></i> 这个数多准？%s</h3>'
         '<div class="ev-bar">'
         '<div class="ev-item"><span class="v" style="color:var(--success-text)">6.9%%</span><span class="l">月度平均误差</span><span class="d">▼7.7→6.9</span></div>'
         '<div class="ev-item"><span class="v" style="color:var(--success-text)">74%%</span><span class="l">方向准确率（目标65%%）</span></div>'
         '<div class="ev-item"><span class="v">56</span><span class="l">折 walk-forward 验证</span></div>'
         '<div class="ev-item"><span class="v">9.4%%</span><span class="l">头部线（通用电源管理）误差</span></div></div>'
         % guide_btn('g_ev'))
H.append('<details style="margin-top:12px"><summary style="cursor:pointer;font-size:var(--font-sm);color:var(--text-tertiary)">方法与验证细节（点击展开）</summary>'
         '<div class="c2" style="margin-top:10px"><div><div class="subsection-title">误差改善阶梯（FVA）</div><div id="cFva" style="width:100%%;height:260px"></div></div>'
         '<div><div class="subsection-title">方向准确率对比</div><div id="cDir" style="width:100%%;height:260px"></div></div></div></details></div>')

H.append('</div>')

H.append('<script>const D = %s;</script>' % json.dumps(DATA, ensure_ascii=False))
H.append('''<script>
// === 平台 popover 移植（chart-guide 浮层） ===
const GUIDE_DETAIL = __GUIDE_JSON__;
const TABS = {popover: {
 _el:null,_btn:null,
 toggle:function(btn,evt){
  if(evt)evt.stopPropagation();
  closeFaceMeta();
  if(this._btn===btn){this.close();return}
  this.close();
  var html=GUIDE_DETAIL[btn.getAttribute('data-guide-key')]||'暂无详细说明';
  var pop=document.createElement('div');
  pop.className='chart-guide-popover';
  pop.innerHTML='<div class="cg-title">图表口径与读图指引</div><div>'+html+'</div>';
  document.body.appendChild(pop);
  var rect=btn.getBoundingClientRect();
  var left=rect.left+rect.width/2-170, top=rect.bottom+8;
  if(left<10)left=10;
  if(left+pop.offsetWidth>window.innerWidth-10)left=window.innerWidth-pop.offsetWidth-10;
  pop.style.left=left+'px';pop.style.top=top+'px';
  this._el=pop;this._btn=btn;
  pop.addEventListener('click',function(e){e.stopPropagation()});
 },
 close:function(){if(this._el){this._el.remove();this._el=null}this._btn=null;}
}};
function toggleFaceMeta(){
 const body=document.getElementById('faceMetaBodyP');
 TABS.popover.close();
 body.classList.toggle('open');
 const sum=document.querySelector('#faceMetaP .face-meta-summary i');
 if(sum)sum.className=body.classList.contains('open')?'fa-solid fa-chevron-down':'fa-solid fa-circle-info';
}
function closeFaceMeta(){const b=document.getElementById('faceMetaBodyP');if(b)b.classList.remove('open');}
document.addEventListener('click',function(e){
 const meta=document.getElementById('faceMetaP');
 if(meta&&meta.querySelector('.face-meta-body').classList.contains('open')&&!meta.contains(e.target))closeFaceMeta();
 if(TABS.popover._el&&TABS.popover._btn&&!TABS.popover._btn.contains(e.target)&&!TABS.popover._el.contains(e.target))TABS.popover.close();
});
window.addEventListener('scroll',function(){TABS.popover.close();closeFaceMeta();},true);

// === 图表（token 对齐平台 --chart-1~6） ===
const C1='#2563EB',C2='#F59E0B',C3='#0EA5E9',C4='#1E293B',C5='#94A3B8',C6='#14B8A6';
const PALETTE=[C1,C2,C3,C4,C6,C5];
const SUB='#64748B',BDR='#e2e8f0',TXT='#0F172A';
const baseOpt={textStyle:{fontFamily:"-apple-system,'Microsoft YaHei',sans-serif",color:SUB},
tooltip:{trigger:'axis',backgroundColor:'rgba(255,255,255,0.97)',borderColor:BDR,borderWidth:1,
textStyle:{color:TXT,fontSize:12},extraCssText:'box-shadow:0 4px 12px rgba(15,23,42,0.08);border-radius:8px;'},
grid:{left:64,right:24,top:44,bottom:64}};
const charts=[];
function mk(id,opt){const c=echarts.init(document.getElementById(id));c.setOption(opt);charts.push(c);return c;}

const X=[...D.histMonths,...D.months];
const cnyMark={silent:true,itemStyle:{color:'rgba(245,158,11,0.10)'},data:[
 [{name:'春节',xAxis:'2026-02'},{xAxis:'2026-02'}],[{name:'春节',xAxis:'2027-02'},{xAxis:'2027-02'}]]};
const winIdx={fy:[D.histMonths.length,D.histMonths.length+3],m6:[D.histMonths.length,D.histMonths.length+5],m12:[D.histMonths.length,D.histMonths.length+11]};

// L1 主图（置信带 stack 写法）
const cHist=mk('cHist',{...baseOpt,legend:{data:['实际','基准预测','无偏口径'],top:4,left:8,itemGap:14,textStyle:{fontSize:11}},
dataZoom:[{type:'slider',start:68,end:100,height:16,bottom:6},{type:'inside'}],
xAxis:{type:'category',data:X,axisLabel:{color:SUB,interval:8}},
yAxis:{type:'value',axisLabel:{color:SUB},splitLine:{lineStyle:{color:BDR}}},
series:[
{name:'_lo',type:'line',data:D.bandLo,stack:'band',lineStyle:{opacity:0},symbol:'none',silent:true},
{name:'八成区间',type:'line',data:D.bandRng,stack:'band',areaStyle:{color:'rgba(37,99,235,0.08)'},lineStyle:{opacity:0},symbol:'none',silent:true},
{name:'实际',type:'line',data:[...D.histVal,...Array(D.months.length).fill(null)],showSymbol:false,lineStyle:{width:2,color:C3},itemStyle:{color:C3}},
{name:'基准预测',type:'line',data:[...Array(D.histMonths.length-1).fill(null),D.histVal[D.histVal.length-1],...D.base],lineStyle:{width:2,type:'dashed',color:C2},itemStyle:{color:C2},symbol:'circle',symbolSize:5,
 markLine:{silent:true,symbol:'none',lineStyle:{color:C5,type:'dashed'},label:{formatter:'数据截止',color:SUB,fontSize:9,position:'insideEndTop'},data:[{xAxis:D.histMonths[D.histMonths.length-1]}]},
 markArea:{silent:true,itemStyle:{color:'rgba(245,158,11,0.08)'},label:{show:true,position:'insideBottom',fontSize:9,color:'#B45309',formatter:'春节'},data:[[{xAxis:'2026-02'},{xAxis:'2026-02'}],[{xAxis:'2027-02'},{xAxis:'2027-02'}]]}},
{name:'无偏口径',type:'line',data:[...Array(D.histMonths.length-1).fill(null),Math.round(D.histVal[D.histVal.length-1]*1.04),...D.unbiased],lineStyle:{width:1.5,type:'dotted',color:'#93C5FD'},itemStyle:{color:'#93C5FD'},symbol:'none'}]});

let curWin='fy';
function setWin(btn){
 document.querySelectorAll('.btn-toggle').forEach(b=>b.classList.remove('active'));
 btn.classList.add('active');
 curWin=btn.getAttribute('data-win');
 const [a,b]=winIdx[curWin];
 cHist.setOption({series:[{},{},{},{markArea:{silent:true,itemStyle:{color:'rgba(37,99,235,0.06)'},
  data:[[{name:'窗口',xAxis:X[a]},{xAxis:X[b]}]]}},{}]});
 document.querySelectorAll('.num-item').forEach(n=>n.classList.remove('chip-on-num'));
 const map={fy:0,m6:1,m12:2};
 document.querySelectorAll('.num-item')[map[curWin]].classList.add('chip-on-num');
}

// L2 产品线多线图（单系列连续线，图例默认换行不截断；历史/预测分界靠主图承担）
const lineSeries=[];
D.linesTop.forEach((l,i)=>{
 const col=PALETTE[i%PALETTE.length];
 const cont=[...l.hist, l.hist[l.hist.length-1], ...l.fut]; // 历史+桥接点+预测连续
 lineSeries.push({name:l.n,type:'line',data:cont,showSymbol:false,
  lineStyle:{width:1.8,color:col},itemStyle:{color:col}});
});
const cLines=mk('cLines',{...baseOpt,legend:{top:4,left:8,itemGap:12,textStyle:{fontSize:11}},
dataZoom:[{type:'slider',start:60,end:100,height:16,bottom:6},{type:'inside'}],
xAxis:{type:'category',data:X,axisLabel:{color:SUB,interval:8}},
yAxis:{type:'value',axisLabel:{color:SUB},splitLine:{lineStyle:{color:BDR}}},
series:lineSeries});

// 月历
document.getElementById('calGrid').innerHTML=D.months.map((m,i)=>{
 const cny=(m==='2027-01'||m==='2027-02')?' cny':'';
 return '<div class="cal-cell'+cny+'"><div class="m">'+m.slice(2).replace('-','/')+'</div><div class="v">'+D.base[i].toLocaleString()+'</div><div class="u">'+D.unbiased[i].toLocaleString()+'</div></div>';
}).join('');

// 产品线明细表（分档分组）
let tb='';
const groups=[['A','A 档 · 数可直接用'],['B','B 档 · 可用留余量'],['C','C 档 · 仅看结构（数值不引用）']];
groups.forEach(([g,label])=>{
 const rows=D.lines.filter(l=>l.g===g);
 if(!rows.length)return;
 tb+='<tr class="ghd"><td colspan="6">'+label+'（'+rows.length+' 条）</td></tr>';
 rows.forEach(l=>{
  const dim=g==='C'?' class="rowlink dim"':' class="rowlink"';
  const v6=g==='C'?'—':l.v6.toLocaleString();
  const v12=g==='C'?'—':l.v12.toLocaleString();
  tb+='<tr'+dim+' data-line="'+l.n+'"><td>'+l.n+'</td><td class="ctr"><span class="grade g'+g+'">'+g+'</span></td><td class="num">'+l.wape.toFixed(1)+'%</td><td class="num">'+l.share.toFixed(1)+'%</td><td class="num">'+v6+'</td><td class="num">'+v12+'</td></tr>';
 });
});
document.getElementById('lineBody').innerHTML=tb;
// 行点击 → 产品线图高亮该线
document.querySelectorAll('.rowlink').forEach(tr=>{
 tr.addEventListener('click',()=>{
  const name=tr.getAttribute('data-line');
  const c=charts.find(c=>c.getDom().id==='cLines');
  if(!c)return;
  D.linesTop.forEach(l=>{c.dispatchAction({type:l.n===name?'legendSelect':'legendUnSelect',name:l.n});});
  c.getDom().scrollIntoView({behavior:'smooth',block:'center'});
 });
});

// L5 附录图
mk('cFva',{...baseOpt,grid:{...baseOpt.grid,left:120},
xAxis:{type:'value',max:16,axisLabel:{color:SUB,formatter:'{value}%'},splitLine:{lineStyle:{color:BDR}}},
yAxis:{type:'category',data:[['上月延续',14.7],['近6月平均',10.3],['冠军组合(春节规则)',7.9],['线级锚定',7.4],['无偏校正',6.9]].map(x=>x[0]).reverse(),axisLabel:{color:TXT}},
series:[{type:'bar',data:[14.7,10.3,7.9,7.4,6.9].reverse(),barWidth:'52%',
itemStyle:{color:p=>p.dataIndex===4?'#10B981':C1,borderRadius:[0,4,4,0]},
label:{show:true,position:'right',formatter:'{c}%',color:TXT,fontWeight:600}}]});
mk('cDir',{...baseOpt,xAxis:{type:'category',data:['近6月平均','工作日法','组合预测','冠军量价系统'],axisLabel:{color:SUB,interval:0}},
yAxis:{type:'value',min:30,max:85,axisLabel:{color:SUB,formatter:'{value}%'},splitLine:{lineStyle:{color:BDR}}},
series:[{type:'bar',data:[58,63,68,74],barWidth:'46%',
itemStyle:{color:p=>p.dataIndex===3?'#10B981':C1,borderRadius:[4,4,0,0]},
label:{show:true,position:'top',formatter:'{c}%',color:TXT,fontWeight:600},
markLine:{silent:true,symbol:'none',lineStyle:{color:C2,type:'dashed'},label:{formatter:'目标 65%',color:C2},data:[{yAxis:65}]}}]});
window.addEventListener('resize',()=>charts.forEach(c=>c.resize()));
</script></body></html>'''.replace('__GUIDE_JSON__', json.dumps(GUIDE, ensure_ascii=False)))

import os
with open(DEST, 'w', encoding='utf-8') as f:
    f.write('\n'.join(H))
print('已生成 v5:', DEST, '(%.0f KB)' % (os.path.getsize(DEST) / 1024))
