# -*- coding: utf-8 -*-
"""E16：SKU 级分配测试（线级锚定 × SKU 份额 vs SKU 直测）+ E12b 2026 分段校验"""
import sys
import numpy as np
import pandas as pd
sys.stdout.reconfigure(encoding='utf-8')

SILVER = r'E:\3-其他资料\数据分析\sales_analytics_platform\output\silver\silver_cleaned_rows.parquet'
OUT = r'E:\3-其他资料\数据分析\project_analysis\月度滚动预测_20260910'

df = pd.read_parquet(SILVER, columns=['发货日期', '金额', '型号_产品线（新）', '产品品种'])
df = df.rename(columns={'型号_产品线（新）': '产品线'})
df['月'] = pd.to_datetime(df['发货日期'], errors='coerce').dt.strftime('%Y-%m')
df = df.dropna(subset=['月'])
df['金额'] = pd.to_numeric(df['金额'], errors='coerce').fillna(0)

# ---------- E12b 2026 分段 ----------
r2 = pd.read_csv(OUT + r'\E12b_量价集成_对比.csv')
r26 = r2[r2['月'] >= '2026-01']

def w(c, d):
    return (d[c] - d['实际']).abs().sum() / d['实际'].sum()

print('=== E12b 2026 分段校验（n=%d）===' % len(r26))
print('combo: %.1f%% | combo_volxasp: %.1f%%' % (w('combo', r26)*100, w('combo_volxasp', r26)*100))

# ---------- E16 SKU 分配 ----------
sku = df.groupby(['产品线', '产品品种', '月'])['金额'].sum()
line_month = df.groupby(['产品线', '月'])['金额'].sum()
months_all = sorted(df['月'].unique())
test_months = [m for m in months_all if m >= '2025-01']
combo = r2.set_index('月')['combo'].to_dict()

results = []
for (line, skuname), ss in sku.groupby(level=[0, 1]):
    ss = ss.droplevel([0, 1]).sort_index()
    ss = ss.reindex(months_all, fill_value=0.0)   # r28 复核修复：日历月补零（零销售月不丢行）
    lg = line_month.loc[line].sort_index()
    lg = lg.reindex(months_all, fill_value=0.0)
    for t in test_months:
        if t not in combo:
            continue
        prev = [m for m in months_all if m < t][-3:]
        shist = ss[ss.index < t]
        lhist = lg[lg.index < t]
        if len(prev) < 3 or len(lhist) < 6 or float(shist.sum()) < 50e4:   # PIT 过滤：仅用 <t 累计
            continue
        direct = float(shist.iloc[-6:].mean())   # 日历 ma6（含零月）
        tot_prev = float(sum(lg.get(p, 0) for p in prev))
        share = (sum(ss.get(p, 0) for p in prev) / tot_prev) if tot_prev > 0 else 0.0
        line_ma6 = float(lhist.iloc[-6:].mean())
        alloc = line_ma6 * share
        actual = float(ss.get(t, 0.0))
        results.append({'月': t, '产品线': line, 'SKU': skuname, '实际': actual,
                        'direct': direct, 'alloc': alloc})
res = pd.DataFrame(results)
n_sku = res['SKU'].nunique()
print()
print('=== E16 SKU 级分配测试（%d SKU × %d 月 = %d 行）===' % (n_sku, len(test_months), len(res)))
print('SKU 直测 ma6:        WAPE %.1f%%' % (w('direct', res)*100))
print('线级锚定×份额分配:    WAPE %.1f%%' % (w('alloc', res)*100))
# 月度明细
mm = res.groupby('月').apply(lambda d: pd.Series({
    'direct': (d['direct']-d['实际']).abs().sum()/d['实际'].sum(),
    'alloc': (d['alloc']-d['实际']).abs().sum()/d['实际'].sum()}), include_groups=False)
print()
print('近8月明细:')
print(mm.tail(8).to_string())
res.to_csv(OUT + r'\E16_SKU分配_对比.csv', index=False, encoding='utf-8-sig')
print()
print('明细已存: E16_SKU分配_对比.csv')
