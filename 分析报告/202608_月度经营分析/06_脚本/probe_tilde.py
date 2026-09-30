# -*- coding: utf-8 -*-
r"""波浪号criteria探针: 定位SUMIFS对含~品类失配的真因"""
import time
import pythoncom
import pywintypes
import win32com.client as win32

BK = r"E:\3-其他资料\数据分析\月度分析模板_8月报告副本.xlsx"
LOGF = r"C:\Users\910373\AppData\Local\Temp\opencode\build\probe_log.txt"

def log(msg):
    with open(LOGF, "a", encoding="utf-8") as f:
        f.write(str(msg) + "\n")

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

H = "'D-镜像'!$H$2:$H$206900"
A = "'D-镜像'!$A$2:$A$206900"
M = "'D-镜像'!$M$2:$M$206900"

pythoncom.CoInitialize()
xl = None
try:
    xl = with_retry(lambda: win32.DispatchEx("Excel.Application"))
    xl.Visible = False
    xl.DisplayAlerts = False
    wb = with_retry(lambda: xl.Workbooks.Open(BK, ReadOnly=True))
    with_retry(lambda: xl.__setattr__("Calculation", -4135))
    log("opened")

    w = with_retry(lambda: xl.Worksheets("R10-量效应"))
    f3 = with_retry(lambda: w.Cells(3, 4).Formula)
    cat3 = with_retry(lambda: w.Cells(3, 3).Value)
    log(f"D3 formula = {f3}")
    log(f"C3 category = {cat3}")
    if isinstance(cat3, str):
        log(f"C3 codepoints tail = {[hex(ord(c)) for c in cat3[-6:]]}")

    def ev(expr):
        try:
            return with_retry(lambda: xl.Evaluate(expr))
        except Exception as e:
            return f"ERR {e}"

    cat = str(cat3)
    # 1) 精确等值计数(SUMPRODUCT = 无通配符语义)
    e1 = ev(f"SUMPRODUCT(--({H}=\"{cat}\"))")
    log(f"[1] SUMPRODUCT exact count = {e1}")
    # 2) COUNTIF 原始串(通配符语义)
    e2 = ev(f"COUNTIF({H},\"{cat}\")")
    log(f"[2] COUNTIF raw = {e2}")
    # 3) COUNTIF ~转义串
    e3 = ev(f"COUNTIF({H},\"{cat.replace('~', '~~')}\")")
    log(f"[3] COUNTIF ~~escape = {e3}")
    # 4) COUNTIF 去掉~ (如 "1~3A"->"13A") 看是否~被吃掉后匹配
    e4 = ev(f"COUNTIF({H},\"{cat.replace('~', '')}\")")
    log(f"[4] COUNTIF tilde-removed = {e4}")
    # 5) 全角～变体
    cat_fw = cat.replace("~", "～")
    e5 = ev(f"COUNTIF({H},\"{cat_fw}\")")
    log(f"[5] COUNTIF fullwidth～ = {e5}")
    # 6) SUMIFS 8月窗口 原始串(复现失败)
    e6 = ev(f"SUMIFS({M},{H},\"{cat}\",{A},\">=\"&DATE(2026,8,1),{A},\"<\"&DATE(2026,9,1))/10000")
    log(f"[6] SUMIFS raw 8月收入/1e4 = {e6}")
    # 7) SUMPRODUCT 精确版 8月收入
    e7 = ev(f"SUMPRODUCT(({H}=\"{cat}\")*({A}>=DATE(2026,8,1))*({A}<DATE(2026,9,1))*{M})/10000")
    log(f"[7] SUMPRODUCT exact 8月收入/1e4 = {e7}")

    # H列样本码点: 取一个匹配行 (用MATCH找)
    e8 = ev(f"MATCH(\"{cat}\",{H},0)")
    log(f"[8] MATCH exact first row = {e8}")
    if isinstance(e8, (int, float)) and e8 > 0:
        v = with_retry(lambda: xl.Worksheets("D-镜像").Cells(int(e8) + 1, 8).Value)
        log(f"[9] H列实际值 = {v}, codepoints = {[hex(ord(c)) for c in str(v)[-6:]]}")

    with_retry(lambda: wb.Close(False))
finally:
    if xl is not None:
        try:
            xl.Quit()
        except Exception:
            pass
    pythoncom.CoUninitialize()
print("PROBE_DONE")
