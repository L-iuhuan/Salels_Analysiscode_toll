# -*- coding: utf-8 -*-
"""D2：生命周期因子 × 预测修正（PIT 画像 → 线级特征 → expanding OLS 修正 → 20 折回测）
- 基线：线级 ma6（与全公司基线同法）
- 特征（每个截点，SKU 画像按近12月收入加权聚合到产品线）：
    dec_share  衰退类画像收入占比（衰退期/夕阳产品/隐性衰退/清仓偶发）
    grow_share 成长类画像收入占比（成长期/健康扩张/预警增长/新品观察）
    score_w    加权综合评分
- 修正：ratio(实际/ma6) ~ 1 + 特征，expanding 拟合（只用更早折），预测比 → base×比
- 评估：线级金额加权 WAPE + 线级简单平均 WAPE + 公司求和 WAPE（全期/2026）
"""
import sys
import numpy as np
import pandas as pd
sys.stdout.reconfigure(encoding='utf-8')

SILVER = r'E:\3-其他资料\数据分析\sales_analytics_platform\output\silver\silver_cleaned_rows.parquet'
HIST = r'E:\3-其他资料\数据分析\sales_analytics_platform\output\gold\gold_product_portrait_history.csv'
OUT = r'E:\3-其他资料\数据分析\project_analysis\月度滚动预测_20260910'

df = pd.read_parquet(SILVER, columns=['发货日期', '产品品种', '型号_产品线（新）', '金额'])
df['月'] = pd.to_datetime(df['发货日期'], errors='coerce').dt.strftime('%Y-%m')
df = df.dropna(subset=['月'])
df['金额'] = pd.to_numeric(df['金额'], errors='coerce').fillna(0)

pv = df.groupby(['月', '型号_产品线（新）'])['金额'].sum().unstack(fill_value=0.0).sort_index()
months = list(pv.index)
sku_line = df.groupby('产品品种')['型号_产品线（新）'].agg(lambda s: s.mode().iloc[0]).to_dict()
sku_m = df.groupby(['月', '产品品种'])['金额'].sum().unstack(fill_value=0.0).sort_index()

hist = pd.read_csv(HIST, encoding='utf-8-sig').set_index('产品名称')

DEC = {'衰退期', '夕阳产品', '隐性衰退', '清仓/偶发'}
GROW = {'成长期', '健康扩张', '预警增长', '新品观察'}

targets = [m for m in months if '2025-01' <= m <= '2026-08']  # 20 折
rows = []
for idx, t in enumerate(targets):
    N = 20 - idx                       # 截点 t-N = 目标月前一月
    i = months.index(t)
    if i < 6:
        continue
    col, score_col = '当前画像_t-%d' % N, '综合评分_t-%d' % N
    if col not in hist.columns:
        print('缺列', col); continue
    win = months[max(0, i - 12):i]     # 近12月（截至截点）
    wsum = sku_m.loc[win].sum()
    for line in pv.columns:
        base = float(pv[line].values[i-6:i].mean())
        actual = float(pv[line].values[i])
        if base <= 0:
            continue
        skus = [s for s in wsum.index if sku_line.get(s) == line]
        tot = float(wsum[skus].sum()) if skus else 0.0
        dec = grow = score = np.nan
        if tot > 0:
            w = wsum[skus]
            po = hist.reindex(skus)[col]
            dec = float(w[po.isin(DEC)].sum()) / tot
            grow = float(w[po.isin(GROW)].sum()) / tot
            sc = pd.to_numeric(hist.reindex(skus)[score_col], errors='coerce').fillna(0.0)
            score = float((w.values * sc.values).sum()) / tot
        rows.append({'月': t, 'idx': idx, 'N': N, '产品线': line, '实际': actual,
                     'base': base, 'ratio': actual / base,
                     'dec_share': dec, 'grow_share': grow, 'score_w': score})
d = pd.DataFrame(rows)
d = d.dropna(subset=['dec_share', 'grow_share'])
print('样本: %d 线-折（%d 折 × %d 线）' % (len(d), d['idx'].nunique(), d['产品线'].nunique()))

print()
print('=== 诊断：误差比 ratio 与生命周期特征的相关（全样本）===')
for c in ['dec_share', 'grow_share', 'score_w']:
    print('  %-11s pearson r=%+.3f' % (c, d[['ratio', c]].corr().iloc[0, 1]))

def fit_predict(feats):
    res = []
    for idx in sorted(d['idx'].unique()):
        if idx < 6:
            continue
        tr, te = d[d['idx'] < idx], d[d['idx'] == idx]
        if len(tr) < 40 or len(te) == 0:
            continue
        X = np.column_stack([np.ones(len(tr))] + [tr[c].values for c in feats])
        y = np.clip(tr['ratio'].values, 0.25, 4.0)
        coef, *_ = np.linalg.lstsq(X, y, rcond=None)
        Xt = np.column_stack([np.ones(len(te))] + [te[c].values for c in feats])
        rh = np.clip(Xt @ coef, 0.5, 2.0)
        for (_, row), v in zip(te.iterrows(), rh):
            res.append({'月': row['月'], '产品线': row['产品线'], '实际': row['实际'],
                        'base': row['base'], 'corr': row['base'] * v})
    return pd.DataFrame(res)

def wape(dd, c):
    return (dd[c] - dd['实际']).abs().sum() / max(dd['实际'].sum(), 1e-9)

def smean(dd, c):
    g = dd.groupby('产品线').apply(
        lambda x: (x[c] - x['实际']).abs().sum() / max(x['实际'].sum(), 1e-9), include_groups=False)
    return g.mean()

print()
print('=== 增量测试（expanding，idx>=6 → 14 折；clip 预测比 [0.5,2.0]）===')
variants = {
    'V1 dec': ['dec_share'],
    'V2 dec+grow': ['dec_share', 'grow_share'],
    'V3 dec+grow+score': ['dec_share', 'grow_share', 'score_w'],
}
for name, feats in variants.items():
    rr = fit_predict(feats)
    if rr.empty:
        continue
    for seg, dd in [('全期', rr), ('2026', rr[rr['月'] >= '2026-01'])]:
        cs = dd.groupby('月')[['实际', 'base', 'corr']].sum()
        print('%-18s %-4s 线级金额加权 base %.1f%% → corr %.1f%% | 线级简单平均 %.1f%% → %.1f%% | 公司求和 %.1f%% → %.1f%%' % (
            name, seg, wape(dd, 'base')*100, wape(dd, 'corr')*100,
            smean(dd, 'base')*100, smean(dd, 'corr')*100,
            wape(cs, 'base')*100, wape(cs, 'corr')*100))
    rr.to_csv(OUT + r'\D2_生命周期因子_%s.csv' % name.replace(' ', '_'), index=False, encoding='utf-8-sig')

# 对照：combo_phase（公司口径）
e3 = pd.read_csv(OUT + r'\E3_节前月加成_对比.csv').dropna(subset=['combo_phase'])
e3['月'] = e3['月'].astype(str)
for seg in ['全期', '2026']:
    dd = e3 if seg == '全期' else e3[e3['月'] >= '2026-01']
    print('对照 combo_phase %-4s 公司口径 WAPE %.1f%%' % (seg, wape(dd, 'combo_phase')*100))
print()
print('明细已存: D2_生命周期因子_V*.csv')
