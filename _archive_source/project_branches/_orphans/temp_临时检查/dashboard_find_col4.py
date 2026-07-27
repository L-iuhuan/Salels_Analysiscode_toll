import pandas as pd
path = r'C:\Users\45091\Desktop\工作文件\semiconductor_analysis\data\财务分析-5月（6.3）.xlsx'

# Check sheets
xl = pd.ExcelFile(path)
print(f"Sheets: {xl.sheet_names}")

# Read sheet "总表"
df = pd.read_excel(path, sheet_name="总表", nrows=1)
all_cols = list(df.columns)
with open('col_output.txt', 'w', encoding='utf-8') as f:
    f.write(f"Sheet: 总表, Total columns: {len(all_cols)}\n\n")
    f.write("Columns containing '品类' or '品线':\n")
    for i, c in enumerate(all_cols):
        if '品类' in str(c) or '品线' in str(c):
            f.write(f"  [{i}] {c}\n")
    f.write("\nLast 5 columns:\n")
    for c in all_cols[-5:]:
        f.write(f"  {c}\n")
    f.write(f"\nTotal: {len(all_cols)} columns, last col: {all_cols[-1]}")
print("Done")
