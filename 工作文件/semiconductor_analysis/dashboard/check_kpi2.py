import json, re, os
base = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(base, 'dashboard_a.html'), encoding='utf-8') as f:
    html = f.read()

# The KPI values are hardcoded in HTML - let me find them
import re
# Find the KPI card values
patterns = {
    '收入': r'本年度收入.*?<div class="kv">([\d,]+)',
    '利润': r'本年度利润.*?<div class="kv">([\d,]+)',
    '毛利': r'本年度毛利.*?<div class="kv">([\d,]+)',
    '毛利率': r'毛利率 ([\d.]+)%',
}
with open('audit_output.txt', 'w', encoding='utf-8') as f:
    for name, pat in patterns.items():
        m = re.search(pat, html)
        if m:
            val = m.group(1).replace(',','')
            f.write(f"{name}: {val}\n")

    # Extract from embedded data to verify
    m2 = re.search(r'var TREND = (\{.*?\});', html, re.DOTALL)
    if m2:
        trend = json.loads(m2.group(1))
        f.write(f"\nTREND 2026 revenue sum: {sum(v for v in trend.get('r26',[]) if v)}")
        f.write(f"\nTREND 2026 profit sum: {sum(v for v in trend.get('p26',[]) if v)}")
    else:
        f.write("\nTREND not found")
print("Done")
