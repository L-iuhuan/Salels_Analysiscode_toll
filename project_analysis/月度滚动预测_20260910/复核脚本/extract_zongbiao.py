# -*- coding: utf-8 -*-
"""探针+抽取：总表（长历史）→ 2024 之前月度序列"""
import sys
import os
import time
import pandas as pd
sys.path.insert(0, r'E:\3-其他资料\数据分析\sales_analytics_platform\processing')
sys.stdout.reconfigure(encoding='utf-8')
from shared.excel_com import read_encrypted_com

DATA_DIR = r'E:\3-其他资料\数据分析\sales_analytics_platform\data'
OUT = r'E:\3-其他资料\数据分析\project_analysis\月度滚动预测_20260910'
xl = [f for f in os.listdir(DATA_DIR) if f.endswith('.xlsx') and not f.startswith('~$')]
path = os.path.join(DATA_DIR, max(xl, key=lambda f: os.path.getmtime(os.path.join(DATA_DIR, f))))
print('源: %s' % path)

t0 = time.time()
df, used = read_encrypted_com(path, '总表', strict=True)
if df is None:
    print('未找到"总表" sheet；读取首 sheet 看名字：')
    df0, used0 = read_encrypted_com(path, '总表', strict=False)
    print('读取到 sheet=%s, 形状=%s' % (used0, df0.shape if df0 is not None else None))
    if df0 is not None:
        print('首sheet列: %s' % list(df0.columns)[:60])
    sys.exit(0)

print('读取用时 %.1fs | sheet=%s | 形状 %s' % (time.time()-t0, used, df.shape))
print('列: %s' % list(df.columns))

dc = None
for c in df.columns:
    if '日期' in str(c):
        dc = c
        break
amt = None
for cand in ['金额', '出货总金额', 'RMB 未税金额小计', '利润']:
    if cand in df.columns:
        amt = cand
        break
print('日期列: %s | 金额列: %s' % (dc, amt))

if dc and amt:
    df['_dt'] = pd.to_datetime(df[dc], errors='coerce')
    df = df.dropna(subset=['_dt'])
    df['_amt'] = pd.to_numeric(df[amt], errors='coerce').fillna(0)
    df['_ym'] = df['_dt'].dt.strftime('%Y-%m')
    m = df.groupby('_ym')['_amt'].sum().sort_index()
    print('月度范围: %s ~ %s (%d 个月)' % (m.index[0], m.index[-1], len(m)))
    print()
    print('月度合计(万):')
    for ym, v in m.items():
        print('%s: %.0f' % (ym, v/1e4))
    pre = m[m.index < '2024-01']
    print()
    print('2024之前: %d 个月 (%s ~ %s)' % (len(pre), pre.index[0] if len(pre) else '—', pre.index[-1] if len(pre) else '—'))
    out = pd.DataFrame({'月': m.index, '金额': m.values})
    out.to_parquet(os.path.join(OUT, '总表_月度长序列.parquet'), index=False)
    out.to_csv(os.path.join(OUT, '总表_月度长序列.csv'), index=False, encoding='utf-8-sig')
    print('已存: 总表_月度长序列.parquet/.csv (%d 月)' % len(out))
