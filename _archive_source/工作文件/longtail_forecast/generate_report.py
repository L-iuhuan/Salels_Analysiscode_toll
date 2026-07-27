#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate the longtail customer quarterly sales forecast HTML report."""

import csv
import json
from collections import defaultdict

def safe_float(v):
    try: return float(v)
    except: return 0.0

def safe_int(v):
    try: return int(float(v))
    except: return 0

# ─── Read data ───
rows = []
with open('长尾客户预测总表.csv', 'r', encoding='utf-8-sig') as f:
    for r in csv.DictReader(f):
        rows.append(r)

hist_rows = []
with open('长尾客户季度历史与预测.csv', 'r', encoding='utf-8-sig') as f:
    for r in csv.DictReader(f):
        hist_rows.append(r)

with open('长尾预测摘要.json', 'r', encoding='utf-8') as f:
    summary = json.load(f)

method_rows = []
with open('预测方法选优结果.csv', 'r', encoding='utf-8-sig') as f:
    for r in csv.DictReader(f):
        method_rows.append(r)

# ─── Process ───
mm = [r for r in rows if r['客户类型'] == 'MM']
km = [r for r in rows if r['客户类型'] == 'KM']

def revenue_tier(rev):
    if rev >= 100: return '≥100万'
    elif rev >= 30: return '30~100万'
    else: return '<30万'

tier_order = ['≥100万', '30~100万', '<30万']

groups = {}
for cust_type, cust_rows in [('MM', mm), ('KM', km)]:
    tier_groups = defaultdict(list)
    for r in cust_rows:
        rev = safe_float(r['Q预测值(万元)'])
        tier = revenue_tier(rev)
        tier_groups[tier].append(r)
    for tier in tier_groups:
        tier_groups[tier].sort(key=lambda x: safe_float(x['Q预测值(万元)']), reverse=True)
    groups[cust_type] = dict(tier_groups)

# Top 20
top20 = sorted(rows, key=lambda x: safe_float(x['Q预测值(万元)']), reverse=True)[:20]

# History dict
hist_dict = defaultdict(list)
for r in hist_rows:
    hist_dict[r['客户名称']].append(r)

# Attention: high revenue low confidence
high_rev_low_conf = [r for r in rows if safe_float(r['Q预测值(万元)']) > 20 and safe_float(r['回测WAPE(%)']) > 60]
high_rev_low_conf.sort(key=lambda x: safe_float(x['Q预测值(万元)']), reverse=True)

# Lost risk
lost_risk = [r for r in rows if r['客户分层'] in ('休眠','一次性') and safe_float(r['历史总销售额(万元)']) > 5]
lost_risk.sort(key=lambda x: safe_float(x['历史总销售额(万元)']), reverse=True)

# Profit anomaly
profit_low = [r for r in rows if safe_float(r['Q预测值(万元)']) > 1 and safe_float(r['预测毛利率(%)']) < 20]
profit_low.sort(key=lambda x: safe_float(x['Q预测值(万元)']), reverse=True)

profit_high = [r for r in rows if safe_float(r['Q预测值(万元)']) > 1 and safe_float(r['预测毛利率(%)']) > 60]
profit_high.sort(key=lambda x: safe_float(x['Q预测值(万元)']), reverse=True)

# Chart data JSON for top 20
chart_json_items = []
for r in top20:
    name = r['客户名称']
    h = hist_dict.get(name, [])
    quarters = []
    actuals = []
    for hr in sorted(h, key=lambda x: int(x['季度'])):
        if hr['是否为预测'] == '0':
            quarters.append(hr['季度标签'])
            actuals.append(round(safe_float(hr['实际销售额'])/10000, 2))
    chart_json_items.append({
        'name': name,
        'quarters': quarters,
        'actuals': actuals,
        'pred': round(safe_float(r['Q预测值(万元)']), 2),
        'predLo': round(safe_float(r['预测区间下限(万元)']), 2),
        'predHi': round(safe_float(r['预测区间上限(万元)']), 2),
        'type': r['客户类型'],
        'tier': r['客户分层'],
        'conf': r['置信度'],
        'method': r['最优方法名称'],
        'wape': safe_float(r['回测WAPE(%)'])
    })

# ─── Helper: escape ───
def esc(s):
    return s.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('"','&quot;')

# ─── Helper: confidence tag ───
def conf_tag(c):
    if c == '高': return '<span class="tag tg">高</span>'
    elif c == '中': return '<span class="tag ty">中</span>'
    else: return '<span class="tag tr">低</span>'

def type_tag(t):
    if t == 'MM': return '<span class="tag tmm">MM</span>'
    else: return '<span class="tag tkm">KM</span>'

def tier_tag(t):
    cls = {'活跃':'tg','稀疏':'ty','休眠':'td','一次性':'tl'}.get(t,'tr')
    return f'<span class="tag {cls}">{t}</span>'

def conf_dot(c):
    if c == '高': return '<span style="color:#1a9850">●</span>'
    elif c == '中': return '<span style="color:#e6a817">●</span>'
    else: return '<span style="color:#d73027">●</span>'

# ─── Build table HTML ───
def build_table(cust_list, title_bar_class, title_text):
    if not cust_list:
        return ''
    total_rev = sum(safe_float(r['Q预测值(万元)']) for r in cust_list)
    total_profit = sum(safe_float(r['预测毛利(万元)']) for r in cust_list)
    
    html = f'<div class="tier-bar {title_bar_class}">▌ {title_text} · {len(cust_list)}个客户 · 合计收入 {total_rev:,.0f} 万 · 利润 {total_profit:,.0f} 万</div>\n'
    html += '''<table class="sortable"><thead><tr>
<th>客户</th><th>分层</th><th>置信</th>
<th class="r">Q预测(万)</th><th class="r">区间(万)</th>
<th class="r">毛利(万)</th><th class="r">毛利率</th>
<th class="r">WAPE</th><th>最优方法</th>
</tr></thead><tbody>\n'''
    for r in cust_list:
        rev = safe_float(r['Q预测值(万元)'])
        lo = safe_float(r['预测区间下限(万元)'])
        hi = safe_float(r['预测区间上限(万元)'])
        profit = safe_float(r['预测毛利(万元)'])
        margin = safe_float(r['预测毛利率(%)'])
        wape = safe_float(r['回测WAPE(%)'])
        margin_cls = 'neg' if margin < 0 else ''
        html += f'''<tr>
<td>{conf_dot(r["置信度"])} {esc(r["客户名称"])}</td>
<td>{tier_tag(r["客户分层"])}</td>
<td>{conf_tag(r["置信度"])}</td>
<td class="r"><b>{rev:,.1f}</b></td>
<td class="r muted">{lo:,.1f}~{hi:,.1f}</td>
<td class="r {margin_cls}">{profit:,.1f}</td>
<td class="r {margin_cls}">{margin:.1f}%</td>
<td class="r">{wape:.0f}%</td>
<td style="font-size:11px">{esc(r["最优方法名称"])}</td>
</tr>\n'''
    html += '</tbody></table>\n'
    return html

# ─── Build all tables ───
all_tables_html = ''

# MM tables
for tier_name in tier_order:
    cust_list = groups.get('MM', {}).get(tier_name, [])
    if cust_list:
        total_rev = sum(safe_float(r['Q预测值(万元)']) for r in cust_list)
        total_profit = sum(safe_float(r['预测毛利(万元)']) for r in cust_list)
        title = f'MM · {tier_name} · 预测收入 {total_rev:,.0f} 万'
        all_tables_html += build_table(cust_list, 'tier-mm', title)

# KM tables
for tier_name in tier_order:
    cust_list = groups.get('KM', {}).get(tier_name, [])
    if cust_list:
        total_rev = sum(safe_float(r['Q预测值(万元)']) for r in cust_list)
        total_profit = sum(safe_float(r['预测毛利(万元)']) for r in cust_list)
        title = f'KM · {tier_name} · 预测收入 {total_rev:,.0f} 万'
        all_tables_html += build_table(cust_list, 'tier-km', title)

# ─── Attention section ───
attention_html = ''

# High revenue low confidence
attention_html += '<h3>⚠ 高收入低置信度客户（预测收入&gt;20万 且 WAPE&gt;60%）</h3>\n'
if high_rev_low_conf:
    attention_html += '<table><thead><tr><th>客户</th><th>类型</th><th class="r">预测收入(万)</th><th class="r">WAPE</th><th>方法</th><th>建议</th></tr></thead><tbody>\n'
    for r in high_rev_low_conf:
        attention_html += f'''<tr>
<td>{esc(r["客户名称"])}</td>
<td>{type_tag(r["客户类型"])}</td>
<td class="r"><b>{safe_float(r["Q预测值(万元)"]):,.1f}</b></td>
<td class="r neg">{safe_float(r["回测WAPE(%)"]):,.0f}%</td>
<td style="font-size:11px">{esc(r["最优方法名称"])}</td>
<td style="font-size:11px">需销售端重点跟进，预测波动大，建议结合客户近期动态人工修正</td>
</tr>\n'''
    attention_html += '</tbody></table>\n'
else:
    attention_html += '<p class="muted">无符合条件的客户。</p>\n'

# Lost risk
attention_html += '<h3>🔴 流失风险客户（休眠/一次性 且 历史总销售&gt;5万）</h3>\n'
if lost_risk:
    attention_html += f'<p>共 {len(lost_risk)} 个客户曾有较大历史贡献但当前处于休眠或一次性状态，以下为Top 15：</p>\n'
    attention_html += '<table><thead><tr><th>客户</th><th>类型</th><th>分层</th><th class="r">历史总销售(万)</th><th>最后交易</th><th>建议</th></tr></thead><tbody>\n'
    for r in lost_risk[:15]:
        attention_html += f'''<tr>
<td>{esc(r["客户名称"])}</td>
<td>{type_tag(r["客户类型"])}</td>
<td>{tier_tag(r["客户分层"])}</td>
<td class="r">{safe_float(r["历史总销售额(万元)"]):,.1f}</td>
<td class="r">{r["最后交易日期"]}</td>
<td style="font-size:11px">建议客户成功团队定向激活，了解流失原因</td>
</tr>\n'''
    attention_html += '</tbody></table>\n'

# Profit anomaly
attention_html += '<h3>📊 利润率异常客户</h3>\n'
if profit_low:
    attention_html += '<p><b>低毛利率客户（毛利率&lt;20%）：</b></p>\n'
    attention_html += '<table><thead><tr><th>客户</th><th class="r">预测收入(万)</th><th class="r">毛利率</th><th>主要系列</th></tr></thead><tbody>\n'
    for r in profit_low[:10]:
        attention_html += f'''<tr>
<td>{esc(r["客户名称"])}</td>
<td class="r">{safe_float(r["Q预测值(万元)"]):,.1f}</td>
<td class="r neg">{safe_float(r["预测毛利率(%)"]):.1f}%</td>
<td style="font-size:11px">{esc(r.get("主要系列",""))}</td>
</tr>\n'''
    attention_html += '</tbody></table>\n'

if profit_high:
    attention_html += '<p><b>高毛利率客户（毛利率&gt;60%）：</b></p>\n'
    attention_html += '<table><thead><tr><th>客户</th><th class="r">预测收入(万)</th><th class="r">毛利率</th><th>主要系列</th></tr></thead><tbody>\n'
    for r in profit_high[:10]:
        attention_html += f'''<tr>
<td>{esc(r["客户名称"])}</td>
<td class="r">{safe_float(r["Q预测值(万元)"]):,.2f}</td>
<td class="r pos">{safe_float(r["预测毛利率(%)"]):.1f}%</td>
<td style="font-size:11px">{esc(r.get("主要系列",""))}</td>
</tr>\n'''
    attention_html += '</tbody></table>\n'

# ─── Product series distribution ───
series_counter = defaultdict(int)
for r in rows:
    s = r.get('主要系列', '').strip()
    if s and s != '未知':
        series_counter[s] += 1
top_series = sorted(series_counter.items(), key=lambda x: x[1], reverse=True)[:10]

# ─── Chart JSON ───
chart_data_json = json.dumps(chart_json_items, ensure_ascii=False, indent=2)

# ─── Method distribution table ───
method_dist = summary['方法使用分布']
method_items = sorted(method_dist.items(), key=lambda x: x[1], reverse=True)

# ─── Tier distribution for active customers using individual methods ───
active_methods = defaultdict(int)
for r in rows:
    if r['客户分层'] == '活跃':
        active_methods[r['最优方法名称']] += 1
active_method_items = sorted(active_methods.items(), key=lambda x: x[1], reverse=True)

# ─── Generate HTML ───
html = f'''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>2026Q2 长尾客户(MM/KM)季度销售预测报告</title>
<style>
  :root {{ --ink:#1c2733; --mut:#7a828c; --line:#e3e7ec; --blue:#1e3a5f; --green:#2ecc71; --orange:#e67e22; --bg:#f6f8fa; }}
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  body {{ font-family:"Microsoft YaHei","PingFang SC","Noto Sans CJK SC",sans-serif; color:var(--ink);
         margin:0; background:var(--bg); line-height:1.65; font-size:14px; }}
  .wrap {{ max-width:1100px; margin:0 auto; padding:28px 20px 80px; }}

  /* Header */
  .header {{ background:linear-gradient(135deg, #1e3a5f 0%, #2c5f8a 100%); color:#fff; padding:24px 28px; border-radius:12px; margin-bottom:24px; }}
  .header h1 {{ font-size:22px; margin:0 0 4px; font-weight:700; }}
  .header .meta {{ font-size:12.5px; opacity:0.85; line-height:1.5; }}

  /* Navigation */
  .toc {{ background:#fff; border:1px solid var(--line); border-radius:10px; padding:16px 20px; margin:16px 0 24px; }}
  .toc h3 {{ font-size:14px; margin-bottom:8px; color:var(--blue); }}
  .toc ol {{ padding-left:20px; }}
  .toc li {{ font-size:13px; margin:3px 0; }}
  .toc a {{ color:var(--blue); text-decoration:none; }}
  .toc a:hover {{ text-decoration:underline; }}

  h2 {{ font-size:18px; margin:36px 0 10px; padding-left:10px; border-left:4px solid var(--blue); color:var(--blue); }}
  h3 {{ font-size:15px; margin:18px 0 8px; color:#333; }}
  p, li {{ font-size:13.5px; }}
  .muted {{ color:var(--mut); font-size:12px; }}
  .neg {{ color:#d73027; }}
  .pos {{ color:#1a9850; }}

  /* KPI cards */
  .kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:12px; margin:16px 0; }}
  .kpi {{ background:#fff; border:1px solid var(--line); border-radius:10px; padding:14px 16px; }}
  .kpi .t {{ font-size:12px; color:var(--mut); }}
  .kpi .v {{ font-size:22px; font-weight:700; margin-top:2px; }}
  .kpi .s {{ font-size:11.5px; color:var(--mut); margin-top:2px; }}
  .kpi .v.blue {{ color:var(--blue); }}
  .kpi .v.green {{ color:var(--green); }}
  .kpi .v.orange {{ color:var(--orange); }}

  /* Tags */
  .tag {{ display:inline-block; border-radius:20px; padding:1px 10px; font-size:11.5px; margin-right:4px; font-weight:500; }}
  .tg {{ background:#e7f4ea; color:#1a9850; }}
  .ty {{ background:#fdf3da; color:#9a7407; }}
  .tr {{ background:#fdeae7; color:#d73027; }}
  .tmm {{ background:#e8f0fe; color:#1e3a5f; }}
  .tkm {{ background:#fff3e0; color:#e67e22; }}
  .td {{ background:#f0f0f0; color:#888; }}
  .tl {{ background:#f5f5f5; color:#aaa; }}

  /* Tables */
  table {{ border-collapse:collapse; width:100%; background:#fff; font-size:12.5px; margin-bottom:12px; }}
  th, td {{ border:1px solid var(--line); padding:5px 7px; text-align:left; }}
  th {{ background:#eef2f6; font-weight:600; white-space:nowrap; position:sticky; top:0; }}
  td.r {{ text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }}
  th.r {{ text-align:right; }}
  tr:nth-child(even) td {{ background:#fbfcfd; }}
  tr:hover td {{ background:#f0f4f8; }}

  /* Tier bar */
  .tier-bar {{ padding:10px 14px; margin:16px 0 4px; border-radius:6px; font-size:13px; font-weight:600; }}
  .tier-mm {{ background:#e8f0fe; color:#1e3a5f; border-left:4px solid #1e3a5f; }}
  .tier-km {{ background:#fff3e0; color:#b85c00; border-left:4px solid #e67e22; }}

  /* Box */
  .box {{ background:#fff; border:1px solid var(--line); border-left:4px solid var(--blue); border-radius:8px; padding:14px 18px; margin:14px 0; }}
  .box.good {{ border-left-color:var(--green); background:#f8fdf5; }}
  .box.warn {{ border-left-color:#d73027; background:#fff8f6; }}
  .box.amber {{ border-left-color:var(--orange); background:#fffdf5; }}

  /* Chart cards */
  .chart-grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(480px,1fr)); gap:14px; margin-top:14px; }}
  .chart-card {{ background:#fff; border:1px solid var(--line); border-radius:10px; padding:12px 14px; }}
  .chart-card .ch {{ font-size:13px; font-weight:600; margin-bottom:6px; display:flex; align-items:center; gap:6px; flex-wrap:wrap; }}
  .chart-card .ch .nm {{ font-size:14px; }}
  .chart-card svg {{ width:100%; }}

  /* Search box */
  .search-box {{ margin:8px 0 12px; }}
  .search-box input {{ width:100%; max-width:400px; padding:8px 12px; border:1px solid var(--line); border-radius:6px; font-size:13px; outline:none; }}
  .search-box input:focus {{ border-color:var(--blue); box-shadow:0 0 0 2px rgba(30,58,95,0.1); }}

  /* Method grid */
  .method-grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(220px,1fr)); gap:8px; margin:10px 0; }}
  .method-item {{ background:#fff; border:1px solid var(--line); border-radius:6px; padding:8px 12px; font-size:12px; }}
  .method-item .mn {{ font-weight:600; }}
  .method-item .mc {{ color:var(--mut); font-size:11px; }}

  /* Print */
  @media print {{
    body {{ background:#fff; font-size:11px; }}
    .wrap {{ max-width:100%; padding:10px; }}
    .header {{ padding:12px; }}
    .toc, .search-box {{ display:none; }}
    .chart-grid {{ grid-template-columns:repeat(2,1fr); }}
    .kpi, .chart-card, .box, table {{ break-inside:avoid; }}
    table {{ font-size:10px; }}
  }}
  @page {{ size: A4 landscape; margin: 10mm; }}
</style>
</head>
<body>

<div class="wrap">

<!-- Header -->
<div class="header">
  <h1>长尾客户(MM/KM) 季度销售预测报告</h1>
  <div style="font-size:15px; margin:4px 0 8px; opacity:0.9;">预测目标季度：Q26（2026年4–6月）</div>
  <div class="meta">
    编制：CFO办公室 × AI预测引擎 ｜ 数据截止 2026-05-30 ｜ 报告日期 2026-06-11<br>
    数据源：财务分析-5月（6.3）.xlsx「总表」 ｜ 客户分类：<span class="tag tmm">MM 202个</span> <span class="tag tkm">KM 49个</span> 共 251 个长尾客户
  </div>
</div>

<!-- TOC -->
<div class="toc">
  <h3>目录</h3>
  <ol>
    <li><a href="#sec1">执行摘要</a></li>
    <li><a href="#sec2">数据说明</a></li>
    <li><a href="#sec3">预测总表（MM/KM分层 × 收入分级）</a></li>
    <li><a href="#sec4">长尾客户全景图（Top 20）</a></li>
    <li><a href="#sec5">需关注的客户</a></li>
    <li><a href="#sec6">方法论详解</a></li>
    <li><a href="#sec7">长尾客户经营洞察</a></li>
    <li><a href="#sec8">口径与说明</a></li>
  </ol>
</div>

<!-- ===== 一、执行摘要 ===== -->
<h2 id="sec1">一、执行摘要</h2>
<div class="box good">
  <p style="font-size:15px"><b>2026Q2（4–6月）MM+KM长尾客户合计：预测收入 <span style="color:var(--blue)">1,850 万元</span>（区间 1,284 ~ 2,416 万），预测利润 <span style="color:var(--blue)">726 万元</span>（毛利率 39.3%）。</b></p>
  <p>其中<span class="tag tmm">MM 202个</span>贡献 1,442 万（占78%），<span class="tag tkm">KM 49个</span>贡献 408 万。长尾客户数量占全部客户87%，但收入仅占KA+AA+长尾总量的 21.9%。<span class="tag tg">16高</span><span class="tag ty">4中</span><span class="tag tr">231低</span>置信分层，92%的客户预测不确定性较高，需结合销售端判断。</p>
  <p style="margin-top:6px">长尾客户整体毛利率 40.79%，显著高于KA客户的 29.98%，体现精细化运营的利润价值。</p>
</div>

<div class="kpis">
  <div class="kpi"><div class="t">Q26 预测收入</div><div class="v blue">1,850 万</div><div class="s">MM 1,442万 + KM 408万</div></div>
  <div class="kpi"><div class="t">Q26 预测利润</div><div class="v green">726 万</div><div class="s">毛利率 39.3%</div></div>
  <div class="kpi"><div class="t">客户构成</div><div class="v">251 客户</div><div class="s">占客户总数87%（MM 202 + KM 49）</div></div>
  <div class="kpi"><div class="t">收入占比</div><div class="v orange">21.9%</div><div class="s">KA+AA预测 8,457万 vs 长尾 1,850万</div></div>
</div>

<div class="kpis">
  <div class="kpi"><div class="t">活跃客户（25个）</div><div class="v blue">1,580 万</div><div class="s">占长尾总预测85%，核心收入来源</div></div>
  <div class="kpi"><div class="t">长尾毛利率</div><div class="v green">40.79%</div><div class="s">高于KA的 29.98%，利润质量优</div></div>
  <div class="kpi"><div class="t">高置信度客户</div><div class="v">16 个 (6.4%)</div><div class="s">WAPE≤20%，预测可靠</div></div>
  <div class="kpi"><div class="t">Top3 预测收入</div><div class="v blue">658 万</div><div class="s">汤诚349万 + 福锐166万 + 嘉智联143万</div></div>
</div>

<!-- ===== 二、数据说明 ===== -->
<h2 id="sec2">二、数据说明</h2>
<div class="box">
  <h3>预测目标</h3>
  <p><b>预测季度：</b>Q26（2026年4月–6月），即下一完整季度。数据截至 2026-05-30，Q26中4–5月已有实际交易数据，预测主要聚焦6月及整体季度校准。</p>

  <h3 style="margin-top:12px">客户分类标准</h3>
  <p><span class="tag tmm">MM</span>（Mini-Major）：客户自身年营收 &lt; 1,000 万元，共 202 个。<br>
  <span class="tag tkm">KM</span>（Key-Medium）：客户自身年营收 1,000 万 ~ 1 亿元，共 49 个。<br>
  两类合计 251 个客户，占全部客户数量的 87%，是<strong>客户数量的绝对主体</strong>。</p>

  <h3 style="margin-top:12px">客户分层定义</h3>
  <table>
    <tr><th>分层</th><th>定义</th><th>客户数</th><th>预测收入</th></tr>
    <tr><td><span class="tag tg">活跃</span></td><td>近4个季度中有≥3个季度有交易记录</td><td>25</td><td>1,580 万（85%）</td></tr>
    <tr><td><span class="tag ty">稀疏</span></td><td>近8个季度中有2~4个季度有交易，非连续</td><td>27</td><td>253 万（14%）</td></tr>
    <tr><td><span class="tag td">休眠</span></td><td>最后交易在2023年，且历史≥2次交易</td><td>57</td><td>14 万（0.7%）</td></tr>
    <tr><td><span class="tag tl">一次性</span></td><td>仅1次交易记录</td><td>142</td><td>3 万（0.2%）</td></tr>
  </table>

  <h3 style="margin-top:12px">预测方法概述</h3>
  <p>系统为每个客户独立选择最优预测方法：先根据客户分层和数据丰富度筛选候选方法池，再通过4个历史季度的滚动回测（Q21~Q24），选择WAPE（加权平均百分比误差）最低的方法作为该客户的最优预测器。</p>
  <p>活跃客户使用完整时间序列方法（EWMA、中位数、移动平均、同比季节等），稀疏/休眠/一次性客户则使用群体复购率模型（群体中位数 × 复购率）或Croston间歇需求模型。</p>

  <h3 style="margin-top:12px">与KA/AA报告方法论异同</h3>
  <table>
    <tr><th>维度</th><th>KA/AA报告</th><th>长尾报告（本报告）</th></tr>
    <tr><td>预测粒度</td><td>客户×产品级（SKU级）</td><td>客户级汇总</td></tr>
    <tr><td>候选方法数</td><td>392种</td><td>9种核心 + 群体复购模型</td></tr>
    <tr><td>回测机制</td><td>8折滚动回测</td><td>4季度滚动回测（Q21~Q24）</td></tr>
    <tr><td>单价模型</td><td>近3月加权均价 × 趋势因子</td><td>近3月加权均价（简化）</td></tr>
    <tr><td>间歇需求处理</td><td>Croston方法</td><td>Croston + 群体复购率组合</td></tr>
    <tr><td>置信度标准</td><td>高≤20%, 中20~45%, 低&gt;45%</td><td>同标准</td></tr>
  </table>
</div>

<!-- ===== 三、预测总表 ===== -->
<h2 id="sec3">三、预测总表（MM/KM分层 × 收入分级）</h2>
<p class="muted" style="margin-bottom:8px">置信度：<span class="tag tg">高</span>WAPE≤20% <span class="tag ty">中</span>20~45% <span class="tag tr">低</span>&gt;45%。按MM/KM分组，组内按预测收入降序。支持搜索和排序。</p>

<div class="search-box">
  <input type="text" id="tableSearch" placeholder="🔍 搜索客户名称..." onkeyup="filterTable()">
</div>

{all_tables_html}

<!-- ===== 四、长尾客户全景图 ===== -->
<h2 id="sec4">四、长尾客户全景图（Top 20 预测收入客户）</h2>
<p class="muted">每个卡片展示历史季度实际销售额（蓝色柱）+ Q26预测值（虚线框）+ 预测区间（工字线）。长尾客户数据点较稀疏，采用单面板展示。</p>

<div class="chart-grid" id="chartGrid"></div>

<!-- ===== 五、需关注的客户 ===== -->
<h2 id="sec5">五、需关注的客户</h2>

{attention_html}

<!-- ===== 六、方法论详解 ===== -->
<h2 id="sec6">六、方法论详解</h2>

<h3>6.1 候选预测方法</h3>
<table>
<tr><th>方法</th><th>原理</th><th>适用场景</th><th>使用客户数</th></tr>
<tr><td>EWMA(α=0.3/0.7/0.85)</td><td>指数加权移动平均，近期数据权重更高</td><td>连续交易的活跃客户，趋势平滑</td><td>9</td></tr>
<tr><td>移动平均(w=1/2/4)</td><td>近w期简单平均</td><td>波动较小的稳定客户</td><td>3</td></tr>
<tr><td>中位数(w=3/4)</td><td>近w期中位数，抗异常值</td><td>有偶发大额订单的客户</td><td>5</td></tr>
<tr><td>同比季节(lag=4)</td><td>使用去年同季度数据 + 增长因子</td><td>有明显季节性的客户</td><td>2</td></tr>
<tr><td>线性趋势</td><td>线性回归拟合趋势</td><td>呈明显增长/下降趋势的客户</td><td>1</td></tr>
<tr><td>Croston</td><td>间歇需求专用方法，分别预测频率和需求量</td><td>交易不连续的稀疏客户</td><td>2</td></tr>
<tr><td>Croston×50%+群体×50%</td><td>Croston与群体复购率的加权组合</td><td>数据不足以单独使用Croston的稀疏客户</td><td>27</td></tr>
<tr><td>群体中位数×N%复购</td><td>使用同类客户中位数 × 复购概率</td><td>休眠/一次性客户，无足够自身数据</td><td>199</td></tr>
<tr><td>中位数×50%+群体×50%</td><td>自身中位数与群体复购的混合</td><td>回测期数不足的活跃客户</td><td>4</td></tr>
</table>

<h3>6.2 客户分层与方法选择逻辑</h3>
<div class="box">
<p><b>活跃客户（≥3季度交易）：</b>使用完整时间序列方法池（EWMA/移动平均/中位数/同比季节/线性趋势/Croston），回测选优。活跃客户中 EWMA 最常用（9/21），其次中位数（3/21）和同比季节（2/21）。</p>
<p><b>稀疏客户（2~4季度交易，非连续）：</b>优先 Croston×50%+群体×50% 组合方法，少数使用群体复购模型。</p>
<p><b>休眠客户（最后交易在2023年）：</b>使用群体复购率模型，复购率按6%估算（基于历史休眠客户复购统计）。</p>
<p><b>一次性客户（仅1次交易）：</b>使用群体复购率模型，复购率按2%~5%估算（根据交易时间远近）。</p>
</div>

<h3>6.3 回测选优框架</h3>
<div class="box">
<p>对每个有足够历史数据的客户，执行 Q21~Q24 四个季度的滚动回测：</p>
<ol style="margin:8px 0 0 20px;">
<li>用截止Q(t-1)的数据预测Q(t)，与实际值对比</li>
<li>计算每个方法的 WAPE = Σ|预测-实际| / Σ|实际|</li>
<li>选择 WAPE 最低的方法作为该客户的最优预测器</li>
<li>预测区间基于回测误差分布的 ±1.5 倍标准差</li>
</ol>
<p style="margin-top:8px"><b>回测季度：</b>Q24(2025Q4)、Q23(2025Q3)、Q22(2025Q2)、Q21(2025Q1)，共4个测试点。</p>
</div>

<h3>6.4 单价与毛利率预测</h3>
<div class="box">
<p><b>预测单价：</b>近3个月交易量加权平均价，不做趋势调整（长尾客户单价波动较小）。</p>
<p><b>毛利率预测：</b>使用客户历史平均毛利率，对无足够数据的客户使用同产品系列的群体毛利率中位数。</p>
</div>

<h3>6.5 活跃客户方法使用分布</h3>
<div class="method-grid">
'''

for method, count in active_method_items:
    html += f'<div class="method-item"><span class="mn">{esc(method)}</span> <span class="mc">({count}个客户)</span></div>\n'

html += '''</div>

<h3 style="margin-top:16px">6.6 全客户方法使用分布</h3>
<table>
<tr><th>方法</th><th class="r">使用客户数</th><th class="r">占比</th></tr>
'''

total_methods = sum(method_dist.values())
for method, count in method_items:
    pct = count / total_methods * 100 if total_methods > 0 else 0
    html += f'<tr><td>{esc(method)}</td><td class="r">{count}</td><td class="r">{pct:.1f}%</td></tr>\n'

html += f'''</table>

<h3 style="margin-top:16px">6.7 与KA/AA方法体系差异对比</h3>
<table>
<tr><th>维度</th><th>KA/AA</th><th>长尾(MM/KM)</th><th>差异原因</th></tr>
<tr><td>预测粒度</td><td>客户×产品×SKU</td><td>客户级汇总</td><td>长尾客户产品分散，SKU级数据不足</td></tr>
<tr><td>候选方法数</td><td>392种组合</td><td>9种核心+群体模型</td><td>长尾数据稀疏，复杂方法易过拟合</td></tr>
<tr><td>间歇需求方法</td><td>标准Croston</td><td>Croston+群体复购混合</td><td>单次交易客户无法单独建模</td></tr>
<tr><td>回测深度</td><td>8折滚动</td><td>4季度滚动</td><td>长尾客户历史期数短</td></tr>
<tr><td>群体模型</td><td>不使用</td><td>群体中位数×复购率</td><td>长尾中85%客户数据不足，需群体兜底</td></tr>
<tr><td>预测区间</td><td>基于回测误差分布</td><td>同方法，但稀疏客户区间更宽</td><td>不确定性差异</td></tr>
</table>

<!-- ===== 七、长尾客户经营洞察 ===== -->
<h2 id="sec7">七、长尾客户经营洞察</h2>

<div class="box good">
<h3>洞察1：长尾客户高利润率特征 → 值得精细化运营</h3>
<p>长尾客户整体毛利率 <b>40.79%</b>，显著高于KA客户的 29.98%（高出 <b>10.8 个百分点</b>）。这意味着长尾客户虽然单客收入小，但利润质量高。建议：</p>
<ul style="margin:6px 0 0 20px;">
<li>将长尾客户纳入精细化运营体系，而非粗放管理</li>
<li>重点关注利润率 >50% 的高价值长尾客户（如弘智芯 48.5%、品创兴 54.1%、好年华 20.8%但体量大）</li>
<li>探索长尾客户的增值服务机会（技术支持、定制方案）提升客单价</li>
</ul>
</div>

<div class="box amber">
<h3>洞察2：头部集中效应 → 二八法则显著</h3>
<p><b>25个活跃客户贡献了 1,580 万元（85%）</b>的长尾预测收入。其中Top 3（汤诚科技 349万、福锐实业 166万、嘉智联 143万）合计 658 万元，占长尾总量的 35.6%。建议：</p>
<ul style="margin:6px 0 0 20px;">
<li>活跃客户中Top 10应配备专属客户经理，服务标准接近KA</li>
<li>活跃客户中的"腰部"（30~100万区间，共10个）是增长潜力池</li>
<li>对活跃客户建立季度业务回顾机制，防止流失</li>
</ul>
</div>

<div class="box warn">
<h3>洞察3：大量一次性客户 → 客户留存/复购课题</h3>
<p><b>142个一次性客户</b>占客户总数的56.6%，但仅贡献 3 万元预测收入。这些客户中部分曾有可观的历史交易（如新木犀电器历史 59.5万、杭州浙豪 8.9万），但已不再复购。建议：</p>
<ul style="margin:6px 0 0 20px;">
<li>对历史交易额 >10万的一次性客户进行流失原因分析</li>
<li>建立新客户首次交易后90天跟踪机制，识别复购信号</li>
<li>制定长尾客户复购激励方案（阶梯折扣、积分返利）</li>
</ul>
</div>

<div class="box">
<h3>洞察4：产品偏好集中 → 标品策略为主</h3>
<p>长尾客户的产品系列分布高度集中：</p>
<div class="method-grid">
'''

for series, count in top_series:
    html += f'<div class="method-item"><span class="mn">{esc(series)}</span> <span class="mc">({count}个客户)</span></div>\n'

html += f'''</div>
<p style="margin-top:8px">电源管理类（Buck/LDO/DCDC等）覆盖约79%的长尾客户，说明长尾客户以标准化产品采购为主。建议：</p>
<ul style="margin:6px 0 0 20px;">
<li>针对电源管理系列建立长尾客户自助订购平台，降低服务成本</li>
<li>长尾客户的产品推荐策略以标品为主，减少定制化投入</li>
<li>对非电源系列的长尾客户（如马达、POE、晶圆），评估是否有交叉销售机会</li>
</ul>
</div>

<div class="box amber">
<h3>洞察5：预测不确定性高 → 需结合销售端判断</h3>
<p><b>92%的客户（231个）处于低置信度</b>，这是因为长尾客户数据天然稀疏——大部分客户交易不连续或仅有单次交易，模型难以从有限数据中提取可靠规律。建议：</p>
<ul style="margin:6px 0 0 20px;">
<li>16个高置信度客户的预测数据可直接用于财务规划</li>
<li>4个中置信度客户（信溢达、品创兴、好年华、研之芯）的预测可作为参考，但需季度修正</li>
<li>低置信度客户的预测值<b>不应作为刚性预算依据</b>，而应视为"可能性参考"</li>
<li>建议每月由销售团队更新长尾活跃客户的Pipeline状态，与模型预测交叉验证</li>
</ul>
</div>

<!-- ===== 八、口径与说明 ===== -->
<h2 id="sec8">八、口径与说明</h2>

<div class="box">
<h3>数据来源</h3>
<ul style="margin:4px 0 0 20px;">
<li><b>交易数据：</b>财务分析-5月（6.3）.xlsx「总表」，按终端客户简称分组汇总</li>
<li><b>客户分类：</b>按终端客户名称_客户类别字段筛选 MM（&lt;1000万）和 KM（1000万~1亿）</li>
<li><b>数据截止：</b>2026-05-30（Q26的4–5月已有实际交易）</li>
<li><b>预测范围：</b>251个MM/KM客户的Q26（2026年4–6月）季度销售额</li>
</ul>

<h3 style="margin-top:12px">局限性</h3>
<ul style="margin:4px 0 0 20px;">
<li>长尾客户数据稀疏性导致92%客户预测置信度低，预测值仅供参考</li>
<li>客户级汇总预测未考虑产品组合变化对单价的影响</li>
<li>群体复购率模型假设同类客户行为相似，对个体差异的刻画有限</li>
<li>Q26中4–5月已有实际数据，但预测模型未做实时融合（后续版本可改进）</li>
</ul>

<h3 style="margin-top:12px">使用建议</h3>
<ul style="margin:4px 0 0 20px;">
<li>高/中置信度客户（共20个）的预测可作为财务规划直接输入</li>
<li>低置信度客户预测应视为"数量级参考"，实际执行中由销售端修正</li>
<li>建议将本报告与KA/AA报告（同期Q13）合并查看，形成完整客户组合预测视图</li>
<li>下一季度预测前，建议更新6月实际交易数据并重新运行回测</li>
</ul>

<h3 style="margin-top:12px">与KA/AA报告口径一致性</h3>
<table>
<tr><th>口径项</th><th>KA/AA报告</th><th>长尾报告</th><th>一致性</th></tr>
<tr><td>预测季度</td><td>Q13 (2026Q3: 6-8月)</td><td>Q26 (2026Q2: 4-6月)</td><td>⚠ 季度编号体系不同*</td></tr>
<tr><td>数据源</td><td>财务分析-5月（6.3）.xlsx</td><td>同一数据源</td><td>✅ 一致</td></tr>
<tr><td>客户分类依据</td><td>客户自身营收规模</td><td>客户自身营收规模</td><td>✅ 一致</td></tr>
<tr><td>毛利率口径</td><td>客户历史加权平均</td><td>客户历史加权平均</td><td>✅ 一致</td></tr>
<tr><td>置信度标准</td><td>高≤20%/中20~45%/低>45%</td><td>同标准</td><td>✅ 一致</td></tr>
</table>
<p class="muted" style="margin-top:6px">* KA/AA报告的"Q13"与本报告的"Q26"使用不同季度编号体系：KA/AA按季度序列号编号，长尾报告按年份+季度编号（26=2026年第2季度）。两者指向不同的预测目标季度。</p>

<h3 style="margin-top:12px">模型版本</h3>
<p>预测引擎版本：v2.0-longtail ｜ 回测框架：4季度滚动 ｜ 生成时间：2026-06-11 17:36:46</p>
</div>

<div style="text-align:center; color:var(--mut); font-size:11px; margin-top:40px; padding-top:20px; border-top:1px solid var(--line);">
  CFO办公室 × AI预测引擎 · 数据截止2026-05-30 · 长尾客户(MM/KM)季度销售预测报告<br>
  本报告由AI预测引擎自动生成，仅供内部决策参考，不构成财务承诺
</div>

</div><!-- .wrap -->

<script>
// ─── Chart data ───
const chartData = {chart_data_json};

// ─── Render charts ───
function renderCharts() {{
  const grid = document.getElementById('chartGrid');
  chartData.forEach(d => {{
    const card = document.createElement('div');
    card.className = 'chart-card';

    const confColors = {{'高':'#1a9850','中':'#e6a817','低':'#d73027'}};
    const typeColors = {{'MM':'#1e3a5f','KM':'#e67e22'}};
    const confColor = confColors[d.conf] || '#999';

    let headerHtml = `<div class="ch">
      <span style="color:${{confColor}}">●</span>
      <span class="nm">${{d.name}}</span>
      <span class="tag ${{d.type==='MM'?'tmm':'tkm'}}">${{d.type}}</span>
      <span class="tag ${{d.tier==='活跃'?'tg':(d.tier==='稀疏'?'ty':'td')}}">${{d.tier}}</span>
      <span class="muted" style="margin-left:auto;font-size:11px">${{d.method}} · WAPE ${{d.wape.toFixed(0)}}%</span>
    </div>`;

    // SVG chart
    const W = 440, H = 160, pad = {{l:45,r:40,t:15,b:25}};
    const cw = W - pad.l - pad.r, ch = H - pad.t - pad.b;

    const allVals = [...d.actuals, d.pred, d.predHi];
    const maxVal = Math.max(...allVals, 1) * 1.15;
    const n = d.actuals.length;
    const barW = Math.min(18, (cw / (n + 2)) * 0.7);
    const gap = cw / (n + 2);

    let svg = `<svg viewBox="0 0 ${{W}} ${{H}}" preserveAspectRatio="xMidYMid meet">`;

    // Grid lines
    for (let i = 0; i <= 3; i++) {{
      const y = pad.t + (ch / 3) * i;
      const val = maxVal * (1 - i / 3);
      svg += `<line x1="${{pad.l}}" y1="${{y}}" x2="${{W-pad.r}}" y2="${{y}}" stroke="#e8ebef" stroke-width="0.5" stroke-dasharray="2,2"/>`;
      svg += `<text x="${{pad.l-3}}" y="${{y+3}}" font-size="8" fill="#9aa1aa" text-anchor="end">${{val.toFixed(0)}}万</text>`;
    }}

    // Actual bars
    d.actuals.forEach((v, i) => {{
      const x = pad.l + gap * (i + 0.5) + gap * 0.15;
      const h = (v / maxVal) * ch;
      const y = pad.t + ch - h;
      svg += `<rect x="${{x}}" y="${{y}}" width="${{barW}}" height="${{h}}" fill="#aac6e2" rx="1"/>`;
      // Quarter label
      const qlabel = d.quarters[i] ? d.quarters[i].replace('20','') : '';
      svg += `<text x="${{x + barW/2}}" y="${{H-5}}" font-size="7.5" fill="#9aa1aa" text-anchor="middle">${{qlabel}}</text>`;
    }});

    // Prediction bar (dashed border)
    const px = pad.l + gap * (n + 0.5) + gap * 0.15;
    const ph = (d.pred / maxVal) * ch;
    const py = pad.t + ch - ph;
    svg += `<rect x="${{px}}" y="${{py}}" width="${{barW}}" height="${{ph}}" fill="#aac6e2" opacity="0.5" rx="1" stroke="#1e3a5f" stroke-width="1.2" stroke-dasharray="3,2"/>`;
    svg += `<text x="${{px + barW/2}}" y="${{H-5}}" font-size="7.5" fill="#1e3a5f" text-anchor="middle" font-weight="600">Q26预测</text>`;

    // Prediction interval (I-beam)
    const ilo = (d.predLo / maxVal) * ch;
    const ihi = (d.predHi / maxVal) * ch;
    const ix = px + barW / 2;
    const iy1 = pad.t + ch - ihi;
    const iy2 = pad.t + ch - ilo;
    svg += `<line x1="${{ix}}" y1="${{iy1}}" x2="${{ix}}" y2="${{iy2}}" stroke="#1e3a5f" stroke-width="1.5"/>`;
    svg += `<line x1="${{ix-4}}" y1="${{iy1}}" x2="${{ix+4}}" y2="${{iy1}}" stroke="#1e3a5f" stroke-width="1.5"/>`;
    svg += `<line x1="${{ix-4}}" y1="${{iy2}}" x2="${{ix+4}}" y2="${{iy2}}" stroke="#1e3a5f" stroke-width="1.5"/>`;

    // Prediction value label
    svg += `<text x="${{px + barW + 3}}" y="${{py + 4}}" font-size="8.5" fill="#1e3a5f" font-weight="600">${{d.pred.toFixed(1)}}万</text>`;
    svg += `<text x="${{px + barW + 3}}" y="${{py + 14}}" font-size="7" fill="#9aa1aa">${{d.predLo.toFixed(0)}}~${{d.predHi.toFixed(0)}}</text>`;

    svg += `</svg>`;

    card.innerHTML = headerHtml + svg;
    grid.appendChild(card);
  }});
}}

// ─── Table search ───
function filterTable() {{
  const input = document.getElementById('tableSearch').value.toLowerCase();
  const tables = document.querySelectorAll('table.sortable');
  tables.forEach(table => {{
    const rows = table.querySelectorAll('tbody tr');
    rows.forEach(row => {{
      const text = row.textContent.toLowerCase();
      row.style.display = text.includes(input) ? '' : 'none';
    }});
  }});
}}

// ─── Init ───
document.addEventListener('DOMContentLoaded', () => {{
  renderCharts();
}});
</script>
</body></html>'''

output_path = '长尾客户季度销售预测报告.html'
with open(output_path, 'w', encoding='utf-8') as f:
    f.write(html)

print(f'Report generated: {output_path}')
print(f'File size: {len(html):,} bytes')
