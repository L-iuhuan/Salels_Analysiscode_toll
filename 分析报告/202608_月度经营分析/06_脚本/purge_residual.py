# -*- coding: utf-8 -*-
r"""清除R-报告补充59+残留(整行Delete) + 前后读证 + 结构复验"""
import time
import pythoncom
import pywintypes
import win32com.client as win32

BK = r"E:\3-其他资料\数据分析\月度分析模板_8月报告副本.xlsx"
LOGF = r"C:\Users\910373\AppData\Local\Temp\opencode\build\purge_log.txt"

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
    wb = with_retry(lambda: xl.Workbooks.Open(BK))
    with_retry(lambda: xl.__setattr__("Calculation", -4135))
    ws = with_retry(lambda: xl.Worksheets("R-报告补充"))

    def peek(label):
        vals = []
        for r in range(59, 75):
            v = with_retry(lambda: ws.Cells(r, 1).Value)
            if v:
                vals.append((r, str(v)[:28]))
        cnt = 0
        for r in range(59, 400):
            if with_retry(lambda: ws.Cells(r, 1).Value):
                cnt += 1
        log(f"{label}: 59-74可见={vals[:4]} 59-399非空={cnt}")
        return cnt

    before = peek("before")
    with_retry(lambda: ws.Rows("59:400").Delete)
    after = peek("after-delete")
    # 关键块完整性
    r2 = with_retry(lambda: ws.Cells(6, 1).Value)
    r3a = with_retry(lambda: ws.Cells(19, 1).Value)
    r27 = with_retry(lambda: ws.Cells(27, 2).Value)
    r5 = with_retry(lambda: ws.Cells(45, 1).Value)
    r57 = with_retry(lambda: ws.Cells(57, 3).Value)
    log(f"blocks: R2指针={str(r2)[:20]} R3首行={r3a} R3总计B27={r27} R5首行={r5} R5末行C57={r57}")
    with_retry(lambda: xl.__setattr__("Calculation", -4105))
    with_retry(lambda: wb.Save())
    with_retry(lambda: wb.Close(False))
    log(f"saved (before={before} after={after})")
finally:
    if xl is not None:
        try:
            xl.Quit()
        except Exception:
            pass
    pythoncom.CoUninitialize()
print("PURGE_DONE")
