import csv, json

# 读取回测摘要
with open('回测摘要.json', encoding='utf-8') as f:
    summary = json.load(f)

# 读取预测总表
pred = []
with open('全客户增强预测总表.csv', encoding='utf-8-sig') as f:
    for r in csv.DictReader(f):
        pred.append({
            'n': r['终端客户名称'],
            't': r['客户类别'],
            'tier': r['分层'],
            'q': int(r['季度数']),
            'rev': round(float(r['预测销售额']), 2),
            'pft': round(float(r['预测利润']), 2),
            'wape': round(float(r['WAPE']), 2),
            'g': r['置信等级'],
            'm': r['最优方法'],
            'tm': int(r['测试方法数']),
            'top3': r['Top3方法'],
            'ht': round(float(r['总历史销售额']), 2)
        })

# 读取历史+预测明细
hist = []
with open('全客户季度历史与预测.csv', encoding='utf-8-sig') as f:
    for r in csv.DictReader(f):
        hist.append({
            'n': r['终端客户名称'],
            'q': r['季度'],
            'rev': round(float(r['销售额']), 2),
            'pft': round(float(r['利润']), 2),
            'dt': r['数据类型']
        })

# 读取多维度对比
multi = []
with open('多维度对比.csv', encoding='utf-8-sig') as f:
    for r in csv.DictReader(f):
        multi.append({
            'n': r['终端客户名称'],
            'dm': r['多维度方法'],
            'dp': round(float(r['多维度预测']), 2),
            'dw': round(float(r['多维度WAPE']), 2),
            'diff': round(float(r['差异率(%)']), 2)
        })

# 获取客户级数据
client_pred = {}
for r in pred:
    client_pred[r['n']] = r

# 构建每个有预测客户的历史时间序列
active_names = set(r['n'] for r in pred if r['rev'] > 0)
hist_by_client = {}
for h in hist:
    if h['n'] in active_names:
        hist_by_client.setdefault(h['n'], []).append(h)

# 多维度对比按客户分组
multi_by_client = {}
for m in multi:
    if m['n'] in active_names:
        multi_by_client.setdefault(m['n'], []).append(m)

# 构建JS数据
js_pred = json.dumps(pred, ensure_ascii=False)
js_hist = json.dumps({k: v for k, v in hist_by_client.items()}, ensure_ascii=False)
js_multi = json.dumps({k: v for k, v in multi_by_client.items()}, ensure_ascii=False)

# 统计摘要数据
total_rev = summary['总体预测']['预测总收入(万元)']
total_profit = summary['总体预测']['预测总利润(万元)']
total_customers = summary['数据说明']['总客户数']
non_zero = summary['总体预测']['非零预测客户数']
avg_wape = summary['平均WAPE(活跃+半活跃)']
conf_dist = summary['置信度分布(整体)']
conf_by_type = summary['置信度分布(按客户类别)']
conf_by_tier = summary['置信度分布(按分层)']
wape_dist = summary['WAPE分布']
top20_methods = summary['Top20方法使用频次']
type_top5 = summary['各客户类型推荐方法Top5']
compare = summary['与上一版对比']
tier_dist = summary['数据说明']['客户分层']
type_dist = summary['数据说明']['客户类别']

html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>长尾客户预测增强仪表盘 · v2 (2026-Q2)</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Segoe UI','Microsoft YaHei',system-ui,sans-serif;background:#f0f4f8;color:#2d3748;line-height:1.6}}
.container{{max-width:1480px;margin:0 auto;padding:20px 24px}}
.header{{text-align:center;padding:28px 0 18px;border-bottom:2px solid #e2e8f0;margin-bottom:24px}}
.header h1{{font-size:26px;color:#1e3a5f;font-weight:700;letter-spacing:1px}}
.header .subtitle{{font-size:14px;color:#718096;margin-top:6px}}
.kpi-row{{display:grid;grid-template-columns:repeat(5,1fr);gap:16px;margin-bottom:28px}}
.kpi-card{{background:#fff;border-radius:12px;padding:20px 18px;box-shadow:0 2px 8px rgba(0,0,0,.06);border-left:4px solid #2ecc71;transition:transform .15s}}
.kpi-card:hover{{transform:translateY(-2px);box-shadow:0 4px 16px rgba(0,0,0,.1)}}
.kpi-card:nth-child(2){{border-left-color:#e67e22}}
.kpi-card:nth-child(3){{border-left-color:#3498db}}
.kpi-card:nth-child(4){{border-left-color:#9b59b6}}
.kpi-card:nth-child(5){{border-left-color:#17a2b8}}
.kpi-label{{font-size:11px;color:#a0aec0;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px}}
.kpi-value{{font-size:28px;font-weight:700;color:#1e3a5f}}
.kpi-sub{{font-size:11px;color:#718096;margin-top:4px}}
.kpi-change{{font-size:11px;margin-top:4px}}
.kpi-change.up{{color:#2ecc71}}
.kpi-change.down{{color:#e74c3c}}
.chart-row{{display:grid;gap:20px;margin-bottom:20px}}
.row-2{{grid-template-columns:1fr 1fr}}
.row-3{{grid-template-columns:1fr 1fr 1fr}}
.row-full{{grid-template-columns:1fr}}
.chart-box{{background:#fff;border-radius:12px;padding:20px;box-shadow:0 2px 8px rgba(0,0,0,.06)}}
.chart-box h3{{font-size:15px;color:#1e3a5f;margin-bottom:14px;font-weight:600;display:flex;align-items:center;gap:8px}}
.chart-box h3 .badge{{font-size:11px;background:#e8f5e9;color:#2e7d32;padding:2px 8px;border-radius:10px;font-weight:500}}
.chart-container{{width:100%;position:relative}}
.chart-container.sm{{height:280px}}
.chart-container.md{{height:340px}}
.chart-container.lg{{height:420px}}
.chart-container.xl{{height:500px}}
.filter-bar{{display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap}}
.filter-btn{{padding:5px 14px;border:1px solid #e2e8f0;border-radius:6px;background:#fff;cursor:pointer;font-size:12px;color:#718096;transition:all .15s}}
.filter-btn:hover,.filter-btn.active{{background:#1e3a5f;color:#fff;border-color:#1e3a5f}}
.filter-select{{padding:5px 10px;border:1px solid #e2e8f0;border-radius:6px;background:#fff;cursor:pointer;font-size:12px;color:#718096}}
.filter-input{{padding:5px 10px;border:1px solid #e2e8f0;border-radius:6px;font-size:12px;width:200px}}
.table-wrap{{max-height:600px;overflow-y:auto;border:1px solid #e2e8f0;border-radius:8px}}
table{{width:100%;border-collapse:collapse;font-size:12px}}
thead{{background:#f7fafc;position:sticky;top:0;z-index:1}}
th{{padding:10px 12px;text-align:left;font-weight:600;color:#4a5568;border-bottom:2px solid #e2e8f0;cursor:pointer;white-space:nowrap}}
th:hover{{background:#edf2f7}}
td{{padding:8px 12px;border-bottom:1px solid #edf2f7;white-space:nowrap}}
tr:hover{{background:#f7fafc}}
.grade-A{{background:#d4edda;color:#155724;padding:2px 8px;border-radius:4px;font-weight:600}}
.grade-B{{background:#d1ecf1;color:#0c5460;padding:2px 8px;border-radius:4px;font-weight:600}}
.grade-C{{background:#fff3cd;color:#856404;padding:2px 8px;border-radius:4px;font-weight:600}}
.grade-D{{background:#f8d7da;color:#721c24;padding:2px 8px;border-radius:4px;font-weight:600}}
.grade-E{{background:#e2e3e5;color:#383d41;padding:2px 8px;border-radius:4px;font-weight:600}}
.compare-table{{width:100%;border-collapse:collapse;font-size:13px}}
.compare-table th,.compare-table td{{padding:10px 14px;border:1px solid #e2e8f0;text-align:center}}
.compare-table th{{background:#1e3a5f;color:#fff;font-weight:600}}
.compare-table tr:nth-child(even){{background:#f7fafc}}
.compare-table .old{{color:#e74c3c}}
.compare-table .new{{color:#2ecc71;font-weight:600}}
.export-btn{{padding:8px 20px;background:#1e3a5f;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:13px}}
.export-btn:hover{{background:#2c5282}}
.section-title{{font-size:18px;color:#1e3a5f;font-weight:700;margin:28px 0 16px;padding-bottom:8px;border-bottom:2px solid #e2e8f0}}
.footer{{text-align:center;padding:20px 0;color:#a0aec0;font-size:12px;margin-top:20px;border-top:1px solid #e2e8f0}}
@media(max-width:1024px){{.kpi-row{{grid-template-columns:repeat(2,1fr)}}.row-2,.row-3{{grid-template-columns:1fr}}}}
@media(max-width:640px){{.kpi-row{{grid-template-columns:1fr}}}}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>长尾客户预测增强仪表盘 · v2 (2026-Q2)</h1>
    <div class="subtitle">全客户 321 家 · 预测总收入 {total_rev:.2f} 万 · 方法库 494 · 数据截止 2026-05-30</div>
  </div>

  <!-- KPI Cards -->
  <div class="kpi-row">
    <div class="kpi-card">
      <div class="kpi-label">预测总收入</div>
      <div class="kpi-value">{total_rev:,.2f}<span style="font-size:14px;color:#718096"> 万</span></div>
      <div class="kpi-sub">非零预测客户 {non_zero} 家</div>
      <div class="kpi-change up">▲ +{total_rev - compare['上一版(仅长尾MM/KM)']['预测总收入(万元)']:.2f} 万 vs 上一版</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">预测总利润</div>
      <div class="kpi-value">{total_profit:,.2f}<span style="font-size:14px;color:#718096"> 万</span></div>
      <div class="kpi-sub">平均利润率 {(total_profit/total_rev*100):.1f}%</div>
      <div class="kpi-change up">▲ 全量客户预测</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">客户覆盖率</div>
      <div class="kpi-value">{non_zero}/{total_customers}</div>
      <div class="kpi-sub">覆盖率 {(non_zero/total_customers*100):.1f}%</div>
      <div class="kpi-change up">▲ 上一版 {compare['上一版(仅长尾MM/KM)']['客户数']} 家</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">平均WAPE</div>
      <div class="kpi-value">{avg_wape:.2f}<span style="font-size:14px;color:#718096">%</span></div>
      <div class="kpi-sub">活跃+半活跃客户</div>
      <div class="kpi-change up">▲ 上一版 MM 91% / KM 93%</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">A+B级客户占比</div>
      <div class="kpi-value">{summary['与上一版对比']['本版(全客户)']['A+B级(高置信度)']}<span style="font-size:14px;color:#718096"> / {total_customers}</span></div>
      <div class="kpi-sub">占比 {(summary['与上一版对比']['本版(全客户)']['A+B级(高置信度)']/total_customers*100):.1f}%</div>
      <div class="kpi-change up">▲ 上一版 16 家 (6.4%)</div>
    </div>
  </div>

  <!-- 模块2: 置信度分布 -->
  <div class="section-title">置信度分布分析</div>
  <div class="chart-row row-2">
    <div class="chart-box">
      <h3>置信等级分布 <span class="badge">A-E级</span></h3>
      <div class="chart-container md"><canvas id="confPie"></canvas></div>
    </div>
    <div class="chart-box">
      <h3>按客户类别置信度分布 <span class="badge">KA/AA/MM/KM</span></h3>
      <div class="chart-container md"><canvas id="confStack"></canvas></div>
    </div>
  </div>

  <!-- 模块4: 方法性能分析 -->
  <div class="section-title">方法性能分析</div>
  <div class="chart-row row-2">
    <div class="chart-box">
      <h3>Top 10 方法使用频次 <span class="badge">494种方法</span></h3>
      <div class="chart-container md"><canvas id="methodBar"></canvas></div>
    </div>
    <div class="chart-box">
      <h3>方法类别占比 <span class="badge">按置信等级</span></h3>
      <div class="chart-container md"><canvas id="methodCatPie"></canvas></div>
    </div>
  </div>

  <!-- 模块3: 预测结果表格 -->
  <div class="section-title">客户预测明细表</div>
  <div class="chart-box">
    <div class="filter-bar" style="margin-bottom:12px">
      <input type="text" id="searchInput" class="filter-input" placeholder="搜索客户名称..." oninput="filterTable()">
      <select id="typeFilter" class="filter-select" onchange="filterTable()">
        <option value="">全部类别</option>
        <option value="KA>1亿">KA>1亿</option>
        <option value="AA>5000万">AA>5000万</option>
        <option value="KM>1000万">KM>1000万</option>
        <option value="MM<1000万">MM&lt;1000万</option>
        <option value="">未分类</option>
      </select>
      <select id="gradeFilter" class="filter-select" onchange="filterTable()">
        <option value="">全部等级</option>
        <option value="A">A级</option>
        <option value="B">B级</option>
        <option value="C">C级</option>
        <option value="D">D级</option>
        <option value="E">E级</option>
      </select>
      <button class="export-btn" onclick="exportCSV()">导出CSV</button>
    </div>
    <div class="table-wrap">
      <table id="predTable">
        <thead>
          <tr>
            <th onclick="sortTable(0)">客户名称</th>
            <th onclick="sortTable(1)">客户类别</th>
            <th onclick="sortTable(2)">分层</th>
            <th onclick="sortTable(3)">预测收入(万)</th>
            <th onclick="sortTable(4)">预测利润(万)</th>
            <th onclick="sortTable(5)">WAPE(%)</th>
            <th onclick="sortTable(6)">置信等级</th>
            <th onclick="sortTable(7)">最优方法</th>
          </tr>
        </thead>
        <tbody id="tableBody"></tbody>
      </table>
    </div>
  </div>

  <!-- 模块5: 历史趋势与预测 -->
  <div class="section-title">历史趋势与预测</div>
  <div class="chart-box">
    <div class="filter-bar" style="margin-bottom:12px">
      <select id="clientSelect" class="filter-select" onchange="showClientHistory()" style="width:400px">
        <option value="">-- 选择客户 --</option>
      </select>
    </div>
    <div class="chart-container lg"><canvas id="histChart"></canvas></div>
  </div>

  <!-- 模块6: 多维度预测对比 -->
  <div class="section-title">多维度预测对比</div>
  <div class="chart-box">
    <div class="filter-bar" style="margin-bottom:12px">
      <select id="multiClientSelect" class="filter-select" onchange="showMultiCompare()" style="width:400px">
        <option value="">-- 选择客户 --</option>
      </select>
    </div>
    <div class="chart-container xl"><canvas id="multiChart"></canvas></div>
  </div>

  <!-- 模块7: 与上一版对比 -->
  <div class="section-title">与上一版对比</div>
  <div class="chart-box">
    <table class="compare-table">
      <thead>
        <tr><th>指标</th><th>上一版 (仅长尾MM/KM)</th><th>本版 (全客户增强)</th><th>变化</th></tr>
      </thead>
      <tbody>
        <tr><td>客户数</td><td class="old">{compare['上一版(仅长尾MM/KM)']['客户数']}</td><td class="new">{compare['本版(全客户)']['客户数']}</td><td>+{compare['本版(全客户)']['客户数'] - compare['上一版(仅长尾MM/KM)']['客户数']}</td></tr>
        <tr><td>预测总收入(万)</td><td class="old">{compare['上一版(仅长尾MM/KM)']['预测总收入(万元)']}</td><td class="new">{compare['本版(全客户)']['预测总收入(万元)']}</td><td>+{compare['本版(全客户)']['预测总收入(万元)'] - compare['上一版(仅长尾MM/KM)']['预测总收入(万元)']:.2f}</td></tr>
        <tr><td>平均WAPE</td><td class="old">{compare['上一版(仅长尾MM/KM)']['平均WAPE(%)']}</td><td class="new">{compare['本版(全客户)']['平均WAPE(活跃+半活跃)']}</td><td>大幅改善</td></tr>
        <tr><td>高置信度客户</td><td class="old">{compare['上一版(仅长尾MM/KM)']['高置信度占比']}</td><td class="new">{compare['本版(全客户)']['A+B级(高置信度)']} 家 ({(summary['与上一版对比']['本版(全客户)']['A+B级(高置信度)']/total_customers*100):.1f}%)</td><td>+{compare['本版(全客户)']['A+B级(高置信度)'] - 16} 家</td></tr>
        <tr><td>方法数</td><td class="old">{compare['上一版(仅长尾MM/KM)']['方法数']}</td><td class="new">{compare['本版(全客户)']['方法数']}</td><td>+{compare['本版(全客户)']['方法数'] - compare['上一版(仅长尾MM/KM)']['方法数']}</td></tr>
        <tr><td>回测折数</td><td class="old">{compare['上一版(仅长尾MM/KM)']['回测折数']}</td><td class="new">{compare['本版(全客户)']['回测折数']}</td><td>增强</td></tr>
      </tbody>
    </table>
  </div>

  <div class="footer">长尾客户预测增强仪表盘 · v2 · 智数分析专家团 · 生成时间 {summary['生成时间']}</div>
</div>

<script>
// 嵌入数据
const PRED = {js_pred};
const HIST = {js_hist};
const MULTI = {js_multi};
const SUMMARY = {json.dumps(summary, ensure_ascii=False)};

// Chart.js 全局配置
Chart.defaults.font.family = "'Segoe UI','Microsoft YaHei',system-ui,sans-serif";
Chart.defaults.font.size = 12;
Chart.defaults.plugins.legend.labels.usePointStyle = true;

const COLORS = {{
  A: '#2ecc71', B: '#3498db', C: '#f39c12', D: '#e74c3c', E: '#95a5a6',
  KA: '#1e3a5f', AA: '#9b59b6', KM: '#e67e22', MM: '#17a2b8', '': '#bdc3c7'
}};

// ===== 模块2: 置信度分布饼图 =====
const confData = {json.dumps(conf_dist, ensure_ascii=False)};
const confLabels = Object.keys(confData);
const confValues = confLabels.map(k => parseInt(confData[k]));
new Chart(document.getElementById('confPie'), {{
  type: 'pie',
  data: {{
    labels: confLabels.map(k => k + '级'),
    datasets: [{{
      data: confValues,
      backgroundColor: confLabels.map(k => COLORS[k]),
      borderWidth: 2, borderColor: '#fff'
    }}]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{
      legend: {{ position: 'right' }},
      tooltip: {{
        callbacks: {{
          label: ctx => {{
            const pct = (ctx.raw / confValues.reduce((a,b)=>a+b,0) * 100).toFixed(1);
            return ctx.label + ': ' + ctx.raw + ' 家 (' + pct + '%)';
          }}
        }}
      }}
    }}
  }}
}});

// 按客户类别置信度堆叠柱状图
const confByType = {json.dumps(conf_by_type, ensure_ascii=False)};
const typeKeys = Object.keys(confByType).filter(k => k !== '');
const typeLabels = ['KA>1亿','AA>5000万','KM>1000万','MM<1000万','未分类'].filter(k => confByType[k] || confByType[k==='未分类'] !== undefined);
const gradeLabels = ['A','B','C','D','E'];
const stackDatasets = gradeLabels.map(g => ({{
  label: g + '级',
  data: typeLabels.map(t => {{
    const key = t === '未分类' ? '' : t;
    return (confByType[key] && confByType[key][g]) || 0;
  }}),
  backgroundColor: COLORS[g]
}}));
new Chart(document.getElementById('confStack'), {{
  type: 'bar',
  data: {{ labels: typeLabels, datasets: stackDatasets }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    scales: {{ x: {{ stacked: true }}, y: {{ stacked: true, beginAtZero: true }} }},
    plugins: {{ legend: {{ position: 'top' }} }}
  }}
}});

// ===== 模块4: 方法使用频次 =====
const top20 = {json.dumps(top20_methods, ensure_ascii=False)};
const top10 = top20.slice(0, 10);
new Chart(document.getElementById('methodBar'), {{
  type: 'bar',
  data: {{
    labels: top10.map(m => m['方法'].length > 20 ? m['方法'].substring(0,20)+'...' : m['方法']),
    datasets: [{{
      data: top10.map(m => m['使用次数']),
      backgroundColor: '#1e3a5f',
      borderRadius: 4
    }}]
  }},
  options: {{
    indexAxis: 'y',
    responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ display: false }} }},
    scales: {{ x: {{ beginAtZero: true }} }}
  }}
}});

// 方法类别占比饼图 - 基于A/B/C/D/E分布
const methodCatData = [
  {{ label: 'A级(最优)', count: {sum(1 for r in pred if r['g']=='A')} }},
  {{ label: 'B级(良好)', count: {sum(1 for r in pred if r['g']=='B')} }},
  {{ label: 'C级(一般)', count: {sum(1 for r in pred if r['g']=='C')} }},
  {{ label: 'D级(较差)', count: {sum(1 for r in pred if r['g']=='D')} }},
  {{ label: 'E级(零预测)', count: {sum(1 for r in pred if r['g']=='E')} }}
];
new Chart(document.getElementById('methodCatPie'), {{
  type: 'doughnut',
  data: {{
    labels: methodCatData.map(d => d.label),
    datasets: [{{
      data: methodCatData.map(d => d.count),
      backgroundColor: ['#2ecc71','#3498db','#f39c12','#e74c3c','#95a5a6'],
      borderWidth: 2, borderColor: '#fff'
    }}]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{
      legend: {{ position: 'right' }},
      tooltip: {{
        callbacks: {{
          label: ctx => ctx.label + ': ' + ctx.raw + ' 家'
        }}
      }}
    }}
  }}
}});

// ===== 模块3: 预测结果表格 =====
let sortCol = -1, sortAsc = true;
function renderTable(data) {{
  const tbody = document.getElementById('tableBody');
  tbody.innerHTML = data.map(r => `
    <tr>
      <td title="${{r.n}}">${{r.n.length > 25 ? r.n.substring(0,25)+'...' : r.n}}</td>
      <td>${{r.t || '未分类'}}</td>
      <td>${{r.tier}}</td>
      <td style="text-align:right">${{(r.rev/10000).toFixed(2)}}</td>
      <td style="text-align:right">${{(r.pft/10000).toFixed(2)}}</td>
      <td style="text-align:right">${{r.wape === 999 ? '-' : r.wape.toFixed(1)}}</td>
      <td><span class="grade-${{r.g}}">${{r.g}}</span></td>
      <td title="${{r.m}}">${{r.m.length > 25 ? r.m.substring(0,25)+'...' : r.m}}</td>
    </tr>
  `).join('');
}}

function filterTable() {{
  const search = document.getElementById('searchInput').value.toLowerCase();
  const type = document.getElementById('typeFilter').value;
  const grade = document.getElementById('gradeFilter').value;
  let filtered = PRED.filter(r => {{
    if (search && !r.n.toLowerCase().includes(search)) return false;
    if (type && r.t !== type) return false;
    if (grade && r.g !== grade) return false;
    return true;
  }});
  renderTable(filtered);
}}

function sortTable(col) {{
  if (sortCol === col) sortAsc = !sortAsc;
  else {{ sortCol = col; sortAsc = true; }}
  const keys = ['n','t','tier','rev','pft','wape','g','m'];
  PRED.sort((a,b) => {{
    let va = a[keys[col]], vb = b[keys[col]];
    if (typeof va === 'number') return sortAsc ? va - vb : vb - va;
    return sortAsc ? String(va).localeCompare(String(vb)) : String(vb).localeCompare(String(va));
  }});
  filterTable();
}}

function exportCSV() {{
  const search = document.getElementById('searchInput').value.toLowerCase();
  const type = document.getElementById('typeFilter').value;
  const grade = document.getElementById('gradeFilter').value;
  let filtered = PRED.filter(r => {{
    if (search && !r.n.toLowerCase().includes(search)) return false;
    if (type && r.t !== type) return false;
    if (grade && r.g !== grade) return false;
    return true;
  }});
  let csv = '客户名称,客户类别,分层,预测收入,预测利润,WAPE,置信等级,最优方法\\n';
  filtered.forEach(r => {{
    csv += `"${{r.n}}","${{r.t}}","${{r.tier}}",${{r.rev.toFixed(2)}},${{r.pft.toFixed(2)}},${{r.wape}},${{r.g}},"${{r.m}}"\\n`;
  }});
  const blob = new Blob(['\\uFEFF' + csv], {{ type: 'text/csv;charset=utf-8;' }});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = 'v2_预测结果_筛选导出.csv'; a.click();
  URL.revokeObjectURL(url);
}}

// 初始渲染 - 按预测收入降序
PRED.sort((a,b) => b.rev - a.rev);
filterTable();

// ===== 模块5: 历史趋势 =====
const clientSelect = document.getElementById('clientSelect');
const activeNames = PRED.filter(r => r.rev > 0).map(r => r.n);
activeNames.sort((a,b) => a.localeCompare(b, 'zh-CN'));
activeNames.forEach(n => {{
  const opt = document.createElement('option');
  opt.value = n; opt.textContent = n;
  clientSelect.appendChild(opt);
}});

let histChart = null;
function showClientHistory() {{
  const name = clientSelect.value;
  if (!name || !HIST[name]) return;
  const data = HIST[name].sort((a,b) => a.q.localeCompare(b.q));
  const labels = data.map(d => d.q);
  const histRev = data.map(d => d.dt === '历史' ? d.rev/10000 : null);
  const predRev = data.map(d => d.dt === '预测' ? d.rev/10000 : null);
  // 最后一个历史点连接到预测
  const lastHistIdx = data.map(d => d.dt).lastIndexOf('历史');
  if (lastHistIdx >= 0 && lastHistIdx < data.length - 1) {{
    predRev[lastHistIdx] = data[lastHistIdx].rev/10000;
  }}
  if (histChart) histChart.destroy();
  histChart = new Chart(document.getElementById('histChart'), {{
    type: 'line',
    data: {{
      labels,
      datasets: [
        {{ label: '历史销售额(万)', data: histRev, borderColor: '#1e3a5f', backgroundColor: 'rgba(30,58,95,.1)', fill: true, tension: 0.3 }},
        {{ label: '预测销售额(万)', data: predRev, borderColor: '#2ecc71', borderDash: [5,5], backgroundColor: 'rgba(46,204,113,.1)', fill: false, tension: 0.3 }}
      ]
    }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      plugins: {{
        title: {{ display: true, text: name + ' - 季度销售趋势', font: {{ size: 14 }} }},
        tooltip: {{ callbacks: {{ label: ctx => ctx.dataset.label + ': ' + (ctx.raw !== null ? ctx.raw.toFixed(2) + ' 万' : '-') }} }}
      }},
      scales: {{ y: {{ beginAtZero: true }} }}
    }}
  }});
}}

// ===== 模块6: 多维度对比 =====
const multiSelect = document.getElementById('multiClientSelect');
const multiNames = Object.keys(MULTI);
multiNames.sort((a,b) => a.localeCompare(b, 'zh-CN'));
multiNames.forEach(n => {{
  const opt = document.createElement('option');
  opt.value = n; opt.textContent = n;
  multiSelect.appendChild(opt);
}});

let multiChart = null;
function showMultiCompare() {{
  const name = multiSelect.value;
  if (!name || !MULTI[name]) return;
  const clientData = MULTI[name];
  const clientInfo = PRED.find(r => r.n === name);
  const labels = ['客户级预测'].concat(clientData.map(d => d.dm));
  const values = [clientInfo ? clientInfo.rev/10000 : 0].concat(clientData.map(d => d.dp/10000));
  const colors = ['#1e3a5f'].concat(clientData.map((_,i) => i%2===0 ? '#3498db' : '#17a2b8'));
  if (multiChart) multiChart.destroy();
  multiChart = new Chart(document.getElementById('multiChart'), {{
    type: 'bar',
    data: {{
      labels: labels.map(l => l.length > 18 ? l.substring(0,18)+'...' : l),
      datasets: [{{
        label: '预测值(万)',
        data: values,
        backgroundColor: colors,
        borderRadius: 4
      }}]
    }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      plugins: {{
        title: {{ display: true, text: name + ' - 多维度预测对比', font: {{ size: 14 }} }},
        legend: {{ display: false }},
        tooltip: {{ callbacks: {{ label: ctx => ctx.raw.toFixed(2) + ' 万' }} }}
      }},
      scales: {{ y: {{ beginAtZero: true }} }}
    }}
  }});
}}
</script>
</body>
</html>'''

with open('长尾预测增强版仪表盘.html', 'w', encoding='utf-8') as f:
    f.write(html)

print(f"Dashboard generated: {len(html)} bytes")
print(f"Pred: {len(pred)}, Hist: {len(hist)}, Multi: {len(multi)}")
