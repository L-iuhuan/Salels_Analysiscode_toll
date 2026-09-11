# -*- coding: utf-8 -*-
"""E8：概率区间预测（公司合计，冠军系统 combo_phase）
- 三法对比：经验比率分位 / Conformal(|err|分位) / 正态(±1.28σ)
- expanding 估计（仅用当折之前残差），评估覆盖率（目标80%）与区间宽度
- 输出 Sep-Dec 2026 与全年区间（独立/全相关两种）
"""
import sys
import numpy as np
import pandas as pd
sys.stdout.reconfigure(encoding='utf-8')

OUT = r'E:\3-其他资料\数据分析\project_analysis\月度滚动预测_20260910'
bt = pd.read_csv(OUT + r'\E3_节前月加成_对比.csv')
bt = bt[['月', '实际', 'combo_phase']].dropna().reset_index(drop=True)
bt['ratio'] = bt['实际'] / bt['combo_phase']
bt['absratio'] = (bt['实际'] - bt['combo_phase']).abs() / bt['combo_phase']

cover = {'emp': [], 'conformal': [], 'normal': []}
width = {'emp': [], 'conformal': [], 'normal': []}
for i in range(len(bt)):
    if i < 6:
        continue
    row = bt.iloc[i]
    hist = bt.iloc[:i]
    pred, act = row['combo_phase'], row['实际']
    q10, q90 = np.percentile(hist['ratio'], [10, 90])
    lo, hi = pred * q10, pred * q90
    cover['emp'].append(lo <= act <= hi); width['emp'].append((hi - lo) / pred)
    q80 = np.percentile(hist['absratio'], 80)
    lo2, hi2 = pred * (1 - q80), pred * (1 + q80)
    cover['conformal'].append(lo2 <= act <= hi2); width['conformal'].append((hi2 - lo2) / pred)
    mu, sd = hist['ratio'].mean(), hist['ratio'].std()
    lo3, hi3 = pred * (mu - 1.2816 * sd), pred * (mu + 1.2816 * sd)
    cover['normal'].append(lo3 <= act <= hi3); width['normal'].append((hi3 - lo3) / pred)

n = len(cover['emp'])
print('=== E8 区间法对比（expanding 估计，%d 折）===' % n)
print('%-10s %10s %14s' % ('方法', '覆盖率', '平均宽度(相对)'))
for k in ['emp', 'conformal', 'normal']:
    print('%-10s %9.0f%% %13.1f%%' % (k, np.mean(cover[k])*100, np.mean(width[k])*100))
print('（目标覆盖率 80%%；每折≈%.1fpp 粒度）' % (100/n))

# Sep-Dec 2026 区间（冠军系统对非春节月=ma6，点值与直接法一致）
fc = np.array([7311.7, 7467.9, 7289.9, 7350.2]) * 1e4
F = fc.sum()
q10, q90 = np.percentile(bt['ratio'], [10, 90])
mu, sd = bt['ratio'].mean(), bt['ratio'].std()
q80 = np.percentile(bt['absratio'], 80)

rng = np.random.default_rng(42)
sims_ind = np.array([sum(fc[j] * rng.choice(bt['ratio'].values) for j in range(4)) for _ in range(4000)])
sims_cor = np.array([F * rng.choice(bt['ratio'].values) for _ in range(4000)])
print()
print('=== 2026 9-12月区间（点值 %.1f万）===' % (F/1e4))
print('经验比率法(全相关): [%.1f, %.1f]万' % (F*q10/1e4, F*q90/1e4))
print('独立抽样: [%.1f, %.1f]万' % (np.percentile(sims_ind, 10)/1e4, np.percentile(sims_ind, 90)/1e4))
print('Conformal(±%.1f%%): [%.1f, %.1f]万' % (q80*100, F*(1-q80)/1e4, F*(1+q80)/1e4))

ytd = 57742.8e4
print()
print('=== 2026 全年区间（1-8月实际 %.1f万 + 9-12月）===' % (ytd/1e4))
print('经验法全相关: [%.1f, %.1f]万 ([%.2f, %.2f]亿)' % ((ytd+F*q10)/1e4, (ytd+F*q90)/1e4, (ytd+F*q10)/1e8, (ytd+F*q90)/1e8))
print('独立抽样: [%.1f, %.1f]万 ([%.2f, %.2f]亿)' % ((ytd+np.percentile(sims_ind,10))/1e4, (ytd+np.percentile(sims_ind,90))/1e4, (ytd+np.percentile(sims_ind,10))/1e8, (ytd+np.percentile(sims_ind,90))/1e8))

res = pd.DataFrame([
    {'方法': 'emp', '覆盖率': np.mean(cover['emp']), '平均宽度': np.mean(width['emp'])},
    {'方法': 'conformal', '覆盖率': np.mean(cover['conformal']), '平均宽度': np.mean(width['conformal'])},
    {'方法': 'normal', '覆盖率': np.mean(cover['normal']), '平均宽度': np.mean(width['normal'])},
])
res.to_csv(OUT + r'\E8_概率区间_对比.csv', index=False, encoding='utf-8-sig')
print()
print('明细已存: E8_概率区间_对比.csv')
