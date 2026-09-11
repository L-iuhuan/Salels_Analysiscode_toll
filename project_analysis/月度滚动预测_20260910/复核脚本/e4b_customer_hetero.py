# -*- coding: utf-8 -*-
"""E4b：客户级 bottom-up（异质化）——每客户独立选方法 vs 公司直接
- 恒等发现：同方法（ma6）下 BU ≡ 直接（线性可加）→ 必须异质化才有检验价值
- 变体: bu_sel_all（全客户独立选优）/ bu_sel_big（大客户独立选优，其余ma6）
- 方法池: naive/ma3/ma6/ma12/snaive/trend12（向量化）
- 选择: 各客户按 expanding WAPE 选优（≥6 折且累计实际≥10万者，否则 ma6）
- 叠加 E3 春节规则（Jan=相位/Feb=wd3）成最终系统
"""
import sys, calendar, datetime, warnings
import numpy as np
import pandas as pd
warnings.filterwarnings('ignore')
sys.stdout.reconfigure(encoding='utf-8')

SILVER = r'E:\3-其他资料\数据分析\sales_analytics_platform\output\silver\silver_cleaned_rows.parquet'
OUT = r'E:\3-其他资料\数据分析\project_analysis\月度滚动预测_20260910'

df = pd.read_parquet(SILVER, columns=['发货日期', '客户编号', '实际终端客户', '金额'])
df['月'] = pd.to_datetime(df['发货日期'], errors='coerce').dt.strftime('%Y-%m')
df = df.dropna(subset=['月'])
df['金额'] = pd.to_numeric(df['金额'], errors='coerce').fillna(0)
df['_cust'] = df['客户编号'].fillna(df['实际终端客户']).fillna('未知')
cm = df.groupby(['月', '_cust'])['金额'].sum().unstack(fill_value=0.0).sort_index()
ts = cm.sum(axis=1)
months = list(ts.index)
vals = cm.values.astype(float)  # (T, C)
T, C = vals.shape
print('客户数:', C, '| 月份数:', T)

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

METHODS = ['naive', 'ma3', 'ma6', 'ma12', 'snaive', 'trend12']

def predict_matrix(hist):
    """hist: (t, C) → dict method → (C,) 下月预测"""
    P = {}
    P['naive'] = hist[-1].copy()
    P['ma3'] = hist[-3:].mean(axis=0)
    P['ma6'] = hist[-6:].mean(axis=0)
    P['ma12'] = hist[-12:].mean(axis=0)
    P['snaive'] = hist[-12].copy()
    y = hist[-12:]
    x = np.arange(12)
    xm, ym = x.mean(), y.mean(axis=0)
    cov = ((x - xm)[:, None] * (y - ym)).sum(axis=0)
    slope = cov / ((x - xm) ** 2).sum()
    intercept = ym - slope * xm
    P['trend12'] = np.maximum(0.0, intercept + slope * 12)
    return P

# 预计算所有折的预测矩阵
fold_preds = {}
for i in range(12, T):
    fold_preds[i] = predict_matrix(vals[:i])

def phase_pred(t):
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

def wd3(t):
    idx = months.index(t)
    rev = ts.iloc[max(0, idx-3):idx].sum()
    wds = sum(wd_map[m] for m in months[max(0, idx-3):idx])
    return float(rev / max(wds, 1) * wd_map[t])

targets = [m for m in months if '2025-01' <= m <= '2026-08']
# 累计实际（用于大客户判定）
cum_actual = vals[:12].sum(axis=0)

rows = []
for t in targets:
    i = months.index(t)
    act = float(ts.iloc[i])
    P = fold_preds[i]
    # 每客户 expanding WAPE（用 12..i-1 折）
    seen = list(range(12, i))
    if len(seen) >= 6:
        wape_c = {}
        for mname in METHODS:
            err = np.zeros(C)
            for j in seen:
                err += np.abs(fold_preds[j][mname] - vals[j])
            wape_c[mname] = err / np.maximum(vals[seen].sum(axis=0), 1.0)
        # 选优（仅对累计实际≥10万的客户，其余用 ma6）
        elig = cum_actual >= 1e5
        wmat = np.stack([wape_c[mname] for mname in METHODS])  # (M, C)
        best_idx = np.argmin(wmat, axis=0)
        bu_sel = np.zeros(C)
        bu_big = np.zeros(C)
        for ci in range(C):
            if elig[ci]:
                mname = METHODS[best_idx[ci]]
                bu_sel[ci] = P[mname][ci]
                bu_big[ci] = P[mname][ci]
            else:
                bu_sel[ci] = P['ma6'][ci]
                bu_big[ci] = P['ma6'][ci]
        # bu_big: 仅大客户独立选优，其余 ma6（与 bu_sel 同构但阈值更严）
        elig2 = cum_actual >= 1e6
        for ci in range(C):
            if elig2[ci]:
                mname = METHODS[best_idx[ci]]
                bu_big[ci] = P[mname][ci]
        bu_sel_sum = float(bu_sel.sum())
        bu_big_sum = float(bu_big.sum())
    else:
        bu_sel_sum = float(P['ma6'].sum())
        bu_big_sum = float(P['ma6'].sum())
    direct = float(P['ma6'].sum())  # 恒等于 ts 的 ma6
    # E3 规则
    m = t[5:7]
    if m == '01':
        p_ph = phase_pred(t)
        fin_dir = p_ph if p_ph is not None else wd3(t)
        fin_sel = fin_dir
        fin_big = fin_dir
    elif m == '02':
        fin_dir = fin_sel = fin_big = wd3(t)
    else:
        fin_dir = direct
        fin_sel = bu_sel_sum
        fin_big = bu_big_sum
    rows.append({'月': t, '实际': act, 'direct_ma6': direct, 'bu_sel_all': bu_sel_sum,
                 'bu_sel_big': bu_big_sum, 'final_direct': fin_dir, 'final_bu_sel': fin_sel,
                 'final_bu_big': fin_big})
bt = pd.DataFrame(rows)

def wape(c, sub=None):
    d = bt if sub is None else bt[bt['月'].str.startswith(sub)]
    return (d[c] - d['实际']).abs().sum() / d['实际'].sum()

def ape_m(c, m):
    d = bt[bt['月'] == m]
    return float(((d[c] - d['实际']).abs() / d['实际']).iloc[0])

print()
print('=== E4b A/B 对比（2025-01~2026-08）===')
print('%-16s %9s %9s' % ('变体', '全期WAPE', '2026WAPE'))
for c in ['direct_ma6', 'bu_sel_all', 'bu_sel_big', 'final_direct', 'final_bu_sel', 'final_bu_big']:
    print('%-16s %8.1f%% %8.1f%%' % (c, wape(c)*100, wape(c, '2026')*100))

print()
print('=== 2026 逐月 APE ===')
KEY = ['final_direct', 'final_bu_sel', 'final_bu_big']
hdr = '%-9s' % '月份'
for c in KEY:
    hdr += ' %15s' % c
print(hdr)
for m in sorted([x for x in bt['月'].unique() if x >= '2026-01']):
    line = '%-9s' % m
    for c in KEY:
        line += ' %14.1f%%' % (ape_m(c, m)*100)
    print(line)

bt.to_csv(OUT + r'\E4b_客户级bottomup_异质_对比.csv', index=False, encoding='utf-8-sig')
print()
print('明细已存: E4b_客户级bottomup_异质_对比.csv')
