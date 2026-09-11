# -*- coding: utf-8 -*-
"""2026 月度滚动窗口回测 + A档准确度 + 全年总收入预测（区间+点值）

口径：silver_cleaned_rows（平台清洗层，与经营报告同源）
方法池：naive / ma3 / ma6 / ma12 / snaive(去年同月) / yoy_adj(去年同月×近12月增速) / trend6 / trend12
回测：滚动窗口（每月用当月之前全部历史重估），目标月=2025-01..2026-08
输出：A档2026 WAPE + 全公司月度准确度 + 2026 9-12月预测 + 全年总收入区间
"""
import sys
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')

SILVER = r'E:\3-其他资料\数据分析\sales_analytics_platform\output\silver\silver_cleaned_rows.parquet'
OUT = r'E:\3-其他资料\数据分析\project_analysis\月度滚动预测_20260910'
import os
os.makedirs(OUT, exist_ok=True)

A_LINES = ['通用电源管理', '硬件锂电保护', '充电与控制电源管理', '步进电机驱动', '有刷直流电机驱动', 'POE电源管理', '磁传感']

df = pd.read_parquet(SILVER, columns=['发货日期', '型号_产品线（新）', '金额'])
df['月'] = pd.to_datetime(df['发货日期'], errors='coerce').dt.strftime('%Y-%m')
df = df.dropna(subset=['月']).copy()
df = df[df['型号_产品线（新）'].astype(str).str.strip() != '']   # r28 复核：空名线过滤（含空串）
df['金额'] = pd.to_numeric(df['金额'], errors='coerce').fillna(0.0)
pv = df.groupby(['月', '型号_产品线（新）'])['金额'].sum().unstack(fill_value=0.0).sort_index()

print('月份范围:', pv.index[0], '~', pv.index[-1], '| 月数:', len(pv), '| 产品线数:', pv.shape[1])
print('产品线:', list(pv.columns))
ytd26 = pv.loc['2026-01':'2026-08'].sum().sum()
y25 = pv.loc['2025-01':'2025-12'].sum().sum()
sd25 = pv.loc['2025-09':'2025-12'].sum().sum()
print('2026 1-8月: %.1f万 | 2025全年: %.1f万 | 2025 9-12月: %.1f万' % (ytd26/1e4, y25/1e4, sd25/1e4))
print()

# ---------- 方法池 ----------
METHODS = ['naive', 'ma3', 'ma6', 'ma12', 'snaive', 'yoy_adj', 'trend6', 'trend12']

def predict_one(v, method):
    n = len(v)
    if method == 'naive':
        return v[-1]
    if method.startswith('ma'):
        k = int(method[2:])
        return v[-k:].mean() if n >= k else v.mean()
    if method == 'snaive':
        return v[-12] if n >= 12 else v.mean()
    if method == 'yoy_adj':
        base = v[-12] if n >= 12 else v.mean()
        den = float(v[-24:-12].sum())
        g = (float(v[-12:].sum()) / den) if (n >= 24 and den > 1e5) else 1.0   # r28 复核修复：近零分母保护
        return base * g
    if method.startswith('trend'):
        k = int(method[5:])
        y = v[-k:]
        x = np.arange(len(y))
        if len(y) >= 3 and y.std() > 0:
            sl, ic = np.polyfit(x, y, 1)
            return max(0.0, ic + sl * len(y))
        return y.mean()
    raise ValueError(method)

def forecast_steps(hist, method, steps=4):
    h = list(hist)
    out = []
    for _ in range(steps):
        p = predict_one(np.array(h), method)
        out.append(p)
        h.append(p)
    return out

# ---------- 回测（滚动窗口：2025-01 ~ 2026-08） ----------
months = list(pv.index)
targets = [m for m in months if '2025-01' <= m <= '2026-08']
recs = []
for line in pv.columns:
    s = pv[line]
    for t in targets:
        h = s[s.index < t].values
        if len(h) < 12:
            continue
        act = float(s[t])
        for meth in METHODS:
            recs.append((line, t, meth, float(predict_one(h, meth)), act))
bt = pd.DataFrame(recs, columns=['产品线', '月', '方法', '预测', '实际'])
bt['误差'] = bt['预测'] - bt['实际']

# 每线每方法 WAPE（全期 / 2026）
def wape_table(data, label):
    rows = []
    for (line, meth), g in data.groupby(['产品线', '方法']):
        rows.append({'产品线': line, '方法': meth, label + '_WAPE': np.abs(g['误差']).sum() / max(g['实际'].sum(), 1e-9),
                     'Bias': g['误差'].sum() / max(g['实际'].sum(), 1e-9), 'n': len(g)})
    return pd.DataFrame(rows)

w_all = wape_table(bt, '全期')
bt26 = bt[bt['月'] >= '2026-01']
w_26 = wape_table(bt26, 'Y26')
w = w_all.merge(w_26, on=['产品线', '方法'], suffixes=('', '_y26'), how='left')

# 选方法：全期 WAPE 最小（更稳），并列取更朴素
order = {m: i for i, m in enumerate(METHODS)}
best_rows = []
for line, g in w.groupby('产品线'):
    g2 = g.sort_values(['全期_WAPE', '方法'], key=lambda col: col.map(order) if col.name == '方法' else col)
    best_rows.append(g2.iloc[0])
best = pd.DataFrame(best_rows)

print('=== 全产品线：月度滚动回测（选优方法）===')
print('%-14s %-8s %8s %8s %8s' % ('产品线', '最优方法', '全期WAPE', '2026WAPE', 'Bias'))
for _, r in best.sort_values('Y26_WAPE').iterrows():
    tag = ' [A档]' if r['产品线'] in A_LINES else ''
    print('%-14s %-8s %7.1f%% %7.1f%% %7.1f%%%s' % (r['产品线'], r['方法'], r['全期_WAPE']*100, r['Y26_WAPE']*100, r['Bias']*100, tag))

print()
print('=== A档 7 线（2026 月度滚动准确度）===')
a = best[best['产品线'].isin(A_LINES)]
for _, r in a.sort_values('Y26_WAPE').iterrows():
    print('%-14s %-8s 2026WAPE %5.1f%% | Bias %+5.1f%% | 全期WAPE %5.1f%%' % (r['产品线'], r['方法'], r['Y26_WAPE']*100, r['Bias']*100, r['全期_WAPE']*100))

# A档合并口径（按金额加权）
bt26a = bt26[bt26['产品线'].isin(A_LINES)].copy()
best_map = best.set_index('产品线')['方法'].to_dict()
bt26a['_sel'] = [bool(r['方法'] == best_map.get(r['产品线'])) for _, r in bt26a.iterrows()]
bt26a_best = bt26a[bt26a['_sel']]
wape_a = np.abs(bt26a_best['误差']).sum() / bt26a_best['实际'].sum()
print('A档合计（金额加权）2026 WAPE: %.1f%%' % (wape_a * 100))
# 对照：A档用统一 yoy_adj 的 WAPE
bt26a_yoy = bt26a[bt26a['方法'] == 'yoy_adj']
wape_a_yoy = np.abs(bt26a_yoy['误差']).sum() / bt26a_yoy['实际'].sum()
print('A档合计（统一 yoy_adj 方法）2026 WAPE: %.1f%%' % (wape_a_yoy * 100))

# ---------- 全公司层面 ----------
print()
print('=== 全公司月度（合计口径）===')
tot = bt.groupby(['月', '方法']).agg(预测=('预测', 'sum'), 实际=('实际', 'sum')).reset_index()
rows = []
for meth, g in tot.groupby('方法'):
    rows.append({'方法': meth, '全期WAPE': np.abs(g['预测'] - g['实际']).sum() / g['实际'].sum(),
                 'Bias': (g['预测'] - g['实际']).sum() / g['实际'].sum()})
tot_res = pd.DataFrame(rows).sort_values('全期WAPE')
print(tot_res.to_string(index=False))
tot_best = tot_res.iloc[0]['方法']
print('全公司最优方法:', tot_best)

# 全公司直接法 Sep-Dec 预测
ts = pv.sum(axis=1)
ts_hist = ts[ts.index <= '2026-08'].values
tot_fc = forecast_steps(ts_hist, tot_best, 4)
sd_fc_direct = sum(tot_fc)
print('全公司直接法 9-12月预测: %.1f万' % (sd_fc_direct / 1e4))

# 底部向上法（各线选优方法求和）
bu_fc = {}
for line in pv.columns:
    s = pv[line]
    meth = best.set_index('产品线').loc[line, '方法']
    h = s[s.index <= '2026-08'].values
    bu_fc[line] = forecast_steps(h, meth, 4)
bu_total = np.array(list(bu_fc.values())).sum(axis=0)
sd_fc_bu = bu_total.sum()
print('底部向上法 9-12月预测: %.1f万' % (sd_fc_bu / 1e4))

# ---------- 区间估计（Bootstrap） ----------
# 误差比 r = 实际/预测，取全公司层面（直接法）2025-09~2026-08 各月
tot_piv = tot[tot['方法'] == tot_best].set_index('月')
r_hist = (tot_piv['实际'] / tot_piv['预测']).values
# 分步误差池：k 步递推预测的 actual/pred 比率（k=1..4），用于 Sep-Dec 区间模拟
pools = {k: [] for k in range(1, 5)}
for m in targets:
    idx = list(ts.index).index(m)
    for k in range(1, 5):
        if idx - k + 1 <= 0:
            continue
        hist_k = ts.iloc[:idx - k + 1].values
        h = list(hist_k)
        p = None
        for _ in range(k):
            p = predict_one(np.array(h), tot_best)
            h.append(p)
        pools[k].append(float(ts.iloc[idx]) / max(p, 1e-9))

rng = np.random.default_rng(42)
sims = []
for _ in range(4000):
    total = 0.0
    for j in range(4):
        pool = pools[j + 1] if len(pools[j + 1]) >= 5 else r_hist
        total += tot_fc[j] * rng.choice(pool)
    sims.append(total)
sims = np.array(sims)
q10, q50, q90 = np.percentile(sims, [10, 50, 90])

print()
print('=== 误差比分布（全公司1步，n=%d）=== %.2f ~ %.2f, 中位 %.2f' % (len(r_hist), r_hist.min(), r_hist.max(), np.median(r_hist)))
print('=== 2026 9-12月预测（直接法）: %.1f万 | 80%%区间 [%.1f, %.1f] 万' % (sd_fc_direct/1e4, q10/1e4, q90/1e4))

# 底部向上法的区间（用同样分步比率池）
sims_bu = []
for _ in range(4000):
    total = 0.0
    for j in range(4):
        pool = pools[j + 1] if len(pools[j + 1]) >= 5 else r_hist
        total += bu_total[j] * rng.choice(pool)
    sims_bu.append(total)
sims_bu = np.array(sims_bu)
q10b, q90b = np.percentile(sims_bu, [10, 90])
print('=== 底部向上法: %.1f万 | 80%%区间 [%.1f, %.1f] 万' % (sd_fc_bu/1e4, q10b/1e4, q90b/1e4))

# ---------- 全年汇总 ----------
print()
print('=== 2026 全年总收入 ===')
print('1-8月实际: %.1f万 (%.2f亿)' % (ytd26/1e4, ytd26/1e8))
print('9-12月预测(直接法): %.1f万 | 区间 [%.1f, %.1f] 万' % (sd_fc_direct/1e4, q10/1e4, q90/1e4))
fy = ytd26 + sd_fc_direct
fy_lo = ytd26 + q10
fy_hi = ytd26 + q90
print('全年点值: %.1f万 (%.2f亿)' % (fy/1e4, fy/1e8))
print('全年区间: [%.1f, %.1f] 万 ([%.2f, %.2f]亿)' % (fy_lo/1e4, fy_hi/1e4, fy_lo/1e8, fy_hi/1e8))
print('对比2025全年 %.1f万: 增幅 %.1f%%' % (y25/1e4, (fy/y25 - 1)*100))

# 每月预测明细
print()
print('=== 9-12月每月预测（直接法）===')
for i, m in enumerate(['2026-09', '2026-10', '2026-11', '2026-12']):
    print('%s: %.1f万' % (m, tot_fc[i]/1e4))

# ---------- 导出 ----------
bt.to_csv(os.path.join(OUT, '月度滚动回测明细.csv'), index=False, encoding='utf-8-sig')
best.to_csv(os.path.join(OUT, '产品线选优结果.csv'), index=False, encoding='utf-8-sig')
tot_res.to_csv(os.path.join(OUT, '全公司方法对比.csv'), index=False, encoding='utf-8-sig')
summ = pd.DataFrame([
    {'项': '2026_1-8月实际(万)', '值': ytd26/1e4},
    {'项': '2026_9-12月预测_直接法(万)', '值': sd_fc_direct/1e4},
    {'项': '2026_9-12月区间10(万)', '值': q10/1e4},
    {'项': '2026_9-12月区间90(万)', '值': q90/1e4},
    {'项': '2026全年点值(万)', '值': fy/1e4},
    {'项': '2026全年区间下限(万)', '值': fy_lo/1e4},
    {'项': '2026全年区间上限(万)', '值': fy_hi/1e4},
    {'项': '2025全年(万)', '值': y25/1e4},
])
summ.to_csv(os.path.join(OUT, '全年预测汇总.csv'), index=False, encoding='utf-8-sig')
print()
print('产物已存:', OUT)
