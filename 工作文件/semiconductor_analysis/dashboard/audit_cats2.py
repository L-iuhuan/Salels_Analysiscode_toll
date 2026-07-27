import json
import os

base = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(base, 'data', 'b_custs.json'), encoding='utf-8') as f:
    call = json.load(f)

mismatches = []
for c in call:
    cat_rev = c.get('cat_rev', {})
    cc = c.get('cc', 0)
    pie_count = len(cat_rev)
    if cc != pie_count:
        mismatches.append((c['n'], cc, pie_count))

with open(os.path.join(base, 'audit_output.txt'), 'w', encoding='utf-8') as f:
    f.write(f"Total customers: {len(call)}\n")
    f.write(f"With cat_rev: {sum(1 for c in call if c.get('cat_rev'))}\n")
    f.write(f"Mismatches (cc != pie_count): {len(mismatches)}\n\n")
    for name, cc, pie in mismatches[:20]:
        f.write(f"  {name}: cc={cc}, pie={pie}\n")

    # Sample first 3 with data
    f.write("\n\nSample (first 3 with cat_rev):\n")
    n = 0
    for c in call:
        cr = c.get('cat_rev', {})
        if cr:
            f.write(f"\n  {c['n']}: cc={c.get('cc',0)}, pie={len(cr)}\n")
            for k, v in cr.items():
                f.write(f"    {k}: {v}万\n")
            n += 1
            if n >= 3:
                break
print("Done")
