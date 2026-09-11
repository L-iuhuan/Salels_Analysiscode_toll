# -*- coding: utf-8 -*-
"""E6：分层调和-lite（线级预测 → 公司锚点缩放）
- A: 线级选优方法求和（raw）
- B: 调和（等比缩放使 sum = combo_phase 锚点）
- 对照: combo_phase（锚点，公司口径）
- 输出: 公司口径 WAPE 对比 + 线级 raw vs scaled 对比（多少线改善）
"""
import sys
import numpy as np
import pandas as pd
sys.stdout.reconfigure(encoding='utf-8')

SILVER = r'E:\3-其他资料\数据分析\sales_analytics_platform\output\silver\silver_cleaned_rows.parquet'
OUT = r'E:\3-其他资料\数据分析\project_analysis\月度滚动预测_20260910'

df = pd.read_parquet(SILVER, columns=['发货日期', '型号_产品线（新）', '金额'])
df['月'] = pd.to_datetime(df['发货日期'], errors='coerce').dt.strftime('%Y-%m')
df = df.dropna(subset=['月'])
df['金额'] = pd.to_numeric(df['金额'], errors='coerce').fillna(0)
pv = df.groupby(['月', '型号_产品线（新）'])['金额'].sum().unstack(fill_value=0.0).sort_index()
months = list(pv.index)

best = pd.read_csv(OUT + r'\产品线选优结果.csv')
best_map = dict(zip(best['产品线'], best['方法']))

def predict_one(v, method):
    n = len(v)
    if method == 'naive':
        return float(v[-1])
    if method.startswith('ma'):
        k = int(method[2:])
        return float(v[-k:].mean()) if n >= k else float(v.mean())
    if method == 'snaive':
        return float(v[-12]) if n >= 12 else float(v.mean())
    if method in ('trend6', 'trend12'):
        k = int(method[5:])
        y = np.asarray(v[-k:], dtype=float)
        x = np.arange(len(y))
        if len(y) >= 3 and y.std() > 0:
            sl, ic = np.polyfit(x, y, 1)
            return max(0.0, float(ic + sl * len(y)))
        return float(y.mean())
    if method == 'yoy_adj':
        base = float(v[-12]) if n >= 12 else float(v.mean())
        g = (sum(v[-12:]) / max(sum(v[-24:-12]), 1e-9)) if n >= 24 else 1.0
        return base * g
    return float(np.mean(v[-6:]))

e3 = pd.read_csv(OUT + r'\E3_节前月加成_对比.csv')
e3 = e3[['月', '实际', 'combo_phase']].dropna().reset_index(drop=True)
anchor_map = dict(zip(e3['月'], e3['combo_phase']))

targets = [m for m in months if '2025-01' <= m <= '2026-08']
rows = []
per_line = []
for t in targets:
    i = months.index(t)
    raw_sum = 0.0
    line_preds = {}
    for line in pv.columns:
        v = pv[line].values.astype(float)
        h = v[:i]
        mname = best_map.get(line, 'ma6')
        p = predict_one(h, mname)
        line_preds[line] = p
        raw_sum += p
    anchor = anchor_map.get(t)
    if anchor is None:
        continue
    factor = anchor / max(raw_sum, 1e-9)
    act_total = float(pv.loc[t].sum())
    rows.append({'月': t, '实际': act_total, 'raw_sum': raw_sum, 'anchor': anchor,
                 'scaled_sum': raw_sum * factor})
    for line, p in line_preds.items():
        per_line.append({'月': t, '产品线': line, '实际': float(pv.loc[t, line]),
                         'raw': p, 'scaled': p * factor})

r = pd.DataFrame(rows)
pl = pd.DataFrame(per_line)

def wape_col(d, c):
    return (d[c] - d['实际']).abs().sum() / max(d['实际'].sum(), 1e-9)

print('=== E6 公司口径（%d 折）===' % len(r))
print('线级求和(raw):    %.1f%%' % (wape_col(r, 'raw_sum') * 100))
print('锚点(combo_phase): %.1f%%' % (wape_col(r, 'anchor') * 100))
print('调和(缩放后):      %.1f%%' % (wape_col(r, 'scaled_sum') * 100))

print()
print('=== 线级平均 WAPE（raw vs 缩放后）===')
per_line_w = pl.groupby('产品线').apply(
    lambda g: pd.Series({'raw': (g['raw'] - g['实际']).abs().sum() / max(g['实际'].sum(), 1e-9),
                         'scaled': (g['scaled'] - g['实际']).abs().sum() / max(g['实际'].sum(), 1e-9)}))
improved = (per_line_w['scaled'] < per_line_w['raw']).sum()
print('线级平均: raw %.1f%% | scaled %.1f%% | 改善线数 %d/%d' % (
    per_line_w['raw'].mean() * 100, per_line_w['scaled'].mean() * 100, improved, len(per_line_w)))
print()
print('=== 线级明细（WAPE）===')
for line, g in per_line_w.sort_values('raw', ascending=False).iterrows():
    print('%-14s raw %6.1f%% → scaled %6.1f%%' % (line, g['raw'] * 100, g['scaled'] * 100))

r.to_csv(OUT + r'\E6_分层调和_对比.csv', index=False, encoding='utf-8-sig')
print()
print('明细已存: E6_分层调和_对比.csv')
