# -*- coding: utf-8 -*-
import pythoncom
import win32com.client as win32

BASE = r"\\192.168.8.3\财务部\财务电子档案备份\D1经营分析\财务分析-8月（9.5) .xlsx"
pythoncom.CoInitialize()
xl = None
try:
    xl = win32.DispatchEx("Excel.Application")
    xl.Visible = False
    xl.DisplayAlerts = False
    wb = xl.Workbooks.Open(BASE, ReadOnly=True, UpdateLinks=0)
    ws = wb.Worksheets("24-26")
    last_col = ws.Cells(1, ws.Columns.Count).End(-4159).Column
    hdr = ws.Range(ws.Cells(1, 1), ws.Cells(1, last_col)).Value
    print("last_col:", last_col)
    print("type:", type(hdr), "len:", len(hdr) if hasattr(hdr, "__len__") else "?")
    if isinstance(hdr, tuple):
        print("elem0 type:", type(hdr[0]), "val:", repr(hdr[0])[:40])
    lines = []
    if isinstance(hdr, tuple) and hdr and not isinstance(hdr[0], tuple):
        hs = list(hdr)
    else:
        hs = [c[0] for c in hdr]
    lines.append("flat? " + str(not isinstance(hdr[0], tuple) if isinstance(hdr, tuple) else "n/a"))
    lines.append("first12: " + " | ".join(str(h) for h in hs[:12]))
    lines.append("has 存货名称: " + str("存货名称" in hs))
    lines.append("idx 存货名称: " + str(hs.index("存货名称") if "存货名称" in hs else -1))
    open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\hdr_diag.txt", "w", encoding="utf-8").write("\n".join(lines))
    wb.Close(SaveChanges=False)
finally:
    if xl is not None:
        xl.Quit()
    pythoncom.CoUninitialize()
print("DIAG_OK")
