import pandas as pd, json, re, os

base = os.path.dirname(os.path.abspath(__file__))

# 1. Verify silver YTD
print("=== 1. Silver YTD验证 ===")
scm = pd.read_csv(os.path.join(base, '..', 'output', 'silver', 'silver_customer_monthly.csv'))
scm['_m'] = scm['_月'].astype(str)
latest = scm['_m'].max()
ytd = scm[(scm['_m'] >= '2026-01') & (scm['_m'] <= latest)]
r = ytd['rev_sum'].sum()
p = ytd['profit_clip_sum'].sum()
print(f"Silver YTD: rev={r:.0f}元={r/1e4:.1f}万, profit={p:.0f}元={p/1e4:.1f}万, mg={p/r*100:.2f}%")

# 2. Compare with raw Excel
print("\n=== 2. Raw Excel 24-26对比 ===")
raw = pd.read_excel(r'C:\Users\45091\Desktop\工作文件\semiconductor_analysis\data\财务分析-5月（6.3）.xlsx', sheet_name='24-26')
raw['_d'] = pd.to_datetime(raw['发货日期'], errors='coerce')
raw_2026 = raw[(raw['_d'] >= '2026-01-01') & (raw['_d'] <= '2026-05-31')]
raw_r = pd.to_numeric(raw_2026['RMB 未税金额小计'], errors='coerce').sum()
raw_p = pd.to_numeric(raw_2026['利润'], errors='coerce').sum()
print(f"Raw 2026: rev={raw_r:.0f}元={raw_r/1e4:.1f}万, profit={raw_p:.0f}元={raw_p/1e4:.1f}万, mg={raw_p/raw_r*100:.2f}%")
print(f"Diff rev: {(raw_r-r)/1e4:.1f}万 ({(raw_r-r)/raw_r*100:.2f}%)")
print(f"Diff profit: {(raw_p-p)/1e4:.1f}万 ({(raw_p-p)/raw_p*100:.2f}%)")

# 3. HTML audit
print("\n=== 3. HTML审计 ===")
html = open(os.path.join(base, 'dashboard_a.html'), encoding='utf-8').read()
m = re.search(r'var B_CUSTS = (\[.*?\]);', html, re.DOTALL)
b = json.loads(m.group(1))
mismatches = [(c['n'], c.get('cc',0), len(c.get('cat_rev',{}))) for c in b if c.get('cc',0) != len(c.get('cat_rev',{}))]
print(f"客户数: {len(b)}")
print(f"品类数≠饼图: {len(mismatches)}")
pv = re.search(r'本年度毛利.*?(\d[\d,]+)', html)
cv = re.search(r'本年度成本.*?(\d[\d,]+)', html)
mv = re.search(r'毛利率 ([\d.]+)%', html)
if pv and cv and mv:
    print(f"HTML KPI: 毛利={pv.group(1)}万, 成本={cv.group(1)}万, 毛利率={mv.group(1)}%")

# 4. New product audit
new_custs = sum(1 for c in b if len(c.get('new_detail',[])) > 0)
print(f"\n=== 4. 新品审计 ===")
print(f"有新品客户: {new_custs}")
# Check mismatch
nm_mismatch = sum(1 for c in b if c.get('new_count',0) != len(c.get('new_detail',[])))
print(f"新品count≠detail: {nm_mismatch}")

# Save detailed report
with open(os.path.join(base, 'audit_output.txt'), 'w', encoding='utf-8') as f:
    f.write(f"=== 审计报告 ===\n\n")
    f.write(f"1. YTD数据\n")
    f.write(f"   Silver: rev={r/1e4:.1f}万 profit={p/1e4:.1f}万 mg={p/r*100:.2f}%\n")
    f.write(f"   Raw:    rev={raw_r/1e4:.1f}万 profit={raw_p/1e4:.1f}万 mg={raw_p/raw_r*100:.2f}%\n")
    f.write(f"   差异: rev={(raw_r-r)/1e4:.1f}万 ({(raw_r-r)/raw_r*100:.2f}%) profit={(raw_p-p)/1e4:.1f}万\n")
    f.write(f"\n2. HTML数据完整性\n")
    f.write(f"   客户数: {len(b)}\n")
    f.write(f"   品类cc≠pie: {len(mismatches)}\n")
    f.write(f"   新品count≠detail: {nm_mismatch}\n")
    if mismatches:
        for name, cc, pie in mismatches[:10]:
            f.write(f"     {name}: cc={cc} pie={pie}\n")
    f.write(f"\n3. 总计: 全部检查{'通过' if len(mismatches)==0 and nm_mismatch==0 else '有问题'}\n")
    f.write(f"   YTD与Raw差异: {(raw_r-r)/raw_r*100:.2f}% (来自pipeline清洗)\n")

print("\nDone. 查看 audit_output.txt")
