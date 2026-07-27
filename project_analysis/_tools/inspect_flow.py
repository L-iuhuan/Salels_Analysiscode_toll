# -*- coding: utf-8 -*-
import json, os
d = json.load(open(r'E:\3-其他资料\数据分析\project_analysis\03_data_flow_auto.json', encoding='utf-8'))
comps = d['components']
for i, c in enumerate(comps):
    names = [s.split('/')[-1] for s in c['scripts']]
    if 'run_all.py' in names or 'generate_dashboard.py' in names or 'run_chain.py' in names:
        print(f'--- comp{i}: {len(c["scripts"])} scripts, {len(c["data"])} data, tags={c["tags"]}')
        for s in c['scripts']: print('  S:', s)
        for x in c['data']: print('  D:', x['ref'], '|', x['class'], '|', 'disk' if x['exists_on_disk'] else 'ref-only')
for idx in (0, 3):
    c = comps[idx]
    print(f'=== comp{idx}: {len(c["scripts"])} scripts')
    for x in c['data']: print('  D:', x['ref'], '|', x['class'])
    print('  scripts:', [s.split('/')[-1] for s in c['scripts']])
# 各组件规模分布
from collections import Counter
sizes = Counter(len(c['scripts']) for c in comps)
print('组件规模分布(脚本数:组件个数):', dict(sorted(sizes.items(), reverse=True)[:10]))
