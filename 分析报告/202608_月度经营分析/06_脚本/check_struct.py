# -*- coding: utf-8 -*-
import time
import pythoncom
import pywintypes
import win32com.client as win32

FINAL = r"E:\3-其他资料\数据分析\2026年8月销售经营分析报告_草稿(修订版).docx"

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

out = []
pythoncom.CoInitialize()
word = None
try:
    word = win32.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    doc = with_retry(lambda: word.Documents.Open(FINAL, ReadOnly=True))
    np_ = with_retry(lambda: doc.Paragraphs.Count)
    out.append(f"paras={np_}")
    for i in range(1, np_ + 1):
        p = with_retry(lambda: doc.Paragraphs(i))
        t = with_retry(lambda: p.Range.Text).replace("\r", "").replace("\x07", "").strip()
        if t.startswith(("四、", "五、", "六、", "2.1 ", "2.2 ", "3.1 ", "3.2 ", "3.3 ", "3.5 ")) or "中兴康讯已成为" in t or "待确认问题清单" in t or "数据来源与口径" in t or t.startswith("按\""):
            out.append(f"[{i}] {t[:70]}")
    with_retry(lambda: doc.Close(False))
finally:
    if word is not None:
        try:
            word.Quit()
        except Exception:
            pass
    pythoncom.CoUninitialize()
open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\struct_check.txt", "w", encoding="utf-8").write("\n".join(out))
print("done")
