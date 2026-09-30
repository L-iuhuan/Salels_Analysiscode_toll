# -*- coding: utf-8 -*-
import re, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
t = open(r'E:\3-其他资料\工作文件\工作文件\semiconductor_analysis\dashboard\dashboard_a.html', encoding='utf-8', errors='ignore').read()
# find tab-content sections
for m in re.finditer(r'<div class="tab-content[^"]*" id="tab([A-Z])">', t):
    print('TAB', m.group(1), 'at', m.start())
# Find all <h2>/<h3> headings
for m in re.finditer(r'<(h2|h3|h4)[^>]*>(.*?)</\1>', t, re.S):
    txt = re.sub(r'<[^>]+>', '', m.group(2)).strip()
    if txt:
        print(m.group(1).upper(), txt[:90])
