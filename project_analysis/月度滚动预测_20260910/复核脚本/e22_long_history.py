# -*- coding: utf-8 -*-
"""E22 长历史增益检验：80 个月长序列上的 walk-forward 方法重排
Q1: 56 折长验证窗下方法排名（冠军是否易主）
Q2: 季节指数法（长历史独有）表现
Q3: 数据驱动春节规则 vs 现行 phase 规则（6 个春节样本）
口径：金额（RMB未税），公司级月度。所有估计均 expanding 无前视。
"""
import sys
import numpy as np
import pandas as pd
from datetime import date, timedelta
import chinese_calendar as cc
sys.stdout.reconfigure(encoding='utf-8')

WH = r'E:\3-其他资料\数据分析\sales_analytics_platform\data_warehouse\历史总表_202001_202605'
df = pd.read_parquet(WH + r'\company_monthly_rmb_202001_202608.parquet')
ts = pd.Series(df['金额'].values, index=df['月']).sort_index()
months = list(ts.index)
V = ts.values.astype(float)

def workdays(y, m):
    d = date(y, m, 1); n = 0
    while d.month == m:
        if cc.is_workday(d):
            n += 1
        d += timedelta(days=1)
    return n

def si_est(hist, hist_months):
    """expanding 季节指数：每年12个月归一后的月比值，取各月 median。需>=24个月。"""
    if len(hist) < 24:
        return None
    d = pd.DataFrame({'月': hist_months, 'v': hist})
    d['y'] = d['月'].str[:4]; d['m'] = d['月'].str[5:7].astype(int)
    # 只用完整年（12个月）估计
    full_years = [y for y, g in d.groupby('y') if len(g) == 12]
    d = d[d['y'].isin(full_years)]
    if d['y'].nunique() < 2:
        return None
    yavg = d.groupby('y')['v'].transform('mean')
    d['si'] = d['v'] / yavg
    return d.groupby('m')['si'].median()

def predict(method, hist, hist_months, target):
    n = len(hist)
    v = np.asarray(hist, dtype=float)
    tm = int(target[5:7])
    if method == 'naive':
        return v[-1]
    if method.startswith('ma'):
        k = int(method[2:])
        return v[-k:].mean() if n >= k else v.mean()
    if method == 'snaive':
        return v[-12] if n >= 12 else v.mean()
    if method == 'yoy_adj':
        if n >= 24 and v[-24:-12].sum() > 1e5:
            return v[-12] * v[-12:].sum() / v[-24:-12].sum()
        return v[-12] if n >= 12 else v.mean()
    if method.startswith('trend'):
        k = int(method[5:])
        y = v[-k:]
        if len(y) >= 3 and y.std() > 0:
            sl, ic = np.polyfit(np.arange(len(y)), y, 1)
            return max(0.0, ic + sl * len(y))
        return y.mean()
    if method == 'si_l12':
        si = si_est(hist, hist_months)
        if si is None or n < 12:
            return v[-6:].mean() if n >= 6 else v.mean()
        last12_m = [int(mm[5:7]) for mm in hist_months[-12:]]
        si_norm = np.mean([si.get(mm, 1.0) for mm in last12_m])
        return v[-12:].mean() * si.get(tm, 1.0) / si_norm
    if method == 'combo_now':
        # 现行冠军：1月 phase 参照去年1月×trailingYoY；2月 wd3；其他 ma6
        if tm == 1:
            ly = str(int(target[:4])-1) + '-01'
            if ly in hist_months:
                g = v[-12:].sum() / max(v[-24:-12].sum(), 1.0) if n >= 24 else 1.0
                return v[hist_months.index(ly)] * g
            return v[-6:].mean()
        if tm == 2:
            wd = workdays(int(target[:4]), 2)
            wds = [workdays(int(mm[:4]), int(mm[5:7])) for mm in hist_months[-3:]]
            rate = v[-3:].sum() / max(sum(wds), 1)
            return rate * wd
        return v[-6:].mean() if n >= 6 else v.mean()
    raise ValueError(method)

METHODS = ['naive', 'ma3', 'ma6', 'ma12', 'snaive', 'yoy_adj', 'trend6', 'trend12', 'si_l12', 'combo_now']

def walkback(targets):
    rec = {m: [] for m in METHODS}
    act = []
    for t in targets:
        i = months.index(t)
        if i < 12:
            continue
        a = V[i]
        act.append((t, a))
        for m in METHODS:
            p = predict(m, list(V[:i]), months[:i], t)
            rec[m].append((t, p, a))
    return rec, act

def wape(rows):
    e = sum(abs(p-a) for _, p, a in rows); s = sum(a for _, _, a in rows)
    return e/s if s else np.nan

def bias(rows):
    e = sum(p-a for _, p, a in rows); s = sum(a for _, _, a in rows)
    return e/s if s else np.nan

# === Q1+Q2: 长验证窗 2022-01~2026-08（56折）===
win_long = [m for m in months if '2022-01' <= m <= '2026-08']
win_old = [m for m in months if '2024-01' <= m <= '2026-08']
rec, _ = walkback(win_long)
print('=== 方法排名：长验证窗 2022-01~2026-08（%d折）===' % len(rec['ma6']))
print('%-10s %8s %8s' % ('方法', 'WAPE', 'Bias'))
for m in sorted(METHODS, key=lambda m: wape(rec[m])):
    print('%-10s %8.1f%% %+7.1f%%' % (m, wape(rec[m])*100, bias(rec[m])*100))

rec2, _ = walkback(win_old)
print('\n=== 子窗 2024-01~2026-08（%d折，与旧实验可比）===' % len(rec2['ma6']))
print('%-10s %8s %8s' % ('方法', 'WAPE', 'Bias'))
for m in sorted(METHODS, key=lambda m: wape(rec2[m])):
    print('%-10s %8.1f%% %+7.1f%%' % (m, wape(rec2[m])*100, bias(rec2[m])*100))

# 分年 WAPE（长窗 top4 方法）
print('\n=== 分年 WAPE（长窗）===')
top = sorted(METHODS, key=lambda m: wape(rec[m]))[:5]
hdr = '%-10s' % '方法' + ''.join('%8s' % y for y in ['2022','2023','2024','2025','2026'])
print(hdr)
for m in top:
    line = '%-10s' % m
    for y in ['2022','2023','2024','2025','2026']:
        rows = [r for r in rec[m] if r[0].startswith(y)]
        line += '%8.1f' % (wape(rows)*100 if rows else float('nan'))
    print(line)

# === Q3: 春节月专项（6 样本：2021-02,2022-02,2023-01,2024-02,2025-01,2026-02）===
cny_targets = ['2021-02', '2022-02', '2023-01', '2024-02', '2025-01', '2026-02']
print('\n=== Q3 春节月预测误差（现行 combo_now 规则）===')
print('%-8s %10s %10s %8s' % ('月', '预测', '实际', '误差%'))
for t in cny_targets:
    i = months.index(t)
    p = predict('combo_now', list(V[:i]), months[:i], t)
    a = V[i]
    print('%-8s %10.0f %10.0f %+7.1f%%' % (t, p/1e4, a/1e4, (p-a)/a*100))

# 春节月/前月比值（供规则标定）
print('\n=== 春节月/前月 实际比值（规则标定用）===')
ratios = []
for t in cny_targets:
    i = months.index(t)
    r = V[i]/V[i-1]
    ratios.append(r)
    print('%s: %.2f' % (t, r))
print('中位: %.2f | 剔除2025-01后中位: %.2f' % (
    np.median(ratios), np.median([r for t, r in zip(cny_targets, ratios) if t != '2025-01'])))

# 春节月规则候选：prev × ratio_fixed(0.56) 回测
print('\n=== 候选规则回测：春节月 = 前月 × 0.56 ===')
for t in cny_targets:
    i = months.index(t)
    p = V[i-1] * 0.56
    a = V[i]
    print('%-8s 预测 %8.0f 实际 %8.0f 误差 %+7.1f%%' % (t, p/1e4, a/1e4, (p-a)/a*100))
