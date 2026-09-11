# -*- coding: utf-8 -*-
"""融合测试：combo_phase(+vol×asp) + 线级锚定缩放 + SKU 份额分配 + Conformal 区间
口径（议会裁决）：线级选优 expanding（无前视）；SKU 过滤 PIT（仅 <t 累计）；SKU 直测日历月 ma6；
空名线过滤；拆分：全期/2026/春节月/非春节月；对照：ma6/mix_wd3/combo/combo_volxasp。
"""
import sys
import numpy as np
import pandas as pd
sys.stdout.reconfigure(encoding='utf-8')

SILVER = r'E:\3-其他资料\数据分析\sales_analytics_platform\output\silver\silver_cleaned_rows.parquet'
OUT = r'E:\3-其他资料\数据分析\project_analysis\月度滚动预测_20260910'
METHODS = ['naive', 'ma3', 'ma6', 'ma12', 'snaive', 'yoy_adj', 'trend6', 'trend12']

df = pd.read_parquet(SILVER, columns=['发货日期', '产品品种', '型号_产品线（新）', '金额'])
df['月'] = pd.to_datetime(df['发货日期'], errors='coerce').dt.strftime('%Y-%m')
df = df.dropna(subset=['月'])
df = df.dropna(subset=['型号_产品线（新）'])
df = df[df['型号_产品线（新）'].astype(str).str.strip() != '']   # 空名线过滤（议会 Bug-3，含空串）
df['金额'] = pd.to_numeric(df['金额'], errors='coerce').fillna(0.0)
pv = df.groupby(['月', '型号_产品线（新）'])['金额'].sum().unstack(fill_value=0.0).sort_index()
months = list(pv.index)
sku_line = df.groupby('产品品种')['型号_产品线（新）'].agg(lambda s: s.mode().iloc[0]).to_dict()
sku_cal = df.groupby(['月', '产品品种'])['金额'].sum().unstack(fill_value=0.0).reindex(months, fill_value=0.0)

def predict_one(v, method):
    n = len(v)
    if method == 'naive':
        return float(v[-1])
    if method.startswith('ma'):
        k = int(method[2:])
        return float(v[-k:].mean()) if n >= k else float(v.mean())
    if method == 'snaive':
        return float(v[-12]) if n >= 12 else float(v.mean())
    if method == 'yoy_adj':
        base = float(v[-12]) if n >= 12 else float(v.mean())
        den = float(v[-24:-12].sum())
        g = (float(v[-12:].sum()) / den) if (n >= 24 and den > 1e5) else 1.0
        return base * g
    if method.startswith('trend'):
        k = int(method[5:])
        y = np.asarray(v[-k:], dtype=float)
        x = np.arange(len(y))
        if len(y) >= 3 and y.std() > 0:
            sl, ic = np.polyfit(x, y, 1)
            return max(0.0, float(ic + sl * len(y)))
        return float(y.mean())
    raise ValueError(method)

targets = [m for m in months if '2025-01' <= m <= '2026-08']

def wape(d, c):
    return (d[c] - d['实际']).abs().sum() / max(d['实际'].sum(), 1e-9)

def seg_of(d, seg):
    if seg == '全期':
        return d
    if seg == '2026':
        return d[d['月'] >= '2026-01']
    cny = d['月'].str[5:7].isin(['01', '02'])
    return d[cny] if seg == '春节' else d[~cny]

def rowline(label, d, cols):
    parts = []
    for seg in ['全期', '2026', '春节', '非春节']:
        dd = seg_of(d, seg)
        vals = ' | '.join('%s %.1f%%' % (c, wape(dd, c) * 100) for c in cols)
        parts.append('%s[%s]' % (seg, vals))
    print('%-14s %s' % (label, '  '.join(parts)))

# ---------- B1 公司口径 ----------
e3 = pd.read_csv(OUT + r'\E3_节前月加成_对比.csv')
e12 = pd.read_csv(OUT + r'\E12b_量价集成_对比.csv')
comp = e12[['月', '实际', 'combo', 'combo_volxasp']].merge(e3[['月', 'ma6', 'mix_wd3']], on='月')
print('=== B1 公司口径 WAPE ===')
for c in ['ma6', 'mix_wd3', 'combo', 'combo_volxasp']:
    rowline(c, comp, [c])

# ---------- B2 线级：expanding 选优 + 锚定缩放 ----------
rows, sel_log = [], []
for idx, t in enumerate(targets):
    i = months.index(t)
    line_preds = {}
    for line in pv.columns:
        v = pv[line].values.astype(float)
        if idx >= 4:
            scores = {}
            for m in METHODS:
                errs = acts = 0.0
                for j in range(idx):
                    ij = months.index(targets[j])
                    hj = v[:ij]
                    if len(hj) < 12:
                        continue
                    errs += abs(predict_one(hj, m) - v[ij])
                    acts += v[ij]
                if acts > 0:
                    scores[m] = errs / acts
            best_m = min(scores, key=lambda m: (scores[m], METHODS.index(m))) if scores else 'ma6'
        else:
            best_m = 'ma6'
        line_preds[line] = predict_one(v[:i], best_m)
        sel_log.append({'月': t, '产品线': line, '选优方法': best_m})
    raw_sum = sum(line_preds.values())
    anchor = float(comp[comp['月'] == t]['combo_volxasp'].iloc[0])
    factor = anchor / max(raw_sum, 1e-9)
    for line, p in line_preds.items():
        rows.append({'月': t, '产品线': line, '实际': float(pv.loc[t, line]), 'raw': p, 'scaled': p * factor})
ln = pd.DataFrame(rows)
print()
print('=== B2 线级 WAPE（expanding 选优 + 锚定缩放）===')
rowline('线级raw', ln, ['raw'])
rowline('线级scaled', ln, ['scaled'])
per = ln.groupby('产品线').apply(
    lambda g: pd.Series({'raw': (g['raw'] - g['实际']).abs().sum() / max(g['实际'].sum(), 1e-9),
                         'scaled': (g['scaled'] - g['实际']).abs().sum() / max(g['实际'].sum(), 1e-9)}),
    include_groups=False)
print('线级改善: %d/%d 条（scaled<raw）| 简单平均 raw %.1f%% → scaled %.1f%%' % (
    int((per['scaled'] < per['raw']).sum()), len(per), per['raw'].mean() * 100, per['scaled'].mean() * 100))
sel_df = pd.DataFrame(sel_log)

# ---------- B3 SKU 层：scaled 线 × 日历3月份额；直测=日历 ma6 ----------
srows = []
for t in targets:
    i = months.index(t)
    win3, win6 = months[i-3:i], months[i-6:i]
    for line in pv.columns:
        line_scaled = float(ln[(ln['月'] == t) & (ln['产品线'] == line)]['scaled'].iloc[0])
        lg3 = float(pv.loc[win3, line].sum())
        for skuname in sku_cal.columns:
            if sku_line.get(skuname) != line:
                continue
            ss = sku_cal[skuname]
            if float(ss[ss.index < t].sum()) < 50e4:   # PIT 过滤
                continue
            direct = float(ss.loc[win6].sum()) / 6.0    # 日历 ma6（含零月）
            share = float(ss.loc[win3].sum()) / lg3 if lg3 > 0 else 0.0
            srows.append({'月': t, '产品线': line, 'SKU': skuname,
                          '实际': float(ss.get(t, 0.0)), 'direct': direct, 'alloc': line_scaled * share})
sk = pd.DataFrame(srows)
print()
print('=== B3 SKU 级 WAPE（PIT 过滤 + 日历 ma6；%d SKU×折）===' % len(sk))
rowline('SKU直测', sk, ['direct'])
rowline('SKU分配', sk, ['alloc'])
per_sku = sk.groupby('SKU').apply(
    lambda g: pd.Series({'direct': (g['direct'] - g['实际']).abs().sum() / max(g['实际'].sum(), 1e-9),
                         'alloc': (g['alloc'] - g['实际']).abs().sum() / max(g['实际'].sum(), 1e-9)}),
    include_groups=False)
print('SKU 改善: %d/%d 个 | 分配质量保留率（Σalloc/线scaled 均值）%.2f' % (
    int((per_sku['alloc'] < per_sku['direct']).sum()), len(per_sku),
    float((sk.groupby(['月', '产品线'])['alloc'].sum() /
           ln.set_index(['月', '产品线'])['scaled']).mean())))

# ---------- 区间：Conformal（复算，去硬编码）----------
bt = comp.copy()
bt['absratio'] = (bt['实际'] - bt['combo_volxasp']).abs() / bt['combo_volxasp']
cov, wid = [], []
for i in range(len(bt)):
    if i < 6:
        continue
    hist = bt.iloc[:i]
    pred, act = float(bt.iloc[i]['combo_volxasp']), float(bt.iloc[i]['实际'])
    q80 = np.percentile(hist['absratio'], 80)
    lo, hi = pred * (1 - q80), pred * (1 + q80)
    cov.append(lo <= act <= hi)
    wid.append((hi - lo) / pred)
print()
print('=== 区间（Conformal 复算）===')
print('覆盖率 %.0f%%（%d 折）| 平均宽度 %.1f%%' % (np.mean(cov) * 100, len(cov), np.mean(wid) * 100))

# ---------- 导出 ----------
comp.to_csv(OUT + r'\融合测试_公司口径.csv', index=False, encoding='utf-8-sig')
ln.to_csv(OUT + r'\融合测试_线级.csv', index=False, encoding='utf-8-sig')
sk.to_csv(OUT + r'\融合测试_SKU级.csv', index=False, encoding='utf-8-sig')
sel_df.to_csv(OUT + r'\融合测试_线级选优日志.csv', index=False, encoding='utf-8-sig')
print()
print('明细已存: 融合测试_*.csv')
