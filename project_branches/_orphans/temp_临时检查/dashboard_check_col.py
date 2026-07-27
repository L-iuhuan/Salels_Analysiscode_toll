import pandas as pd

# Check original Excel last column
df = pd.read_excel(r'C:\Users\45091\Desktop\工作文件\semiconductor_analysis\data\财务分析-5月（6.3）.xlsx', nrows=2)
last_col = df.columns[-1]
print(f"ERP原始文件最后一列: {last_col}")
cols_cat = [c for c in df.columns if '品类' in str(c) or '品线' in str(c)]
print(f"ERP品类相关列: {cols_cat}")

# Check ERP_COL_MAP in settings
import sys
sys.path.insert(0, r'C:\Users\45091\Desktop\工作文件\semiconductor_analysis')
from config.settings import ERP_COL_MAP
for k,v in ERP_COL_MAP.items():
    if '品类' in k or '品线' in k or '型号' in k:
        print(f"ERP_COL_MAP: {k} -> {v}")

# Check bridge table
cxp = pd.read_csv(r'C:\Users\45091\Desktop\工作文件\semiconductor_analysis\output\silver\silver_customer_x_product.csv', nrows=3)
cols2 = [c for c in cxp.columns if '品类' in str(c) or '品线' in str(c) or '型号' in str(c)]
print(f"桥接表: {cols2}")

# Check which column in bridge matches "产品品类（新）"
for c in cols2:
    vals = cxp[c].dropna().head(3).tolist()
    print(f"  {c}: {vals}")
