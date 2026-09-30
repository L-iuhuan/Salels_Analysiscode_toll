# -*- coding: utf-8 -*-
import re, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
t = open(r'E:\3-其他资料\工作文件\工作文件\semiconductor_analysis\dashboard\dashboard_a.html', encoding='utf-8', errors='ignore').read()
tabs = set(re.findall(r'switchTab\(\s*[\'"]([A-Za-z])[\'"]\s*\)', t))
print('TABS:', sorted(tabs))
# find tab section headers
m = re.findall(r'class="tab-btn[^"]*"[^>]*>\s*([^<]{1,20})', t)
print('tab buttons:', m[:20])
