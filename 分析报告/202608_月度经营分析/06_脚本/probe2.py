# -*- coding: utf-8 -*-
import re, io, sys, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
base = r'E:\3-其他资料\工作文件\工作文件\semiconductor_analysis\dashboard'
targets = ['口径', '地图', '代理商', '经销', '区域', '省份', '城市', '地理', 'echarts', 'GeoJSON', 'geoMap', 'mapChart', 'china', '地图数据', '坐标']
files = [f for f in os.listdir(base) if f.endswith('.html')]
for fn in sorted(files):
    t = open(os.path.join(base, fn), encoding='utf-8', errors='ignore').read()
    hits = []
    for kw in targets:
        for m in re.finditer(re.escape(kw), t):
            s = max(0, m.start()-60); e = min(len(t), m.end()+80)
            ctx = t[s:e].replace('\n', ' ').replace('\r', ' ')
            hits.append((kw, ctx))
    if hits:
        print(f'===== {fn} ({round(len(t)/1024,1)}KB) =====')
        seen = set()
        for kw, ctx in hits:
            key = kw + '|' + ctx[:60]
            if key in seen: continue
            seen.add(key)
            print(f'[{kw}] ...{ctx}...')
            print('---')
