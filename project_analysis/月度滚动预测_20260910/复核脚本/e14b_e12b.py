# -*- coding: utf-8 -*-
"""E14b：Nowcasting 修正（h1 × ratio）+ E12b：量价拆解集成进 combo（非春节月用 vol×asp）"""
import sys
import numpy as np
import pandas as pd
sys.stdout.reconfigure(encoding='utf-8')

SILVER = r'E:\3-其他资料\数据分析\sales_analytics_platform\output\silver\silver_cleaned_rows.parquet'
OUT = r'E:\3-其他资料\数据分析\project_analysis\月度滚动预测_20260910'

df = pd.read_parquet(SILVER, columns=['发货日期', '数量', '金额'])
df['dt'] = pd.to_datetime(df['发货日期'], errors='coerce')
df = df.dropna(subset=['dt'])
df['月'] = df['dt'].dt.strftime('%Y-%m')
df['日'] = df['dt'].dt.day
df['金额'] = pd.to_numeric(df['金额'], errors='coerce').fillna(0)
df['数量'] = pd.to_numeric(df['数量'], errors='coerce').fillna(0)

# ---------- E14b Nowcasting 修正 ----------
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
    rows.append({'月': m.index[i], 'h1': m.iloc[i]['h1'], '实际': m.iloc[i]['full'],
                 'mean_ratio': prior.mean(), 'median_ratio': prior.median()})
r = pd.DataFrame(rows)
r['pred_mean'] = r['h1'] * r['mean_ratio']
r['pred_med'] = r['h1'] * r['median_ratio']

def ape(c):
    return ((r[c] - r['实际']).abs() / r['实际']).mean()

print('=== E14b Nowcasting（修正：h1 × ratio）===')
print('均值法 平均APE: %.1f%% | 中位法 平均APE: %.1f%% (n=%d)' % (ape('pred_mean')*100, ape('pred_med')*100, len(r)))
print('比率分布: 均值 %.2f 中位 %.2f 标准差 %.2f' % (m['ratio'].mean(), m['ratio'].median(), m['ratio'].std()))
print()
for _, row in r.iterrows():
    print('%s: h1 %.0f万 → 预测 %.0f万 | 实际 %.0f万 | APE %.1f%%' % (
        row['月'], row['h1']/1e4, row['pred_med']/1e4, row['实际']/1e4,
        abs(row['pred_med']-row['实际'])/row['实际']*100))

# ---------- E12b 量价拆解集成 combo ----------
g = df.groupby('月').agg(rev=('金额', 'sum'), vol=('数量', 'sum')).sort_index()
g['asp'] = g['rev'] / g['vol'].clip(lower=1)
months = list(g.index)
rev = g['rev'].values.astype(float)
vol = g['vol'].values.astype(float)
asp = g['asp'].values.astype(float)

e3 = pd.read_csv(OUT + r'\E3_节前月加成_对比.csv')
e3 = e3.dropna(subset=['combo_phase']).set_index('月')
combo_map = e3['combo_phase'].to_dict()
wd3_map = e3['wd3'].to_dict()
phase_map = e3['phase'].to_dict()

def mav(v, i, k):
    return float(v[max(0, i-k):i].mean())

rows2 = []
for i in range(len(months)):
    t = months[i]
    if t < '2025-01' or t not in combo_map:
        continue
    vp6 = mav(vol, i, 6)
    ap6 = mav(asp, i, 6)
    volxasp = vp6 * ap6
    mm = t[5:7]
    if mm == '01':
        ph = phase_map.get(t)
        newpred = ph if (ph is not None and not pd.isna(ph)) else wd3_map.get(t, combo_map[t])
    elif mm == '02':
        newpred = wd3_map.get(t, combo_map[t])
    else:
        newpred = volxasp
    rows2.append({'月': t, '实际': rev[i], 'combo': combo_map[t], 'combo_volxasp': newpred})
r2 = pd.DataFrame(rows2)

def w(c):
    return (r2[c] - r2['实际']).abs().sum() / r2['实际'].sum()

print()
print('=== E12b 量价拆解集成 combo（非春节月用 vol×asp）===')
print('combo（原）:           %.1f%%' % (w('combo')*100))
print('combo_volxasp（集成）:  %.1f%%' % (w('combo_volxasp')*100))
r2.to_csv(OUT + r'\E12b_量价集成_对比.csv', index=False, encoding='utf-8-sig')
print()
print('明细已存: E12b_量价集成_对比.csv')
