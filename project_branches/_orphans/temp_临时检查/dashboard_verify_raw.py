import pandas as pd

# Read raw "24-26" sheet
path = r'C:\Users\45091\Desktop\工作文件\semiconductor_analysis\data\财务分析-5月（6.3）.xlsx'
raw = pd.read_excel(path, sheet_name='24-26')

with open('audit_output.txt', 'w', encoding='utf-8') as f:
    f.write(f"Raw columns: {len(raw.columns)}\n")
    f.write(f"Raw rows: {len(raw)}\n")

    # Find key columns
    f.write(f"\nKey columns:\n")
    for i, c in enumerate(raw.columns):
        if any(kw in str(c) for kw in ['金额','日期','数量','编号','品种','客户','利润','成本']):
            f.write(f"  [{i}] {c}\n")

    # Find 2026 data
    date_col = None
    for c in raw.columns:
        if '日期' in str(c) or '发货' in str(c):
            date_col = c
            break

    if date_col:
        raw['_d'] = pd.to_datetime(raw[date_col], errors='coerce')
        raw_2026 = raw[(raw['_d'] >= '2026-01-01') & (raw['_d'] <= '2026-05-31')]
        f.write(f"\n2026 rows: {len(raw_2026)}")

        # Sum revenue (金额)
        for c in raw.columns:
            if '金额' in str(c):
                rev = pd.to_numeric(raw_2026[c], errors='coerce').sum()
                f.write(f"\n2026 [{c}] sum: {rev:.2f} = {rev/1e4:.1f}万")

        # Sum profit
        for c in raw.columns:
            if '利润' in str(c):
                prof = pd.to_numeric(raw_2026[c], errors='coerce').sum()
                f.write(f"\n2026 [{c}] sum: {prof:.2f} = {prof/1e4:.1f}万")

        # Also check quantity
        for c in raw.columns:
            if '数量' in str(c):
                qty = pd.to_numeric(raw_2026[c], errors='coerce').sum()
                f.write(f"\n2026 [{c}] sum: {qty:.0f}")

        # Negative rows
        f.write(f"\n2026 negative rev rows: {(pd.to_numeric(raw_2026.get('金额',raw_2026.iloc[:,-4]), errors='coerce') < 0).sum()}")
    else:
        f.write("\nNo date column found!")

print("Done")
