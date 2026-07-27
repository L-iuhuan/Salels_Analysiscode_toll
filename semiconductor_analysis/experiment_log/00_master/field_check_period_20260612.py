# -*- coding: utf-8 -*-
import pandas as pd
from pathlib import Path
path = Path(r'E:\3-其他资料\数据分析\semiconductor_analysis\data\财务分析-5月（6.3）.xlsx')
cols = ['发货日期','终端客户简称','终端客户名称_客户类别','客户订单号','ERP订单号','存货编码','存货名称','型号_产品线（新）','型号_产品品类','发货数量']
try:
    df = pd.read_excel(path, sheet_name='总表', usecols=lambda c: c in cols, engine='calamine')
except Exception:
    df = pd.read_excel(path, sheet_name='总表', usecols=lambda c: c in cols)
df['发货日期'] = pd.to_datetime(df['发货日期'], errors='coerce')
df['发货数量'] = pd.to_numeric(df['发货数量'], errors='coerce')
df = df[df['发货日期'].notna() & (df['发货数量'].fillna(0) > 0)].copy()
periods = {
    'all_clean': df,
    'history_2023-06_to_2026-05': df[(df['发货日期'] >= '2023-06-01') & (df['发货日期'] <= '2026-05-31')],
    'since_2024': df[df['发货日期'] >= '2024-01-01'],
}
for name, sub in periods.items():
    print('PERIOD', name, 'rows', len(sub))
    for c in ['终端客户简称','终端客户名称_客户类别','客户订单号','ERP订单号','存货编码','存货名称','型号_产品线（新）','型号_产品品类']:
        if c in sub.columns:
            miss = int(sub[c].isna().sum() + ((sub[c].astype(str).str.strip() == '').sum() if sub[c].dtype == 'object' else 0))
            print(f'{c}\t{miss}\t{miss/len(sub):.4%}\t{sub[c].nunique(dropna=True)}')
    print('---')
