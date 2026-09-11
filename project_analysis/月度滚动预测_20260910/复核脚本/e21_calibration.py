# -*- coding: utf-8 -*-
"""E21：校准方法扩展测试（公司口径 A-E + 线级 F）——全部 expanding（只用更早折）
A 截尾均值因子(10%) / B EWMA因子(h=6) / C WAPE网格最优因子 / D 冠军×trend12混合 / E 残差AR(1)
F 线级分线中位因子（raw→raw_cal→重锚定）
参考：E20-V2 中位因子。段 = 折7-20（14 折）。
"""
import sys
import numpy as np
import pandas as pd
sys.stdout.reconfigure(encoding='utf-8')

OUT = r'E:\3-其他资料\数据分析\project_analysis\月度滚动预测_20260910'

e12 = pd.read_csv(OUT + r'\E12b_量价集成_对比.csv')
e3 = pd.read_csv(OUT + r'\E3_节前月加成_对比.csv')
bt = e12[['月', '实际', 'combo_volxasp']].merge(e3[['月', 'ma6']], on='月').reset_index(drop=True)
det = pd.read_csv(OUT + r'\月度滚动回测明细.csv')
bt['trend12'] = bt['月'].map(det[det['方法'] == 'trend12'].groupby('月')['预测'].sum())
bt['ratio'] = bt['实际'] / bt['combo_volxasp']
bt['resid'] = bt['实际'] - bt['combo_volxasp']

def wape(d, c):
    return (d[c] - d['实际']).abs().sum() / d['实际'].sum()
def bias(d, c):
    return (d[c] - d['实际']).sum() / d['实际'].sum()

fA, fB, fC, corrE = [], [], [], []
for i in range(len(bt)):
    if i < 6:
        fA.append(np.nan); fB.append(np.nan); fC.append(np.nan); corrE.append(np.nan)
        continue
    prior = bt.loc[:i-1, 'ratio'].values
    s = np.sort(prior); k = max(1, int(len(s)*0.1))
    s2 = s[k:-k] if len(s) > 2*k else s
    fA.append(min(max(s2.mean(), 0.9), 1.2))
    w = 0.5 ** (np.arange(len(prior))[::-1] / 6.0)
    fB.append(min(max((prior*w).sum()/w.sum(), 0.9), 1.2))
    ps, as_ = bt.loc[:i-1, 'combo_volxasp'].values, bt.loc[:i-1, '实际'].values
    grid = np.arange(0.94, 1.101, 0.01)
    losses = [np.abs(g*ps - as_).sum() for g in grid]
    fC.append(float(grid[int(np.argmin(losses))]))
    r = bt.loc[:i-1, 'resid'].values
    rho = float(np.corrcoef(r[:-1], r[1:])[0, 1]) if (len(r) >= 4 and r.std() > 0) else 0.0
    rho = min(max(rho, -0.6), 0.6)
    corrE.append(float(np.clip(rho * bt.loc[i-1, 'resid'], -0.1*bt.loc[i, 'combo_volxasp'], 0.1*bt.loc[i, 'combo_volxasp'])))

bt['A'] = bt['combo_volxasp'] * fA
bt['B'] = bt['combo_volxasp'] * fB
bt['C'] = bt['combo_volxasp'] * fC
bt['D1'] = 0.9*bt['combo_volxasp'] + 0.1*bt['trend12']
bt['D2'] = 0.8*bt['combo_volxasp'] + 0.2*bt['trend12']
bt['E'] = bt['combo_volxasp'] + corrE
f2 = []
for i in range(len(bt)):
    f2.append(1.0 if i < 6 else min(max(float(np.median(bt.loc[:i-1, 'ratio'])), 0.9), 1.2))
bt['V2'] = bt['combo_volxasp'] * f2

seg = bt[bt.index >= 6]
print('=== E21 公司口径（折7-20，14 折）===')
for c, name in [('combo_volxasp', '冠军（未校正）'), ('V2', 'E20-V2 中位因子'), ('A', 'A 截尾均值10%'), ('B', 'B EWMA(h=6)'),
                ('C', 'C WAPE网格最优'), ('D1', 'D1 0.9冠军+0.1trend12'), ('D2', 'D2 0.8冠军+0.2trend12'), ('E', 'E 残差AR(1)')]:
    print('%-22s WAPE %5.1f%% | Bias %+5.1f%%' % (name, wape(seg, c)*100, bias(seg, c)*100))
s26 = seg[seg['月'] >= '2026-01']
print()
print('2026 段（%d 折）:' % len(s26))
for c, name in [('combo_volxasp', '冠军'), ('V2', 'E20-V2'), ('A', 'A'), ('B', 'B'), ('C', 'C'), ('D1', 'D1'), ('D2', 'D2'), ('E', 'E')]:
    print('%-10s WAPE %5.1f%% | Bias %+5.1f%%' % (name, wape(s26, c)*100, bias(s26, c)*100))

# ---------- F 线级分线校准 ----------
ln = pd.read_csv(OUT + r'\融合测试_线级.csv').sort_values(['产品线', '月']).reset_index(drop=True)
fmap = {}
for line, g in ln.groupby('产品线'):
    g = g.sort_values('月').reset_index(drop=True)
    facs = []
    for j in range(len(g)):
        if j < 6:
            facs.append(1.0); continue
        prior = (g.loc[:j-1, '实际'] / g.loc[:j-1, 'raw']).values
        facs.append(min(max(float(np.median(prior)), 0.85), 1.2))
    fmap[line] = dict(zip(g['月'], facs))
ln['fl'] = [fmap[l][m] for l, m in zip(ln['产品线'], ln['月'])]
ln['raw_cal'] = ln['raw'] * ln['fl']
anchor = dict(zip(bt['月'], bt['combo_volxasp']))
ln['anchor'] = ln['月'].map(anchor)
sc = ln.groupby('月')['raw_cal'].transform('sum')
ln['scaled_cal'] = ln['raw_cal'] * ln['anchor'] / sc.clip(lower=1e-9)
m = ln['月'] >= '2025-07'
print()
print('=== F 线级（折7-20）===')
print('raw %.1f%% → 分线校准 %.1f%% | 分线校准+重锚定 %.1f%% | 原锚定 scaled %.1f%%' % (
    wape(ln[m], 'raw')*100, wape(ln[m], 'raw_cal')*100, wape(ln[m], 'scaled_cal')*100, wape(ln[m], 'scaled')*100))

bt.to_csv(OUT + r'\E21_校准扩展_对比.csv', index=False, encoding='utf-8-sig')
print()
print('明细已存: E21_校准扩展_对比.csv')
