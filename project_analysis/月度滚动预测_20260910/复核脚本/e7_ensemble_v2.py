# -*- coding: utf-8 -*-
"""E7：组合改进（多样池 + 成员筛选）——公司合计口径
池（11成员）: naive/ma3/ma6/ma12/snaive/trend6/trend12（简单）
             + ses/holt/theta/arima（statsmodels；statsforecast 不可用，等效替代）
筛选: 非春节月 expanding-WAPE 优于 ma6 的成员入选
变体: ens_all / ens_sel / ens_top3 / ens_top5
与E3组合: Jan=相位(缺则wd3), Feb=wd3, 其余=组合变体
"""
import sys, calendar, datetime, warnings
import numpy as np
import pandas as pd
warnings.filterwarnings('ignore')
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

# ---------- 简单方法 ----------
def m_naive(hv, hm, t): return float(hv[-1])
def m_ma3(hv, hm, t): return float(np.mean(hv[-3:]))
def m_ma6(hv, hm, t): return float(np.mean(hv[-6:]))
def m_ma12(hv, hm, t): return float(np.mean(hv[-12:])) if len(hv) >= 12 else float(np.mean(hv))
def m_snaive(hv, hm, t): return float(hv[-12]) if len(hv) >= 12 else float(np.mean(hv))
def m_trend6(hv, hm, t):
    y = np.asarray(hv[-6:], dtype=float); x = np.arange(len(y))
    if len(y) >= 3 and y.std() > 0:
        sl, ic = np.polyfit(x, y, 1); return max(0.0, float(ic + sl * len(y)))
    return float(y.mean())
def m_trend12(hv, hm, t):
    y = np.asarray(hv[-12:], dtype=float); x = np.arange(len(y))
    if len(y) >= 3 and y.std() > 0:
        sl, ic = np.polyfit(x, y, 1); return max(0.0, float(ic + sl * len(y)))
    return float(y.mean())

# ---------- statsmodels 方法 ----------
def m_ses(hv, hm, t):
    from statsmodels.tsa.holtwinters import SimpleExpSmoothing
    fit = SimpleExpSmoothing(np.asarray(hv, dtype=float)).fit(optimized=True)
    return float(fit.forecast(1)[0])

def m_holt(hv, hm, t):
    from statsmodels.tsa.holtwinters import ExponentialSmoothing
    fit = ExponentialSmoothing(np.asarray(hv, dtype=float), trend='add', damped_trend=True).fit(optimized=True)
    return float(fit.forecast(1)[0])

def m_theta(hv, hm, t):
    from statsmodels.tsa.forecasting.theta import ThetaModel
    fit = ThetaModel(np.asarray(hv, dtype=float)).fit()
    return float(fit.forecast(1)[0])

def m_arima(hv, hm, t):
    from statsmodels.tsa.arima.model import ARIMA
    fit = ARIMA(np.asarray(hv, dtype=float), order=(1, 1, 0)).fit()
    return float(fit.forecast(1)[0])

POOL = {'naive': m_naive, 'ma3': m_ma3, 'ma6': m_ma6, 'ma12': m_ma12,
        'snaive': m_snaive, 'trend6': m_trend6, 'trend12': m_trend12,
        'ses': m_ses, 'holt': m_holt, 'theta': m_theta, 'arima': m_arima}

# ---------- 回测 ----------
targets = [m for m in months if '2025-01' <= m <= '2026-08']
rows = []
for t in targets:
    idx = months.index(t)
    hv = list(ts.iloc[:idx].values)
    hm = list(ts.iloc[:idx].index)
    act = float(ts.iloc[idx])
    preds = {}
    for name, fn in POOL.items():
        try:
            preds[name] = float(fn(hv, hm, t))
        except Exception:
            preds[name] = float(hv[-1])
    rows.append({'月': t, '实际': act, **preds})
bt = pd.DataFrame(rows)

# ---------- 成员筛选（非春节月 expanding WAPE）----------
def expanding_wapes(i):
    hist = bt.iloc[:i]
    hist = hist[~hist['月'].str[5:7].isin(['01', '02'])]
    if len(hist) < 6:
        return None
    return {name: (hist[name] - hist['实际']).abs().sum() / hist['实际'].sum() for name in POOL}

sel_cache = {}
ens = {k: [] for k in ['ens_all', 'ens_sel', 'ens_top3', 'ens_top5']}
for i, r in bt.iterrows():
    vals_all = np.array([r[n] for n in POOL], dtype=float)
    w = expanding_wapes(i)
    sel_cache[i] = w
    ens['ens_all'].append(float(vals_all.mean()))
    if w is None:
        ens['ens_sel'].append(float(vals_all.mean()))
        ens['ens_top3'].append(float(vals_all.mean()))
        ens['ens_top5'].append(float(vals_all.mean()))
    else:
        sel = [n for n, x in w.items() if x < w['ma6']] or [min(w, key=w.get)]
        order = sorted(w, key=w.get)
        ens['ens_sel'].append(float(np.mean([r[n] for n in sel])))
        ens['ens_top3'].append(float(np.mean([r[n] for n in order[:3]])))
        ens['ens_top5'].append(float(np.mean([r[n] for n in order[:5]])))
for k in ens:
    bt[k] = ens[k]

# ---------- E3 春节规则 ----------
def phase_pred(hv, hm, t):
    Y, m = int(t[:4]), int(t[5:7])
    ph = phase(Y, m)
    for Yp in range(Y - 1, 2023, -1):
        key = f'{Yp}-{m:02d}'
        if key in ts.index and phase(Yp, m) == ph:
            gap = Y - Yp
            idx = months.index(t)
            g_ann = ts.iloc[idx-12:idx].sum() / max(ts.iloc[idx-24:idx-12].sum(), 1e-9) if idx >= 24 else 1.0
            return float(ts[key] * (g_ann ** gap))
    return None

def wd3(hv, hm, t, k=3):
    rev = sum(hv[-k:]); wds = sum(wd_map[m] for m in hm[-k:])
    return rev / max(wds, 1) * wd_map[t]

finals = {}
for base in ['ma6', 'ens_all', 'ens_sel', 'ens_top3', 'ens_top5']:
    col = []
    for i, r in bt.iterrows():
        m = r['月'][5:7]
        if m == '01':
            p = phase_pred(list(ts.iloc[:i].values), list(ts.iloc[:i].index), r['月'])
            col.append(p if p is not None else r['wd3_'] if 'wd3_' in bt.columns else r[base])
        elif m == '02':
            col.append(r[base] if False else None)  # placeholder, fixed below
        else:
            col.append(r[base])
    finals[base] = col

# wd3/phase 列先算（修正：用月份位置 idx 而非 bt 行号）
wd3_list = []
phase_list = []
for _, r in bt.iterrows():
    idx = months.index(r['月'])
    hv = list(ts.iloc[:idx].values)
    hm = list(ts.iloc[:idx].index)
    wd3_list.append(wd3(hv, hm, r['月']))
    p = phase_pred(hv, hm, r['月'])
    phase_list.append(p if p is not None else np.nan)
bt['wd3_'] = wd3_list
bt['phase_'] = phase_list
# 最终组装：Jan=相位(缺则wd3), Feb=wd3, 其余=组合变体
for base in ['ma6', 'ens_all', 'ens_sel', 'ens_top3', 'ens_top5']:
    col = []
    for _, r in bt.iterrows():
        m = r['月'][5:7]
        if m == '01':
            col.append(r['phase_'] if not pd.isna(r['phase_']) else r['wd3_'])
        elif m == '02':
            col.append(r['wd3_'])
        else:
            col.append(r[base])
    bt['final_' + base] = col

# ---------- 报告 ----------
def wape(c, sub=None):
    d = bt if sub is None else bt[bt['月'].str.startswith(sub)]
    return (d[c] - d['实际']).abs().sum() / d['实际'].sum()

def ape_m(c, m):
    d = bt[bt['月'] == m]
    return float(((d[c] - d['实际']).abs() / d['实际']).iloc[0])

print('=== E7 组合对比（公司合计，2025-01~2026-08）===')
print('%-12s %9s %9s' % ('变体', '全期WAPE', '2026WAPE'))
for c in ['ma6', 'ens_all', 'ens_sel', 'ens_top3', 'ens_top5']:
    print('%-12s %8.1f%% %8.1f%%' % (c, wape(c)*100, wape(c, '2026')*100))

print()
print('=== 最终系统（E3春节规则 + 组合）对比 ===')
print('%-14s %9s %9s %9s %9s %9s %9s' % ('变体', '全期WAPE', '2026WAPE', '25-01', '25-02', '26-01', '26-02'))
for c in ['final_ma6', 'final_ens_all', 'final_ens_sel', 'final_ens_top3', 'final_ens_top5']:
    print('%-14s %8.1f%% %8.1f%% %8.1f%% %8.1f%% %8.1f%% %8.1f%%' % (
        c, wape(c)*100, wape(c, '2026')*100,
        ape_m(c, '2025-01')*100, ape_m(c, '2025-02')*100, ape_m(c, '2026-01')*100, ape_m(c, '2026-02')*100))

print()
print('=== 2026 逐月 APE（最终系统）===')
KEY = ['final_ma6', 'final_ens_sel', 'final_ens_top3', 'final_ens_top5']
hdr = '%-9s' % '月份'
for c in KEY:
    hdr += ' %13s' % c
print(hdr)
for m in sorted([x for x in bt['月'].unique() if x >= '2026-01']):
    line = '%-9s' % m
    for c in KEY:
        line += ' %12.1f%%' % (ape_m(c, m)*100)
    print(line)

# 成员筛选示例（最后一折的入选成员）
w = sel_cache[len(bt)-1]
if w:
    sel = [n for n, x in w.items() if x < w['ma6']]
    print()
    print('末折(2026-08)非春节月 expanding-WAPE 前5:', {n: round(w[n]*100, 1) for n in sorted(w, key=w.get)[:5]})
    print('入选(优于ma6=%.1f%%):' % (w['ma6']*100), sel)

bt.to_csv(OUT + r'\E7_组合改进_对比.csv', index=False, encoding='utf-8-sig')
print()
print('明细已存: E7_组合改进_对比.csv')
