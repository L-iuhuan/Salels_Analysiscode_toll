# -*- coding: utf-8 -*-
import sys, os, json, math, re
from collections import Counter, defaultdict
from datetime import datetime
try:
    import pandas as pd
    import numpy as np
except ImportError:
    print('Missing pandas/numpy: pip install pandas numpy')
    sys.exit(1)

def safe_float(val, default=None):
    if val is None or (isinstance(val, float) and (math.isnan(val) or math.isinf(val))): return default
    try:
        v = float(val)
        return default if (math.isnan(v) or math.isinf(v)) else v
    except (ValueError, TypeError): return default

def safe_int(val, default=None):
    v = safe_float(val)
    return default if v is None else int(v)

def find_sheet(wb_names, candidates):
    for c in candidates:
        for n in wb_names:
            if c in n: return n
    return None

def build_table_data(df):
    cols = [
        '产品名称', '所属参照组', '帕累托分类', '当前画像', '管理层摘要',
        '近12月销量', '近12月增长率%', '近12月毛利率%', '毛利率趋势斜率%/月',
        '衰退风险得分', '衰退风险等级', '通用策略建议',
        '前12月销量', '营收增长率%', '当月毛利率%', '前12月毛利率%',
        '毛利率同比变化%', 'ASP趋势%/月',
        '客户集中度-前1大%', '客户集中度-前3大%', '订货波动性CV',
        '风险主导因子', '特情说明', '销量动能', '盈利健康', '数据不足'
    ]
    int_cols = {'近12月销量', '前12月销量'}
    float_cols = {'近12月增长率%', '近12月毛利率%', '毛利率趋势斜率%/月',
                  '衰退风险得分', '营收增长率%', '当月毛利率%', '前12月毛利率%',
                  '毛利率同比变化%', 'ASP趋势%/月',
                  '客户集中度-前1大%', '客户集中度-前3大%', '订货波动性CV'}
    rows = []
    for _, row in df.iterrows():
        rec = {}
        for c in cols:
            if c in df.columns:
                v = row[c]
                if c in int_cols: rec[c] = safe_int(v, 0)
                elif c in float_cols: rec[c] = safe_float(v, 0)
                elif c == '数据不足': rec[c] = bool(v) if v is not None else False
                else: rec[c] = str(v) if pd.notna(v) else ''
            else:
                rec[c] = 0 if c in int_cols | float_cols else ('' if c != '数据不足' else False)
        rows.append(rec)
    return rows

def build_kpi(table, insufficient_count=0):
    total = len(table)
    high_risk = sum(1 for r in table if r['衰退风险等级'] == '高风险')
    declining = sum(1 for r in table if r['当前画像'] in {'衰退期', '夕阳产品', '隐性衰退'})
    growing = sum(1 for r in table if r['当前画像'] in {'成长期', '健康扩张', '预警增长'})
    gm_sum = sum(safe_float(r['近12月毛利率%'], 0) * safe_float(r['近12月销量'], 0) for r in table)
    sales_sum = sum(safe_float(r['近12月销量'], 0) for r in table)
    growth_sum = sum(safe_float(r['近12月增长率%'], 0) for r in table)
    avg_gm = round(gm_sum / sales_sum, 1) if sales_sum > 0 else 0
    avg_growth = round(growth_sum / total, 1) if total > 0 else 0
    return {
        'total_products': total, 'high_risk': high_risk, 'extreme_risk': 0,
        'avg_gm': avg_gm, 'avg_growth': avg_growth,
        'declining': declining, 'growing': growing,
        'data_insufficient': insufficient_count
    }

def build_filters(table):
    def uniq(col):
        return sorted({r[col] for r in table if r.get(col, '')})
    return {
        'portrait': uniq('当前画像'), 'risk': uniq('衰退风险等级'),
        'pareto': uniq('帕累托分类'), 'group': uniq('所属参照组'),
        'momentum': uniq('销量动能'), 'profit': uniq('盈利健康'),
        'summary': uniq('管理层摘要')
    }

def build_scatter(table):
    out = []
    for r in table:
        out.append({
            'name': r['产品名称'], 'group': r['所属参照组'],
            'x': round(safe_float(r['近12月毛利率%'], 0), 2),
            'y': round(safe_float(r['近12月增长率%'], 0), 2),
            'z': safe_float(r['近12月销量'], 0),
            'risk': r['衰退风险等级'], 'portrait': r['当前画像'],
            'gm_trend': round(safe_float(r['毛利率趋势斜率%/月'], 0), 2)
        })
    return out

def build_sankey_wide(df_hist, df_snap, top_n=100):
    if df_hist is None or df_hist.empty: return {'nodes': [], 'links': []}
    name_col = '产品名称'
    if name_col not in df_hist.columns: return {'nodes': [], 'links': []}
    portrait_cols = [c for c in df_hist.columns if c and '当前画像' in str(c)]
    if not portrait_cols: return {'nodes': [], 'links': []}
    # Map t-N to quarterly intervals
    t_to_q = {}
    for c in portrait_cols:
        import re as _re
        m = _re.search(r't-(\d+)', c)
        if m:
            t = int(m.group(1))
            # t-1,t-2,t-3 = Q4; t-4,t-5,t-6 = Q3; t-7,t-8,t-9 = Q2; t-10,t-11,t-12 = Q1
            if t <= 3: q = 'Q4'
            elif t <= 6: q = 'Q3'
            elif t <= 9: q = 'Q2'
            else: q = 'Q1'
            t_to_q[c] = q
    # Get top N products by sales
    if '近12月销量' in df_snap.columns:
        top_prods = set(df_snap.nlargest(top_n, '近12月销量')['产品名称'])
    else:
        top_prods = set(df_hist[name_col].unique()[:top_n])
    df = df_hist[df_hist[name_col].isin(top_prods)].copy()
    # Build long format
    rows = []
    for _, row in df.iterrows():
        for col, q in t_to_q.items():
            v = row[col]
            if pd.notna(v) and str(v).strip():
                rows.append({'产品名称': row[name_col], '季度': q, '画像': str(v).strip()})
    long_df = pd.DataFrame(rows)
    if long_df.empty: return {'nodes': [], 'links': []}
    quarters = ['Q1', 'Q2', 'Q3', 'Q4']
    p_order = ['新品观察','成长期','健康扩张','预警增长','现金牛','利润优化','隐性衰退','主动收缩','衰退期','夕阳产品','清仓/偶发']
    p_pos = {p: i for i, p in enumerate(p_order)}
    nodes = []
    for q in quarters:
        ps = long_df[long_df['季度'] == q]['画像'].unique()
        for p in sorted(ps, key=lambda x: p_pos.get(x, 99)):
            nodes.append({'name': q + '_' + p})
    node_names = {n['name'] for n in nodes}
    links = []
    for i in range(len(quarters) - 1):
        fq, tq = quarters[i], quarters[i+1]
        fd = long_df[long_df['季度'] == fq].groupby(['产品名称','画像']).size().reset_index(name='c')
        td = long_df[long_df['季度'] == tq].groupby(['产品名称','画像']).size().reset_index(name='c')
        m = fd.merge(td, on='产品名称')
        m = m[m['画像_x'] != m['画像_y']]
        for _, rw in m.iterrows():
            s, t = fq + '_' + rw['画像_x'], tq + '_' + rw['画像_y']
            if s in node_names and t in node_names:
                links.append({'source': s, 'target': t, 'value': int(rw['c_x']), 'products': [rw['产品名称']]})
    agg = {}
    for lk in links:
        k = (lk['source'], lk['target'])
        if k not in agg:
            agg[k] = {'source': lk['source'], 'target': lk['target'], 'value': 0, 'products': []}
        agg[k]['value'] += lk['value']
        agg[k]['products'].extend(lk['products'])
    final = list(agg.values())
    np_map = defaultdict(list)
    for lk in links:
        np_map[lk['source']].extend(lk['products'])
        np_map[lk['target']].extend(lk['products'])
    for nd in nodes:
        nd['products'] = sorted(set(np_map.get(nd['name'], [])))
    for lk in final:
        lk['products'] = sorted(set(lk['products']))
    return {'nodes': nodes, 'links': final}


def build_rfm(df):
    if df is None or df.empty or '客户类型' not in df.columns: return {}
    return {str(k): int(v) for k, v in df['客户类型'].value_counts().items()}

def build_network(df, top_n=50):
    if df is None or df.empty: return {'nodes': [], 'links': []}
    for c in ['产品A', '产品B', '支持度', '置信度(A->B)']:
        if c not in df.columns: return {'nodes': [], 'links': []}
    df = df.head(top_n).copy()
    deg = Counter()
    for _, r in df.iterrows():
        deg[r['产品A']] += 1
        deg[r['产品B']] += 1
    nodes = [{'name': n, 'value': c} for n, c in deg.most_common()]
    links = [{'source': r['产品A'], 'target': r['产品B'],
              'support': round(float(r['支持度']), 4),
              'confidence': round(float(r['置信度(A->B)']), 4)} for _, r in df.iterrows()]
    return {'nodes': nodes, 'links': links}

def build_history_wide(df_hist, df_snap):
    if df_hist is None or df_hist.empty: return {}
    name_col = '产品名称'
    if name_col not in df_hist.columns: return {}
    portrait_cols = [c for c in df_hist.columns if c and '当前画像' in str(c)]
    sales_cols = [c for c in df_hist.columns if c and '近12月销量' in str(c)]
    gm_cols = [c for c in df_hist.columns if c and '近12月毛利率%' in str(c)]
    hist = {}
    for _, row in df_snap.iterrows():
        name = row[name_col]
        ph = df_hist[df_hist[name_col] == name]
        if ph.empty: continue
        ph = ph.iloc[0]
        portraits = []
        for c in sorted(portrait_cols, reverse=True):
            v = ph[c]
            if pd.notna(v): portraits.append(str(v).strip())
        sales = []
        gm = []
        for c in sorted(sales_cols, reverse=True):
            sales.append(int(safe_float(ph.get(c, 0), 0)))
        for c in sorted(gm_cols, reverse=True):
            gm.append(round(safe_float(ph.get(c, 0), 0), 2))
        if portraits: hist[name] = {'portraits': portraits, 'sales': sales, 'gm': gm}
    return hist

def build_forecasts(df):
    if df is None or df.empty or '产品名称' not in df.columns: return {}
    fc = {}
    for _, r in df.iterrows():
        name = r['产品名称']
        f1_col = [c for c in df.columns if c and '预测_第1月' in str(c)]
        f2_col = [c for c in df.columns if c and '预测_第2月' in str(c)]
        f3_col = [c for c in df.columns if c and '预测_第3月' in str(c)]
        trend_col = [c for c in df.columns if c and '趋势方向预测' in str(c)]
        fc[name] = {
            'f1': safe_int(r.get(f1_col[0], None)) if f1_col else None,
            'f2': safe_int(r.get(f2_col[0], None)) if f2_col else None,
            'f3': safe_int(r.get(f3_col[0], None)) if f3_col else None,
            'trend': str(r.get(trend_col[0], '')) if trend_col and pd.notna(r.get(trend_col[0], )) else ''
        }
    return fc

def generate_dashboard(excel_path, output_path=None):
    import openpyxl
    print('[*] 读取数据文件: ' + excel_path)
    if not os.path.exists(excel_path):
        print('[错误] 文件不存在: ' + excel_path)
        sys.exit(1)
    wb = openpyxl.load_workbook(excel_path, read_only=True)
    sheet_names = wb.sheetnames
    print('[*] 找到 ' + str(len(sheet_names)) + ' 个工作表')
    snapshot_sheet = find_sheet(sheet_names, ['产品快照', '产品快照表'])
    hist_sheet = find_sheet(sheet_names, ['历史', '历史画像', '历史画像追踪'])
    forecast_sheet = find_sheet(sheet_names, ['预测', '趋势预测', '趋势预测汇总'])
    rfm_sheet = find_sheet(sheet_names, ['RFM', '客户RFM', '客户RFM分群'])
    assoc_sheet = find_sheet(sheet_names, ['关联', '产品关联', '产品关联分析'])
    insufficient_sheet = find_sheet(sheet_names, ['数据不足', '数据不足产品'])
    if snapshot_sheet:
        df_snapshot = pd.read_excel(excel_path, sheet_name=snapshot_sheet)
        print('[*] 产品快照表: ' + str(len(df_snapshot)) + ' 行')
    else:
        print('[错误] 未找到产品快照表')
        sys.exit(1)
    data_insufficient_count = 0
    if insufficient_sheet:
        df_insufficient = pd.read_excel(excel_path, sheet_name=insufficient_sheet)
        data_insufficient_count = len(df_insufficient)
    df_hist = pd.read_excel(excel_path, sheet_name=hist_sheet) if hist_sheet else None
    df_forecast = pd.read_excel(excel_path, sheet_name=forecast_sheet) if forecast_sheet else None
    df_rfm = pd.read_excel(excel_path, sheet_name=rfm_sheet) if rfm_sheet else None
    df_assoc = pd.read_excel(excel_path, sheet_name=assoc_sheet) if assoc_sheet else None
    print('[*] 构建数据结构...')
    table_data = build_table_data(df_snapshot)
    kpi = build_kpi(table_data, data_insufficient_count)
    filters = build_filters(table_data)
    scatter = build_scatter(table_data)
    sankey = build_sankey_wide(df_hist, df_snapshot)
    rfm = build_rfm(df_rfm)
    network = build_network(df_assoc)
    history = build_history_wide(df_hist, df_snapshot)
    forecasts = build_forecasts(df_forecast)
    data_month = '未知'
    if '最新数据月份' in df_snapshot.columns:
        months = df_snapshot['最新数据月份'].dropna().unique()
        if len(months) > 0: data_month = str(months[0])
    data_obj = {
        'kpi': kpi,
        'charts': {
            'portrait': dict(Counter(r['当前画像'] for r in table_data)),
            'risk': dict(Counter(r['衰退风险等级'] for r in table_data)),
            'pareto': dict(Counter(r['帕累托分类'] for r in table_data if r['帕累托分类'])),
            'summary': dict(Counter(r['管理层摘要'] for r in table_data)),
            'profit_health': dict(Counter(r['盈利健康'] for r in table_data if r['盈利健康'])),
            'momentum': dict(Counter(r['销量动能'] for r in table_data if r['销量动能']))
        },
        'scatter': scatter, 'sankey': sankey, 'rfm': rfm,
        'graph': network, 'filters': filters, 'table': table_data,
        'history': history, 'forecasts': forecasts
    }
    data_json = json.dumps(data_obj, ensure_ascii=False, default=str)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    tpl_path = os.path.join(script_dir, '_dashboard_template.json')
    if os.path.exists(tpl_path):
        with open(tpl_path, 'r', encoding='utf-8') as tf:
            tpl = json.load(tf)
        html = tpl['header'] + 'const DATA = ' + data_json + ';\\n' + tpl['footer']
    else:
        html_path = os.path.join(script_dir, 'product_dashboard_v4-演示.html')
        with open(html_path, 'r', encoding='utf-8') as hf:
            full_html = hf.read()
        m = re.search(r'const DATA = ({.*?});', full_html, re.DOTALL)
        if m:
            html = full_html[:m.start()] + 'const DATA = ' + data_json + ';' + full_html[m.end():]
        else:
            print('[错误] 未找到DATA JSON占位符')
            sys.exit(1)
    if output_path is None:
        base = os.path.splitext(os.path.basename(excel_path))[0]
        output_path = os.path.join(os.path.dirname(excel_path), base + '_全景看板.html')
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print('[成功] 全景看板已生成: ' + output_path)
    print('       文件大小: ' + str(round(os.path.getsize(output_path) / 1024, 1)) + ' KB')
    return output_path

def main():
    if len(sys.argv) > 1:
        excel_path = sys.argv[1]
    else:
        print('用法: python generate_dashboard_v4.py <Excel文件路径>')
        script_dir = os.path.dirname(os.path.abspath(__file__))
        excel_files = [f for f in os.listdir(script_dir) if f.startswith('output_v2.8') and f.endswith('.xlsx')]
        if excel_files:
            excel_files.sort(key=lambda x: os.path.getmtime(os.path.join(script_dir, x)), reverse=True)
            excel_path = os.path.join(script_dir, excel_files[0])
            print('自动找到: ' + excel_files[0])
        else:
            print('未找到 output_v2.8_*.xlsx 文件')
            return
    output_path = sys.argv[2] if len(sys.argv) > 2 else None
    generate_dashboard(excel_path, output_path)

if __name__ == '__main__':
    main()
