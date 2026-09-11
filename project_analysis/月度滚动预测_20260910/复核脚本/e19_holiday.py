# -*- coding: utf-8 -*-
"""E19：长假效应诊断（春节 vs 五一/十一）+ 融合冠军偏差画像"""
import sys
import numpy as np
import pandas as pd
from datetime import date, timedelta
import chinese_calendar as cc
sys.stdout.reconfigure(encoding='utf-8')

SILVER = r'E:\3-其他资料\数据分析\sales_analytics_platform\output\silver\silver_cleaned_rows.parquet'
OUT = r'E:\3-其他资料\数据分析\project_analysis\月度滚动预测_20260910'

e12 = pd.read_csv(OUT + r'\E12b_量价集成_对比.csv')
e3 = pd.read_csv(OUT + r'\E3_节前月加成_对比.csv')
bt = e12[['月', '实际', 'combo', 'combo_volxasp']].merge(e3[['月', 'ma6', 'wd3']], on='月')
bt['APE_champ'] = (bt['combo_volxasp'] - bt['实际']).abs() / bt['实际']
bt['APE_ma6'] = (bt['ma6'] - bt['实际']).abs() / bt['实际']

def wape(d, c):
    return (d[c] - d['实际']).abs().sum() / d['实际'].sum()
def bias(d, c):
    return (d[c] - d['实际']).sum() / d['实际'].sum()

print('=== ① 融合冠军偏差画像（20 折）===')
for seg, dd in [('全期', bt), ('2026', bt[bt['月'] >= '2026-01'])]:
    print('%s: 冠军 WAPE %.1f%% Bias %+.1f%% | ma6 WAPE %.1f%% Bias %+.1f%%' % (
        seg, wape(dd, 'combo_volxasp')*100, bias(dd, 'combo_volxasp')*100,
        wape(dd, 'ma6')*100, bias(dd, 'ma6')*100))
print('单月 APE：冠军 min %.1f%% ~ max %.1f%%（最差 %s）| ma6 min %.1f%% ~ max %.1f%%' % (
    bt['APE_champ'].min()*100, bt['APE_champ'].max()*100, bt.loc[bt['APE_champ'].idxmax(), '月'],
    bt['APE_ma6'].min()*100, bt['APE_ma6'].max()*100))
print()
print('逐月 APE（★=长假月 1/2/5/10）:')
for _, r in bt.iterrows():
    mm = r['月'][5:7]
    star = '★' if mm in ('01', '02', '05', '10') else ' '
    print('%s %s 冠军 %5.1f%% | ma6 %5.1f%%' % (r['月'], star, r['APE_champ']*100, r['APE_ma6']*100))

bt['mo'] = bt['月'].str[5:7]
g = bt.groupby('mo').agg(冠军=('APE_champ', 'mean'), ma6=('APE_ma6', 'mean'), n=('月', 'count'))
print()
print('按日历月平均 APE:')
for mo, r in g.iterrows():
    print('  %s月: 冠军 %5.1f%% | ma6 %5.1f%% (n=%d)' % (mo, r['冠军']*100, r['ma6']*100, r['n']))

# ---------- ② 假期窗口日度效应 ----------
df = pd.read_parquet(SILVER, columns=['发货日期', '金额'])
df['dt'] = pd.to_datetime(df['发货日期'], errors='coerce')
df = df.dropna(subset=['dt'])
df['金额'] = pd.to_numeric(df['金额'], errors='coerce').fillna(0)
daily = df.groupby(df['dt'].dt.date)['金额'].sum()

def window_share(s0, s1, e0, e1):
    tot = daily.loc[(daily.index >= s0) & (daily.index <= e1)].sum()
    win = daily.loc[(daily.index >= s0) & (daily.index <= s1)].sum()
    ndays = (e1 - e0).days + 1
    nwin = (s1 - s0).days + 1
    return win, tot, nwin / ndays

print()
print('=== ② 假期窗口日度效应（窗口收入占比 vs 均匀期望；抑制比<1=假期出货受抑）===')
for label, s0, s1, e0, e1 in [
    ('2024 五一', date(2024, 5, 1), date(2024, 5, 5), date(2024, 5, 1), date(2024, 5, 31)),
    ('2025 五一', date(2025, 5, 1), date(2025, 5, 5), date(2025, 5, 1), date(2025, 5, 31)),
    ('2026 五一', date(2026, 5, 1), date(2026, 5, 5), date(2026, 5, 1), date(2026, 5, 31)),
    ('2024 十一', date(2024, 10, 1), date(2024, 10, 7), date(2024, 10, 1), date(2024, 10, 31)),
    ('2025 十一', date(2025, 10, 1), date(2025, 10, 7), date(2025, 10, 1), date(2025, 10, 31)),
    ('2025 春节', date(2025, 1, 28), date(2025, 2, 4), date(2025, 1, 1), date(2025, 2, 28)),
    ('2026 春节', date(2026, 2, 15), date(2026, 2, 23), date(2026, 1, 1), date(2026, 2, 28)),
]:
    win, tot, unif = window_share(s0, s1, e0, e1)
    if tot <= 0:
        continue
    print('%s: 窗口占比 %5.1f%%（均匀 %4.1f%%）→ 抑制比 %.2f | 窗口期收入 %.0f万' % (
        label, win/tot*100, unif*100, (win/tot)/unif, win/1e4))

# ---------- ③ 工作日法对 5/10 月的适用性 ----------
print()
print('=== ③ 工作日法（近3月日收入率×工作日）vs ma6/冠军（5/10 月折）===')
df['月'] = df['dt'].dt.strftime('%Y-%m')
mrev = df.groupby('月')['金额'].sum().sort_index()
def workdays(y, m):
    d = date(y, m, 1); n = 0
    while d.month == m:
        if cc.is_workday(d): n += 1
        d += timedelta(days=1)
    return n
months_all = list(mrev.index)
wd_map = {mm: workdays(int(mm[:4]), int(mm[5:7])) for mm in months_all}
targets = [mm for mm in months_all if '2025-01' <= mm <= '2026-08']
rows = []
for t in targets:
    i = months_all.index(t)
    if i < 3:
        continue
    rate = mrev.iloc[i-3:i].sum() / sum(wd_map[mm] for mm in months_all[i-3:i])
    row = {'月': t, '实际': mrev[t], 'wd': rate * wd_map[t]}
    hit = bt[bt['月'] == t]
    row['ma6'] = float(hit['ma6'].iloc[0]) if len(hit) else np.nan
    row['champ'] = float(hit['combo_volxasp'].iloc[0]) if len(hit) else np.nan
    rows.append(row)
rr = pd.DataFrame(rows).dropna()
for c in ['wd', 'ma6', 'champ']:
    rr['APE_' + c] = (rr[c] - rr['实际']).abs() / rr['实际']
print('全 20 折 WAPE: wd %.1f%% | ma6 %.1f%% | 冠军 %.1f%%' % (
    (rr['wd']-rr['实际']).abs().sum()/rr['实际'].sum()*100,
    (rr['ma6']-rr['实际']).abs().sum()/rr['实际'].sum()*100,
    (rr['champ']-rr['实际']).abs().sum()/rr['实际'].sum()*100))
for grp, mask in [('5/10 月', rr['月'].str[5:7].isin(['05', '10'])), ('1/2 月（对照）', rr['月'].str[5:7].isin(['01', '02']))]:
    print('%s:' % grp)
    for _, r in rr[mask].iterrows():
        print('  %s: wd %5.1f%% | ma6 %5.1f%% | 冠军 %5.1f%% | 工作日 %d' % (
            r['月'], r['APE_wd']*100, r['APE_ma6']*100, r['APE_champ']*100, wd_map[r['月']]))
