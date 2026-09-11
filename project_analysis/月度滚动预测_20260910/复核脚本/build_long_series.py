# -*- coding: utf-8 -*-
"""拼接金额口径长序列：2020-01~2023-12 总表RMB未税 + 2024-01~2026-08 silver金额
产出：公司月度 + 线级月度 长序列"""
import pandas as pd
import numpy as np
import os

WH = r'E:\3-其他资料\数据分析\sales_analytics_platform\data_warehouse\历史总表_202001_202605'
SILVER = r'E:\3-其他资料\数据分析\sales_analytics_platform\output\silver\silver_cleaned_rows.parquet'
LINE_COL = '型号_产品线（新）'

zb = pd.read_parquet(os.path.join(WH, 'zongbiao_frozen_202605.parquet'))
zb['_ym'] = pd.to_datetime(zb['发货日期'], errors='coerce').dt.strftime('%Y-%m')
zb['_amt'] = pd.to_numeric(zb['RMB 未税金额小计'], errors='coerce').fillna(0)
zb = zb[zb['_ym'] < '2024-01']  # 历史段

sv = pd.read_parquet(SILVER)
sv['_ym'] = pd.to_datetime(sv['发货日期'], errors='coerce').dt.strftime('%Y-%m')
sv['_amt'] = pd.to_numeric(sv['金额'], errors='coerce').fillna(0)

# === 公司月度 ===
comp = pd.concat([
    zb.groupby('_ym')['_amt'].sum(),
    sv.groupby('_ym')['_amt'].sum(),
]).sort_index()
out = pd.DataFrame({'月': comp.index, '金额': comp.values})
out.to_parquet(os.path.join(WH, 'company_monthly_rmb_202001_202608.parquet'), index=False)
out.to_csv(os.path.join(WH, 'company_monthly_rmb_202001_202608.csv'), index=False, encoding='utf-8-sig')
print('公司月度长序列: %d月 (%s~%s)' % (len(out), comp.index[0], comp.index[-1]))

# === 线级月度 ===
zb_l = zb.groupby([LINE_COL, '_ym'])['_amt'].sum().rename('金额').reset_index()
sv_l = sv.groupby([LINE_COL, '_ym'])['_amt'].sum().rename('金额').reset_index()
line = pd.concat([zb_l, sv_l]).groupby([LINE_COL, '_ym'])['金额'].sum().reset_index()
line.columns = ['产品线', '月', '金额']
line.to_parquet(os.path.join(WH, 'line_monthly_rmb_202001_202608.parquet'), index=False)
print('线级月度长序列: %d行, %d条线' % (len(line), line['产品线'].nunique()))

# === 年度概览 ===
comp_y = comp.groupby(comp.index.str[:4]).sum()/1e4
print('\n年度合计(亿):')
for y, v in comp_y.items():
    print('  %s: %.2f' % (y, v/1e4))
print('\n2020 明显低——需判断是否业务起步年/疫情年')

# === 季节指数（按自然月，中位数口径，剔除2020起步年另算） ===
dfm = out.copy()
dfm['年'] = dfm['月'].str[:4]
dfm['月序'] = dfm['月'].str[5:7].astype(int)
for excl in [False, True]:
    d = dfm[~dfm['月'].str.startswith('2020')] if excl else dfm
    yearly = d.groupby('年')['金额'].transform('sum') if False else None
    # 每年月均值=该年合计/12，季节指数=当月/年均
    d = d.copy()
    yavg = d.groupby('年')['金额'].transform('mean')
    d['si'] = d['金额']/yavg
    si = d.groupby('月序')['si'].agg(['median','mean','count'])
    tag = '剔除2020' if excl else '含2020'
    print('\n=== 季节指数（%s, 每年12个月归一） ===' % tag)
    print('月: ' + ' '.join('%6d' % m for m in si.index))
    print('中位: ' + ' '.join('%6.2f' % v for v in si['median']))
    print('均值: ' + ' '.join('%6.2f' % v for v in si['mean']))
    print('n:   ' + ' '.join('%6d' % v for v in si['count']))

# === 春节月漂移 ===
cny = {'2020':'2020-01','2021':'2021-02','2022':'2022-02','2023':'2023-01','2024':'2024-02','2025':'2025-01','2026':'2026-02'}
print('\n=== 春节所在月及前后月（万） ===')
for y, m in cny.items():
    yy = pd.Period(m, freq='M')
    v_pre = comp.get(str(yy-1), np.nan)/1e4
    v_cur = comp.get(m, np.nan)/1e4
    v_post = comp.get(str(yy+1), np.nan)/1e4
    print('%s 春节=%s: 前月 %.0f | 当月 %.0f | 后月 %.0f | 当月/前后均 %.2f' % (
        y, m, v_pre, v_cur, v_post, v_cur/((v_pre+v_post)/2)))
