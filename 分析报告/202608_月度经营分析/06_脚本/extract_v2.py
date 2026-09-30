# -*- coding: utf-8 -*-
r"""提取8月报告全文(接受修订+删批注的内存视图)供council分析"""
import json
import time
import pythoncom
import pywintypes
import win32com.client as win32

FINAL = r"E:\3-其他资料\数据分析\2026年8月销售经营分析报告_草稿(修订版).docx"
OUT = r"E:\3-其他资料\数据分析\_council\report_v2_text.txt"

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
    doc = with_retry(lambda: word.Documents.Open(FINAL))
    # 内存态接受所有修订并删除批注(不保存)
    with_retry(lambda: doc.AcceptAllRevisions())
    with_retry(lambda: doc.DeleteAllComments())
    np_ = with_retry(lambda: doc.Paragraphs.Count)
    lines.append(f"[本文档为2026年8月销售经营分析报告草稿v2全文,共{np_}段]")
    for i in range(1, np_ + 1):
        p = with_retry(lambda: doc.Paragraphs(i))
        t = with_retry(lambda: p.Range.Text).replace("\r", "").replace("\x07", "").strip()
        if t:
            lines.append(f"[{i}] {t}")
    # 表格
    nt = with_retry(lambda: doc.Tables.Count)
    lines.append(f"\n===== 共{nt}张表格 =====")
    for ti in range(1, nt + 1):
        tb = with_retry(lambda: doc.Tables(ti))
        nr = with_retry(lambda: tb.Rows.Count)
        lines.append(f"\n--- 表{ti} ({nr}行) ---")
        for ri in range(1, nr + 1):
            try:
                vals = []
                row = with_retry(lambda: tb.Rows(ri).Range)
                cells = with_retry(lambda: row.Cells)
                for ci in range(1, with_retry(lambda: cells.Count) + 1):
                    c = with_retry(lambda: cells(ci))
                    ct = with_retry(lambda: c.Range.Text).replace("\r", "").replace("\x07", "").strip()
                    vals.append(ct)
                lines.append(" | ".join(vals))
            except Exception:
                lines.append(f"(行{ri}读取失败)")
    with_retry(lambda: doc.Close(False))
finally:
    if word is not None:
        try:
            word.Quit()
        except Exception:
            pass
    pythoncom.CoUninitialize()

open(OUT, "w", encoding="utf-8").write("\n".join(lines))
print(f"EXTRACT_DONE lines={len(lines)}")
