# -*- coding: utf-8 -*-
"""E14：Nowcasting（半月→全月）| E15：客户行为模型（简化版）"""
import sys
import numpy as np
import pandas as pd
sys.stdout.reconfigure(encoding='utf-8')

SILVER = r'E:\3-其他资料\数据分析\sales_analytics_platform\output\silver\silver_cleaned_rows.parquet'
OUT = r'E:\3-其他资料\数据分析\project_analysis\月度滚动预测_20260910'

df = pd.read_parquet(SILVER, columns=['发货日期', '金额', '客户编号'])
df['dt'] = pd.to_datetime(df['发货日期'], errors='coerce')
df = df.dropna(subset=['dt'])
df['月'] = df['dt'].dt.strftime('%Y-%m')
df['日'] = df['dt'].dt.day
df['金额'] = pd.to_numeric(df['金额'], errors='coerce').fillna(0)

# ---------- E14 Nowcasting ----------
m = df.groupby('月').agg(full=('金额', 'sum')).sort_index()
h1 = df[df['日'] <= 15].groupby('月')['金额'].sum()
m['h1'] = h1.reindex(m.index).fillna(0)
m = m[m['h1'] > 0]
m['ratio'] = m['full'] / m['h1']
print('=== E14 半月→全月 ===')
print('比率: 均值 %.2f 中位 %.2f 标准差 %.2f (n=%d)' % (m['ratio'].mean(), m['ratio'].median(), m['ratio'].std(), len(m)))
print('相关性 r=%.3f' % np.corrcoef(m['h1'], m['full'])[0, 1])

rows = []
for i in range(len(m)):
    if m.index[i] < '2025-01':
        continue
    prior = m.iloc[:i]['ratio']
    if len(prior) < 6:
        continue
    pred = m.iloc[i]['h1'] / prior.mean()
    rows.append({'月': m.index[i], '预测': pred, '实际': m.iloc[i]['full']})
r = pd.DataFrame(rows)
ape = ((r['预测']-r['实际']).abs()/r['实际']).mean()
print('Nowcast 平均 APE: %.1f%% (n=%d)' % (ape*100, len(r)))
for _, row in r.iterrows():
    print('%s: 预测 %.0f万 | 实际 %.0f万 | APE %.1f%%' % (
        row['月'], row['预测']/1e4, row['实际']/1e4, abs(row['预测']-row['实际'])/row['实际']*100))

# ---------- E15 客户行为 ----------
cust_m = df.groupby(['月', '客户编号'])['金额'].sum().reset_index()
active = cust_m.groupby('月')['客户编号'].nunique()
avg = cust_m.groupby('月')['金额'].sum() / active
g = pd.DataFrame({'active': active, 'avg': avg}).sort_index()
print()
print('=== E15 活跃客户数 × 户均收入（近8月）===')
print(g.tail(8).to_string())

e3 = pd.read_csv(OUT + r'\E3_节前月加成_对比.csv').dropna(subset=['combo_phase'])
combo_map = dict(zip(e3['月'], e3['combo_phase']))
rev = df.groupby('月')['金额'].sum().sort_index()
ms = list(g.index)
rows = []
for i in range(len(ms)):
    if ms[i] < '2025-01':
        continue
    ap = g['active'].values[max(0, i-6):i].mean()
    av = g['avg'].values[max(0, i-6):i].mean()
    rows.append({'月': ms[i], '实际': rev[ms[i]], 'active×avg': ap*av, 'combo': combo_map.get(ms[i], np.nan)})
r2 = pd.DataFrame(rows).dropna()

def w(c):
    return (r2[c] - r2['实际']).abs().sum() / r2['实际'].sum()

print()
print('=== E15 客户行为模型 vs 基线（%d 折）===' % len(r2))
print('active×avg: %.1f%% | combo: %.1f%%' % (w('active×avg')*100, w('combo')*100))

r.to_csv(OUT + r'\E14_nowcasting_对比.csv', index=False, encoding='utf-8-sig')
r2.to_csv(OUT + r'\E15_客户行为_对比.csv', index=False, encoding='utf-8-sig')
print()
print('明细已存: E14_nowcasting_对比.csv / E15_客户行为_对比.csv')
