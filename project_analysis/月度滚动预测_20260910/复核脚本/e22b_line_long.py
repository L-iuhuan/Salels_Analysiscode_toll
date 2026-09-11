# -*- coding: utf-8 -*-
"""E22b 线级长历史检验：长窗(56折) vs 短窗(20折)选优差异 + 线级方法长窗排名
验证：长历史是否改变线级选优结果；长窗选优是否在 2025-01~2026-08 上更稳。
口径：金额（RMB未税），线级月度，expanding 无前视。
"""
import sys
import numpy as np
import pandas as pd
sys.stdout.reconfigure(encoding='utf-8')

WH = r'E:\3-其他资料\数据分析\sales_analytics_platform\data_warehouse\历史总表_202001_202605'
df = pd.read_parquet(WH + r'\line_monthly_rmb_202001_202608.parquet')
pv = df.pivot_table(index='月', columns='产品线', values='金额', aggfunc='sum', fill_value=0.0).sort_index()
months = list(pv.index)
# 只保留近12个月有出货的线（活跃线，与生产口径一致）
recent = pv.loc['2025-09':'2026-08'].sum()
active = list(recent[recent > 0].index)
pv = pv[active]
print('活跃线: %d 条' % len(active))

METHODS = ['naive', 'ma3', 'ma6', 'ma12', 'snaive', 'yoy_adj', 'trend6', 'trend12']

def predict(v, method):
    n = len(v)
    v = np.asarray(v, dtype=float)
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

def wape_line(v, method, targets):
    errs = acts = 0.0
    for t in targets:
        i = months.index(t)
        if i < 12:
            continue
        p = predict(v[:i], method)
        errs += abs(p - v[i]); acts += v[i]
    return errs / acts if acts > 0 else np.inf

WIN_LONG = [m for m in months if '2022-01' <= m <= '2026-08']
WIN_EVAL = [m for m in months if '2025-01' <= m <= '2026-08']  # 短窗=生产现行选优窗
WIN_EVAL2 = [m for m in months if '2022-01' <= m <= '2024-12']  # 纯历史段

rows = []
for line in active:
    v = pv[line].values.astype(float)
    # 短窗选优（现行生产逻辑）
    sc_short = {m: wape_line(v, m, WIN_EVAL) for m in METHODS}
    best_short = min(sc_short, key=lambda m: (sc_short[m], METHODS.index(m)))
    # 长窗选优（56折）
    sc_long = {m: wape_line(v, m, WIN_LONG) for m in METHODS}
    best_long = min(sc_long, key=lambda m: (sc_long[m], METHODS.index(m)))
    # 两选优在"全历史段 2022-2024"与"近期 2025-2026"的交叉表现
    rows.append({
        '产品线': line, '规模万': v[-12:].sum()/1e4,
        '短窗选优': best_short, '长窗选优': best_long,
        '长窗WAPE_短优': sc_long[best_short], '长窗WAPE_长优': sc_long[best_long],
        '近期WAPE_短优': sc_short[best_short], '近期WAPE_长优': sc_short[best_long],
    })
r = pd.DataFrame(rows).sort_values('规模万', ascending=False)
pd.set_option('display.width', 220)
print(r.to_string(index=False, float_format=lambda x: '%.1f' % x))
same = (r['短窗选优'] == r['长窗选优']).sum()
print('\n选优一致: %d/%d 线' % (same, len(r)))
# 金额加权：长窗选优是否在长验证窗上更好（废话，肯定），关键看近期窗上长优 vs 短优
w = r['规模万'].values
long_better = (r['近期WAPE_长优'] < r['近期WAPE_短优'])
print('近期窗(2025-01~2026-08)上 长窗选优更准的线: %d/%d；金额加权 WAPE 差: %+.2f pp' % (
    long_better.sum(), len(r),
    np.average(r['近期WAPE_长优'] - r['近期WAPE_短优'], weights=w)*100))

# 线级方法总排名（长窗，金额加权）
print('\n=== 线级方法长窗排名（金额加权 WAPE）===')
agg = {}
for m in METHODS:
    vals = []
    for line in active:
        vals.append(wape_line(pv[line].values.astype(float), m, WIN_LONG))
    agg[m] = np.average(vals, weights=w)
for m in sorted(agg, key=agg.get):
    print('%-10s %.1f%%' % (m, agg[m]*100))
