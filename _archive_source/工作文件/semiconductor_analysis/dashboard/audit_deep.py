import json, os

base = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(base, 'dashboard_a.html'), encoding='utf-8') as f:
    html = f.read()

import re
m = re.search(r'var B_CUSTS = (\[.*?\]);', html, re.DOTALL)
b_custs = json.loads(m.group(1))

# Find DCE T and 大华集团
targets = ['CETV', '大华集团']
with open(os.path.join(base, 'audit_output.txt'), 'w', encoding='utf-8') as f:
    for c in b_custs:
        if c['n'] in targets or 'CVTE' in c['n'] or '大华' in c['n'] or 'CET' in c['n']:
            cr = c.get('cat_rev', {})
            cc = c.get('cc', 0)
            f.write(f"\n{c['n']}: cc={cc}, pie_items={len(cr)}\n")
            # Check for zero values
            zeros = [(k,v) for k,v in cr.items() if v <= 0]
            f.write(f"  Zero-value cats: {len(zeros)}\n")
            for k, v in cr.items():
                f.write(f"  [{v}万] {k}\n")

    # Check all customers for cc!=pie
    mismatches = [(c['n'], c.get('cc',0), len(c.get('cat_rev',{})))
                  for c in b_custs if c.get('cc',0) != len(c.get('cat_rev',{}))]
    f.write(f"\n\nTotal mismatches: {len(mismatches)}\n")
    for name, cc, pie in mismatches:
        f.write(f"  {name}: cc={cc}, pie_items={pie}\n")

    # Check for zero values across all
    zero_cats = 0
    for c in b_custs:
        for k, v in c.get('cat_rev', {}).items():
            if v <= 0.05:  # Very small
                zero_cats += 1
    f.write(f"\nCategories with value <= 0.05: {zero_cats}\n")
print("Done")
