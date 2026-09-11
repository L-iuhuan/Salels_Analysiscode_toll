# -*- coding: utf-8 -*-
"""A/B 对比：①春节因子（工作日法/春节对齐法）②组合预测（均值/中位数/误差加权）
walk-forward 2025-01~2026-08（20折），公司合计口径"""
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

# ---------- 工作日 ----------
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
    print('[工作日] chinese_calendar OK')
except Exception as e:
    CNY = {2024: (2, 10), 2025: (1, 29), 2026: (2, 17)}
    def workdays(ym):
        y, m = int(ym[:4]), int(ym[5:7])
        n = 0
        for d in range(1, calendar.monthrange(y, m)[1] + 1):
            dt = datetime.date(y, m, d)
            ok = dt.weekday() < 5
            if y in CNY and m == CNY[y][0] and CNY[y][1] <= d <= CNY[y][1] + 7:
                ok = False
            if ok:
                n += 1
        return n
    print('[工作日] fallback（%s）' % e)
wd_map = {m: workdays(m) for m in months}
print('工作日数示例: 2025-01=%s 2025-02=%s 2026-01=%s 2026-02=%s' % (
    wd_map.get('2025-01'), wd_map.get('2025-02'), wd_map.get('2026-01'), wd_map.get('2026-02')))

# ---------- 方法 ----------
def predict_one(v, method):
    n = len(v)
    if method == 'naive':
        return v[-1]
    if method.startswith('ma'):
        k = int(method[2:])
        return v[-k:].mean() if n >= k else v.mean()
    if method == 'snaive':
        return v[-12] if n >= 12 else v.mean()
    if method in ('trend6', 'trend12'):
        k = int(method[5:])
        y = v[-k:]
        x = np.arange(len(y))
        if len(y) >= 3 and y.std() > 0:
            sl, ic = np.polyfit(x, y, 1)
            return max(0.0, ic + sl * len(y))
        return y.mean()
    raise ValueError(method)

METHODS6 = ['naive', 'ma3', 'ma6', 'ma12', 'snaive', 'trend12']
CNY_MONTH = {2024: 2, 2025: 1, 2026: 2}

def cny_wd(hist_vals, hist_months, target, k):
    rev = sum(hist_vals[-k:])
    wds = sum(wd_map[m] for m in hist_months[-k:])
    return rev / max(wds, 1) * wd_map[target]

def cny_swap(hist_vals, hist_months, target):
    y, m = int(target[:4]), int(target[5:7])
    prev_y = y - 1
    if prev_y < 2024:
        return hist_vals[-1]
    role_t = (m == CNY_MONTH[y])
    role_p = (m == CNY_MONTH[prev_y])
    ref = '%04d-%02d' % (prev_y, m if role_t == role_p else 3 - m)
    base = ts[ref] if ref in ts.index else hist_vals[-1]
    hv = hist_vals
    if len(hv) >= 24:
        g = sum(hv[-12:]) / max(sum(hv[-24:-12]), 1e-9)
    elif len(hv) >= 12:
        g = sum(hv[-6:]) / max(sum(hv[-12:-6]), 1e-9)
    else:
        g = 1.0
    return base * g

# ---------- 回测 ----------
targets = [m for m in months if '2025-01' <= m <= '2026-08']
rows = []
for t in targets:
    idx = months.index(t)
    hv = list(ts.iloc[:idx].values)
    hm = list(ts.iloc[:idx].index)
    preds = {m: float(predict_one(np.array(hv), m)) for m in METHODS6}
    v6 = np.array([preds[m] for m in METHODS6])
    ens_mean = float(v6.mean())
    ens_med = float(np.median(v6))
    if len(rows) >= 6:
        w = {}
        for m in METHODS6:
            errs = [abs(r['p'][m] - r['实际']) / max(r['实际'], 1) for r in rows]
            w[m] = 1.0 / (np.mean(errs) + 1e-6)
        tot = sum(w.values())
        ens_w = float(sum(preds[m] * w[m] for m in METHODS6) / tot)
    else:
        ens_w = ens_mean
    act = float(ts.iloc[idx])
    rows.append({
        '月': t, '实际': act, 'p': preds,
        'ma6': preds['ma6'], 'ens_mean': ens_mean, 'ens_med': ens_med, 'ens_w': ens_w,
        'cny_wd6': cny_wd(hv, hm, t, 6), 'cny_wd3': cny_wd(hv, hm, t, 3),
        'cny_swap': cny_swap(hv, hm, t),
    })
bt = pd.DataFrame(rows)
bt['mix_wd6'] = [r['cny_wd6'] if r['月'][5:7] in ('01', '02') else r['ma6'] for _, r in bt.iterrows()]
bt['mix_swap'] = [r['cny_swap'] if r['月'][5:7] in ('01', '02') else r['ma6'] for _, r in bt.iterrows()]
bt['mix_ens_wd6'] = [r['cny_wd6'] if r['月'][5:7] in ('01', '02') else r['ens_w'] for _, r in bt.iterrows()]

COLS = ['ma6', 'ens_mean', 'ens_med', 'ens_w', 'cny_wd6', 'cny_wd3', 'cny_swap', 'mix_wd6', 'mix_swap', 'mix_ens_wd6']

def wape(c, sub=None):
    d = bt if sub is None else bt[bt['月'].str.startswith(sub)]
    return (d[c] - d['实际']).abs().sum() / d['实际'].sum()

def ape_m(c, m):
    d = bt[bt['月'] == m]
    if not len(d):
        return float('nan')
    return float(((d[c] - d['实际']).abs() / d['实际']).iloc[0])

print()
print('=== A/B 对比（公司合计 2025-01~2026-08，20折）===')
print('%-12s %9s %9s %9s %9s %9s %9s' % ('变体', '全期WAPE', '2026WAPE', '25-01APE', '25-02APE', '26-01APE', '26-02APE'))
for c in COLS:
    print('%-12s %8.1f%% %8.1f%% %8.1f%% %8.1f%% %8.1f%% %8.1f%%' % (
        c, wape(c) * 100, wape(c, '2026') * 100,
        ape_m(c, '2025-01') * 100, ape_m(c, '2025-02') * 100,
        ape_m(c, '2026-01') * 100, ape_m(c, '2026-02') * 100))

print()
print('=== 2026 逐月 APE（关键变体）===')
KEY = ['ma6', 'ens_w', 'mix_wd6', 'mix_swap', 'mix_ens_wd6']
hdr = '%-9s' % '月份'
for c in KEY:
    hdr += ' %10s' % c
print(hdr)
for m in [x for x in targets if x >= '2026-01']:
    line = '%-9s' % m
    for c in KEY:
        line += ' %9.1f%%' % (ape_m(c, m) * 100)
    print(line)

bt.drop(columns=['p']).to_csv(OUT + r'\AB对比_春节因子与组合.csv', index=False, encoding='utf-8-sig')
print()
print('明细已存:', OUT + r'\AB对比_春节因子与组合.csv')
