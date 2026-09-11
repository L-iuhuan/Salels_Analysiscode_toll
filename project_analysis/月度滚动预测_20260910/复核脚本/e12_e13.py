# -*- coding: utf-8 -*-
"""E12：量价拆解预测（driver-based）| E13：大单/脉冲诊断"""
import sys
import numpy as np
import pandas as pd
sys.stdout.reconfigure(encoding='utf-8')

SILVER = r'E:\3-其他资料\数据分析\sales_analytics_platform\output\silver\silver_cleaned_rows.parquet'
OUT = r'E:\3-其他资料\数据分析\project_analysis\月度滚动预测_20260910'

df = pd.read_parquet(SILVER, columns=['发货日期', '数量', '金额', '客户编号'])
df['月'] = pd.to_datetime(df['发货日期'], errors='coerce').dt.strftime('%Y-%m')
df = df.dropna(subset=['月'])
df['金额'] = pd.to_numeric(df['金额'], errors='coerce').fillna(0)
df['数量'] = pd.to_numeric(df['数量'], errors='coerce').fillna(0)

g = df.groupby('月').agg(rev=('金额', 'sum'), vol=('数量', 'sum')).sort_index()
g['asp'] = g['rev'] / g['vol'].clip(lower=1)
months = list(g.index)
rev = g['rev'].values.astype(float)
vol = g['vol'].values.astype(float)
asp = g['asp'].values.astype(float)

e3 = pd.read_csv(OUT + r'\E3_节前月加成_对比.csv').dropna(subset=['combo_phase'])
combo_map = dict(zip(e3['月'], e3['combo_phase']))

def mav(v, i, k):
    return float(v[max(0, i-k):i].mean())

rows = []
for i in range(len(months)):
    if months[i] < '2025-01':
        continue
    vp6 = mav(vol, i, 6)
    ap6 = mav(asp, i, 6)
    ap3 = mav(asp, i, 3)
    y = asp[max(0, i-6):i]
    x = np.arange(len(y))
    if len(y) >= 3 and y.std() > 0:
        sl, ic = np.polyfit(x, y, 1)
        ap_t = max(0.0, float(ic + sl * len(y)))
    else:
        ap_t = ap6
    rows.append({'月': months[i], '实际': rev[i],
                 'vol6×asp6': vp6*ap6, 'vol6×asp3': vp6*ap3, 'vol6×asp_trend': vp6*ap_t,
                 'combo': combo_map.get(months[i], np.nan), 'ma6': mav(rev, i, 6)})
r = pd.DataFrame(rows).dropna(subset=['combo'])

def w(c):
    return (r[c] - r['实际']).abs().sum() / r['实际'].sum()

print('=== E12 量价拆解预测（%d 折）===' % len(r))
for c in ['ma6', 'combo', 'vol6×asp6', 'vol6×asp3', 'vol6×asp_trend']:
    print('%-16s %.1f%%' % (c, w(c)*100))

# 量/价各自误差（描述性）
msk = [i for i in range(len(months)) if months[i] >= '2025-01']
vol_w = np.abs(np.array([mav(vol, i, 6) for i in msk]) - vol[msk]).sum() / vol[msk].sum()
asp_w = np.abs(np.array([mav(asp, i, 6) for i in msk]) - asp[msk]).sum() / asp[msk].sum()
print('单因子 WAPE：量 %.1f%% | ASP %.1f%%' % (vol_w*100, asp_w*100))

# ---------- E13 集中度 ----------
cust = df.groupby(['月', '客户编号'])['金额'].sum().reset_index()
rows2 = []
for m, gg in cust.groupby('月'):
    gg = gg.sort_values('金额', ascending=False)
    tot = gg['金额'].sum()
    if tot <= 0:
        continue
    rows2.append({'月': m, 'top1': gg.iloc[0]['金额']/tot, 'top5': gg.head(5)['金额'].sum()/tot, 'n_cust': len(gg)})
c = pd.DataFrame(rows2)
print()
print('=== E13 月度集中度 ===')
print('全体: top1 均值 %.3f 中位 %.3f | top5 均值 %.3f 中位 %.3f' % (
    c['top1'].mean(), c['top1'].median(), c['top5'].mean(), c['top5'].median()))
for m in ['2026-01', '2026-03', '2026-04', '2026-05', '2026-07', '2026-08']:
    row = c[c['月'] == m]
    if len(row):
        print('%s: top1 %.3f top5 %.3f n=%d' % (m, row.iloc[0]['top1'], row.iloc[0]['top5'], row.iloc[0]['n_cust']))

m3 = cust[cust['月'] == '2026-03'].set_index('客户编号')['金额']
m4 = cust[cust['月'] == '2026-04'].set_index('客户编号')['金额']
diff = (m4 - m3.reindex(m4.index).fillna(0)).sort_values(ascending=False)
print()
print('=== 2026-04 环比增量 TOP5 客户（脉冲归因）===')
for k, v in diff.head(5).items():
    print('%s: %+.1f万' % (str(k)[:20], v/1e4))

r.to_csv(OUT + r'\E12_量价拆解_对比.csv', index=False, encoding='utf-8-sig')
c.to_csv(OUT + r'\E13_集中度诊断.csv', index=False, encoding='utf-8-sig')
print()
print('明细已存: E12_量价拆解_对比.csv / E13_集中度诊断.csv')
