# -*- coding: utf-8 -*-
import re
with open('recession_risk_opt/phase2_f1_repair.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find lines with Mann-Whitney print
lines = content.split('\n')
for i, line in enumerate(lines):
    if 'Mann-Whitney' in line and 'stat=' in line:
        print(f'Line {i+1}: found')
        print(repr(line))
