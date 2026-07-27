import json, pandas as pd

df = pd.read_csv('../output/gold/客户全景.csv')

with open('data/b_custs.json', encoding='utf-8') as f:
    call = json.load(f)

mismatches = []
cat_detail = []
for c in call:
    cat_rev = c.get('cat_rev', {})
    cc = c.get('cc', 0)
    pie_count = len(cat_rev)
    if cc != pie_count:
        mismatches.append((c['n'], cc, pie_count))
    if pie_count > 0:
        cat_detail.append((c['n'], cc, pie_count, list(cat_rev.keys())[:5]))

print(f"=== 品类数量矛盾 ({len(mismatches)}个) ===")
for name, cc, pie in mismatches[:10]:
    print(f"  {name}: cc={cc}, pie={pie}")

print(f"\n=== 品类样例 (前3个有数据的客户) ===")
for name, cc, pie, keys in cat_detail[:3]:
    print(f"  {name}: cc={cc}, pie={pie}, cats: {keys}")
    cr = call[[c['n'] for c in call].index(name)]['cat_rev']
    for k, v in cr.items():
        print(f"    {k}: {v}万")

print(f"\n总客户: {len(call)}, 有cat_rev的: {sum(1 for c in call if c.get('cat_rev'))}")
