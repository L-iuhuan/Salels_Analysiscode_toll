# -*- coding: utf-8 -*-
"""E5：间歇性需求方法（Croston/SBA/TSB）对稀疏产品线
- 目标：C 档稀疏线（dTOF/MLED/电源模组/车规有刷H桥/无刷直流/电机驱动）
- walk-forward 2025-01~2026-08；对照 ma6
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

def croston(y, alpha=0.1, variant='classic'):
    y = np.asarray(y, dtype=float)
    z = None; p = None; last = 0
    for i, v in enumerate(y):
        if v > 0:
            if z is None:
                z = v; p = max(i - last, 1); last = i
            else:
                z = alpha * v + (1 - alpha) * z
                p = alpha * (i - last) + (1 - alpha) * p
                last = i
    if z is None or p is None:
        return 0.0
    f = z / max(p, 1e-9)
    if variant == 'sba':
        f *= 0.95
    return f

def tsb(y, alpha=0.1, beta=0.1):
    y = np.asarray(y, dtype=float)
    p = None; z = None
    for v in y:
        if p is None:
            p = 1.0 if v > 0 else 0.0
            z = v if v > 0 else 0.0
        else:
            p = alpha * (1.0 if v > 0 else 0.0) + (1 - alpha) * p
            if v > 0:
                z = beta * v + (1 - beta) * z
    if p is None or z is None:
        return 0.0
    return p * z

def ma6(y):
    y = np.asarray(y, dtype=float)
    return float(y[-6:].mean()) if len(y) >= 6 else float(y.mean())

C_LINES = ['dTOF模组', '新显示MLED驱动', '电源模组', '车规有刷H桥栅驱', '无刷直流电机驱动', '电机驱动']
C_LINES = [c for c in C_LINES if c in pv.columns]

targets = [m for m in months if '2025-01' <= m <= '2026-08']
rows = []
for line in C_LINES:
    v = pv[line].values.astype(float)
    for t in targets:
        i = months.index(t)
        h = v[:i]
        act = float(v[i])
        rows.append({'产品线': line, '月': t, '实际': act,
                     'ma6': ma6(h), 'croston': croston(h, 0.1, 'classic'),
                     'sba': croston(h, 0.1, 'sba'), 'tsb': tsb(h, 0.1, 0.1)})
r = pd.DataFrame(rows)

print('=== E5 间歇性方法（C 档线，%d 折）===' % len(targets))
print('%-14s %8s %8s %8s %8s' % ('产品线', 'ma6', 'Croston', 'SBA', 'TSB'))
for line, g in r.groupby('产品线'):
    row = [line]
    for c in ['ma6', 'croston', 'sba', 'tsb']:
        row.append((g[c] - g['实际']).abs().sum() / max(g['实际'].sum(), 1e-9))
    print('%-14s %7.1f%% %7.1f%% %7.1f%% %7.1f%%' % (row[0], row[1]*100, row[2]*100, row[3]*100, row[4]*100))

print()
print('=== 全体（6线合并）WAPE ===')
for c in ['ma6', 'croston', 'sba', 'tsb']:
    w = (r[c] - r['实际']).abs().sum() / max(r['实际'].sum(), 1e-9)
    print('%-10s %6.1f%%' % (c, w*100))

r.to_csv(OUT + r'\E5_间歇性方法_对比.csv', index=False, encoding='utf-8-sig')
print()
print('明细已存: E5_间歇性方法_对比.csv')
