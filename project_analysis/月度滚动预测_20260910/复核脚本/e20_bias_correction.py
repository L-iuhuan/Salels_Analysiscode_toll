# -*- coding: utf-8 -*-
"""E20：增长校正实验——消除冠军（combo_volxasp）的系统性低估
四种 expanding 因子（只用更早折，clip[0.9,1.2]）：
  V1 均值因子 / V2 中位因子 / V3 收缩因子(0.5) / V4 滚动6折均值
评估段 = 折7-20（14 折，因子从第 7 折起可用）；含链路联动（线级/SKU）与前向影响。
"""
import sys
import numpy as np
import pandas as pd
sys.stdout.reconfigure(encoding='utf-8')

OUT = r'E:\3-其他资料\数据分析\project_analysis\月度滚动预测_20260910'

e12 = pd.read_csv(OUT + r'\E12b_量价集成_对比.csv')
e3 = pd.read_csv(OUT + r'\E3_节前月加成_对比.csv')
bt = e12[['月', '实际', 'combo_volxasp']].merge(e3[['月', 'ma6']], on='月').reset_index(drop=True)
bt['ratio'] = bt['实际'] / bt['combo_volxasp']

f1, f2, f3, f4 = [], [], [], []
for i in range(len(bt)):
    if i < 6:
        f1.append(1.0); f2.append(1.0); f3.append(1.0); f4.append(1.0)
        continue
    prior = bt.loc[:i-1, 'ratio']
    m1, m2, m4 = float(prior.mean()), float(prior.median()), float(prior.iloc[-6:].mean())
    f1.append(min(max(m1, 0.9), 1.2))
    f2.append(min(max(m2, 0.9), 1.2))
    f3.append(min(max(1 + 0.5*(m1-1), 0.9), 1.2))
    f4.append(min(max(m4, 0.9), 1.2))
bt['f1'], bt['f2'], bt['f3'], bt['f4'] = f1, f2, f3, f4
for v in ['1', '2', '3', '4']:
    bt['V' + v] = bt['combo_volxasp'] * bt['f' + v]

def wape(d, c):
    return (d[c] - d['实际']).abs().sum() / d['实际'].sum()
def bias(d, c):
    return (d[c] - d['实际']).sum() / d['实际'].sum()

seg = bt[bt.index >= 6]
print('=== E20 增长校正（评估段：折7-20 共 14 折）===')
print('%-22s %8s %8s' % ('方案', 'WAPE', 'Bias'))
print('%-22s %7.1f%% %+7.1f%%' % ('冠军（未校正）', wape(seg, 'combo_volxasp')*100, bias(seg, 'combo_volxasp')*100))
for v, name in [('V1', 'V1 均值因子'), ('V2', 'V2 中位因子'), ('V3', 'V3 收缩因子0.5'), ('V4', 'V4 滚动6折')]:
    print('%-22s %7.1f%% %+7.1f%%' % (name, wape(seg, v)*100, bias(seg, v)*100))

s26 = seg[seg['月'] >= '2026-01']
print()
print('2026 段（%d 折）:' % len(s26))
print('%-22s %7.1f%% %+7.1f%%' % ('冠军（未校正）', wape(s26, 'combo_volxasp')*100, bias(s26, 'combo_volxasp')*100))
for v, name in [('V1', 'V1 均值因子'), ('V2', 'V2 中位因子'), ('V3', 'V3 收缩因子0.5'), ('V4', 'V4 滚动6折')]:
    print('%-22s %7.1f%% %+7.1f%%' % (name, wape(s26, v)*100, bias(s26, v)*100))

print()
print('因子路径（折7起）:')
for _, r in seg.iterrows():
    print('%s f1 %.3f | f2 %.3f | f4 %.3f' % (r['月'], r['f1'], r['f2'], r['f4']))

# ---------- 链路联动（线级/SKU，用 f1 缩放）----------
ln = pd.read_csv(OUT + r'\融合测试_线级.csv')
sk = pd.read_csv(OUT + r'\融合测试_SKU级.csv')
fmap = dict(zip(bt['月'], bt['f1']))
ln['f'] = ln['月'].map(fmap)
ln['scaled_corr'] = ln['scaled'] * ln['f']
sk['f'] = sk['月'].map(fmap)
sk['alloc_corr'] = sk['alloc'] * sk['f']
m = ln['月'] >= '2025-07'
ms = sk['月'] >= '2025-07'
print()
print('=== 链路联动（折7-20，f1 缩放）===')
print('线级 scaled: WAPE %.1f%% → 校正后 %.1f%%' % (wape(ln[m], 'scaled')*100, wape(ln[m], 'scaled_corr')*100))
print('SKU alloc:  WAPE %.1f%% → 校正后 %.1f%%' % (wape(sk[ms], 'alloc')*100, wape(sk[ms], 'alloc_corr')*100))

# ---------- 前向影响（9-12月/全年）----------
f_last = float(bt['f1'].iloc[-1])
sd = 29419.6e4 * f_last
ytd = 57742.8e4
print()
print('=== 前向影响（9-12月；因子=%.3f）===' % f_last)
print('9-12月: 未校正 29,419.6万 → 校正后 %.1f万' % (sd/1e4))
print('全年: 87,162.5万（8.72亿）→ %.1f万（%.2f亿）' % ((ytd+sd)/1e4, (ytd+sd)/1e8))

bt.to_csv(OUT + r'\E20_增长校正_对比.csv', index=False, encoding='utf-8-sig')
print()
print('明细已存: E20_增长校正_对比.csv')
