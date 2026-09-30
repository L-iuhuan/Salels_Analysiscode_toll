# -*- coding: utf-8 -*-
r"""提取用户改后的当前文档全文,与v3.1基线差异对比"""
import time
import difflib
import pythoncom
import pywintypes
import win32com.client as win32

DST = r"E:\3-其他资料\数据分析\2026年8月销售经营分析报告(定稿).docx"

def with_retry(fn, *a, **k):
    last = None
    for i in range(12):
        try:
            return fn(*a, **k)
        except pywintypes.com_error as e:
            if e.hresult in (-2147418111, -2147417846) and i < 11:
                last = e
                time.sleep(1.5)
                continue
            raise
    raise last

lines = []
pythoncom.CoInitialize()
word = None
try:
    word = win32.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    doc = with_retry(lambda: word.Documents.Open(DST, ReadOnly=True))
    np_ = with_retry(lambda: doc.Paragraphs.Count)
    ntab = with_retry(lambda: doc.Tables.Count)
    for i in range(1, np_ + 1):
        p = with_retry(lambda: doc.Paragraphs(i))
        t = with_retry(lambda: p.Range.Text).replace("\r", "").replace("\x07", "").strip()
        if t:
            lines.append(t)
    for ti in range(1, ntab + 1):
        tb = with_retry(lambda: doc.Tables(ti))
        nr = with_retry(lambda: tb.Rows.Count)
        lines.append(f"=== 表{ti} ({nr}行) ===")
        for ri in range(1, nr + 1):
            try:
                row = with_retry(lambda: tb.Rows(ri).Range)
                cells = with_retry(lambda: row.Cells)
                vals = []
                for ci in range(1, with_retry(lambda: cells.Count) + 1):
                    c = with_retry(lambda: cells(ci))
                    vals.append(with_retry(lambda: c.Range.Text).replace("\r", "").replace("\x07", "").strip())
                lines.append(" | ".join(vals))
            except Exception:
                pass
    with_retry(lambda: doc.Close(False))
finally:
    if word is not None:
        try:
            word.Quit()
        except Exception:
            pass
    pythoncom.CoUninitialize()

open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\user_edited_text.txt", "w", encoding="utf-8").write("\n".join(lines))

# 与基线diff
base = open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\final_v31_text.txt", encoding="utf-8").read().splitlines()
diff = []
for line in difflib.unified_diff(base, lines, fromfile="v3.1基线", tofile="用户修改后", lineterm="", n=1):
    diff.append(line)
open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\user_diff.txt", "w", encoding="utf-8").write("\n".join(diff))
print(f"EXTRACT_DONE lines={len(lines)} difflines={len(diff)}")
