import pandas as pd
import time
t0 = time.time()

# Only read key columns to speed up
cols_use = [0, 7, 9, 10, 12]
df = pd.read_excel('data/出货明细修正版.xlsx', sheet_name=0, usecols=cols_use)
print(f'Loaded: {len(df)} rows in {time.time()-t0:.1f}s')
print(f'Columns: {list(df.columns)}')

for c in df.columns:
    print(f'  {c!r}: dtype={df[c].dtype}, non-null={df[c].notna().sum()}/{len(df)}, unique={df[c].nunique()}')
    print(f'    sample: {df[c].dropna().iloc[:3].tolist()}')
    
# Check date range
col0 = df.iloc[:, 0]
print(f'\n  日期 range: {col0.min()} to {col0.max()}')
print(f'  日期 unique months: {col0.dt.to_period("M").nunique()}')
