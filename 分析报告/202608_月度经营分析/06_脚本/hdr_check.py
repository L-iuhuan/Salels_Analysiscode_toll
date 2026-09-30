# -*- coding: utf-8 -*-
import time
import pythoncom
import pywintypes
import win32com.client as win32

BK = r"E:\3-其他资料\数据分析\月度分析模板_8月报告副本.xlsx"

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
xl = None
try:
    xl = win32.DispatchEx("Excel.Application")
    xl.Visible = False
    xl.DisplayAlerts = False
    with_retry(lambda: xl.Workbooks.Open(BK, ReadOnly=True))
    for sname in ("D-镜像", "毛利桥"):
        try:
            ws = with_retry(lambda: xl.Worksheets(sname))
            out.append(f"== {sname} ==")
            nr = with_retry(lambda: ws.UsedRange.Rows.Count)
            nc = with_retry(lambda: ws.UsedRange.Columns.Count)
            out.append(f"used: {nr}x{nc}")
            hdr = with_retry(lambda: ws.Range(ws.Cells(1, 1), ws.Cells(1, min(nc, 18))).Value)
            out.append("hdr1: " + json_str(hdr))
            if nr >= 2:
                r2 = with_retry(lambda: ws.Range(ws.Cells(2, 1), ws.Cells(2, min(nc, 18))).Value)
                out.append("row2: " + json_str(r2))
            if sname == "毛利桥":
                body = with_retry(lambda: ws.Range(ws.Cells(1, 1), ws.Cells(min(nr, 40), min(nc, 12))).Value)
                for rr in body:
                    out.append(" | ".join("" if c is None else str(c) for c in rr))
        except Exception as e:
            out.append(f"{sname} ERR: {e}")
    sheets = []
    for i in range(1, with_retry(lambda: xl.Worksheets.Count) + 1):
        s = with_retry(lambda: xl.Worksheets(i))
        sheets.append(f"{with_retry(lambda: s.Name)}(vis={with_retry(lambda: s.Visible)})")
    out.append("SHEETS: " + ", ".join(sheets))
    with_retry(lambda: xl.Workbooks.Close())
finally:
    if xl is not None:
        try:
            xl.Quit()
        except Exception:
            pass
    pythoncom.CoUninitialize()

def json_str(v):
    import json as _j
    return _j.dumps(v, ensure_ascii=False, default=str)

open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\hdr_check.txt", "w", encoding="utf-8").write("\n".join(out))
print("HDR_DONE")
