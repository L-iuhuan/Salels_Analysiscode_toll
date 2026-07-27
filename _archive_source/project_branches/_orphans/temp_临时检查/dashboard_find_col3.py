import pandas as pd
path = r'C:\Users\45091\Desktop\工作文件\semiconductor_analysis\data\财务分析-5月（6.3）.xlsx'

# Read ALL columns (no nrows limit)
df = pd.read_excel(path, nrows=1)
all_cols = list(df.columns)
with open('col_output.txt', 'w', encoding='utf-8') as f:
    f.write(f"Total columns: {len(all_cols)}\n\n")
    f.write("ALL columns:\n")
    for i, c in enumerate(all_cols):
        f.write(f"  [{i}] {c}\n")
    f.write("\n\nColumns containing '品类' or '品线':\n")
    for i, c in enumerate(all_cols):
        if '品类' in str(c) or '品线' in str(c):
            f.write(f"  [{i}] {c}\n")
print("Done")
