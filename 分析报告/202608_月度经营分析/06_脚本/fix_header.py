# -*- coding: utf-8 -*-
r"""修复表18表头三重后缀 + 全量复核"""
import time
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

LOG = []
pythoncom.CoInitialize()
word = None
try:
    word = win32.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    doc = with_retry(lambda: word.Documents.Open(DST))
    with_retry(lambda: doc.__setattr__("TrackRevisions", False))

    for needle, repl in [("销量环比变动(颗)(颗)(颗)", "销量环比变动(颗)"),
                         ("销量环比变动(颗)(颗)", "销量环比变动(颗)")]:
        rng = with_retry(lambda: doc.Content)
        f = with_retry(lambda: rng.Find)
        with_retry(lambda: f.ClearFormatting)
        with_retry(lambda: f.__setattr__("Text", needle))
        with_retry(lambda: f.__setattr__("Forward", True))
        with_retry(lambda: f.__setattr__("Wrap", 0))
        ok = with_retry(lambda: f.Execute())
        if ok:
            found = with_retry(lambda: f.Parent)
            with_retry(lambda: found.__setattr__("Text", repl))
            LOG.append(f"fixed: {needle[:20]}")
        else:
            LOG.append(f"none: {needle[:20]}")

    nrev = with_retry(lambda: doc.Revisions.Count)
    for i in range(nrev, 0, -1):
        rv = with_retry(lambda: doc.Revisions(i))
        with_retry(lambda: rv.Accept())
    with_retry(lambda: doc.Save())
    with_retry(lambda: doc.Close(False))
    LOG.append("saved")
finally:
    if word is not None:
        try:
            word.Quit()
        except Exception:
            pass
    pythoncom.CoUninitialize()
open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\fix3_log.txt", "w", encoding="utf-8").write("\n".join(str(x) for x in LOG))
print("FIX3_DONE")
