# -*- coding: utf-8 -*-
r"""清除定稿残留的1处修订"""
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
    n0 = with_retry(lambda: doc.Revisions.Count)
    LOG.append(f"before: revisions={n0}")
    if n0:
        try:
            rv = with_retry(lambda: doc.Revisions(1))
            LOG.append(f"rev1 type={with_retry(lambda: rv.Type)} range_head={with_retry(lambda: rv.Range.Text)[:40]!r}")
        except Exception as e:
            LOG.append(f"inspect err {e}")
        with_retry(lambda: doc.AcceptAllRevisions())
    with_retry(lambda: doc.__setattr__("TrackRevisions", False))
    n1 = with_retry(lambda: doc.Revisions.Count)
    LOG.append(f"after: revisions={n1}")
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
open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\fixrev_log.txt", "w", encoding="utf-8").write("\n".join(str(x) for x in LOG))
print("FIXREV_DONE")
