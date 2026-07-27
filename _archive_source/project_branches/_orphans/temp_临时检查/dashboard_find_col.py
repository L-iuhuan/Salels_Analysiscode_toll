import pandas as pd
path = r'C:\Users\45091\Desktop\工作文件\semiconductor_analysis\data\财务分析-5月（6.3）.xlsx'
df = pd.read_excel(path, nrows=3)
# Find ALL columns with 品类 or 品线
for i, c in enumerate(df.columns):
    if '品类' in str(c) or '品线' in str(c):
        print(f"Col[{i}]: [{c}] - sample: {df[c].head(2).tolist()}")
# Also print last 3 columns
print(f"\n最后3列: {list(df.columns[-3:])}")
