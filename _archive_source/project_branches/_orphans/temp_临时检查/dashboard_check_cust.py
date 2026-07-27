import pandas as pd

raw = pd.read_excel(r'C:\Users\45091\Desktop\工作文件\semiconductor_analysis\data\财务分析-5月（6.3）.xlsx',
    sheet_name='24-26', usecols=['发货日期','RMB 未税金额小计','利润','终端客户简称','终端客户名称_客户类别'])
raw['_d'] = pd.to_datetime(raw['发货日期'], errors='coerce')
raw['_rev'] = pd.to_numeric(raw['RMB 未税金额小计'], errors='coerce').fillna(0)
raw['_profit'] = pd.to_numeric(raw['利润'], errors='coerce').fillna(0)

r26 = raw[(raw['_d']>='2026-01-01')&(raw['_d']<='2026-05-31')]

# KA customers
ka = r26[r26['终端客户名称_客户类别'].astype(str).str.contains('KA', na=False)]
print(f"KA customers: {ka['终端客户简称'].nunique()}")
print(f"KA total rev: {ka['_rev'].sum():.2f} = {ka['_rev'].sum()/1e4:.2f}万")
print(f"KA total profit: {ka['_profit'].sum():.2f} = {ka['_profit'].sum()/1e4:.2f}万")

# Per-KA-customer YTD
ka_cust = ka.groupby('终端客户简称').agg(ytd_rev=('_rev','sum'), ytd_profit=('_profit','sum'))
ka_cust = ka_cust.sort_values('ytd_rev', ascending=False)
print(f"\nTop 5 KA customers by YTD rev:")
for name, row in ka_cust.head(5).iterrows():
    mg = row['ytd_profit']/row['ytd_rev']*100 if row['ytd_rev']>0 else 0
    print(f"  {name}: rev={row['ytd_rev']:.2f}元={row['ytd_rev']/1e4:.4f}万 profit={row['ytd_profit']:.2f}元={row['ytd_profit']/1e4:.4f}万 mg={mg:.2f}%")

# AA customers
aa = r26[r26['终端客户名称_客户类别'].astype(str).str.contains('AA', na=False)]
print(f"\nAA customers: {aa['终端客户简称'].nunique()}")
print(f"AA total rev: {aa['_rev'].sum():.2f} = {aa['_rev'].sum()/1e4:.2f}万")

with open('audit_output.txt', 'w', encoding='utf-8') as f:
    f.write(f"KA: {ka_cust.head(5).to_string()}\n")
    f.write(f"KA total: rev={ka['_rev'].sum()/1e4:.2f}万 profit={ka['_profit'].sum()/1e4:.2f}万\n")
print("\nDone")
