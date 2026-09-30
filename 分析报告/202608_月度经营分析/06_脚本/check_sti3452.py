# -*- coding: utf-8 -*-
"""STI3452HFI 数据核查（显式列映射）"""
import sys
import pandas as pd
sys.stdout.reconfigure(encoding='utf-8')

df = pd.read_parquet(r'E:\3-其他资料\数据分析\sales_analytics_platform\output\silver\silver_cleaned_rows.parquet')
PC, CC, MC, RC, PC2 = '产品品种', '实际终端客户', '发货日期', '出货总金额', '利润'

sub = df[df[PC].astype(str).str.contains('STI3452', na=False)].copy()
print('STI3452* 行数:', len(sub), '| 品种名:', list(sub[PC].unique())[:5])
if len(sub) == 0:
    sys.exit(0)

sub['_m'] = sub[MC].astype(str).str[:7]
g = sub.groupby('_m').agg(收入万=(RC, 'sum'), 毛利万=(PC2, 'sum'), 行数=(RC, 'size'))
g['收入万'] = (g['收入万'] / 1e4).round(1)
g['毛利万'] = (g['毛利万'] / 1e4).round(1)
print('\n── 月度收入/毛利（万元）──')
print(g.tail(12).to_string())

sub12 = sub[sub['_m'] >= '2025-09']
gc = sub12.groupby(CC)[RC].sum().sort_values(ascending=False)
print('\n── 客户结构（近12月）──')
for k, v in gc.head(8).items():
    print('%s: %.1f万 (%.1f%%)' % (k, v / 1e4, v / gc.sum() * 100))
gp = sub12.groupby(CC)[PC2].sum().sort_values()
print('\n── 对应毛利（万元）──')
for k, v in gp.head(6).items():
    print('%s: %.1f万' % (k, v / 1e4))
