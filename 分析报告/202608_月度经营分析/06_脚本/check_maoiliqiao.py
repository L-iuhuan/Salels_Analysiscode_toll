# -*- coding: utf-8 -*-
r"""核查10-毛利桥 vs 报告表5: 读实际值+三/四因子恒等式对拍"""
import json
import time
import pythoncom
import pywintypes
import win32com.client as win32

BK = r"E:\3-其他资料\数据分析\月度分析模板_8月报告副本.xlsx"
RC = json.load(open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\recompute.json", encoding="utf-8"))

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

out = []
pythoncom.CoInitialize()
xl = None
try:
    xl = with_retry(lambda: win32.DispatchEx("Excel.Application"))
    xl.Visible = False
    xl.DisplayAlerts = False
    wb = with_retry(lambda: xl.Workbooks.Open(BK, ReadOnly=True))
    w = with_retry(lambda: xl.Worksheets("10-毛利桥"))
    for r in range(1, 10):
        vals = []
        for c in range(1, 8):
            v = with_retry(lambda: w.Cells(r, c).Value)
            vals.append("" if v is None else (round(v, 4) if isinstance(v, float) else str(v)))
        if any(str(v) != "" for v in vals):
            out.append(f"r{r}: " + " | ".join(str(v) for v in vals))
    wr = with_retry(lambda: xl.Worksheets("R-报告补充"))
    out.append("--- R1 (rows 1-5) ---")
    for r in range(1, 6):
        vals = []
        for c in range(1, 8):
            v = with_retry(lambda: wr.Cells(r, c).Value)
            vals.append("" if v is None else (round(v, 4) if isinstance(v, float) else str(v)[:60]))
        out.append(f"r{r}: " + " | ".join(str(v) for v in vals))
    with_retry(lambda: wb.Close(False))
finally:
    if xl is not None:
        try:
            xl.Quit()
        except Exception:
            pass
    pythoncom.CoUninitialize()

# 恒等式对拍(未舍入值)
by = RC["桥_同比_2026_08_vs_2025_08"]
bm = RC["桥_环比_2026_08_vs_2026_07"]
out.append("")
out.append(f"恒等式(未舍入): 同比 量4({by['量4']:.1f})+结构({by['结构4']:.1f})={by['量4'] + by['结构4']:.1f} vs 10-毛利桥量3=383")
out.append(f"恒等式(未舍入): 环比 量4({bm['量4']:.1f})+结构({bm['结构4']:.1f})={bm['量4'] + bm['结构4']:.1f} vs 10-毛利桥量3=-291")
out.append(f"价: {by['价']:.1f}/{bm['价']:.1f} vs 表-470/+62; 成本: {by['成本']:.1f}/{bm['成本']:.1f} vs -33/+8; dGP: {by['dGP']:.1f}/{bm['dGP']:.1f} vs -120/-220")
open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\mb_check.txt", "w", encoding="utf-8").write("\n".join(out))
print("MBCHECK_DONE")
