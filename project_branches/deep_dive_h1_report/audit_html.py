import json, re

with open('dashboard_a.html', encoding='utf-8') as f:
    html = f.read()

# Extract embedded B_CUSTS
m = re.search(r'var B_CUSTS = (\[.*?\]);', html, re.DOTALL)
if m:
    b_custs = json.loads(m.group(1))
    mismatches = []
    for c in b_custs:
        cr = c.get('cat_rev', {})
        cc = c.get('cc', 0)
        if cc != len(cr):
            mismatches.append((c['n'], cc, len(cr)))

    with open('audit_output.txt', 'w', encoding='utf-8') as f:
        f.write(f"HTML B_CUSTS count: {len(b_custs)}\n")
        f.write(f"With cat_rev: {sum(1 for c in b_custs if c.get('cat_rev'))}\n")
        f.write(f"Mismatches: {len(mismatches)}\n")
        for name, cc, pie in mismatches[:30]:
            f.write(f"  {name}: cc={cc}, pie={pie}\n")
        # Sample first 3
        f.write("\nSample:\n")
        n = 0
        for c in b_custs:
            cr = c.get('cat_rev', {})
            if cr:
                f.write(f"\n  {c['n']}: cc={c.get('cc')}, pie={len(cr)}\n")
                for k, v in list(cr.items())[:5]:
                    f.write(f"    {k}: {v}万\n")
                n += 1
                if n >= 3:
                    break
else:
    with open('audit_output.txt', 'w') as f:
        f.write("B_CUSTS not found in HTML!")
print("Done")
