# -*- coding: utf-8 -*-
"""E9：LightGBM 全局模型（跨产品线学习）vs 基线
- 样本: 18线×月长表；特征: 滞后1/2/3、ma3/6/12、同比lag12、月序、CNY相位、线ID、时间序
- walk-forward: 每折仅用目标月之前的样本训练，预测18线后汇总公司口径
- 对照: ma6(10.3%) / combo_phase(7.9%)
- 变体: lgbm / lgbm+combo 0.5混合
"""
import sys, calendar, datetime, warnings
import numpy as np
import pandas as pd
warnings.filterwarnings('ignore')
sys.stdout.reconfigure(encoding='utf-8')

SILVER = r'E:\3-其他资料\数据分析\sales_analytics_platform\output\silver\silver_cleaned_rows.parquet'
OUT = r'E:\3-其他资料\数据分析\project_analysis\月度滚动预测_20260910'

df = pd.read_parquet(SILVER, columns=['发货日期', '型号_产品线（新）', '金额'])
df['月'] = pd.to_datetime(df['发货日期'], errors='coerce').dt.strftime('%Y-%m')
df = df.dropna(subset=['月'])
df['金额'] = pd.to_numeric(df['金额'], errors='coerce').fillna(0)
pv = df.groupby(['月', '型号_产品线（新）'])['金额'].sum().unstack(fill_value=0.0).sort_index()
months = list(pv.index)
lines = list(pv.columns)
print('线数:', len(lines), '| 月数:', len(months))

CNY_MONTH = {2024: 2, 2025: 1, 2026: 2}
def phase_code(t):
    y, m = int(t[:4]), int(t[5:7])
    c = CNY_MONTH.get(y)
    if m == 1:
        return 0 if c == 2 else 1   # 0=pre, 1=at
    if m == 2:
        return 1 if c == 2 else 2   # 1=at, 2=post
    return 3

# 构建长表（每线每月，特征仅用该月之前数据）
rows = []
for li, line in enumerate(lines):
    v = pv[line].values.astype(float)
    for i in range(12, len(v)):
        t = months[i]
        rows.append({
            'line': li, 'moy': int(t[5:7]), 'tidx': i, 'phase': phase_code(t),
            'lag1': v[i-1], 'lag2': v[i-2], 'lag3': v[i-3],
            'ma3': v[i-3:i].mean(), 'ma6': v[i-6:i].mean(), 'ma12': v[i-12:i].mean(),
            'yoy': v[i-12],
            'y': v[i],
        })
L = pd.DataFrame(rows)
FEATS = ['line', 'moy', 'tidx', 'phase', 'lag1', 'lag2', 'lag3', 'ma3', 'ma6', 'ma12', 'yoy']
CATS = ['line', 'moy', 'phase']

import lightgbm as lgb

# E3 冠军系统预测（对照）
e3 = pd.read_csv(OUT + r'\E3_节前月加成_对比.csv')
e3 = e3[['月', '实际', 'combo_phase']].dropna().reset_index(drop=True)

targets = [m for m in months if '2025-01' <= m <= '2026-08']
res = []
for t in targets:
    ti = months.index(t)
    train = L[L['tidx'] < ti]
    pred_rows = L[L['tidx'] == ti]
    if len(train) < 60 or len(pred_rows) == 0:
        continue
    model = lgb.LGBMRegressor(n_estimators=150, learning_rate=0.05, num_leaves=15,
                              min_child_samples=5, subsample=0.9, colsample_bytree=0.9,
                              random_state=42, verbose=-1)
    model.fit(train[FEATS], np.log1p(train['y']), categorical_feature=CATS)
    p = np.expm1(model.predict(pred_rows[FEATS]))
    p = np.maximum(p, 0.0)
    lgbm_sum = float(p.sum())
    act = float(pv.loc[t].sum())
    combo = float(e3[e3['月'] == t]['combo_phase'].iloc[0])
    res.append({'月': t, '实际': act, 'lgbm': lgbm_sum, 'combo': combo,
                'blend': 0.5 * lgbm_sum + 0.5 * combo})

r = pd.DataFrame(res)
def wape(c, sub=None):
    d = r if sub is None else r[r['月'].str.startswith(sub)]
    return (d[c] - d['实际']).abs().sum() / d['实际'].sum()

print()
print('=== E9 LightGBM vs 基线（%d 折）===' % len(r))
print('%-10s %9s %9s' % ('变体', '全期WAPE', '2026WAPE'))
for c in ['combo', 'lgbm', 'blend']:
    print('%-10s %8.1f%% %8.1f%%' % (c, wape(c)*100, wape(c, '2026')*100))
print('（对照 ma6 全期 10.3% / 2026 12.4%）')

print()
print('=== 2026 逐月 APE ===')
hdr = '%-9s %12s %12s %12s' % ('月份', 'combo', 'lgbm', 'blend')
print(hdr)
for m in sorted([x for x in r['月'].unique() if x >= '2026-01']):
    d = r[r['月'] == m]
    line = '%-9s' % m
    for c in ['combo', 'lgbm', 'blend']:
        line += ' %11.1f%%' % (((d[c] - d['实际']).abs() / d['实际']).iloc[0] * 100)
    print(line)

r.to_csv(OUT + r'\E9_LightGBM_对比.csv', index=False, encoding='utf-8-sig')
print()
print('明细已存: E9_LightGBM_对比.csv')
