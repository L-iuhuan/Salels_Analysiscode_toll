# -*- coding: utf-8 -*-
"""E3b：春节月最终组合（Jan=相位法优先 / Feb=工作日法）+ statsforecast 可用性检查"""
import sys
import numpy as np
import pandas as pd
sys.stdout.reconfigure(encoding='utf-8')

OUT = r'E:\3-其他资料\数据分析\project_analysis\月度滚动预测_20260910'
bt = pd.read_csv(OUT + r'\E3_节前月加成_对比.csv')

def combo_phase(r):
    m = r['月'][5:7]
    if m == '01':
        return r['wd3'] if pd.isna(r['phase']) else r['phase']
    if m == '02':
        return r['wd3']
    return r['ma6']

def combo_blend(r):
    m = r['月'][5:7]
    if m == '01':
        return r['wd3'] if pd.isna(r['phase']) else (r['phase'] + r['wd3']) / 2
    if m == '02':
        return r['wd3']
    return r['ma6']

bt['combo_phase'] = bt.apply(combo_phase, axis=1)
bt['combo_blend'] = bt.apply(combo_blend, axis=1)

def wape(c, sub=None):
    d = bt if sub is None else bt[bt['月'].str.startswith(sub)]
    return (d[c] - d['实际']).abs().sum() / d['实际'].sum()

def ape_m(c, m):
    d = bt[bt['月'] == m]
    return float(((d[c] - d['实际']).abs() / d['实际']).iloc[0])

print('=== E3b 最终组合对比 ===')
print('%-12s %9s %9s %9s %9s %9s %9s' % ('变体', '全期WAPE', '2026WAPE', '25-01', '25-02', '26-01', '26-02'))
for c in ['ma6', 'mix_wd3', 'combo_phase', 'combo_blend']:
    print('%-12s %8.1f%% %8.1f%% %8.1f%% %8.1f%% %8.1f%% %8.1f%%' % (
        c, wape(c)*100, wape(c, '2026')*100,
        ape_m(c, '2025-01')*100, ape_m(c, '2025-02')*100, ape_m(c, '2026-01')*100, ape_m(c, '2026-02')*100))

# 逐月 2026
print()
print('=== 2026 逐月 APE ===')
KEY = ['ma6', 'mix_wd3', 'combo_phase', 'combo_blend']
hdr = '%-9s' % '月份'
for c in KEY:
    hdr += ' %10s' % c
print(hdr)
for m in sorted([x for x in bt['月'].unique() if x >= '2026-01']):
    line = '%-9s' % m
    for c in KEY:
        line += ' %9.1f%%' % (ape_m(c, m)*100)
    print(line)

bt.to_csv(OUT + r'\E3_节前月加成_对比.csv', index=False, encoding='utf-8-sig')
print()
print('E3b 结果已更新至 E3_节前月加成_对比.csv')

# statsforecast 可用性
print()
try:
    import statsforecast
    print('statsforecast 版本:', statsforecast.__version__)
    from statsforecast import models as sfm
    avail = [n for n in ['AutoETS', 'AutoARIMA', 'AutoTheta', 'Theta', 'SeasonalNaive', 'CrostonSBA', 'TSB', 'ADIDA'] if hasattr(sfm, n)]
    print('可用模型:', avail)
except Exception as e:
    print('statsforecast 不可用:', e)
