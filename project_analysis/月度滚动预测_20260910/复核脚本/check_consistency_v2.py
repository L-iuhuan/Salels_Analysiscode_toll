# -*- coding: utf-8 -*-
"""口径核查v2：总表出货总金额 vs silver 出货总金额 vs silver 金额；修 parquet 保存"""
import sys
import os
import pandas as pd
import numpy as np
sys.path.insert(0, r'E:\3-其他资料\数据分析\sales_analytics_platform\processing')
sys.stdout.reconfigure(encoding='utf-8')
from shared.excel_com import read_encrypted_com

DATA_DIR = r'E:\3-其他资料\数据分析\sales_analytics_platform\data'
SILVER = r'E:\3-其他资料\数据分析\sales_analytics_platform\output\silver\silver_cleaned_rows.parquet'
WH = r'E:\3-其他资料\数据分析\sales_analytics_platform\data_warehouse\历史总表_202001_202605'

xl = [f for f in os.listdir(DATA_DIR) if f.endswith('.xlsx') and not f.startswith('~$')]
path = os.path.join(DATA_DIR, max(xl, key=lambda f: os.path.getmtime(os.path.join(DATA_DIR, f))))

df, used = read_encrypted_com(path, '总表', strict=True)
df['_dt'] = pd.to_datetime(df['发货日期'], errors='coerce')
df = df.dropna(subset=['_dt'])
df['_amt'] = pd.to_numeric(df['出货总金额'], errors='coerce').fillna(0)
df['_ym'] = df['_dt'].dt.strftime('%Y-%m')
zb = df.groupby('_ym')['_amt'].sum().sort_index()

sv = pd.read_parquet(SILVER)
sv['_dt'] = pd.to_datetime(sv['发货日期'], errors='coerce')
sv['_ym'] = sv['_dt'].dt.strftime('%Y-%m')
sv['_ch'] = pd.to_numeric(sv['出货总金额'], errors='coerce').fillna(0)
sv['_je'] = pd.to_numeric(sv['金额'], errors='coerce').fillna(0)
sv_ch = sv.groupby('_ym')['_ch'].sum()
sv_je = sv.groupby('_ym')['_je'].sum()

print('=== 重叠期对比 (2024-01~2026-05)，单位万 ===')
print('%-8s %9s %9s %9s %7s %7s' % ('月', '总表', 'sv出货', 'sv金额', '差A%', '差B%'))
dA, dB = [], []
for ym in sorted(set(zb.index) & set(sv_ch.index)):
    if ym < '2024-01' or ym > '2026-05':
        continue
    a, b, c = zb[ym]/1e4, sv_ch[ym]/1e4, sv_je[ym]/1e4
    da = (a-b)/b*100 if b else np.nan
    db = (a-c)/c*100 if c else np.nan
    dA.append(abs(da)); dB.append(abs(db))
    print('%-8s %9.0f %9.0f %9.0f %7.1f %7.1f' % (ym, a, b, c, da, db))
print('\nvs sv出货总金额: 平均|差| %.2f%% 最大 %.2f%%' % (np.mean(dA), np.max(dA)))
print('vs sv金额:       平均|差| %.2f%% 最大 %.2f%%' % (np.mean(dB), np.max(dB)))

# silver 2026-06~08 两口径
print('\nsilver 2026-06~08: 出货=%s 金额=%s' % (
    {ym: round(sv_ch.get(ym, 0)/1e4) for ym in ['2026-06','2026-07','2026-08']},
    {ym: round(sv_je.get(ym, 0)/1e4) for ym in ['2026-06','2026-07','2026-08']}))

# 保存总表原始 parquet：object 列尝试数值化，失败转 str
raw = df.drop(columns=['_dt', '_amt', '_ym'])
for c in raw.columns:
    if raw[c].dtype == object:
        conv = pd.to_numeric(raw[c], errors='coerce')
        # 若原本非空值大多能转数值，则数值化；否则转字符串
        orig_nn = raw[c].notna().sum()
        if orig_nn > 0 and conv.notna().sum() / orig_nn > 0.9:
            raw[c] = conv
        else:
            raw[c] = raw[c].astype(str).where(raw[c].notna(), None)
os.makedirs(WH, exist_ok=True)
raw.to_parquet(os.path.join(WH, 'zongbiao_frozen_202605.parquet'), index=False)
print('\n原始总表已存: %s (%d行 x %d列)' % (os.path.join(WH, 'zongbiao_frozen_202605.parquet'), len(raw), len(raw.columns)))

# 拼接长序列（用 silver 出货总金额口径对齐总表）：2020-01~2023-12 总表；2024-01 起 silver出货总金额
combined = {}
for ym, v in zb.items():
    if ym < '2024-01':
        combined[ym] = v
for ym, v in sv_ch.items():
    if ym >= '2024-01':
        combined[ym] = v
cs = pd.Series(combined).sort_index()
out = pd.DataFrame({'月': cs.index, '金额': cs.values})
out.to_parquet(os.path.join(WH, 'company_monthly_202001_202608.parquet'), index=False)
out.to_csv(os.path.join(WH, 'company_monthly_202001_202608.csv'), index=False, encoding='utf-8-sig')
print('拼接长序列已存: company_monthly_202001_202608 (%d月: %s~%s)' % (len(out), cs.index[0], cs.index[-1]))
