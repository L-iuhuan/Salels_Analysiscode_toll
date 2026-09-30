# -*- coding: utf-8 -*-
r"""读取主模板VBA模块代码, 定位毛利桥重算逻辑"""
import time
import pythoncom
import pywintypes
import win32com.client as win32

MASTER = r"E:\3-其他资料\数据分析\月度分析模板.xlsm"
OUT = r"C:\Users\910373\AppData\Local\Temp\opencode\build\vba_dump.txt"

def with_retry(fn, *a, **k):
    last = None
    for i in range(15):
        try:
            return fn(*a, **k)
        except pywintypes.com_error as e:
            if e.hresult in (-2147418111, -2147417846) and i < 14:
                last = e
                time.sleep(2)
                continue
            raise
    raise last

lines = []
pythoncom.CoInitialize()
xl = None
try:
    xl = with_retry(lambda: win32.DispatchEx("Excel.Application"))
    xl.Visible = False
    xl.DisplayAlerts = False
    wb = with_retry(lambda: xl.Workbooks.Open(MASTER))
    vbp = with_retry(lambda: wb.VBProject)
    comps = with_retry(lambda: vbp.VBComponents)
    n = with_retry(lambda: comps.Count)
    lines.append(f"VBComponents: {n}")
    for i in range(1, n + 1):
        comp = with_retry(lambda: comps(i))
        nm = with_retry(lambda: comp.Name)
        tp = with_retry(lambda: comp.Type)
        cm = with_retry(lambda: comp.CodeModule)
        cnt = with_retry(lambda: cm.CountOfLines)
        lines.append(f"\n===== [{i}] {nm} (type={tp}, lines={cnt}) =====")
        if cnt and tp in (1, 2):  # 标准模块/类模块
            code = with_retry(lambda: cm.Lines(1, cnt))
            lines.append(code)
    with_retry(lambda: wb.Close(False))
finally:
    if xl is not None:
        try:
            xl.Quit()
        except Exception:
            pass
    pythoncom.CoUninitialize()

open(OUT, "w", encoding="utf-8").write("\n".join(str(x) for x in lines))
print("VBA_DUMP_DONE")
