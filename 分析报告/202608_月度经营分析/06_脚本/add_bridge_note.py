# -*- coding: utf-8 -*-
r"""10-毛利桥加口径桥接注记(A9, VBA重算区之外)"""
import time
import pythoncom
import pywintypes
import win32com.client as win32

BK = r"E:\3-其他资料\数据分析\月度分析模板_8月报告副本.xlsx"

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

NOTE = ("口径桥接注(2026-09-09, 静态注记): 本表为三因子口径(量/价/成本);报告表5与R-报告补充!R1为四因子口径,"
        "将本表'量效应'进一步拆为 量(数量效应)+结构(品类结构效应)。恒等式: 量4+结构=本表量 —— 同比 313+70=383;"
        " 环比 -461+171=-291(未舍入-290.8)。价/成本/可比ΔGP/可比毛利率两表完全一致。")

pythoncom.CoInitialize()
xl = None
try:
    xl = with_retry(lambda: win32.DispatchEx("Excel.Application"))
    xl.Visible = False
    xl.DisplayAlerts = False
    wb = with_retry(lambda: xl.Workbooks.Open(BK))
    w = with_retry(lambda: xl.Worksheets("10-毛利桥"))
    rg = with_retry(lambda: w.Cells(9, 1))
    with_retry(lambda: rg.__setattr__("Value", NOTE))
    v = with_retry(lambda: w.Cells(9, 1).Value)
    ok = v == NOTE
    with_retry(lambda: wb.Save())
    with_retry(lambda: wb.Close(False))
    print("NOTE_OK" if ok else f"NOTE_MISMATCH:{str(v)[:50]}")
finally:
    if xl is not None:
        try:
            xl.Quit()
        except Exception:
            pass
    pythoncom.CoUninitialize()
