# -*- coding: utf-8 -*-
"""枚举 data 目录真实文件名 + 侦察最新 Excel"""
import sys, os, glob
sys.stdout.reconfigure(encoding='utf-8')

d = r'E:\3-其他资料\数据分析\sales_analytics_platform\data'
files = glob.glob(os.path.join(d, '*.xlsx'))
files.sort(key=os.path.getmtime)
print('=== data 目录 xlsx（按 mtime 升序）===')
for f in files:
    print(repr(os.path.basename(f)), '|', round(os.path.getsize(f)/1e6, 1), 'MB')

newest = files[-1] if files else None
print()
print('最新文件:', repr(os.path.basename(newest)) if newest else '无')

if newest:
    head = open(newest, 'rb').read(4)
    print('文件头:', head, '| PK头(明文):', head[:2] == b'PK')
    if head[:2] == b'PK':
        try:
            from python_calamine import CalamineWorkbook
            wb = CalamineWorkbook.from_path(newest)
            names = wb.sheet_names
            print('sheet 列表:', names)
            # 读取首个 sheet 的表头（限制范围，避免全量加载）
            sh = wb.get_sheet_by_name(names[0])
            try:
                rows = sh.range((0, 0, 2, 60))  # 前2行×60列
                rows = rows.to_python() if hasattr(rows, 'to_python') else rows
            except Exception:
                rows = sh.to_python(skip_empty_area=True)
                rows = rows[:2]
            hdr = rows[0] if rows else []
            print('表头列数:', len(hdr))
            print('表头前30:', [str(c)[:16] for c in hdr[:30]])
        except Exception as e:
            print('calamine 失败:', type(e).__name__, str(e)[:180])
    else:
        print('非 PK 头 = DSE 加密，需 COM 转存')
