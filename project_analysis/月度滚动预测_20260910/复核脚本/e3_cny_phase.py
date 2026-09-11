# -*- coding: utf-8 -*-
"""E3 实验：节前月加成（春节相位对齐参照法）
- 目标：修复 1 月误差（2026-01 31.5%）与春节相关月
- 方法：按"春节相位"对齐参照月（pre/at/post 三种），参照月值 × 年化增长^年差
  - 2026-01 相位=pre（春节在2月）→ 参照 2024-01（同为 pre）
  - 2026-02 相位=at（春节在2月）→ 参照 2024-02（同为 at）
  - 无同相参照时回退 wd3（工作日法）
- 对照：ma6 / wd3 / phase / mix 组合
"""
import sys, calendar, datetime
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
ts = pv.sum(axis=1)
months = list(ts.index)

CNY_MONTH = {2024: 2, 2025: 1, 2026: 2}

def phase(year, month):
    c = CNY_MONTH.get(year)
    if month == 1:
        return 'pre' if c == 2 else 'at'
    if month == 2:
        return 'at' if c == 2 else 'post'
    return 'normal'

try:
    import chinese_calendar as cc
    def workdays(ym):
        y, m = int(ym[:4]), int(ym[5:7])
        n = 0
        for d in range(1, calendar.monthrange(y, m)[1] + 1):
            dt = datetime.date(y, m, d)
            try:
                ok = cc.is_workday(dt)
            except Exception:
                ok = dt.weekday() < 5
            if ok:
                n += 1
        return n
except Exception:
    def workdays(ym):
        y, m = int(ym[:4]), int(ym[5:7])
        return sum(1 for d in range(1, calendar.monthrange(y, m)[1] + 1) if datetime.date(y, m, d).weekday() < 5)
wd_map = {m: workdays(m) for m in months}

def ma(v, k=6):
    v = np.asarray(v, dtype=float)
    return v[-k:].mean() if len(v) >= k else v.mean()

def wd_pred(hv, hm, target, k=3):
    rev = sum(hv[-k:])
    wds = sum(wd_map[m] for m in hm[-k:])
    return rev / max(wds, 1) * wd_map[target]

def phase_pred(target):
    Y, m = int(target[:4]), int(target[5:7])
    ph = phase(Y, m)
    for Yp in range(Y - 1, 2023, -1):
        key = f'{Yp}-{m:02d}'
        if key in ts.index and phase(Yp, m) == ph:
            gap = Y - Yp
            idx = months.index(target)
            if idx >= 24:
                g_ann = ts.iloc[idx - 12:idx].sum() / max(ts.iloc[idx - 24:idx - 12].sum(), 1e-9)
            else:
                g_ann = 1.0
            return float(ts[key] * (g_ann ** gap)), key, gap, float(g_ann)
    return None, None, None, None

rows = []
for t in [m for m in months if '2025-01' <= m <= '2026-08']:
    idx = months.index(t)
    hv = list(ts.iloc[:idx].values)
    hm = list(ts.iloc[:idx].index)
    act = float(ts.iloc[idx])
    pp, ref, gap, g = phase_pred(t)
    rows.append({'月': t, '实际': act, 'ma6': ma(hv, 6), 'wd3': wd_pred(hv, hm, t, 3),
                 'phase': np.nan if pp is None else pp, 'ref': ref, 'gap': gap})
bt = pd.DataFrame(rows)

def pick_phase_or_wd(r):
    if r['月'][5:7] in ('01', '02'):
        return r['wd3'] if pd.isna(r['phase']) else r['phase']
    return r['ma6']

def pick_blend(r):
    if r['月'][5:7] in ('01', '02'):
        if pd.isna(r['phase']):
            return r['wd3']
        return (r['phase'] + r['wd3']) / 2
    return r['ma6']

bt['mix_phase'] = bt.apply(pick_phase_or_wd, axis=1)
bt['mix_wd3'] = [r['wd3'] if r['月'][5:7] in ('01', '02') else r['ma6'] for _, r in bt.iterrows()]
bt['mix_blend'] = bt.apply(pick_blend, axis=1)

print('=== 相位参照详情（有参照的月份）===')
for _, r in bt.iterrows():
    if not pd.isna(r['phase']):
        print('%s: 相位参照 %s (gap=%d) → 预测 %.0f万 | wd3 %.0f万 | 实际 %.0f万' % (
            r['月'], r['ref'], r['gap'], r['phase']/1e4, r['wd3']/1e4, r['实际']/1e4))

def wape(c, sub=None):
    d = bt if sub is None else bt[bt['月'].str.startswith(sub)]
    return (d[c] - d['实际']).abs().sum() / d['实际'].sum()

def ape_m(c, m):
    d = bt[bt['月'] == m]
    return float(((d[c] - d['实际']).abs() / d['实际']).iloc[0])

print()
print('=== E3 A/B 对比（2025-01~2026-08）===')
print('%-12s %9s %9s %9s %9s %9s %9s' % ('变体', '全期WAPE', '2026WAPE', '25-01', '25-02', '26-01', '26-02'))
for c in ['ma6', 'wd3', 'mix_wd3', 'mix_phase', 'mix_blend']:
    print('%-12s %8.1f%% %8.1f%% %8.1f%% %8.1f%% %8.1f%% %8.1f%%' % (
        c, wape(c)*100, wape(c, '2026')*100,
        ape_m(c, '2025-01')*100, ape_m(c, '2025-02')*100, ape_m(c, '2026-01')*100, ape_m(c, '2026-02')*100))

print()
print('=== 2026 逐月 APE ===')
KEY = ['ma6', 'mix_wd3', 'mix_phase', 'mix_blend']
hdr = '%-9s' % '月份'
for c in KEY:
    hdr += ' %10s' % c
print(hdr)
for m in [x for x in months if x >= '2026-01']:
    line = '%-9s' % m
    for c in KEY:
        line += ' %9.1f%%' % (ape_m(c, m)*100)
    print(line)

bt.to_csv(OUT + r'\E3_节前月加成_对比.csv', index=False, encoding='utf-8-sig')
print()
print('明细已存: E3_节前月加成_对比.csv')
