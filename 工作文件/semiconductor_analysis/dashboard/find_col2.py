import pandas as pd
path = r'C:\Users\45091\Desktop\工作文件\semiconductor_analysis\data\财务分析-5月（6.3）.xlsx'
df = pd.read_excel(path, nrows=3)
results = []
results.append(f"Total columns: {len(df.columns)}")
for i, c in enumerate(df.columns):
    if '品类' in str(c) or '品线' in str(c):
        results.append(f"Col[{i}]: [{c}]")
# Save to file
with open('col_output.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(results))
print("Done. Check col_output.txt")
