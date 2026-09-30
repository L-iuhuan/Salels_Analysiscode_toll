# -*- coding: utf-8 -*-
r"""仅执行Word图片替换(6张修复版图表)"""
import os
import time
import pythoncom
import pywintypes
import win32com.client as win32

OUT = r"C:\Users\910373\AppData\Local\Temp\opencode\build\chartsA2"
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

LOG = []
pythoncom.CoInitialize()
word = None
try:
    word = win32.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    doc = with_retry(lambda: word.Documents.Open(DST))
    n = with_retry(lambda: doc.InlineShapes.Count)
    LOG.append(f"images before: {n}")
    for k in range(n, 0, -1):
        shp = with_retry(lambda: doc.InlineShapes(k))
        start = with_retry(lambda: shp.Range.Start)
        with_retry(lambda: shp.Delete())
        rng = with_retry(lambda: doc.Range(start, start))
        pic = with_retry(lambda: doc.InlineShapes.AddPicture(os.path.join(OUT, f"fig{k}.png"), False, True, rng.Duplicate))
        with_retry(lambda: pic.__setattr__("Width", 440))
        LOG.append(f"replaced fig{k}")
    n2 = with_retry(lambda: doc.InlineShapes.Count)
    nrev = with_retry(lambda: doc.Revisions.Count)
    with_retry(lambda: doc.Save())
    with_retry(lambda: doc.Close(False))
    LOG.append(f"images after: {n2} revisions={nrev}")
finally:
    if word is not None:
        try:
            word.Quit()
        except Exception:
            pass
    pythoncom.CoUninitialize()
open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\replace_log.txt", "w", encoding="utf-8").write("\n".join(str(x) for x in LOG))
print("REPLACE_DONE")
