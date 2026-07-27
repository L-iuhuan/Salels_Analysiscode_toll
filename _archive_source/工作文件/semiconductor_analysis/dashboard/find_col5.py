import pandas as pd
path = r'C:\Users\45091\Desktop\工作文件\semiconductor_analysis\data\财务分析-5月（6.3）.xlsx'
xl = pd.ExcelFile(path)

with open('col_output.txt', 'w', encoding='utf-8') as f:
    for i, sn in enumerate(xl.sheet_names):
        try:
            df = pd.read_excel(path, sheet_name=i, nrows=1)
            ncols = len(df.columns)
            f.write(f"\nSheet[{i}] '{sn}' -> {ncols} cols\n")
            if ncols > 50:
                # This is the main data sheet
                last_cols = list(df.columns[-5:])
                f.write(f"  Last 5 cols: {last_cols}\n")
                # Find 品类 cols
                for j, c in enumerate(df.columns):
                    if '品类' in str(c) or '品线' in str(c):
                        f.write(f"  [{j}] {c}\n")
        except Exception as e:
            f.write(f"Sheet[{i}] '{sn}' -> ERROR: {e}\n")
print("Done")
