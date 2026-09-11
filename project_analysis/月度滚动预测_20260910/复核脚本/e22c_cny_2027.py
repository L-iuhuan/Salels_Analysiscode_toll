# -*- coding: utf-8 -*-
"""E22c 春节规则标定（金额口径长序列，n=6）+ 2027-01/02 重估
分桶：除夕1月→低谷在1月；除夕2月→低谷在2月、1月为节前冲量月。
2027 春节：正月初一 2027-02-06（周六），除夕 2/5，假期预计 2/5-2/11 → 低谷月=2027-02，节前月=2027-01。
"""
import sys
import numpy as np
import pandas as pd
sys.stdout.reconfigure(encoding='utf-8')

WH = r'E:\3-其他资料\数据分析\sales_analytics_platform\data_warehouse\历史总表_202001_202605'
df = pd.read_parquet(WH + r'\company_monthly_rmb_202001_202608.parquet')
ts = pd.Series(df['金额'].values, index=df['月']).sort_index() / 1e4  # 万元

# 除夕日期（正月初一前一天）
cny_eve = {'2021': '02-11', '2022': '01-31', '2023': '01-21', '2024': '02-09', '2025': '01-28', '2026': '02-16', '2027': '02-05'}

print('=== 春节分桶标定（金额口径，万元）===')
buckets = {'1月低谷': [], '2月低谷': []}
pre_month_ratio = []  # 节前月/前月
for y, eve in cny_eve.items():
    if y == '2027':
        continue
    em = int(eve[:2])
    yy = int(y)
    if em == 1:
        low_m = '%s-01' % y
        pre_m = '%d-12' % (yy-1)
    else:
        low_m = '%s-02' % y
        pre_m = '%s-01' % y
    prev_of_pre = str(pd.Period(pre_m, freq='M') - 1)
    low_prev = str(pd.Period(low_m, freq='M') - 1)
    r_low = ts[low_m] / ts[low_prev]
    r_pre = ts[pre_m] / ts[prev_of_pre] if pre_m != low_m else np.nan
    buckets['1月低谷' if em == 1 else '2月低谷'].append(r_low)
    pre_month_ratio.append((pre_m, r_pre))
    print('%s 除夕%s: 低谷月 %s = %.0f万 (前月 %.0f, 比值 %.2f) | 节前月 %s 比值 %.2f' % (
        y, eve, low_m, ts[low_m], ts[low_prev], r_low, pre_m, r_pre))

print()
for k, v in buckets.items():
    print('%s桶: 比值 %s → 中位 %.2f' % (k, ['%.2f' % x for x in v], np.median(v)))
print('节前月冲量系数: %s → 中位 %.2f' % (['%.2f' % r for _, r in pre_month_ratio], np.median([r for _, r in pre_month_ratio])))

# === 2027-01/02 重估 ===
print('\n=== 2027-01/02 重估 ===')
# 近期增长：近12月(2025-09~2026-08) vs 前12月(2024-09~2025-08)
g = ts.loc['2025-09':'2026-08'].sum() / ts.loc['2024-09':'2025-08'].sum()
print('trailing YoY (2025-09~2026-08 / 2024-09~2025-08): %.3f' % g)
g2 = ts.loc['2026-01':'2026-08'].sum() / ts.loc['2025-01':'2025-08'].sum()
print('2026 前8月 YoY: %.3f' % g2)

# 方法A：2026-01 × YoY（现行报告口径）
a_2027_01 = ts['2026-01'] * g
print('A: 2027-01 = 2026-01(%.0f) × %.3f = %.0f万' % (ts['2026-01'], g, a_2027_01))

# 方法B：节前月冲量——2026-12 预测 × 冲量系数
# 2026-12 预测：用现行 ma6 递归链中的值（交付报告口径 6836×?）——重算：近6月(2026-03~08)均值
ma6_dec = ts.loc['2026-03':'2026-08'].mean()
pre_coef = np.median([r for _, r in pre_month_ratio])
b_2027_01 = ma6_dec * pre_coef
print('B: 2027-01 = 2026-12估(ma6=%.0f) × 冲量系数%.2f = %.0f万' % (ma6_dec, pre_coef, b_2027_01))

# 方法C：2024-01 同相位（同为2月上旬春节的节前月）× 三年复合增长
cagr = (ts.loc['2026-01'] / ts.loc['2024-01']) ** 0.5  # 2024-01→2026-01 两年
c_2027_01 = ts['2024-01'] * cagr ** 3
print('C: 2027-01 = 2024-01(%.0f) × (2年增速%.3f)^3 = %.0f万' % (ts['2024-01'], cagr, c_2027_01))

# 2027-02：低谷月 = 2027-01 × 2月桶中位
low_coef_2 = np.median(buckets['2月低谷'])
for tag, v01 in [('A', a_2027_01), ('B', b_2027_01), ('C', c_2027_01)]:
    print('方法%s → 2027-02 = %.0f × %.2f = %.0f万' % (tag, v01, low_coef_2, v01 * low_coef_2))

# 对照：2月春节年节前月绝对额 vs 当年月均（检验 2027-01 合理带）
print('\n=== 2月春节年的 1月（节前月）绝对额与当年月均之比 ===')
for y in ['2021', '2022', '2024', '2026']:
    jan = ts['%s-01' % y]
    yavg = ts.loc['%s-01' % y:'%s-12' % y].mean()
    print('%s-01: %.0f万, 当年月均 %.0f万, 比值 %.2f' % (y, jan, yavg, jan/yavg))
