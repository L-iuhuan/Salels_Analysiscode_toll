# -*- coding: utf-8 -*-
"""E14 修正版重生成：Nowcasting（h1 × expanding 中位比率）——覆盖旧除法 bug 产物"""
import sys
import numpy as np
import pandas as pd
sys.stdout.reconfigure(encoding='utf-8')

SILVER = r'E:\3-其他资料\数据分析\sales_analytics_platform\output\silver\silver_cleaned_rows.parquet'
OUT = r'E:\3-其他资料\数据分析\project_analysis\月度滚动预测_20260910'

df = pd.read_parquet(SILVER, columns=['发货日期', '金额'])
df['dt'] = pd.to_datetime(df['发货日期'], errors='coerce')
df = df.dropna(subset=['dt'])
df['月'] = df['dt'].dt.strftime('%Y-%m')
df['日'] = df['dt'].dt.day
df['金额'] = pd.to_numeric(df['金额'], errors='coerce').fillna(0)

m = df.groupby('月').agg(full=('金额', 'sum')).sort_index()
h1 = df[df['日'] <= 15].groupby('月')['金额'].sum()
m['h1'] = h1.reindex(m.index).fillna(0)
m = m[m['h1'] > 0]
m['ratio'] = m['full'] / m['h1']

rows = []
for i in range(len(m)):
    if m.index[i] < '2025-01':
        continue
    prior = m.iloc[:i]['ratio']
    if len(prior) < 6:
        continue
    pred = m.iloc[i]['h1'] * prior.median()
    rows.append({'月': m.index[i], '预测': pred, '实际': m.iloc[i]['full']})
r = pd.DataFrame(rows)
r['APE'] = (r['预测'] - r['实际']).abs() / r['实际']
print('中位法平均 APE %.1f%%（%d 折）' % (r['APE'].mean() * 100, len(r)))
r.to_csv(OUT + r'\E14_nowcasting_对比.csv', index=False, encoding='utf-8-sig')
print('已覆盖: E14_nowcasting_对比.csv（旧除法 bug 版已替换）')
