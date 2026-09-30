# -*- coding: utf-8 -*-
import re, io, sys, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
base = r'E:\3-其他资料\工作文件\工作文件\semiconductor_analysis\dashboard'
files = ['dashboard_a.html', 'template.html', '销售看板-测试页.html', 'dashboard_v2.html', 'dashboard_a_v2_template.html', 'generate_dashboard.py']
kws = ['地图', '地图', '代理', '经销', '区域', '省份', '城市', 'GeoJSON', 'geoMap', 'mapChart', '中国地图', '坐标', '经纬', '全国', '省份分布', '地域']
for fn in files:
    t = open(os.path.join(base, fn), encoding='utf-8', errors='ignore').read()
    print(f'##### {fn} ({round(len(t)/1024,1)}KB) #####')
    for kw in kws:
        cnt = t.count(kw)
        if cnt:
            print(f'  [{kw}] count={cnt}')
            i = 0
            for m in re.finditer(re.escape(kw), t):
                if i >= 3: 
                    print('   ...')
                    break
                s = max(0, m.start()-80); e = min(len(t), m.end()+120)
                print('   ctx:', t[s:e].replace('\n', ' ')[:260])
                i += 1
