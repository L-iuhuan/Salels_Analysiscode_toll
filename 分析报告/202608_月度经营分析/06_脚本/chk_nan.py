# -*- coding: utf-8 -*-
import re
src = open(r'E:\3-其他资料\数据分析\sales_analytics_platform\dashboard\generate_dashboard.py', encoding='utf-8').read()
print('helper calls:', src.count('_cust_key_ok('))
for m in re.finditer(r'.{60}\[\"nan\",\"None\",\"\",\"未知客户\"\].{20}', src):
    print(repr(m.group(0)))
for m in re.finditer(r'.{40}in \(\"nan\",\"None\",\"\",\"未知客户\"\).{20}', src):
    print(repr(m.group(0)))
