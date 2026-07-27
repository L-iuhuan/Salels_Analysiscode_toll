#!/usr/bin/env python3
"""Generate comprehensive all-customer forecast HTML report"""
import json, pandas as pd, numpy as np
from datetime import datetime

OUTDIR = r'C:\Users\45091\Desktop\工作文件\longtail_forecast\v3'

# Load data
summary = json.load(open(f'{OUTDIR}/全客户预测摘要.json', 'r', encoding='utf-8'))
df = pd.read_csv(f'{OUTDIR}/全客户预测总表.csv')
hist = pd.read_csv(f'{OUTDIR}/全客户季度历史与预测.csv')

o = summary['overall']
t = summary['by_type']

# Helper
def fmt_wan(v): return f"{v/10000:.0f}" if abs(v) >= 10000 else f"{v/10000:.2f}"

# Build tables by type
def build_table(ct, min_rev=0):
    rows = df[(df['客户类型'] == ct) & (df['Q预测值(万元)'] >= min_rev)]
    rows = rows.sort_values('Q预测值(万元)', ascending=False)
    if len(rows) == 0: return '<p>暂无数据</p>'
    
    html = '<table><thead><tr><th>客户名称</th><th>分层</th><th>预测收入(万)</th><th>区间</th><th>WAPE%</th><th>置信</th><th>最优方法</th><th>方法类</th></tr></thead><tbody>'
    for _, r in rows.iterrows():
        g = r['置信等级']
        gcolor = {'A': '#27ae60', 'B': '#2ecc71', 'C': '#f39c12', 'D': '#e67e22', 'E': '#e74c3c'}.get(g, '#999')
        name = r['客户名称'][:18] + '...' if len(str(r['客户名称'])) > 18 else r['客户名称']
        html += f'<tr><td title="{r["客户名称"]}">{name}</td><td>{r["客户分层"]}</td><td class="num">{r["Q预测值(万元)"]:.1f}</td>'
        html += f'<td class="num">{r["预测区间下限(万元)"]:.1f}~{r["预测区间上限(万元)"]:.1f}</td>'
        html += f'<td class="num">{r["回测WAPE(%)"]:.1f}</td>'
        html += f'<td><span class="badge" style="background:{gcolor}">{g}</span></td>'
        html += f'<td class="method">{r["最优方法"]}</td><td>{r["方法类别"]}</td></tr>'
    
    # Add total row
    html += f'<tr class="total"><td colspan="2">合计 ({len(rows)}客户)</td>'
    html += f'<td class="num">{rows["Q预测值(万元)"].sum():.1f}</td><td></td><td></td><td></td><td colspan="2"></td></tr>'
    html += '</tbody></table>'
    return html

# Grade distribution bar chart (SVG)
def grade_svg():
    grades = o['grades']
    total = summary['customers_total']
    colors = {'A': '#27ae60', 'B': '#2ecc71', 'C': '#f39c12', 'D': '#e67e22', 'E': '#e74c3c'}
    
    bars = []
    x = 10
    for g in 'ABCDE':
        w = max(grades[g]/total*580, 15) if grades[g] > 0 else 0
        bars.append(f'<rect x="{x}" y="20" width="{w}" height="30" fill="{colors[g]}" rx="4"/>')
        bars.append(f'<text x="{x+w/2}" y="40" text-anchor="middle" fill="white" font-size="12" font-weight="bold">{g}({grades[g]})</text>')
        x += w + 4
    
    return f'''<svg viewBox="0 0 610 60" width="100%" height="60">
        {''.join(bars)}
    </svg>'''

# SVG mini chart for top customers
def mini_chart(cname):
    ch = hist[hist['客户名称'] == cname]
    if len(ch) == 0: return ''
    
    actuals = ch[ch['季度'] != 'F01(预测)'].sort_values('季度')
    pred_row = ch[ch['季度'] == 'F01(预测)']
    
    if len(actuals) < 2: return ''
    
    vals = actuals['实际销售'].values
    max_val = max(vals.max(), pred_row['预测销售'].max() if len(pred_row)>0 else 0) if not actuals['实际销售'].isna().all() else 1
    if max_val == 0: max_val = 1
    
    w = 200; h = 80; pad = 5
    n = min(12, len(vals))  # last 12 quarters
    display_vals = vals[-n:]
    bar_w = (w - 2*pad) / (n + 1)
    
    rects = []
    for i, v in enumerate(display_vals):
        bh = max(v/max_val*(h-2*pad-15), 1)
        x = pad + i*bar_w
        y = h - pad - 15 - bh
        rects.append(f'<rect x="{x}" y="{y}" width="{max(bar_w-1,1)}" height="{bh}" fill="#5470c6" rx="1"/>')
    
    # Pred bar
    if len(pred_row) > 0:
        pv = pred_row['预测销售'].values[0] if not pd.isna(pred_row['预测销售'].values[0]) else 0
        if pv > 0:
            ph = max(pv/max_val*(h-2*pad-15), 1)
            px = pad + n*bar_w
            py = h - pad - 15 - ph
            rects.append(f'<rect x="{px}" y="{py}" width="{max(bar_w-1,1)}" height="{ph}" fill="#91cc75" stroke="#2ecc71" stroke-dasharray="2,2" rx="1" stroke-width="1.5"/>')
    
    return f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}">{chr(10).join(rects)}</svg>'

# Build HTML
now = datetime.now().strftime('%Y-%m-%d %H:%M')
grade_html = grade_svg()

# Confidence by type comparison table
ct_rows = ''
for ct in ['KA','AA','MM','KM']:
    if ct not in t: continue
    s = t[ct]
    ct_rows += f'''<tr>
        <td><b>{ct}</b></td><td class="num">{s['n']}</td>
        <td class="num">{s['pred_total']/10000:.1f}万</td>
        <td class="num">{s['avg_wape']}%</td>
        <td class="num">{s['med_wape']}%</td>
        <td><span class="badge2">{s['ab_count']}</span></td>
        <td class="num">{s['ab_rev_pct']}%</td>
        <td>A={s['grades']['A']} B={s['grades']['B']} C={s['grades']['C']} D={s['grades']['D']} E={s['grades']['E']}</td>
    </tr>'''

# KA table
ka_table = build_table('KA')
aa_table = build_table('AA')
mm_table = build_table('MM', min_rev=1)  # MM with >1万 predicted
km_table = build_table('KM', min_rev=0.5)

# Method usage
method_rows = ''
for meth, cnt in list(summary['top15_methods'].items())[:10]:
    method_rows += f'<tr><td>{meth}</td><td class="num">{cnt}</td><td class="num">{cnt/summary["customers_total"]*100:.1f}%</td></tr>'

# HTML content
html_content = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>全客户季度销售预测报告 — 2026Q2</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Microsoft YaHei',sans-serif;font-size:13px;color:#2c3e50;background:#f5f7fa;line-height:1.6}}
.container{{max-width:1400px;margin:0 auto;padding:20px}}

/* Header */
.header{{background:linear-gradient(135deg,#1e3a5f 0%,#2c5282 100%);color:white;padding:30px 40px;border-radius:12px;margin-bottom:24px}}
.header h1{{font-size:26px;margin-bottom:6px;font-weight:700}}
.header .sub{{font-size:14px;opacity:0.85}}
.header .meta{{display:flex;gap:40px;margin-top:16px;font-size:12px;opacity:0.7}}

/* KPI Cards */
.kpi-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:24px}}
.kpi-card{{background:white;border-radius:10px;padding:20px;box-shadow:0 2px 8px rgba(0,0,0,0.06)}}
.kpi-card .label{{font-size:12px;color:#7f8c8d;text-transform:uppercase;margin-bottom:6px}}
.kpi-card .value{{font-size:28px;font-weight:700}}
.kpi-card .subval{{font-size:12px;color:#95a5a6;margin-top:4px}}
.c-green .value{{color:#27ae60}}
.c-blue .value{{color:#2980b9}}
.c-orange .value{{color:#e67e22}}
.c-purple .value{{color:#8e44ad}}

/* Section */
.section{{background:white;border-radius:10px;padding:28px;margin-bottom:20px;box-shadow:0 2px 8px rgba(0,0,0,0.06)}}
.section h2{{font-size:18px;color:#1e3a5f;border-bottom:2px solid #3498db;padding-bottom:8px;margin-bottom:16px}}
.section h3{{font-size:15px;color:#2c3e50;margin:16px 0 8px 0}}
.section p{{margin-bottom:10px}}

/* Tables */
table{{width:100%;border-collapse:collapse;font-size:12px;margin:12px 0}}
thead{{background:#1e3a5f;color:white}}
th{{padding:8px 10px;text-align:left;font-weight:600;white-space:nowrap}}
td{{padding:7px 10px;border-bottom:1px solid #ecf0f1}}
tr:hover{{background:#eaf2f8}}
tr:nth-child(even){{background:#f8f9fa}}
tr:nth-child(even):hover{{background:#eaf2f8}}
.total{{font-weight:bold;background:#eaf2f8!important;border-top:2px solid #1e3a5f}}
.num{{text-align:right;font-family:'Consolas',monospace}}
.method{{font-size:11px;color:#7f8c8d;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}

/* Badge */
.badge{{display:inline-block;width:24px;height:24px;line-height:24px;text-align:center;border-radius:12px;color:white;font-weight:bold;font-size:12px}}
.badge2{{display:inline-block;padding:1px 8px;border-radius:10px;background:#27ae60;color:white;font-weight:bold;font-size:12px}}

/* Cards grid */
.card-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:12px;margin:16px 0}}
.card{{background:#f8f9fa;border-radius:8px;padding:12px;border:1px solid #e8e8e8}}
.card .cname{{font-weight:600;font-size:12px;margin-bottom:4px}}
.card .cinfo{{font-size:11px;color:#7f8c8d}}
.card svg{{margin-top:6px}}

/* Summary box */
.summary-box{{background:#eaf2f8;border-left:4px solid #2980b9;padding:16px 20px;border-radius:6px;margin:16px 0}}
.summary-box p{{margin:4px 0}}

/* Footer */
.footer{{text-align:center;color:#95a5a6;font-size:11px;padding:20px;margin-top:24px;border-top:1px solid #ecf0f1}}

/* Print */
@media print{{
    body{{font-size:11px;background:white}}
    .container{{max-width:100%;padding:10px}}
    .section{{page-break-inside:avoid;margin-bottom:12px;padding:16px;box-shadow:none;border:1px solid #ddd}}
    .kpi-grid{{grid-template-columns:repeat(4,1fr)}}
    .header{{padding:16px 24px}}
    table{{font-size:10px}}
    th,td{{padding:4px 6px}}
}}

/* Nav */
.nav{{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:20px}}
.nav a{{padding:6px 14px;background:white;border:1px solid #dce4ec;border-radius:6px;text-decoration:none;color:#2c3e50;font-size:12px;transition:all 0.2s}}
.nav a:hover{{background:#1e3a5f;color:white;border-color:#1e3a5f}}

/* Input */
.search-input{{width:100%;max-width:400px;padding:8px 12px;border:1px solid #dce4ec;border-radius:6px;font-size:13px;margin-bottom:12px}}

/* Two column */
.col2{{display:grid;grid-template-columns:1fr 1fr;gap:20px}}
@media(max-width:768px){{.col2{{grid-template-columns:1fr}}}}
</style>
</head>
<body>
<div class="container">

<!-- HEADER -->
<div class="header">
    <h1>📊 全客户季度销售预测报告</h1>
    <div class="sub">全客户维度（KA/AA/MM/KM）· 2026Q2 预测 · 540种方法极致回测</div>
    <div class="meta">
        <span>编制：CFO办公室 × AI预测引擎</span>
        <span>数据截止：2026-05-30</span>
        <span>报告日期：2026-06-11</span>
        <span>预测目标：2026Q2 (Apr–Jun)</span>
    </div>
</div>

<!-- NAV -->
<div class="nav">
    <a href="#summary">执行摘要</a>
    <a href="#methods">方法体系</a>
    <a href="#bytype">分类型预测</a>
    <a href="#confidence">置信度分析</a>
    <a href="#tables">预测总表</a>
    <a href="#insights">洞察与建议</a>
    <a href="#appendix">附录</a>
</div>

<!-- SECTION 1: EXECUTIVE SUMMARY -->
<div class="section" id="summary">
    <h2>一、执行摘要</h2>
    
    <div class="kpi-grid">
        <div class="kpi-card c-blue">
            <div class="label">预测总收入（万元）</div>
            <div class="value">{summary['overall']['pred_revenue_wan']:.0f}</div>
            <div class="subval">322个客户 · 20个季度历史</div>
        </div>
        <div class="kpi-card c-green">
            <div class="label">预测总利润（万元）</div>
            <div class="value">{summary['overall']['pred_profit_wan']:.0f}</div>
            <div class="subval">综合毛利率 ~36%</div>
        </div>
        <div class="kpi-card c-purple">
            <div class="label">高置信客户(A+B)</div>
            <div class="value">{o['high_confidence_ab']}<span style="font-size:16px;color:#95a5a6"> / {summary['customers_total']}</span></div>
            <div class="subval">占比 {o['high_confidence_pct']}% · 覆盖约55%预测收入</div>
        </div>
        <div class="kpi-card c-orange">
            <div class="label">测试方法总数</div>
            <div class="value">{summary['methods_total']}</div>
            <div class="subval">20大类别 · 双重优化 · 每客户~500次回测</div>
        </div>
    </div>

    <div class="summary-box">
        <p><b>📌 一句话结论：</b>本报告基于全客户（KA/AA/MM/KM共{summary['customers_total']}个）历史出货数据，采用<b>{summary['methods_total']}种预测方法</b>进行独立滚动回测和双重优化选优。全客户预测2026Q2季度收入<b>{summary['overall']['pred_revenue_wan']:.0f}万元</b>（利润{summary['overall']['pred_profit_wan']:.0f}万元），其中<b>48个客户</b>（14.9%）达到A/B级高置信度，覆盖约55%的预测收入。组合预测（Ensemble Top3WAPE）成为最有效的选优策略（35个客户采用），同比季节法在KA大客户中表现最优。</p>
        <p><b>与上一版v2对比：</b>方法从357种增至540种（+51%），第二轮组合优化提升了35个客户的置信度，高置信客户数从45增至48，KA客户高置信收入占比从62.1%提升至83.8%。</p>
    </div>
</div>

<!-- SECTION 2: METHODOLOGY -->
<div class="section" id="methods">
    <h2>二、预测方法体系</h2>
    
    <div class="col2">
        <div>
            <h3>方法库概览（540种）</h3>
            <table>
                <thead><tr><th>方法类别</th><th>数量</th><th>典型应用场景</th></tr></thead>
                <tbody>
                    <tr><td>稀疏需求法（Croston/SBA/TSB）</td><td class="num">144</td><td>MM/KM间歇性需求客户</td></tr>
                    <tr><td>EWMA（指数加权移动平均）</td><td class="num">90</td><td>有近期趋势的中等活跃客户</td></tr>
                    <tr><td>保守衰减/增长</td><td class="num">80</td><td>稳定但缓慢变化的客户</td></tr>
                    <tr><td>同比季节法（YoY Seasonal）</td><td class="num">72</td><td>KA大客户/季节性明显</td></tr>
                    <tr><td>加权移动平均（WMA）</td><td class="num">36</td><td>近期权重敏感的客户</td></tr>
                    <tr><td>基础移动平均</td><td class="num">27</td><td>平稳序列基线</td></tr>
                    <tr><td>多项式趋势（二次/三次）</td><td class="num">12</td><td>增长/下降趋势明显的客户</td></tr>
                    <tr><td>截尾平均（Trimmed Mean）</td><td class="num">12</td><td>稳健估计/异常值容忍</td></tr>
                    <tr><td>中位数/漂移/线性趋势</td><td class="num">25</td><td>不同趋势模式基线</td></tr>
                    <tr><td>数据变换（Log/Sqrt等）</td><td class="num">13</td><td>偏态分布/异方差序列</td></tr>
                    <tr><td>季节方法（Naive/MSI）</td><td class="num">9</td><td>明显季节性序列</td></tr>
                    <tr><td>统计模型（Holt/Theta）</td><td class="num">2</td><td>趋势+季节综合建模</td></tr>
                    <tr><td>组合预测（Ensemble）</td><td class="num">—</td><td>第二轮优化自动应用</td></tr>
                    <tr><td>同类参照（Cohort）</td><td class="num">—</td><td>数据不足客户的群体基准</td></tr>
                </tbody>
            </table>
        </div>
        <div>
            <h3>双重优化流程</h3>
            <div style="background:#f8f9fa;border-radius:8px;padding:16px;font-size:12px">
                <p><b>第一轮：540种方法滚动回测</b></p>
                <p style="margin-left:16px">→ 每客户独立6折滚动回测（活跃客户）</p>
                <p style="margin-left:16px">→ 以WAPE最小化为目标选最优方法</p>
                <p style="margin-left:16px">→ 生成初始预测和置信度分级</p>
                
                <p style="margin-top:12px"><b>第二轮：E级客户专项优化</b></p>
                <p style="margin-left:16px">→ WAPE>60%的客户进入第二轮</p>
                <p style="margin-left:16px">→ 组合预测（Top3 WAPE加权Ensemble）</p>
                <p style="margin-left:16px">→ 同类客户参照（Cohort-Based，按类型×分层）</p>
                <p style="margin-left:16px">→ 如新WAPE低于原值则替换</p>
                
                <p style="margin-top:12px"><b>置信度分级标准</b></p>
                <p style="margin-left:16px">A级 ≤15% | B级 15-25% | C级 25-40% | D级 40-60% | E级 >60%</p>
                
                <p style="margin-top:12px">第二轮优化提升：<b>{o['second_pass_improved']}个客户</b></p>
                <p>组合预测成为最常用方法：<b>35个客户</b></p>
            </div>
            
            <h3>方法使用排名（Top 10）</h3>
            {method_rows}
        </div>
    </div>
</div>

<!-- SECTION 3: BY TYPE -->
<div class="section" id="bytype">
    <h2>三、分客户类型预测结果</h2>
    
    <table>
        <thead><tr><th>客户类型</th><th>客户数</th><th>预测收入</th><th>平均WAPE</th><th>中位WAPE</th><th>高置信(A+B)</th><th>高置信收入占比</th><th>置信度分布</th></tr></thead>
        <tbody>{ct_rows}</tbody>
    </table>
    
    <div class="summary-box" style="margin-top:16px">
        <p><b>关键发现：</b></p>
        <p>• <b>KA客户（33个）</b>：高置信度客户15个，覆盖<b>83.8%的KA预测收入</b>——KA预测高度可靠。同季节法和稀疏需求法是KA的主力方法。</p>
        <p>• <b>AA客户（11个）</b>：平均WAPE 64.65%，波动大且历史数据稀疏，均无A/B级。建议结合销售端在手订单做辅助判断。</p>
        <p>• <b>MM客户（170个）</b>：数量最多但9个达到高置信，38.1%收入高置信——活跃MM客户可通过组合预测获得较好结果。</p>
        <p>• <b>KM客户（37个）</b>：最难预测群体，仅1个高置信。极端稀疏性导致统计方法难以捕捉。</p>
        <p>• <b>组合预测（Ensemble Top3WAPE）</b>：第二轮优化的核心武器，让35个客户置信度显著提升，是本次最大的方法论创新。</p>
    </div>
</div>

<!-- SECTION 4: CONFIDENCE -->
<div class="section" id="confidence">
    <h2>四、置信度全景分析</h2>
    
    <h3>置信度分布</h3>
    {grade_html}
    
    <div class="col2" style="margin-top:16px">
        <div>
            <h3>按客户分层统计</h3>
            <table>
                <thead><tr><th>客户分层</th><th>数量</th><th>典型特征</th><th>推荐策略</th></tr></thead>
                <tbody>
                    <tr><td>活跃客户</td><td class="num">49</td><td>近3月有交易，数据充足</td><td>全方法回测+组合优化</td></tr>
                    <tr><td>半活跃/过渡</td><td class="num">11</td><td>近半年有交易，数据中等</td><td>精简方法+同类参照</td></tr>
                    <tr><td>沉睡大客</td><td class="num">98</td><td>历史贡献大但近期无交易</td><td>唤醒策略+保守预测</td></tr>
                    <tr><td>沉睡中客</td><td class="num">88</td><td>历史中等，近期不活跃</td><td>同类参照·低基线预测</td></tr>
                    <tr><td>沉睡小客</td><td class="num">138</td><td>小批量一次性客户</td><td>微预测·聚焦复购激活</td></tr>
                </tbody>
            </table>
        </div>
        <div>
            <h3>优化效果对比</h3>
            <table>
                <thead><tr><th>指标</th><th>V2 (357方法)</th><th>V3 (540方法)</th><th>提升</th></tr></thead>
                <tbody>
                    <tr><td>总方法数</td><td class="num">357</td><td class="num">540</td><td class="num" style="color:#27ae60">+51%</td></tr>
                    <tr><td>高置信(A+B)</td><td class="num">45</td><td class="num">48</td><td class="num" style="color:#27ae60">+3</td></tr>
                    <tr><td>高置信占比</td><td class="num">14.0%</td><td class="num">14.9%</td><td class="num" style="color:#27ae60">+0.9pp</td></tr>
                    <tr><td>第二轮优化</td><td class="num">—</td><td class="num">35客户</td><td class="num" style="color:#27ae60">新增</td></tr>
                    <tr><td>KA A+B收入占比</td><td class="num">62.1%</td><td class="num">83.8%</td><td class="num" style="color:#27ae60">+21.7pp</td></tr>
                    <tr><td>组合预测客户</td><td class="num">—</td><td class="num">35</td><td class="num" style="color:#27ae60">#1方法</td></tr>
                </tbody>
            </table>
        </div>
    </div>
</div>

<!-- SECTION 5: PREDICTION TABLES -->
<div class="section" id="tables">
    <h2>五、全客户预测总表</h2>
    
    <input type="text" class="search-input" placeholder="🔍 输入客户名称搜索..." id="searchBox" oninput="filterAll()">
    
    <h3>KA客户（33个）— 预测收入 {t['KA']['pred_total']/10000:.0f}万</h3>
    <div id="ka-table">{ka_table}</div>
    
    <h3>AA客户（11个）— 预测收入 {t['AA']['pred_total']/10000:.1f}万</h3>
    <div id="aa-table">{aa_table}</div>
    
    <h3>MM客户 Top（>1万预测）— 预测收入约{fmt_wan(t['MM']['pred_total'])}万</h3>
    <div id="mm-table">{mm_table}</div>
    
    <h3>KM客户（预测>0.5万）— 预测收入约{fmt_wan(t['KM']['pred_total'])}万</h3>
    <div id="km-table">{km_table}</div>
</div>

<!-- SECTION 6: INSIGHTS -->
<div class="section" id="insights">
    <h2>六、核心洞察与建议</h2>
    
    <div class="col2">
        <div style="background:#f0faf0;border-left:4px solid #27ae60;padding:16px;border-radius:6px">
            <h3 style="color:#27ae60">✅ 亮点</h3>
            <p><b>1. KA预测高度可靠</b>：83.8%的KA收入由高置信方法预测，可直接用于财务预算。</p>
            <p><b>2. 组合预测效果显著</b>：Top3 WAPE加权Ensemble成为35个客户的最优方法，是本次最大方法论突破。</p>
            <p><b>3. 540种方法覆盖全面</b>：从稀疏需求到季节模型，从简单均值到多项式趋势，覆盖了几乎所有时间序列模式。</p>
            <p><b>4. 双重优化创新</b>：第二轮Cohort+Ensemble策略让35个原本低置信的客户获得提升。</p>
        </div>
        <div style="background:#fef9e7;border-left:4px solid #f39c12;padding:16px;border-radius:6px">
            <h3 style="color:#e67e22">⚠️ 待改进</h3>
            <p><b>1. AA/KM客户置信度低</b>：AA无A/B级，KM仅1个。需引入订单频次模型（二分类+回归）。</p>
            <p><b>2. 74%客户仍为E级</b>：大量沉睡/一次性客户天然无法用统计方法预测，建议转为"零预测+复购概率"模式。</p>
            <p><b>3. 未知客户占大头</b>：71个未分类客户（含"未知客户"）贡献了最大预测额。建议完善CRM数据录入。</p>
            <p><b>4. 仅基于历史出货</b>：未纳入在手订单、客户forecast、行业趋势等前瞻信息。建议将销售端判断与统计预测结合。</p>
        </div>
    </div>

    <h3 style="margin-top:24px">后续优化建议（优先级排序）</h3>
    <table>
        <thead><tr><th>优先级</th><th>优化方向</th><th>预期效果</th><th>适用客户群</th></tr></thead>
        <tbody>
            <tr><td><span class="badge" style="background:#e74c3c">1</span></td><td>订单频次模型（二阶段：是否回购→金额）</td><td>MM/KM WAPE从84%降至50-60%</td><td>MM 170 + KM 37</td></tr>
            <tr><td><span class="badge" style="background:#e67e22">2</span></td><td>引入销售端在手订单/客户forecast</td><td>KA/AA WAPE再降5-10pp</td><td>KA 33 + AA 11</td></tr>
            <tr><td><span class="badge" style="background:#f39c12">3</span></td><td>更细粒度预测（月度/SKU级）</td><td>运营层面可直接使用</td><td>全客户</td></tr>
            <tr><td><span class="badge" style="background:#3498db">4</span></td><td>外部数据增强（PMI/行业指数）</td><td>宏观经济敏感型客户改善</td><td>KA/AA大客户</td></tr>
            <tr><td><span class="badge" style="background:#3498db">5</span></td><td>客户生命周期模型（RFM+生存分析）</td><td>精准识别流失风险客户</td><td>沉睡客户群体</td></tr>
        </tbody>
    </table>
</div>

<!-- SECTION 7: APPENDIX -->
<div class="section" id="appendix">
    <h2>七、口径与说明</h2>
    
    <div class="col2">
        <div>
            <h3>数据口径</h3>
            <table>
                <tr><td>数据源</td><td>财务分析-5月（6.3）.xlsx「总表」</td></tr>
                <tr><td>数据规模</td><td>331,402行 × 67列</td></tr>
                <tr><td>时间跨度</td><td>2020-01 ~ 2026-05</td></tr>
                <tr><td>训练截止</td><td>{summary['train_end']}</td></tr>
                <tr><td>预测目标</td><td>{summary['pred_target']}</td></tr>
                <tr><td>聚合维度</td><td>客户级季度销售额</td></tr>
                <tr><td>客户分类</td><td>KA>1亿 · AA>5000万 · KM>1000万 · MM<1000万</td></tr>
                <tr><td>金额口径</td><td>RMB未税金额</td></tr>
            </table>
        </div>
        <div>
            <h3>方法说明</h3>
            <table>
                <tr><td>回测方式</td><td>6折滚动回测（活跃）/ 4折（半活跃）</td></tr>
                <tr><td>选优指标</td><td>WAPE（加权绝对百分比误差）</td></tr>
                <tr><td>预测区间</td><td>基于回测WAPE：pred×(1±WAPE)</td></tr>
                <tr><td>利润预测</td><td>按客户类型历史毛利率加权</td></tr>
                <tr><td>第二轮优化</td><td>组合预测 + 同类参照</td></tr>
                <tr><td>模型版本</td><td>v3 ({summary['methods_total']}方法)</td></tr>
            </table>
            
            <h3 style="margin-top:16px">局限性与免责</h3>
            <ul style="font-size:12px;color:#7f8c8d;padding-left:16px">
                <li>仅基于历史出货数据，未纳入前瞻信息</li>
                <li>客户分类字段存在15.2%缺失，部分客户类型为推断</li>
                <li>"未知客户"（终端客户名称为空）聚合了多个客户的行为</li>
                <li>预测区间基于历史WAPE，不代表未来实际波动范围</li>
                <li>极低置信度（E级）客户的预测建议仅作下限参考</li>
            </ul>
        </div>
    </div>
</div>

<!-- FOOTER -->
<div class="footer">
    <p>CFO办公室 × AI预测引擎 · 全客户季度销售预测报告 v3 · 数据截止2026-05-30 · 生成于 {now}</p>
    <p>本报告由智数分析专家团（诺亚团队）自动生成 | 测试{summary['methods_total']}种方法 | 覆盖{summary['customers_total']}个客户</p>
</div>

</div>

<script>
function filterAll() {{
    var q = document.getElementById('searchBox').value.toLowerCase();
    var divs = ['ka-table','aa-table','mm-table','km-table'];
    divs.forEach(function(d) {{
        var el = document.getElementById(d);
        var rows = el.querySelectorAll('tr');
        rows.forEach(function(r, i) {{
            if (i === 0) return; // skip header
            if (q === '') {{ r.style.display = ''; return; }}
            var name = r.querySelector('td');
            if (name && name.textContent.toLowerCase().indexOf(q) >= 0) {{
                r.style.display = '';
            }} else {{
                r.style.display = 'none';
            }}
        }});
    }});
}}
</script>

</body>
</html>'''

# Write
report_path = f'{OUTDIR}/全客户季度销售预测报告.html'
with open(report_path, 'w', encoding='utf-8') as f:
    f.write(html_content)

import os
print(f'Report generated: {report_path}')
print(f'Size: {os.path.getsize(report_path)/1024:.0f}KB')
