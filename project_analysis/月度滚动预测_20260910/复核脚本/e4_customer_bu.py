# -*- coding: utf-8 -*-
"""E4：客户级 bottom-up vs 公司直接（walk-forward 2025-01~2026-08）
变体:
  A. direct_ma6: 公司直接 ma6（基线）
  B. bu_all: 全部客户各自 ma6 求和
  C. bu_top50: 前50大客户单独 ma6 + 其余合并为 others 单序列 ma6
  D. final_direct: E3规则(Jan=相位/Feb=wd3) + direct ma6（当前冠军）
  E. final_bu / final_bu_top50: 非春节月用 BU，1/2月用 E3 规则
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
# 客户键：客户编号（平台口径=终端客户简称）优先，缺则实际终端客户
df['_cust'] = df['客户编号'].fillna(df['实际终端客户']).fillna('未知')
cm = df.groupby(['月', '_cust'])['金额'].sum().unstack(fill_value=0.0).sort_index()
ts = cm.sum(axis=1)
months = list(ts.index)
print('客户数:', cm.shape[1], '| 月份数:', len(months))

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

def ma6_vec(series_vals):
    """向量化：每列最近6个值均值"""
    return series_vals[-6:].mean(axis=0)

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

# 预计算 top50（用 2024 全年 + 2025H1 的累计？为避免前视：每折动态选 top50）
rows = []
for t in [m for m in months if '2025-01' <= m <= '2026-08']:
    idx = months.index(t)
    hist_cm = cm.iloc[:idx]
    act = float(ts.iloc[idx])
    # 动态 top50（按历史累计收入）
    top50 = hist_cm.sum(axis=0).sort_values(ascending=False).head(50).index
    others = hist_cm.drop(columns=top50).sum(axis=1)
    # A: direct ma6
    direct = float(np.mean(ts.iloc[max(0, idx-6):idx]))
    # B: bu_all
    bu_all = float(ma6_vec(hist_cm.values).sum())
    # C: bu_top50
    top50_hist = hist_cm[top50].values
    top50_pred = ma6_vec(top50_hist).sum()
    others_pred = float(np.mean(others.values[-6:])) if len(others) >= 1 else 0.0
    bu_top50 = float(top50_pred + others_pred)
    # D/E: E3 规则
    p_ph = phase_pred(t)
    w3 = wd3(t)
    m = t[5:7]
    if m == '01':
        final_direct = p_ph if p_ph is not None else w3
        final_bu = final_direct
        final_bu50 = final_direct
    elif m == '02':
        final_direct = final_bu = final_bu50 = w3
    else:
        final_direct = direct
        final_bu = bu_all
        final_bu50 = bu_top50
    rows.append({'月': t, '实际': act, 'direct_ma6': direct, 'bu_all': bu_all, 'bu_top50': bu_top50,
                 'final_direct': final_direct, 'final_bu': final_bu, 'final_bu50': final_bu50})
bt = pd.DataFrame(rows)

def wape(c, sub=None):
    d = bt if sub is None else bt[bt['月'].str.startswith(sub)]
    return (d[c] - d['实际']).abs().sum() / d['实际'].sum()

def ape_m(c, m):
    d = bt[bt['月'] == m]
    return float(((d[c] - d['实际']).abs() / d['实际']).iloc[0])

print()
print('=== E4 A/B 对比（2025-01~2026-08）===')
print('%-14s %9s %9s' % ('变体', '全期WAPE', '2026WAPE'))
for c in ['direct_ma6', 'bu_all', 'bu_top50', 'final_direct', 'final_bu', 'final_bu50']:
    print('%-14s %8.1f%% %8.1f%%' % (c, wape(c)*100, wape(c, '2026')*100))

print()
print('=== 2026 逐月 APE（BU vs direct）===')
KEY = ['final_direct', 'final_bu', 'final_bu50']
hdr = '%-9s' % '月份'
for c in KEY:
    hdr += ' %13s' % c
print(hdr)
for m in sorted([x for x in bt['月'].unique() if x >= '2026-01']):
    line = '%-9s' % m
    for c in KEY:
        line += ' %12.1f%%' % (ape_m(c, m)*100)
    print(line)

bt.to_csv(OUT + r'\E4_客户级bottomup_对比.csv', index=False, encoding='utf-8-sig')
print()
print('明细已存: E4_客户级bottomup_对比.csv')
