# -*- coding: utf-8 -*-
"""E10：外部领先指标（中国制造业PMI）lead-lag 检验 + 增量价值测试
E11：FVA 阶梯（预测增值分析）
"""
import sys
import numpy as np
import pandas as pd
sys.stdout.reconfigure(encoding='utf-8')

SILVER = r'E:\3-其他资料\数据分析\sales_analytics_platform\output\silver\silver_cleaned_rows.parquet'
OUT = r'E:\3-其他资料\数据分析\project_analysis\月度滚动预测_20260910'

# ---------- 数据 ----------
df = pd.read_parquet(SILVER, columns=['发货日期', '金额'])
df['月'] = pd.to_datetime(df['发货日期'], errors='coerce').dt.strftime('%Y-%m')
df = df.dropna(subset=['月'])
df['金额'] = pd.to_numeric(df['金额'], errors='coerce').fillna(0)
ts = df.groupby('月')['金额'].sum().sort_index()
months = list(ts.index)
rev = ts.values

PMI = {
'2024-01':49.2,'2024-02':49.1,'2024-03':50.8,'2024-04':50.4,'2024-05':49.5,'2024-06':49.5,
'2024-07':49.4,'2024-08':49.1,'2024-09':49.8,'2024-10':50.1,'2024-11':50.3,'2024-12':50.1,
'2025-01':49.1,'2025-02':50.2,'2025-03':50.5,'2025-04':49.0,'2025-05':49.5,'2025-06':49.7,
'2025-07':49.3,'2025-08':49.4,'2025-09':49.8,'2025-10':49.0,'2025-11':49.2,'2025-12':50.1,
'2026-01':49.3,'2026-02':49.0,'2026-03':50.4,'2026-04':50.3,'2026-05':50.0,'2026-06':50.3,
'2026-07':49.2,'2026-08':49.8}
print('PMI 覆盖: %d/%d 月' % (sum(1 for m in months if m in PMI), len(months)))

# ---------- E10.1 lead-lag 相关 ----------
print()
print('=== E10.1a PMI[t-k] vs 收入水平（n=32）===')
for k in range(0, 7):
    xs, ys = [], []
    for i in range(len(months)):
        if i - k < 0 or months[i] not in PMI or months[i-k] not in PMI:
            continue
        xs.append(PMI[months[i-k]]); ys.append(rev[i])
    r = np.corrcoef(xs, ys)[0, 1] if len(xs) > 3 else np.nan
    print('k=%d: r=%+.2f (n=%d)' % (k, r, len(xs)))

print()
print('=== E10.1b PMI[t-k] vs 收入同比增速（n≈20）===')
for k in range(0, 7):
    xs, ys = [], []
    for i in range(12, len(months)):
        if months[i] not in PMI or months[i-k] not in PMI:
            continue
        xs.append(PMI[months[i-k]]); ys.append(rev[i]/rev[i-12]-1)
    r = np.corrcoef(xs, ys)[0, 1] if len(xs) > 3 else np.nan
    print('k=%d: r=%+.2f (n=%d)' % (k, r, len(xs)))

# ---------- E10.2 增量价值 ----------
print()
print('=== E10.2 PMI 比率修正（expanding OLS，clip[0.7,1.3]）===')
def ma6_at(i):
    return float(rev[max(0, i-6):i].mean()) if i >= 6 else float(rev[:i].mean())

res = []
for i in range(len(months)):
    if months[i] < '2025-01':
        continue
    res.append({'月': months[i], 'base': ma6_at(i), '实际': rev[i]})
r10 = pd.DataFrame(res).reset_index(drop=True)

for k in [1, 2, 3]:
    preds = []
    for j in range(len(r10)):
        train = r10.iloc[:j]
        xs, ys = [], []
        for _, row in train.iterrows():
            tj = months.index(row['月'])
            if tj - k < 0 or months[tj-k] not in PMI:
                continue
            xs.append(PMI[months[tj-k]] - 50.0)
            ys.append(row['实际'] / row['base'])
        ti = months.index(r10.iloc[j]['月'])
        if len(xs) < 6:
            preds.append(r10.iloc[j]['base']); continue
        A = np.vstack([np.ones(len(xs)), np.array(xs)]).T
        coef, *_ = np.linalg.lstsq(A, np.array(ys), rcond=None)
        sig = (PMI[months[ti-k]] - 50.0) if (ti-k >= 0 and months[ti-k] in PMI) else 0.0
        ratio = min(max(coef[0] + coef[1]*sig, 0.7), 1.3)
        preds.append(r10.iloc[j]['base'] * ratio)
    r10['pmi_k%d' % k] = preds

def w(c):
    return (r10[c] - r10['实际']).abs().sum() / r10['实际'].sum()
print('基线 ma6:          %.1f%%' % (w('base')*100))
for k in [1, 2, 3]:
    print('PMI 修正(k=%d):     %.1f%%' % (k, w('pmi_k%d' % k)*100))

# ---------- E11 FVA 阶梯 ----------
print()
print('=== E11 FVA 阶梯（预测增值分析）===')
mc = pd.read_csv(OUT + r'\全公司方法对比.csv')
naive_w = float(mc[mc['方法'] == 'naive']['全期WAPE'].iloc[0])
ma6_w = float(mc[mc['方法'] == 'ma6']['全期WAPE'].iloc[0])
e3 = pd.read_csv(OUT + r'\E3_节前月加成_对比.csv').dropna(subset=['combo_phase'])
combo_w = (e3['combo_phase'] - e3['实际']).abs().sum() / e3['实际'].sum()
print('L0 naive（持续性）: %.1f%%' % (naive_w*100))
print('L1 ma6:            %.1f%%  FVA %+.1fpp' % (ma6_w*100, (naive_w-ma6_w)*100))
print('L2 combo_phase:    %.1f%%  FVA %+.1fpp' % (combo_w*100, (ma6_w-combo_w)*100))
print('L3 +锚定缩放:      公司不变；线级 43.7%%→42.7%%（15/18 线改善）')
print('L4 +区间口径:      Conformal 覆盖 79%%（目标 80%%）')

r10.to_csv(OUT + r'\E10_PMI领先指标_对比.csv', index=False, encoding='utf-8-sig')
print()
print('明细已存: E10_PMI领先指标_对比.csv')
