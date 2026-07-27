import pandas as pd

scm = pd.read_csv(r'C:\Users\45091\Desktop\工作文件\semiconductor_analysis\output\silver\silver_customer_monthly.csv')
scm['_m'] = scm['_月'].astype(str)
latest = scm['_m'].max()
print(f"Latest month: {latest}")
print(f"Total rows: {len(scm)}")

# YTD 2026
ytd = scm[(scm['_m'] >= '2026-01') & (scm['_m'] <= latest)]
print(f"\nYTD rows: {len(ytd)}")
print(f"Months in YTD: {sorted(ytd['_m'].unique())}")

# Sum
r = ytd['rev_sum'].sum()
p = ytd['profit_clip_sum'].sum()
print(f"\nYTD rev_sum: {r:.2f} = {r/1e4:.1f}万")
print(f"YTD profit_clip_sum: {p:.2f} = {p/1e4:.1f}万")
print(f"Margin: {p/r*100:.2f}%")

# Check by month
monthly = ytd.groupby('_m').agg(rev=('rev_sum','sum'), profit=('profit_clip_sum','sum'))
print(f"\nMonthly breakdown:")
for _, row in monthly.iterrows():
    print(f"  {row.name}: rev={row['rev']/1e4:.0f}万 profit={row['profit']/1e4:.0f}万 mg={row['profit']/row['rev']*100:.1f}%")

# Also check: was the silver rebuilt properly?
print(f"\nTotal unique customers: {scm['客户编号'].nunique()}")
print(f"Total months: {sorted(scm['_m'].unique())}")
