# -*- coding: utf-8 -*-
r"""修复missing-parens bug: 真正执行 Delete/Clear(带括号) + 内存即时验证 + 0-说明r55清理"""
import time
import pythoncom
import pywintypes
import win32com.client as win32

BK = r"E:\3-其他资料\数据分析\月度分析模板_8月报告副本.xlsx"
LOGF = r"C:\Users\910373\AppData\Local\Temp\opencode\build\purge2_log.txt"

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

    def count_below():
        cnt = 0
        first = None
        for r in range(59, 400):
            if with_retry(lambda: ws.Cells(r, 1).Value):
                cnt += 1
                if first is None:
                    first = (r, str(with_retry(lambda: ws.Cells(r, 1).Value))[:25])
        return cnt, first

    b = count_below()
    log(f"before: {b}")
    # 真正执行(带调用括号!)
    with_retry(lambda: ws.Rows("59:400").Delete())
    a = count_below()
    log(f"after-delete: {a}")
    if a[0] > 0:
        # 兜底: 逐块ClearContents
        with_retry(lambda: ws.Range("A59:AZ400").ClearContents())
        a2 = count_below()
        log(f"after-clearcontents: {a2}")

    # 0-说明 r55 残留清理(真正执行)
    w0 = with_retry(lambda: xl.Worksheets("0-说明"))
    v55 = with_retry(lambda: w0.Cells(55, 1).Value)
    log(f"0-说明 r55 before: {str(v55)[:40]}")
    if v55:
        with_retry(lambda: w0.Cells(55, 1).ClearContents())
        log(f"0-说明 r55 after: {with_retry(lambda: w0.Cells(55, 1).Value)}")

    # 关键块完整性
    r2 = with_retry(lambda: ws.Cells(6, 1).Value)
    r27 = with_retry(lambda: ws.Cells(27, 2).Value)
    r57 = with_retry(lambda: ws.Cells(57, 3).Value)
    log(f"blocks: R2指针={str(r2)[:18]} R3总计={r27} R5末={r57}")
    with_retry(lambda: xl.__setattr__("Calculation", -4105))
    with_retry(lambda: wb.Save())
    with_retry(lambda: wb.Close(False))
    # 重开验证持久化
    wb2 = with_retry(lambda: xl.Workbooks.Open(BK, ReadOnly=True))
    ws2 = with_retry(lambda: xl.Worksheets("R-报告补充"))
    cnt = 0
    for r in range(59, 400):
        if with_retry(lambda: ws2.Cells(r, 1).Value):
            cnt += 1
    w02 = with_retry(lambda: xl.Worksheets("0-说明"))
    log(f"reopen验证: R-报告补充59+非空={cnt}, 0-说明r55={str(with_retry(lambda: w02.Cells(55, 1).Value))[:30]}")
    with_retry(lambda: wb2.Close(False))
    log("saved+verified")
finally:
    if xl is not None:
        try:
            xl.Quit()
        except Exception:
            pass
    pythoncom.CoUninitialize()
print("PURGE2_DONE")
