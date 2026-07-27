# -*- coding: utf-8 -*-
import pandas as pd
sp = pd.read_pickle('recession_risk_opt/data/samples.pkl')
print('date_month sample:', sp['date_month'].head(3).tolist())
print('date_month dtype:', sp['date_month'].dtype)
print('product_id sample:', sp['product_id'].head(3).tolist())
print('product_id dtype:', sp['product_id'].dtype)

# check date format
print('date_month format examples:')
for d in sp['date_month'].head(5):
    print(f'  {repr(d)}')

# Check f1f data
use_cols = ['发货日期', '存货名称', '出货总金额', '成本', '利润']
df = pd.read_excel('data/所有的出货明细5.9.xlsx', usecols=use_cols, nrows=5000)
product_ids = set(sp['product_id'].unique())
df = df[df['存货名称'].isin(product_ids)]
df['年月'] = df['发货日期'].dt.to_period('M').astype(str)
df = df.rename(columns={'存货名称': 'product_id'})

print()
print('年月 sample:', df['年月'].head(3).tolist())
print('年月 dtype:', df['年月'].dtype)

# Check merge compatibility
print()
print(f'sp product_id dtype: {sp["product_id"].dtype}')
print(f'df product_id dtype: {df["product_id"].dtype}')
print(f'sp product_id[0] type: {type(sp["product_id"].iloc[0])}')
print(f'df product_id[0] type: {type(df["product_id"].iloc[0])}')
