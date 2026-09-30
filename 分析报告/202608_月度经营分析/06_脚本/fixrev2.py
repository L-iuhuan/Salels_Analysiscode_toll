# -*- coding: utf-8 -*-
r"""定点清除段落属性类残留修订: rv.Accept + 遍历页眉页脚"""
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
    n = with_retry(lambda: doc.Revisions.Count)
    LOG.append(f"revisions={n}")
    # 定点Accept
    for i in range(n, 0, -1):
        try:
            rv = with_retry(lambda: doc.Revisions(i))
            with_retry(lambda: rv.Accept())
            LOG.append(f"accepted rev{i}")
        except Exception as e:
            LOG.append(f"rev{i} accept err: {e}")
    n2 = with_retry(lambda: doc.Revisions.Count)
    LOG.append(f"after direct accept: {n2}")
    # 若仍有, 遍历节页眉页脚
    if n2:
        for si in range(1, with_retry(lambda: doc.Sections.Count) + 1):
            sec = with_retry(lambda: doc.Sections(si))
            for kind in ("Headers", "Footers"):
                coll = with_retry(lambda: getattr(sec, kind))
                cnt = with_retry(lambda: coll.Count)
                for hi in range(1, cnt + 1):
                    hf = with_retry(lambda: coll(hi))
                    try:
                        rc = with_retry(lambda: hf.Range.Revisions.Count)
                        if rc:
                            LOG.append(f"section{si} {kind}{hi}: {rc} revisions -> accept all")
                            with_retry(lambda: hf.Range.Revisions.AcceptAll())
                    except Exception as e:
                        LOG.append(f"sec{si}{kind}{hi} err {e}")
    n3 = with_retry(lambda: doc.Revisions.Count)
    LOG.append(f"final: {n3}")
    with_retry(lambda: doc.Save())
    with_retry(lambda: doc.Close(False))
finally:
    if word is not None:
        try:
            word.Quit()
        except Exception:
            pass
    pythoncom.CoUninitialize()
open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\fixrev2_log.txt", "w", encoding="utf-8").write("\n".join(str(x) for x in LOG))
print("FIXREV2_DONE")
