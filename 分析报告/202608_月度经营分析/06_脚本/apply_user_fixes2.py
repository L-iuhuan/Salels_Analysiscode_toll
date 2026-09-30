# -*- coding: utf-8 -*-
r"""重做5处修改: Find定位→Range.Text直接赋值(绕过Execute Replace参数失效问题)"""
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

FIXES = [
    ("立即停售-3452HFI等负毛利型号", "立即停售STI3452HFI等负毛利型号"),
    ("已已进入", "已进入"),
    ("需要结合9月数据核查是否是整体销量出现下滑的趋势。", "需结合9月数据确认是否形成销量下滑趋势。"),
    ("销量环比变动", "销量环比变动(颗)"),
    ("其问题是收入下滑而非品类结构。提升路径为将采购往高毛利同线品引导，或采取挽救措施，及时跟进采购量持续降低的原因;共进",
     "其问题是收入下滑而非品类结构,应采取挽救措施、及时跟进采购量持续降低的原因。提升路径为将采购往高毛利同线品引导;共进"),
]

LOG = []
pythoncom.CoInitialize()
word = None
try:
    word = win32.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    doc = with_retry(lambda: word.Documents.Open(DST))
    with_retry(lambda: doc.__setattr__("TrackRevisions", False))

    def locate_replace(needle, repl, max_hits=3):
        hits = 0
        for _ in range(max_hits):
            rng = with_retry(lambda: doc.Content)
            f = with_retry(lambda: rng.Find)
            with_retry(lambda: f.ClearFormatting)
            with_retry(lambda: f.__setattr__("Text", needle))
            with_retry(lambda: f.__setattr__("Forward", True))
            with_retry(lambda: f.__setattr__("Wrap", 0))  # wdFindStop, 避免循环
            ok = with_retry(lambda: f.Execute())
            if not ok:
                break
            found = with_retry(lambda: f.Parent)
            with_retry(lambda: found.__setattr__("Text", repl))
            hits += 1
        LOG.append(f"hits={hits} {needle[:24]}")
        return hits

    for needle, repl in FIXES:
        locate_replace(needle, repl)

    nrev = with_retry(lambda: doc.Revisions.Count)
    for i in range(nrev, 0, -1):
        rv = with_retry(lambda: doc.Revisions(i))
        with_retry(lambda: rv.Accept())
    with_retry(lambda: doc.Save())
    ntab = with_retry(lambda: doc.Tables.Count)
    nimg = with_retry(lambda: doc.InlineShapes.Count)
    with_retry(lambda: doc.Close(False))
    LOG.append(f"[DONE] tables={ntab} images={nimg}")
finally:
    if word is not None:
        try:
            word.Quit()
        except Exception:
            pass
    pythoncom.CoUninitialize()

open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\apply2_log.txt", "w", encoding="utf-8").write("\n".join(str(x) for x in LOG))
print("APPLY2_DONE")
