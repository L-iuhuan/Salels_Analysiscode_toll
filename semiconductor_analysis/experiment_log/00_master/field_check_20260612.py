# -*- coding: utf-8 -*-
import pandas as pd
from pathlib import Path

path = Path(r'E:\3-其他资料\数据分析\semiconductor_analysis\data\财务分析-5月（6.3）.xlsx')
cols = [
    '发货日期','型号_产品线（新）','存货编码','存货名称','型号_产品品类',
    '终端客户简称','终端客户名称_客户类别','发货数量','RMB 未税金额小计',
    '总成本','利润','未税单价','单位成本','客户订单号','ERP订单号'
]
try:
    import python_calamine  # noqa: F401
    df = pd.read_excel(path, sheet_name='总表', usecols=lambda c: c in cols, engine='calamine')
except Exception:
    df = pd.read_excel(path, sheet_name='总表', usecols=lambda c: c in cols)
print('rows', len(df))
print('cols', list(df.columns))
for c in df.columns:
    s = df[c]
    blank = (s.astype(str).str.strip() == '').sum() if s.dtype == 'object' else 0
    miss = int(s.isna().sum() + blank)
    print(f'{c}\tmissing={miss}\tmissing_rate={miss/len(df):.4%}\tnunique={s.nunique(dropna=True)}')
print('--- sku checks ---')
if '存货编码' in df and '存货名称' in df:
    code_missing_name_ok = df['存货编码'].isna() & df['存货名称'].notna() & (df['存货名称'].astype(str).str.strip() != '')
    print('存货编码缺失但存货名称不缺', int(code_missing_name_ok.sum()))
    print('一个存货编码对应多个存货名称数', int(df.dropna(subset=['存货编码']).groupby('存货编码')['存货名称'].nunique().gt(1).sum()))
    print('一个存货名称对应多个存货编码数', int(df.dropna(subset=['存货名称']).groupby('存货名称')['存货编码'].nunique().gt(1).sum()))
print('--- customer checks ---')
if '终端客户简称' in df:
    print('终端客户简称缺失行数', int(df['终端客户简称'].isna().sum()))
if '终端客户名称_客户类别' in df:
    print('客户类别缺失行数', int(df['终端客户名称_客户类别'].isna().sum()))
if '客户订单号' in df:
    print('客户订单号缺失行数', int(df['客户订单号'].isna().sum()))
if 'ERP订单号' in df:
    print('ERP订单号缺失行数', int(df['ERP订单号'].isna().sum()))
