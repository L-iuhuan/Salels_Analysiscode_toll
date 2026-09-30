# -*- coding: utf-8 -*-
"""数据语义对拍：20DB 的 gold 历史 近12月销量_t-N vs silver 真实月度销量"""
import sys
import pandas as pd
sys.stdout.reconfigure(encoding='utf-8')

BASE = r'E:\3-其他资料\数据分析\sales_analytics_platform'
PC, MC, QC, RC = '产品品种', '发货日期', '数量', '出货总金额'

# 1. gold 历史值
hist = pd.read_csv(BASE + r'\output\gold\gold_product_portrait_history.csv', encoding='utf-8-sig')
hist.columns = [str(c).strip() for c in hist.columns]
row = hist[hist['产品名称'].astype(str).str.contains('20DB', na=False)].iloc[0]
cols = sorted([c for c in hist.columns if c.startswith('近12月销量_t-')], key=lambda c: int(c.split('t-')[1]))
print('=== gold 历史 近12月销量_t-N（20DB，t-1→t-12）===')
print([round(float(row[c]), 0) for c in cols[:12]])

# 2. silver 真实月度
silver = pd.read_parquet(BASE + r'\output\silver\silver_cleaned_rows.parquet')
sub = silver[silver[PC].astype(str).str.contains('20DB', na=False)].copy()
sub['_m'] = sub[MC].astype(str).str[:7]
g = sub.groupby('_m')[QC].sum().sort_index()
print()
print('=== silver 真实月度销量（20DB，最近14个月）===')
print({k: round(float(v), 0) for k, v in g.tail(14).items()})

# 3. 对拍结论
last12 = g[g.index >= '2025-09']
print()
print('silver 近12月(25-09~26-08)合计 =', round(float(last12.sum()), 0))
print('gold 近12月销量_t-1 =', round(float(row['近12月销量_t-1']), 0))
print('silver 最新单月(26-08) =', round(float(g.get('2026-08', 0)), 0))
print()
print('结论: gold 值≈滚动12月合计?', abs(float(row['近12月销量_t-1']) - float(last12.sum())) / max(float(last12.sum()), 1) < 0.05)
