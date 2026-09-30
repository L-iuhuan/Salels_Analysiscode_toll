# -*- coding: utf-8 -*-
r"""副本10-毛利桥同步四因子块(静态快照) + 主模板0-说明追加升级记录"""
import json
import time
import pythoncom
import pywintypes
import win32com.client as win32

MASTER = r"E:\3-其他资料\数据分析\月度分析模板.xlsm"
COPY = r"E:\3-其他资料\数据分析\月度分析模板_8月报告副本.xlsx"
SNAP = json.load(open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\mb_snapshot.json", encoding="utf-8"))
LOGF = r"C:\Users\910373\AppData\Local\Temp\opencode\build\sync_copy_log.txt"

def log(msg):
    with open(LOGF, "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")

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

pythoncom.CoInitialize()
xl = None
try:
    xl = with_retry(lambda: win32.DispatchEx("Excel.Application"))
    xl.Visible = False
    xl.DisplayAlerts = False

    # ---- 1) 副本同步 ----
    wb = with_retry(lambda: xl.Workbooks.Open(COPY))
    ws = with_retry(lambda: xl.Worksheets("10-毛利桥"))

    def sv(r, c, v):
        rg = with_retry(lambda: ws.Cells(r, c))
        with_retry(lambda: rg.__setattr__("Value", v if v is not None else ""))

    # 清旧A9桥接注 + 写新块
    with_retry(lambda: ws.Range("A9").ClearContents())
    sv(1, 1, SNAP["A1"])
    sv(2, 1, str(SNAP["A2"]) + " (副本为静态快照,活算在主模板xlsm)")
    sv(8, 1, "副本同步自主模板重算: 2026-09-10 (静态)")
    for ri, row in enumerate(SNAP["rows"]):
        r = 10 + ri
        for c, v in enumerate(row, 1):
            if v is not None and str(v) != "":
                try:
                    v2 = float(v)
                    if v2 == int(v2):
                        v2 = int(v2)
                    sv(r, c, v2)
                except (TypeError, ValueError):
                    sv(r, c, v)
    with_retry(lambda: ws.Range("B12:F13").NumberFormat.__class__ is not None) if False else None
    with_retry(lambda: ws.Range("B12:F13").__setattr__("NumberFormat", "+#,##0;-#,##0;0"))
    log("copy 10-毛利桥 synced")
    # 回读验证
    def rv(r, c):
        return with_retry(lambda: ws.Cells(r, c).Value)
    checks = {12: [313, 70, -470, -33, -120], 13: [-461, 171, 62, 8, -220]}
    ok = True
    for r, exp in checks.items():
        for c, e in enumerate(exp, 2):
            v = rv(r, c)
            try:
                if abs(float(v) - e) > 1:
                    ok = False
                    log(f"FAIL copy r{r}c{c} expect={e} got={v}")
            except (TypeError, ValueError):
                ok = False
                log(f"FAIL copy r{r}c{c} 非数值 {v}")
    log(f"copy verify {'PASS' if ok else 'FAIL'}")
    with_retry(lambda: wb.Save())
    with_retry(lambda: wb.Close(False))

    # ---- 2) 主模板0-说明追加 ----
    wb2 = with_retry(lambda: xl.Workbooks.Open(MASTER))
    w0 = with_retry(lambda: xl.Worksheets("0-说明"))
    lr = with_retry(lambda: w0.UsedRange.Rows.Count)
    rg = with_retry(lambda: w0.Cells(lr + 1, 1))
    with_retry(lambda: rg.__setattr__("Value", "2026-09-10: 重算毛利桥升级为双口径——行4-6三因子(锚点,量3=ΣΔq×基准UM),行11-13四因子(报告口径,量4=(Q1-Q0)×基准平均UM,结构=Σq1×基准UM−Q1×基准平均UM),H列恒等式残差应≈0;恒等式: 量4+结构=量3。报表月切换后一键重算即产出新月份双口径。"))
    with_retry(lambda: wb2.Save())
    with_retry(lambda: wb2.Close(False))
    log("master 0-说明 appended")
finally:
    if xl is not None:
        try:
            xl.Quit()
        except Exception:
            pass
    pythoncom.CoUninitialize()
print("SYNC_DONE")
