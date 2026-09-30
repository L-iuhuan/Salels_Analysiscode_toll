# -*- coding: utf-8 -*-
r"""draft4 微修：四、标题段落重组"""
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

LOG = []
pythoncom.CoInitialize()
word = None
try:
    word = win32.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    doc = with_retry(lambda: word.Documents.Open(FINAL))
    with_retry(lambda: doc.__setattr__("TrackRevisions", True))
    np_ = with_retry(lambda: doc.Paragraphs.Count)
    hit = None
    for i in range(1, np_ + 1):
        p = with_retry(lambda: doc.Paragraphs(i))
        t = with_retry(lambda: p.Range.Text).replace("\r", "").replace("\x07", "")
        if t.strip().startswith("四、从SKU变化透视") or ("四、从SKU变化透视" in t):
            hit = (i, t.strip())
            break
    LOG.append(f"found: {hit[0] if hit else None} len={len(hit[1]) if hit else 0}")
    LOG.append(f"text head: {hit[1][:80] if hit else '-'}")
    if hit:
        p = with_retry(lambda: doc.Paragraphs(hit[0]))
        newt = "四、专项:中兴康讯——规模第二、毛利转负的结构性亏损"
        with_retry(lambda: p.Range.__setattr__("Text", newt + "\r"))
        with_retry(lambda: p.Range.Comments.Add(p.Range.Duplicate,
            "【结构变更】专项由\"追觅\"更换为\"中兴康讯\":追觅连续两月低位已并入3.3;8月最突出新问题为中兴康讯转亏(数据底表:R-报告补充R3)。"))
        LOG.append("[OK] 四、标题已改写")
    nrev = with_retry(lambda: doc.Revisions.Count)
    ncom = with_retry(lambda: doc.Comments.Count)
    with_retry(lambda: doc.Save())
    with_retry(lambda: doc.Close(False))
    LOG.append(f"[DONE] 修订数={nrev} 批注数={ncom}")
finally:
    if word is not None:
        try:
            word.Quit()
        except Exception:
            pass
    pythoncom.CoUninitialize()

open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\draft4_log.txt", "w", encoding="utf-8").write("\n".join(LOG))
print("DRAFT4_DONE")
