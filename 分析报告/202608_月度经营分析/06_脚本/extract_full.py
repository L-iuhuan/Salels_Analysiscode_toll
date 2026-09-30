# -*- coding: utf-8 -*-
r"""全量提取7月报告：所有表格全部单元格 + 全部非空段落全文（JSON格式供编辑器使用）"""
import json
import time
import pythoncom
import pywintypes
import win32com.client as win32

DOC = r"\\192.168.8.3\财务部\财务电子档案备份\D1经营分析\分析报告\分析报告-202608\2026年7月销售经营分析报告(5).docx"
OUT = r"C:\Users\910373\AppData\Local\Temp\opencode\build\july_full.json"

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

data = {"paragraphs": [], "tables": []}
pythoncom.CoInitialize()
word = None
try:
    word = win32.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    doc = with_retry(lambda: word.Documents.Open(DOC, ReadOnly=True, AddToRecentFiles=False))
    for i in range(1, with_retry(lambda: doc.Paragraphs.Count) + 1):
        try:
            p = with_retry(lambda: doc.Paragraphs(i))
            t = with_retry(lambda: p.Range.Text).replace("\r", "").replace("\x07", "").strip()
            if t:
                data["paragraphs"].append({"i": i, "t": t})
        except Exception:
            continue
    ntab = with_retry(lambda: doc.Tables.Count)
    for ti in range(1, ntab + 1):
        try:
            tb = with_retry(lambda: doc.Tables(ti))
            nrow = with_retry(lambda: tb.Rows.Count)
            ncol = with_retry(lambda: tb.Columns.Count)
            cells = []
            for r in range(1, nrow + 1):
                row = []
                for c in range(1, ncol + 1):
                    try:
                        row.append(with_retry(lambda: tb.Cell(r, c).Range.Text).replace("\r\x07", "").strip())
                    except Exception:
                        row.append(None)
                cells.append(row)
            data["tables"].append({"ti": ti, "rows": nrow, "cols": ncol, "cells": cells})
        except Exception as e:
            data["tables"].append({"ti": ti, "error": str(e)})
    with_retry(lambda: doc.Close(False))
finally:
    if word is not None:
        try:
            word.Quit()
        except Exception:
            pass
    pythoncom.CoUninitialize()

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=1)
print("FULL_DONE paras:", len(data["paragraphs"]), "tables:", len(data["tables"]))
