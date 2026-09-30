# -*- coding: utf-8 -*-
"""Word COM 提取 DSE 加密 docx 全文（含段落+表格结构线索）"""
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
path = r'E:\3-其他资料\数据分析\2026年8月销售经营分析报告(定稿).docx'
out = r'C:\Users\910373\AppData\Local\Temp\opencode\report_202608.txt'

# 验头
head = open(path, 'rb').read(4)
print('文件头4字节:', head, '| 是PK zip头:', head[:2] == b'PK')

import win32com.client
import pythoncom
pythoncom.CoInitialize()
word = None
try:
    word = win32com.client.Dispatch('Word.Application')
    word.Visible = False
    word.DisplayAlerts = 0
    doc = word.Documents.Open(path, ReadOnly=True, AddToRecentFiles=False)
    lines = []
    for p in doc.Paragraphs:
        t = p.Range.Text.strip()
        if not t:
            continue
        style = ''
        try:
            sn = str(p.Style.NameLocal)
            if ('标题' in sn) or ('Heading' in sn):
                style = '【' + sn + '】'
        except Exception:
            pass
        lines.append(style + t if style else t)
    for ti, tbl in enumerate(doc.Tables):
        lines.append('── 表格%d ──' % (ti + 1))
        for row in tbl.Rows:
            cells = []
            for c in row.Cells:
                cells.append(c.Range.Text.replace('\r', '').replace('\x07', '').strip())
            lines.append(' | '.join(cells))
    doc.Close(False)
    open(out, 'w', encoding='utf-8').write('\n'.join(lines))
    print('提取完成: 段落+表格行=%d → %s' % (len(lines), out))
finally:
    if word is not None:
        word.Quit()
    pythoncom.CoUninitialize()
