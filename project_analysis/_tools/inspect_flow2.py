# -*- coding: utf-8 -*-
import json
d = json.load(open(r'E:\3-其他资料\数据分析\project_analysis\03_data_flow_auto.json', encoding='utf-8'))
comps = d['components']
for idx in (1, 2, 4, 5, 6):
    c = comps[idx]
    print(f'=== comp{idx}: {len(c["scripts"])} scripts, tags={c["tags"]}')
    for s in c['scripts']: print('  S:', s)
    for x in c['data']: print('  D:', x['ref'], '|', x['class'], '|', 'disk' if x['exists_on_disk'] else 'ref-only')
print('=== top shared modules ===')
for m in d['shared_modules'][:12]:
    print(f'  {m["module"]} <- {len(m["used_by"])} scripts')
