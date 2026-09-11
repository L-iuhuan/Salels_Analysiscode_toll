# -*- coding: utf-8 -*-
"""E21b：增长信号诊断 + 2027-01 重估
1) 增速序列（逐月同比）与减速视图
2) 诊断：ratio(实际/冠军) 与近期增速相关 —— 高增长月是否系统性低估
3) 增长调制校正：ratio ~ g_recent（expanding OLS），对比 E20-V2 是否还能改善
4) 2027-01 重估：多变体对比
"""
import sys
import numpy as np
import pandas as pd
sys.stdout.reconfigure(encoding='utf-8')

SILVER = r'E:\3-其他资料\数据分析\sales_analytics_platform\output\silver\silver_cleaned_rows.parquet'
OUT = r'E:\3-其他资料\数据分析\project_analysis\月度滚动预测_20260910'

df = pd.read_parquet(SILVER, columns=['发货日期', '金额'])
df['月'] = pd.to_datetime(df['发货日期'], errors='coerce').dt.strftime('%Y-%m')
df = df.dropna(subset=['月'])
df['金额'] = pd.to_numeric(df['金额'], errors='coerce').fillna(0)
ts = df.groupby('月')['金额'].sum().sort_index()

# YoY（同月环比上一年）
yoy = ts / ts.shift(12) - 1.0
print('=== 增速序列（逐月同比）===')
for m in ts.index:
    v = yoy.get(m)
    print('%s: %s' % (m, '%+.1f%%' % (v*100) if pd.notna(v) else '—'))

# 近3月同比（截至 t-1，预测时点可得）
def g_recent(m):
    i = list(ts.index).index(m)
    if i < 15:
        return np.nan
    return float(ts.iloc[i-3:i].sum() / ts.iloc[i-15:i-12].sum() - 1.0)

e12 = pd.read_csv(OUT + r'\E12b_量价集成_对比.csv')
bt = e12[['月', '实际', 'combo_volxasp']].copy()
bt['ratio'] = bt['实际'] / bt['combo_volxasp']
bt['g_recent'] = bt['月'].map(g_recent)
bt['g_own'] = bt['月'].map(yoy)

print()
print('=== 诊断：误差比 ratio vs 增速 ===')
dd = bt.dropna(subset=['g_recent'])
print('corr(ratio, 近3月YoY[可观测]): %+.3f (n=%d)' % (dd['ratio'].corr(dd['g_recent']), len(dd)))
dd2 = bt.dropna(subset=['g_own'])
print('corr(ratio, 当月YoY[参考]):    %+.3f (n=%d)' % (dd2['ratio'].corr(dd2['g_own']), len(dd2)))
# 增速分段均值
q = dd['g_recent'].quantile([1/3, 2/3]).values
hi = dd[dd['g_recent'] > q[1]]; lo = dd[dd['g_recent'] <= q[0]]
print('高增长 1/3 月: 平均 ratio %.3f | 低增长 1/3 月: 平均 ratio %.3f' % (hi['ratio'].mean(), lo['ratio'].mean()))

print()
print('=== 增长调制校正：ratio ~ g_recent（expanding OLS）===')
preds = {'champ': [], 'V2': [], 'V5': []}
for i in range(len(bt)):
    if i < 6 or pd.isna(bt.loc[i, 'g_recent']):
        for k in preds:
            preds[k].append(np.nan)
        continue
    tr = bt.iloc[:i].dropna(subset=['g_recent'])
    med = float(np.median(tr['ratio']))
    X = np.column_stack([np.ones(len(tr)), tr['g_recent'].values])
    y = tr['ratio'].values
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    rhat = min(max(coef[0] + coef[1]*float(bt.loc[i, 'g_recent']), 0.7), 1.5)
    preds['champ'].append(float(bt.loc[i, 'combo_volxasp']))
    preds['V2'].append(float(bt.loc[i, 'combo_volxasp']) * med)
    preds['V5'].append(float(bt.loc[i, 'combo_volxasp']) * rhat)
for k in preds:
    bt[k] = preds[k]
seg = bt.dropna(subset=['V2', 'V5'])
def wape(c):
    return (seg[c] - seg['实际']).abs().sum() / seg['实际'].sum()
def bias(c):
    return (seg[c] - seg['实际']).sum() / seg['实际'].sum()
print('折7-20: 冠军 %.1f%%/%+.1f%% | E20-V2 %.1f%%/%+.1f%% | V5 增长调制 %.1f%%/%+.1f%%' % (
    wape('champ')*100, bias('champ')*100, wape('V2')*100, bias('V2')*100, wape('V5')*100, bias('V5')*100))

# ---------- 2027-01 重估 ----------
print()
print('=== 2027-01 重估（2026-01 实际 %.1f万）===' % (ts['2026-01']/1e4))
g_trail = float(ts.iloc[-12:].sum() / ts.iloc[-24:-12].sum())
g_own0826 = float(yoy['2026-08'])
g_last3 = float(ts.iloc[-3:].sum() / ts.iloc[-6:-3].sum() - 1.0)
g_ann = float(ts.loc['2025-01':'2025-12'].sum() / ts.loc['2024-01':'2024-12'].sum())
v26 = float(ts['2026-01']); v24 = float(ts['2024-01'])
print('增速口径：trailing12月 YoY %+.1f%% | 2026-08 单月 %+.1f%% | 近3月(6-8) %+.1f%% | 年化(25/24) %+.1f%%' % (
    (g_trail-1)*100, g_own0826*100, g_last3*100, (g_ann-1)*100))
print('变体 A（现值，×trailing %.3f）: %.0f万' % (g_trail, v26*g_trail/1e4))
print('变体 B（×2026-08 单月YoY %.3f）: %.0f万' % (1+g_own0826, v26*(1+g_own0826)/1e4))
print('变体 C（×近3月YoY %.3f）: %.0f万' % (1+g_last3, v26*(1+g_last3)/1e4))
print('变体 D（2024-01×g_ann³，原相位规则口径）: %.0f万' % (v24*(g_ann**3)/1e4))
print('变体 E（2024-01×g_ann²，同 2026 规则即 E3 口径）: %.0f万' % (v24*(g_ann**2)/1e4))
